from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass


HEADER_FORMAT = "!2sBBIQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
DEFAULT_MAX_MESSAGE_SIZE = 1 << 20


MESSAGE_TYPE = {
    "Initialize": 0,
    "InitializeResponse": 1,
    "FatalError": 2,
    "Error": 3,
    "AsyncLock": 4,
    "AsyncLockResponse": 5,
    "Data": 6,
    "DataEnd": 7,
    "DeviceClearComplete": 8,
    "DeviceClearAcknowledge": 9,
    "AsyncRemoteLocalControl": 10,
    "AsyncRemoteLocalResponse": 11,
    "Trigger": 12,
    "Interrupted": 13,
    "AsyncInterrupted": 14,
    "AsyncMaxMsgSize": 15,
    "AsyncMaxMsgSizeResponse": 16,
    "AsyncInitialize": 17,
    "AsyncInitializeResponse": 18,
    "AsyncDeviceClear": 19,
    "AsyncServiceRequest": 20,
    "AsyncStatusQuery": 21,
    "AsyncStatusResponse": 22,
    "AsyncDeviceClearAcknowledge": 23,
    "AsyncLockInfo": 24,
    "AsyncLockInfoResponse": 25,
}
MESSAGE_NAME = {value: key for key, value in MESSAGE_TYPE.items()}


@dataclass
class HiSlipHeader:
    msg_type: str
    control_code: int
    message_parameter: int
    payload_length: int


class ScpiTransportError(RuntimeError):
    pass


class TransportBase:
    async def connect(self, host: str, port: int) -> None:
        raise NotImplementedError

    async def disconnect(self) -> None:
        raise NotImplementedError

    async def send(self, command: str, expect_response: bool, timeout_ms: int) -> str | None:
        raise NotImplementedError

    async def query_bytes(self, command: str, timeout_ms: int) -> bytes:
        raise NotImplementedError

    async def send_raw_payload(self, payload: bytes, expect_response: bool, timeout_ms: int) -> str | None:
        """Send raw bytes payload (e.g. for binary block data upload). No encoding applied."""
        raise NotImplementedError

    @property
    def connected(self) -> bool:
        raise NotImplementedError


class SocketTransport(TransportBase):
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self, host: str, port: int) -> None:
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.open_connection(host=host, port=port)
        except ConnectionRefusedError:
            raise ScpiTransportError(
                f"Connection refused to {host}:{port}. "
                f"Is the AREG800A device running and listening on this address?"
            )
        except asyncio.TimeoutError:
            raise ScpiTransportError(
                f"Connection timeout to {host}:{port}. "
                f"Device is not responding. Check network connectivity and device status."
            )
        except OSError as e:
            raise ScpiTransportError(
                f"Network error connecting to {host}:{port}: {e}. "
                f"Verify the host address and network connectivity."
            )

    async def disconnect(self) -> None:
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
        self._reader = None
        self._writer = None

    async def send(self, command: str, expect_response: bool, timeout_ms: int) -> str | None:
        data = await self.query_bytes(command, timeout_ms) if expect_response else None
        return None if data is None else data.decode("ascii", errors="ignore").strip()

    async def query_bytes(self, command: str, timeout_ms: int) -> bytes:
        if not self.connected or self._reader is None or self._writer is None:
            raise ScpiTransportError("No active session. Connect first.")

        payload = (command.rstrip() + "\n").encode("ascii", errors="ignore")
        timeout_s = max(timeout_ms, 1) / 1000

        async with self._lock:
            self._writer.write(payload)
            await self._writer.drain()

            chunks: list[bytes] = []
            quiet_timeout = min(timeout_s, 0.25)
            while True:
                try:
                    chunk = await asyncio.wait_for(self._reader.read(4096), timeout=quiet_timeout)
                except TimeoutError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
                if len(chunk) < 4096:
                    try:
                        more = await asyncio.wait_for(self._reader.read(1), timeout=quiet_timeout)
                    except TimeoutError:
                        break
                    if not more:
                        break
                    chunks.append(more)
            return b"".join(chunks)

    async def send_raw_payload(self, payload: bytes, expect_response: bool, timeout_ms: int) -> str | None:
        """Send raw bytes payload directly (for binary block data like MMEMory:DATA upload)."""
        if not self.connected or self._reader is None or self._writer is None:
            raise ScpiTransportError("No active session. Connect first.")
        timeout_s = max(timeout_ms, 1) / 1000
        async with self._lock:
            self._writer.write(payload)
            await self._writer.drain()
            if not expect_response:
                return None
            chunks: list[bytes] = []
            quiet_timeout = min(timeout_s, 0.25)
            while True:
                try:
                    chunk = await asyncio.wait_for(self._reader.read(4096), timeout=quiet_timeout)
                except TimeoutError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
                if len(chunk) < 4096:
                    try:
                        more = await asyncio.wait_for(self._reader.read(1), timeout=quiet_timeout)
                    except TimeoutError:
                        break
                    if not more:
                        break
                    chunks.append(more)
            return b"".join(chunks).decode("ascii", errors="ignore").strip()

    @property
    def connected(self) -> bool:
        return self._reader is not None and self._writer is not None


class HiSlipTransport(TransportBase):
    """HiSLIP transport with sync/async channels and framed message handling."""

    def __init__(self) -> None:
        self._sync_reader: asyncio.StreamReader | None = None
        self._sync_writer: asyncio.StreamWriter | None = None
        self._async_reader: asyncio.StreamReader | None = None
        self._async_writer: asyncio.StreamWriter | None = None
        self._sync_lock = asyncio.Lock()
        self._async_waiters: dict[str, asyncio.Queue[tuple[HiSlipHeader, bytes]]] = {}
        self._async_task: asyncio.Task[None] | None = None
        self._message_id = 0xFFFF_FF00
        self._last_message_id: int | None = None
        self._max_message_size = DEFAULT_MAX_MESSAGE_SIZE

    async def connect(self, host: str, port: int) -> None:
        if self.connected:
            return

        try:
            self._sync_reader, self._sync_writer = await asyncio.open_connection(host=host, port=port)
        except ConnectionRefusedError:
            raise ScpiTransportError(
                f"Connection refused to {host}:{port}. "
                f"Is the AREG800A device running and listening on this address?"
            )
        except asyncio.TimeoutError:
            raise ScpiTransportError(
                f"Connection timeout to {host}:{port}. "
                f"Device is not responding. Check network connectivity and device status."
            )
        except OSError as e:
            raise ScpiTransportError(
                f"Network error connecting to {host}:{port}: {e}. "
                f"Verify the host address and network connectivity."
            )

        try:
            await self._initialize_sync(sub_address=b"hislip0")

            self._async_reader, self._async_writer = await asyncio.open_connection(host=host, port=port)
            session_id = self._session_id_from_initialize_response
            await self._send_async_message("AsyncInitialize", 0, session_id, b"")
            response = await self._recv_async_header(expected="AsyncInitializeResponse")
            if response.control_code != 0:
                raise ScpiTransportError("Async HiSLIP channel initialization failed.")

            self._async_task = asyncio.create_task(self._async_read_loop())
        except ScpiTransportError:
            raise
        except Exception as e:
            await self.disconnect()
            raise ScpiTransportError(
                f"HiSLIP initialization failed: {e}. "
                f"Device may not support HiSLIP protocol. Try Socket protocol instead."
            )

    async def disconnect(self) -> None:
        if self._async_task is not None:
            self._async_task.cancel()
            try:
                await self._async_task
            except asyncio.CancelledError:
                pass
            self._async_task = None

        if self._async_writer is not None:
            self._async_writer.close()
            await self._async_writer.wait_closed()

        if self._sync_writer is not None:
            self._sync_writer.close()
            await self._sync_writer.wait_closed()

        self._sync_reader = None
        self._sync_writer = None
        self._async_reader = None
        self._async_writer = None
        self._message_id = 0xFFFF_FF00
        self._last_message_id = None

    async def send(self, command: str, expect_response: bool, timeout_ms: int) -> str | None:
        if not self.connected or self._sync_reader is None or self._sync_writer is None:
            raise ScpiTransportError("No active session. Connect first.")

        timeout_s = max(timeout_ms, 1) / 1000
        payload = (command.rstrip() + "\n").encode("ascii", errors="ignore")

        async with self._sync_lock:
            await self._send_scpi_payload(payload)

            if not expect_response:
                return None

            data = await asyncio.wait_for(self._receive_scpi_payload(), timeout=timeout_s)
            return data.decode("ascii", errors="ignore").strip()

    async def send_raw_payload(self, payload: bytes, expect_response: bool, timeout_ms: int) -> str | None:
        """Send raw bytes payload directly (for binary block data like MMEMory:DATA upload)."""
        if not self.connected or self._sync_reader is None or self._sync_writer is None:
            raise ScpiTransportError("No active session. Connect first.")
        timeout_s = max(timeout_ms, 1) / 1000
        async with self._sync_lock:
            await self._send_scpi_payload(payload)
            if not expect_response:
                return None
            data = await asyncio.wait_for(self._receive_scpi_payload(), timeout=timeout_s)
            return data.decode("ascii", errors="ignore").strip()

    async def query_bytes(self, command: str, timeout_ms: int) -> bytes:
        if not self.connected or self._sync_reader is None or self._sync_writer is None:
            raise ScpiTransportError("No active session. Connect first.")

        timeout_s = max(timeout_ms, 1) / 1000
        payload = (command.rstrip() + "\n").encode("ascii", errors="ignore")

        async with self._sync_lock:
            await self._send_scpi_payload(payload)
            return await asyncio.wait_for(self._receive_scpi_payload(), timeout=timeout_s)

    async def _initialize_sync(self, sub_address: bytes) -> None:
        if self._sync_writer is None:
            raise ScpiTransportError("Sync channel unavailable during initialize.")

        header = struct.pack(
            "!2sBBBB2sQ",
            b"HS",
            MESSAGE_TYPE["Initialize"],
            0,
            1,
            0,
            b"xx",
            len(sub_address),
        )
        self._sync_writer.write(header + sub_address)
        await self._sync_writer.drain()

        response = await self._recv_sync_header(expected="InitializeResponse")
        if response.payload_length != 0:
            await self._recv_sync_payload(response.payload_length)

        if self._sync_init_header_raw is None:
            raise ScpiTransportError("Missing initialize response payload.")

    async def _send_scpi_payload(self, payload: bytes) -> None:
        chunk_size = self._max_message_size - HEADER_SIZE
        view = memoryview(payload)
        remaining = len(payload)

        while remaining > 0:
            if remaining <= chunk_size:
                chunk = view[:remaining].tobytes()
                await self._send_sync_message("DataEnd", 0, self._message_id, chunk)
                self._last_message_id = self._message_id
                self._message_id = (self._message_id + 2) & 0xFFFF_FFFF
                break

            chunk = view[:chunk_size].tobytes()
            await self._send_sync_message("Data", 0, self._message_id, chunk)
            self._last_message_id = self._message_id
            self._message_id = (self._message_id + 2) & 0xFFFF_FFFF
            view = view[chunk_size:]
            remaining -= chunk_size

    async def _receive_scpi_payload(self) -> bytes:
        if self._sync_reader is None:
            raise ScpiTransportError("Sync channel unavailable.")

        chunks: list[bytes] = []
        while True:
            header = await self._recv_sync_header()
            if header.msg_type == "Interrupted":
                raise ScpiTransportError("Read interrupted by instrument clear operation.")
            if header.msg_type not in {"Data", "DataEnd"}:
                await self._recv_sync_payload(header.payload_length)
                continue

            if header.message_parameter not in {0xFFFF_FFFF, self._last_message_id}:
                await self._recv_sync_payload(header.payload_length)
                continue

            payload = await self._recv_sync_payload(header.payload_length)
            chunks.append(payload)
            if header.msg_type == "DataEnd":
                break

        return b"".join(chunks)

    async def _send_sync_message(
        self,
        msg_type: str,
        control_code: int,
        message_parameter: int,
        payload: bytes,
    ) -> None:
        if self._sync_writer is None:
            raise ScpiTransportError("Sync channel not connected.")

        packet = struct.pack(
            HEADER_FORMAT,
            b"HS",
            MESSAGE_TYPE[msg_type],
            control_code,
            message_parameter,
            len(payload),
        ) + payload
        self._sync_writer.write(packet)
        await self._sync_writer.drain()

    async def _send_async_message(
        self,
        msg_type: str,
        control_code: int,
        message_parameter: int,
        payload: bytes,
    ) -> None:
        if self._async_writer is None:
            raise ScpiTransportError("Async channel not connected.")

        packet = struct.pack(
            HEADER_FORMAT,
            b"HS",
            MESSAGE_TYPE[msg_type],
            control_code,
            message_parameter,
            len(payload),
        ) + payload
        self._async_writer.write(packet)
        await self._async_writer.drain()

    async def _recv_sync_header(self, expected: str | None = None) -> HiSlipHeader:
        if self._sync_reader is None:
            raise ScpiTransportError("Sync channel reader unavailable.")

        raw = await self._sync_reader.readexactly(HEADER_SIZE)
        header = self._decode_header(raw)
        self._sync_init_header_raw = raw
        if expected and header.msg_type != expected:
            raise ScpiTransportError(f"Expected {expected}, got {header.msg_type}")
        return header

    async def _recv_async_header(self, expected: str | None = None) -> HiSlipHeader:
        if self._async_reader is None:
            raise ScpiTransportError("Async channel reader unavailable.")

        raw = await self._async_reader.readexactly(HEADER_SIZE)
        header = self._decode_header(raw)
        self._async_last_header_raw = raw
        if expected and header.msg_type != expected:
            raise ScpiTransportError(f"Expected {expected}, got {header.msg_type}")
        return header

    async def _recv_sync_payload(self, length: int) -> bytes:
        if self._sync_reader is None:
            raise ScpiTransportError("Sync channel reader unavailable.")
        if length == 0:
            return b""
        return await self._sync_reader.readexactly(length)

    async def _recv_async_payload(self, length: int) -> bytes:
        if self._async_reader is None:
            raise ScpiTransportError("Async channel reader unavailable.")
        if length == 0:
            return b""
        return await self._async_reader.readexactly(length)

    async def _async_read_loop(self) -> None:
        while self._async_reader is not None:
            header = await self._recv_async_header()
            payload = await self._recv_async_payload(header.payload_length)
            queue = self._async_waiters.get(header.msg_type)
            if queue is not None:
                await queue.put((header, payload))

    def _decode_header(self, raw: bytes) -> HiSlipHeader:
        prologue, msg_type, control_code, message_parameter, payload_length = struct.unpack(HEADER_FORMAT, raw)
        if prologue != b"HS":
            raise ScpiTransportError("Protocol synchronization error. Invalid HiSLIP prologue.")

        if msg_type not in MESSAGE_NAME:
            raise ScpiTransportError(f"Unknown HiSLIP message type: {msg_type}")

        return HiSlipHeader(
            msg_type=MESSAGE_NAME[msg_type],
            control_code=control_code,
            message_parameter=message_parameter,
            payload_length=payload_length,
        )

    @property
    def _session_id_from_initialize_response(self) -> int:
        if self._sync_init_header_raw is None:
            raise ScpiTransportError("Initialize response header unavailable.")
        _, _, _, _, _ = struct.unpack(HEADER_FORMAT, self._sync_init_header_raw)
        _, session_id = struct.unpack("!4xHH8x", self._sync_init_header_raw)
        return session_id

    _sync_init_header_raw: bytes | None = None
    _async_last_header_raw: bytes | None = None

    @property
    def connected(self) -> bool:
        return (
            self._sync_reader is not None
            and self._sync_writer is not None
            and self._async_reader is not None
            and self._async_writer is not None
        )
