from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any

import yaml

from backend.app.core.config import load_settings
from backend.app.core.hislip import ScpiTransportError, SocketTransport


@dataclass(frozen=True)
class CommandSource:
    path: Path
    document: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> CommandSource:
        if not path.exists():
            raise FileNotFoundError(f"Command source not found: {path}")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("Command source must be a YAML mapping.")
        return cls(path=path, document=document)


@dataclass(frozen=True)
class CommandStep:
    command: str
    response: str | None = None
    note: str | None = None


class AregSocketController:
    def __init__(self, command_source_path: Path | None = None) -> None:
        settings = load_settings()
        self.command_source_path = command_source_path or settings.command_source_path
        self.command_source = CommandSource.load(self.command_source_path)
        self.transport = SocketTransport()
        self.settings = settings

    async def write_scpi(self, command: str, timeout_ms: int | None = None) -> None:
        """Send a setter/event SCPI command. Do not read response."""
        timeout = timeout_ms if timeout_ms is not None else self.settings.command_timeout_ms
        await self.transport.send(command, expect_response=False, timeout_ms=timeout)

    async def query_scpi(self, command: str, timeout_ms: int | None = None) -> str:
        """Send a query SCPI command (must end with ?). Read and return response."""
        if "?" not in command:
            raise ValueError(f"query_scpi() called with non-query command: {command}. Use write_scpi().")
        timeout = timeout_ms if timeout_ms is not None else self.settings.command_timeout_ms
        response = await self.transport.send(command, expect_response=True, timeout_ms=timeout)
        return "" if response is None else response

    async def opc_sync(self, timeout_ms: int | None = None) -> None:
        """Wait for operation complete. Raises if response is not '1'."""
        response = await self.query_scpi("*OPC?", timeout_ms=timeout_ms)
        if response.strip() != "1":
            raise RuntimeError(f"Unexpected *OPC? response: {response}")

    async def check_errors(self, timeout_ms: int | None = None) -> str:
        """Query SYSTem:ERRor:ALL? and return the error string."""
        return await self.query_scpi("SYSTem:ERRor:ALL?", timeout_ms=timeout_ms)

    async def write(self, command: str, timeout_ms: int | None = None) -> None:
        """Backward-compatible: delegate to write_scpi()."""
        await self.write_scpi(command, timeout_ms=timeout_ms)

    async def query(self, command: str, timeout_ms: int | None = None) -> str:
        """Backward-compatible: delegate to query_scpi()."""
        return await self.query_scpi(command, timeout_ms=timeout_ms)

    def command_library(self) -> dict[str, Any]:
        self.command_source = CommandSource.load(self.command_source_path)
        source = self.command_source.document
        command_groups = source.get("command_groups", {})
        if not isinstance(command_groups, dict):
            raise ValueError("Command groups must be a YAML mapping.")

        commands: list[dict[str, Any]] = []
        for group_name, group_data in command_groups.items():
            if not isinstance(group_data, dict):
                continue

            commands_list = group_data.get("commands", [])
            if not isinstance(commands_list, list):
                continue

            for command_item in commands_list:
                if not isinstance(command_item, dict):
                    continue

                command_text = str(command_item.get("command", "")).strip()
                if not command_text:
                    continue

                placeholders = list(dict.fromkeys(re.findall(r"<([^>]+)>", command_text)))
                commands.append(
                    {
                        "group": str(group_name),
                        "command": command_text,
                        "purpose": str(command_item.get("purpose", "")),
                        "example": command_item.get("example"),
                        "placeholders": placeholders,
                    }
                )

        return {
            "device": str(source.get("source", {}).get("device", "AREG800A")),
            "warning": str(source.get("source", {}).get("warning", "")),
            "placeholders": dict(source.get("syntax_notes", {}).get("placeholders", {})),
            "commands": commands,
        }

    async def run_static_object_setup(
        self,
        host: str,
        port: int = 5025,
        source_hw: int = 1,
        object_index: int = 1,
        range_value: float | None = None,
        attenuation: float | None = None,
        rcs: float | None = None,
        doppler_speed: float | None = None,
        doppler_frequency: float | None = None,
        angle_horizontal: float | None = None,
    ) -> tuple[list[CommandStep], list[str]]:
        steps: list[CommandStep] = []
        errors: list[str] = []
        source = f"SOURce{source_hw}"
        object_prefix = f"{source}:AREGenerator:OBJect{object_index}"

        await self.transport.connect(host, port)
        try:
            steps.append(CommandStep(command="*IDN?", response=await self.query_scpi("*IDN?")))
            await self.write_scpi("*CLS")
            steps.append(CommandStep(command="*CLS"))

            setup_commands = [
                f"{source}:AREGenerator:OSETup:MODE STATic",
                f"{source}:AREGenerator:OSETup:REFerence ORIGin",
                f"{source}:AREGenerator:OSETup:APPLy",
            ]
            for command in setup_commands:
                await self.write_scpi(command)
                steps.append(CommandStep(command=command))
            await self.opc_sync()
            setup_error = await self.check_errors()
            steps.append(CommandStep(command="SYSTem:ERRor:ALL?", response=setup_error))
            if not setup_error.startswith("0"):
                errors.append(setup_error)

            object_commands: list[tuple[str, str, float | None]] = [
                ("RANGe", f"{object_prefix}:RANGe", range_value),
                ("ATTenuation", f"{object_prefix}:ATTenuation", attenuation),
                ("RCS", f"{object_prefix}:RCS", rcs),
                ("DOPPler:SPEed", f"{object_prefix}:DOPPler:SPEed", doppler_speed),
                ("DOPPler:FREQuency", f"{object_prefix}:DOPPler:FREQuency", doppler_frequency),
                ("ANGLe:HORizontal", f"{object_prefix}:ANGLe:HORizontal", angle_horizontal),
            ]
            for _limit_name, command_prefix, value in object_commands:
                if value is None:
                    continue

                for limit in ("MIN", "MAX"):
                    limit_command = f"{command_prefix}? {limit}"
                    try:
                        limit_response = await self.query_scpi(limit_command)
                        steps.append(CommandStep(command=limit_command, response=limit_response, note="Limit probe"))
                    except (ScpiTransportError, TimeoutError) as ex:
                        steps.append(CommandStep(command=limit_command, note=f"Limit probe unsupported: {ex}"))

                set_command = f"{command_prefix} {value}"
                await self.write_scpi(set_command)
                steps.append(CommandStep(command=set_command))

            state_command = f"{object_prefix}:STATe ON"
            await self.write_scpi(state_command)
            steps.append(CommandStep(command=state_command))

            await self.opc_sync()
            object_error = await self.check_errors()
            steps.append(CommandStep(command="SYSTem:ERRor:ALL?", response=object_error))
            if not object_error.startswith("0"):
                errors.append(object_error)

            return steps, errors
        finally:
            await self.transport.disconnect()