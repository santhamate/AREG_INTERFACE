from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.core.config import load_settings
from backend.app.core.hislip import HiSlipTransport, ScpiTransportError, SocketTransport, TransportBase


@dataclass
class SessionInfo:
    connected: bool
    host: str | None
    port: int | None
    transport: str


class ScpiService:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.host: str | None = None
        self.port: int | None = None
        self.protocol: str = "hislip"
        self.transport: TransportBase = HiSlipTransport()
        self.transport_name = "hislip"

    def _select_transport(self, protocol: str) -> tuple[TransportBase, int]:
        if protocol == "hislip":
            return HiSlipTransport(), self.settings.hislip_port
        if protocol == "socket":
            return SocketTransport(), self.settings.socket_port
        raise ValueError(f"Protocol '{protocol}' is not supported yet. Use hislip or socket.")

    async def connect(self, host: str | None = None, port: int | None = None, protocol: str = "hislip") -> SessionInfo:
        self.transport, default_port = self._select_transport(protocol)
        self.protocol = protocol
        self.transport_name = protocol
        self.host = host or (self.settings.hislip_host if protocol == "hislip" else self.settings.socket_host)
        self.port = port or default_port
        await self.transport.connect(self.host, self.port)
        return self.session_state()

    async def disconnect(self) -> SessionInfo:
        await self.transport.disconnect()
        return self.session_state()

    def session_state(self) -> SessionInfo:
        return SessionInfo(
            connected=self.transport.connected,
            host=self.host,
            port=self.port,
            transport=self.transport_name,
        )

    async def execute(self, command: str, expect_response: bool | None = None, timeout_ms: int | None = None) -> str | None:
        """Execute SCPI command. If expect_response is None, auto-detect based on ? in command."""
        cleaned = command.strip()
        if not cleaned:
            raise ValueError("Command is empty.")

        # Auto-detect query vs setter if not explicitly specified
        auto_detect = expect_response is None
        if auto_detect:
            expect_response = "?" in cleaned

        timeout = timeout_ms if timeout_ms is not None else self.settings.command_timeout_ms
        try:
            return await self.transport.send(cleaned, expect_response=expect_response, timeout_ms=timeout)
        except ScpiTransportError:
            raise
        except TimeoutError as ex:
            raise ScpiTransportError(f"Command timeout: {cleaned}") from ex

    async def execute_with_classification(
        self, command: str, timeout_ms: int | None = None
    ) -> dict[str, object]:
        """Execute SCPI command and return detailed result including command type.
        
        This is the central executor that handles query vs write detection.
        - Query commands (ending with ?) wait for response
        - Write commands (not ending with ?) don't wait for response
        
        Returns:
            {
                "ok": bool,
                "command": str,
                "command_type": "query" | "write" | "empty",
                "response": str | None,
                "message": str | None,
                "error": str | None
            }
        """
        cleaned = command.strip()
        
        if not cleaned:
            return {
                "ok": False,
                "command": cleaned,
                "command_type": "empty",
                "response": None,
                "message": None,
                "error": "Command is empty.",
            }
        
        # A SCPI query can be bare ("*IDN?") or have trailing arguments
        # (e.g. ':MMEMory:CATalog? "/osi"').  Detect the ? before any space.
        cmd_head = cleaned.split()[0] if cleaned else ""
        is_query = cmd_head.endswith("?")
        timeout = timeout_ms if timeout_ms is not None else self.settings.command_timeout_ms
        
        try:
            if is_query:
                # Query: send and wait for response
                response = await self.transport.send(cleaned, expect_response=True, timeout_ms=timeout)
                return {
                    "ok": True,
                    "command": cleaned,
                    "command_type": "query",
                    "response": response if response else "",
                    "message": None,
                    "error": None,
                }
            else:
                # Write: send without waiting
                await self.transport.send(cleaned, expect_response=False, timeout_ms=timeout)
                return {
                    "ok": True,
                    "command": cleaned,
                    "command_type": "write",
                    "response": None,
                    "message": "Command sent",
                    "error": None,
                }
        except ScpiTransportError as ex:
            return {
                "ok": False,
                "command": cleaned,
                "command_type": "query" if is_query else "write",
                "response": None,
                "message": None,
                "error": str(ex),
            }
        except TimeoutError as ex:
            error_msg = f"Command timeout: {cleaned}" if is_query else f"Write timeout: {cleaned}"
            return {
                "ok": False,
                "command": cleaned,
                "command_type": "query" if is_query else "write",
                "response": None,
                "message": None,
                "error": error_msg,
            }

    async def upload_binary_file(self, remote_path: str, data: bytes, timeout_ms: int | None = None) -> dict[str, object]:
        """Upload binary data to device via SCPI :MMEMory:DATA command.

        Builds an IEEE 488.2 definite-length arbitrary block and sends it as:
            :MMEMory:DATA "remote_path",#<n><size><data>
        """
        if not self.transport.connected:
            raise ScpiTransportError("No active session. Connect first.")

        size_str = str(len(data))
        n = len(size_str)
        block = f"#{n}{size_str}".encode("ascii") + data
        command_header = f':MMEMory:DATA "{remote_path}",'.encode("ascii")
        payload = command_header + block + b"\n"

        timeout = timeout_ms if timeout_ms is not None else self.settings.command_timeout_ms
        try:
            await self.transport.send_raw_payload(payload, expect_response=False, timeout_ms=timeout)
            return {"ok": True, "bytes_transferred": len(data), "error": None}
        except ScpiTransportError as ex:
            return {"ok": False, "bytes_transferred": 0, "error": str(ex)}
        except TimeoutError:
            return {"ok": False, "bytes_transferred": 0, "error": f"Upload timeout for {remote_path}"}

    async def capture_hardcopy(self, save_path: str, timeout_ms: int | None = None) -> Path:
        if not save_path.strip():
            raise ValueError("Save path is empty.")
        if not self.transport.connected:
            raise ScpiTransportError("No active session. Connect first.")

        output_path = Path(save_path).expanduser()
        if output_path.is_dir():
            output_path = output_path / "hardcopy.png"
        if not output_path.suffix:
            output_path = output_path.with_suffix(".png")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        timeout = timeout_ms if timeout_ms is not None else self.settings.command_timeout_ms
        try:
            await self.transport.send(":HCOPY:IMAGE:FORMAT PNG", expect_response=False, timeout_ms=timeout)
            await self.transport.send(":HCOPY:EXECUTE", expect_response=False, timeout_ms=timeout)
            data = await self.transport.query_bytes(":HCOPY:DATA?", timeout_ms=timeout)
        except TimeoutError as ex:
            raise ScpiTransportError("Hardcopy capture timed out.") from ex

        output_path.write_bytes(data)
        return output_path
