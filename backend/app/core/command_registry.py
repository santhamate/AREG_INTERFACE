from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.core.areg_controller import CommandSource
from backend.app.core.catalog import load_catalog
from backend.app.core.config import load_settings


PLACEHOLDER_PATTERN = re.compile(r"<([^>]+)>")


@dataclass(frozen=True)
class RegistryCommand:
    key: str
    group: str
    command: str
    command_type: str
    purpose: str
    example: str | None = None
    placeholders: tuple[str, ...] = ()
    source: str | None = None
    verified: bool = False
    origin: str = "builtin"


class CommandRegistryService:
    """Unified command registry for the manual console and scenario controls."""

    def __init__(self, command_source_path: Path | None = None) -> None:
        settings = load_settings()
        self.command_source_path = command_source_path or settings.command_source_path

    def _extract_placeholders(self, command: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(match.strip() for match in PLACEHOLDER_PATTERN.findall(command)))

    def _builtin_commands(self) -> list[RegistryCommand]:
        commands = [
            RegistryCommand(
                key="core.idn",
                group="Core",
                command="*IDN?",
                command_type="query",
                purpose="Identify the connected instrument.",
                example="*IDN?",
                verified=True,
            ),
            RegistryCommand(
                key="core.clear_status",
                group="Core",
                command="*CLS",
                command_type="action",
                purpose="Clear status registers and error queue.",
                example="*CLS",
                verified=True,
            ),
            RegistryCommand(
                key="core.opc_query",
                group="Core",
                command="*OPC?",
                command_type="query",
                purpose="Wait for operation complete.",
                example="*OPC?",
                verified=True,
            ),
            RegistryCommand(
                key="system.error_all",
                group="Diagnostics",
                command="SYSTem:ERRor:ALL?",
                command_type="query",
                purpose="Read the instrument error queue.",
                example="SYSTem:ERRor:ALL?",
                verified=True,
            ),
            RegistryCommand(
                key="hardcopy.language",
                group="Hardcopy",
                command=":HCOPy:DEVice:LANGuage <file_format>",
                command_type="write",
                purpose="Select the hardcopy image format.",
                example=":HCOPy:DEVice:LANGuage PNG",
                source="AREG User Manual HCOPy subsystem",
                verified=True,
            ),
            RegistryCommand(
                key="hardcopy.auto_name",
                group="Hardcopy",
                command=":HCOPy:FILE:NAME:AUTO:STATe <state>",
                command_type="write",
                purpose="Enable or disable instrument-managed hardcopy file naming.",
                example=":HCOPy:FILE:NAME:AUTO:STATe 1",
                source="AREG User Manual HCOPy subsystem",
                verified=True,
            ),
            RegistryCommand(
                key="hardcopy.execute",
                group="Hardcopy",
                command=":HCOPy:EXECute",
                command_type="action",
                purpose="Trigger hardcopy generation on the instrument.",
                example=":HCOPy:EXECute",
                source="AREG User Manual HCOPy subsystem",
                verified=True,
            ),
            RegistryCommand(
                key="hardcopy.data",
                group="Hardcopy",
                command=":HCOPy:DATA?",
                command_type="binary-query",
                purpose="Read hardcopy data as a definite-length SCPI binary block.",
                example=":HCOPy:DATA?",
                source="AREG User Manual HCOPy subsystem",
                verified=True,
            ),
            RegistryCommand(
                key="scenario.catalog",
                group="Scenario Player",
                command='SOURce<source_hw>:AREGenerator:SCENario:FILE:CATalog? "<directory>"',
                command_type="query",
                purpose="List available .osi scenario files on the instrument.",
                example='SOURce1:AREGenerator:SCENario:FILE:CATalog? "/osi"',
                verified=True,
            ),
            RegistryCommand(
                key="scenario.file",
                group="Scenario Player",
                command='SOURce<source_hw>:AREGenerator:SCENario:FILE "<scenario_name>"',
                command_type="write",
                purpose="Load a scenario file by remote path or filename.",
                example='SOURce1:AREGenerator:SCENario:FILE "range_sweep.osi"',
                verified=True,
            ),
            RegistryCommand(
                key="scenario.play",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:STARt",
                command_type="action",
                purpose="Start playback of the loaded scenario.",
                example="SOURce1:AREGenerator:SCENario:STARt",
                verified=True,
            ),
            RegistryCommand(
                key="scenario.pause",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:PAUSe",
                command_type="action",
                purpose="Pause playback of the loaded scenario.",
                example="SOURce1:AREGenerator:SCENario:PAUSe",
                verified=True,
            ),
            RegistryCommand(
                key="scenario.stop",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:STOP",
                command_type="action",
                purpose="Stop playback of the loaded scenario.",
                example="SOURce1:AREGenerator:SCENario:STOP",
                verified=True,
            ),
            RegistryCommand(
                key="scenario.replay_mode.set",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:REPLay:MODE <mode>",
                command_type="write",
                purpose="Set replay mode to SINGle or LOOP.",
                example="SOURce1:AREGenerator:SCENario:REPLay:MODE LOOP",
                verified=True,
            ),
            RegistryCommand(
                key="scenario.replay_mode.query",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:REPLay:MODE?",
                command_type="query",
                purpose="Query the current replay mode.",
                example="SOURce1:AREGenerator:SCENario:REPLay:MODE?",
                verified=True,
            ),
            RegistryCommand(
                key="scenario.state",
                group="Scenario Player",
                command="SOURce<source_hw>:AREGenerator:SCENario:STATe?",
                command_type="query",
                purpose="Query the current scenario playback state.",
                example="SOURce1:AREGenerator:SCENario:STATe?",
                verified=True,
            ),
        ]
        return [
            RegistryCommand(
                **{
                    **command.__dict__,
                    "placeholders": self._extract_placeholders(command.command),
                }
            )
            for command in commands
        ]

    def _yaml_commands(self) -> tuple[list[RegistryCommand], str | None]:
        if not self.command_source_path.exists():
            return [], f"Optional command source not found: {self.command_source_path.name}. Using built-in registry and catalog fallback."

        try:
            source = CommandSource.load(self.command_source_path).document
        except Exception as ex:
            return [], f"Failed to read optional command source: {ex}. Using built-in registry and catalog fallback."

        command_groups = source.get("command_groups", {})
        if not isinstance(command_groups, dict):
            return [], "Optional command source is malformed. Using built-in registry and catalog fallback."

        commands: list[RegistryCommand] = []
        for group_name, group_data in command_groups.items():
            if not isinstance(group_data, dict):
                continue
            commands_list = group_data.get("commands", [])
            if not isinstance(commands_list, list):
                continue
            for index, command_item in enumerate(commands_list):
                if not isinstance(command_item, dict):
                    continue
                command_text = str(command_item.get("command", "")).strip()
                if not command_text:
                    continue
                entry_key = str(command_item.get("key") or f"yaml.{group_name}.{index}")
                commands.append(
                    RegistryCommand(
                        key=entry_key,
                        group=str(group_name),
                        command=command_text,
                        command_type="query" if command_text.split()[0].endswith("?") else "write",
                        purpose=str(command_item.get("purpose", "")),
                        example=command_item.get("example"),
                        placeholders=self._extract_placeholders(command_text),
                        source=str(self.command_source_path),
                        verified=False,
                        origin="yaml",
                    )
                )
        return commands, None

    def _catalog_commands(self) -> list[RegistryCommand]:
        catalog = load_catalog()
        commands: list[RegistryCommand] = []
        for entry in catalog.commands:
            commands.append(
                RegistryCommand(
                    key=f"catalog.{entry.key}.{len(commands)}",
                    group="Catalog",
                    command=entry.command,
                    command_type=entry.type,
                    purpose=entry.description,
                    example=entry.example,
                    placeholders=self._extract_placeholders(entry.command),
                    source=entry.source,
                    verified=entry.verified,
                    origin="catalog",
                )
            )
        return commands

    def list_commands(self) -> tuple[list[RegistryCommand], str]:
        warning_parts: list[str] = []
        commands_by_command: dict[str, RegistryCommand] = {}
        commands_by_key: dict[str, RegistryCommand] = {}

        def add(entry: RegistryCommand) -> None:
            normalized_command = entry.command.strip().upper()
            if entry.key not in commands_by_key:
                commands_by_key[entry.key] = entry
            if normalized_command not in commands_by_command:
                commands_by_command[normalized_command] = entry

        for entry in self._builtin_commands():
            add(entry)

        yaml_commands, yaml_warning = self._yaml_commands()
        if yaml_warning:
            warning_parts.append(yaml_warning)
        for entry in yaml_commands:
            add(entry)

        for entry in self._catalog_commands():
            add(entry)

        commands = sorted(commands_by_command.values(), key=lambda item: (item.group, item.command))
        return commands, " ".join(warning_parts).strip()

    def command_library(self) -> dict[str, Any]:
        commands, warning = self.list_commands()
        placeholder_help = {
            "source_hw": "Source hardware index",
            "directory": "Remote directory path",
            "scenario_name": "Remote scenario filename or path",
            "mode": "Replay mode, e.g. SINGle or LOOP",
            "file_format": "Hardcopy format such as PNG/JPG/BMP",
            "state": "Boolean state, typically 0/1 or ON/OFF",
        }
        return {
            "device": "AREG800A",
            "warning": warning,
            "placeholders": placeholder_help,
            "commands": [
                {
                    "key": entry.key,
                    "group": entry.group,
                    "command": entry.command,
                    "purpose": entry.purpose,
                    "example": entry.example,
                    "placeholders": list(entry.placeholders),
                    "command_type": entry.command_type,
                    "verified": entry.verified,
                    "origin": entry.origin,
                    "source": entry.source,
                }
                for entry in commands
            ],
        }

    def resolve(self, key: str, values: dict[str, object] | None = None) -> str:
        values = values or {}
        commands, _warning = self.list_commands()
        entry = next((command for command in commands if command.key == key), None)
        if entry is None:
            raise KeyError(f"Unknown command key: {key}")

        def replace(match: re.Match[str]) -> str:
            name = match.group(1).strip()
            if name not in values:
                raise KeyError(f"Missing placeholder '{name}' for command key '{key}'")
            return str(values[name])

        return PLACEHOLDER_PATTERN.sub(replace, entry.command)

    def lookup(self, command_line: str) -> dict[str, Any]:
        cleaned = command_line.strip()
        if not cleaned:
            return {"known": False, "matches": []}
        normalized = cleaned.upper()
        commands, _warning = self.list_commands()
        matches = [
            {
                "key": entry.key,
                "command": entry.command,
                "group": entry.group,
                "command_type": entry.command_type,
                "purpose": entry.purpose,
                "verified": entry.verified,
                "origin": entry.origin,
            }
            for entry in commands
            if normalized.startswith(entry.command.upper().split()[0])
        ]
        return {"known": bool(matches), "matches": matches[:10]}