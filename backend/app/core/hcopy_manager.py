"""HCopy manager for AREG800A: manual-aligned HCOPy subsystem operations.

Implements the HCOPy subsystem as documented in the R&S AREG800A User Manual.
Key separation:
  - HCOPy:EXECute saves a file on the INSTRUMENT file system.
  - HCOPy:DATA? transfers the image directly to the PC as binary block data.
  - File management of saved screenshots is done via MMEMory (memory_manager).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.core.scpi_service import ScpiService


VALID_FORMATS: frozenset[str] = frozenset({"PNG", "BMP", "JPG", "XPM"})
VALID_REGIONS: frozenset[str] = frozenset({"ALL", "DIALog"})
FORMAT_EXT: dict[str, str] = {"PNG": ".png", "BMP": ".bmp", "JPG": ".jpg", "XPM": ".xpm"}

# Default local save directory when capturing data directly to PC.
_DEFAULT_LOCAL_DIR = Path("./screenshots")


class HCopyManager:
    """Manual-aligned manager for the HCOPy subsystem of the AREG800A.

    All setter/event methods do NOT wait for a response body.
    Only commands explicitly ending with '?' are treated as queries.
    """

    def __init__(self, scpi_service: ScpiService) -> None:
        self.scpi_service = scpi_service
        # Cached settings so the UI can reflect current state without extra queries.
        self._format: str = "PNG"
        self._region: str = "ALL"
        self._auto_naming: bool = True
        self._manual_filename: str = ""
        self._auto_directory: str = "/var/user"
        self._prefix_enabled: bool = False
        self._prefix: str = ""
        self._year_enabled: bool = False
        self._month_enabled: bool = False
        self._day_enabled: bool = False

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    async def _write(self, command: str) -> tuple[bool, str | None]:
        """Send a setter/event SCPI command (no response expected)."""
        result = await self.scpi_service.execute_with_classification(command)
        if not result.get("ok"):
            return False, str(result.get("error") or "Command failed")
        return True, None

    async def _query(self, command: str) -> tuple[str | None, str | None]:
        """Send a query command and return (response_str, error)."""
        result = await self.scpi_service.execute_with_classification(command)
        if not result.get("ok"):
            return None, str(result.get("error") or "Query failed")
        raw = str(result.get("response") or "").strip()
        # Strip surrounding quotes that instruments sometimes include.
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        return raw, None

    @staticmethod
    def _norm(path: str) -> str:
        return path.replace("\\", "/").strip()

    @staticmethod
    def _q(path: str) -> str:
        safe = HCopyManager._norm(path).replace('"', '""')
        return f'"{safe}"'

    @staticmethod
    def _bool_state(enabled: bool) -> str:
        return "1" if enabled else "0"

    # -----------------------------------------------------------------------
    # Format and region
    # -----------------------------------------------------------------------

    async def set_format(self, fmt: str) -> tuple[bool, str | None]:
        """Send :HCOPy:DEVice:LANGuage <format>. Validates against allowed values."""
        fmt = fmt.upper()
        if fmt not in VALID_FORMATS:
            return False, f"Invalid format '{fmt}'. Allowed: {', '.join(sorted(VALID_FORMATS))}"
        ok, err = await self._write(f":HCOPy:DEVice:LANGuage {fmt}")
        if ok:
            self._format = fmt
        return ok, err

    async def set_region(self, region: str) -> tuple[bool, str | None]:
        """Send :HCOPy:REGion <region>. Validates against ALL/DIALog."""
        region = region.upper()
        if region not in VALID_REGIONS:
            return False, f"Invalid region '{region}'. Allowed: {', '.join(sorted(VALID_REGIONS))}"
        ok, err = await self._write(f":HCOPy:REGion {region}")
        if ok:
            self._region = region
        return ok, err

    # -----------------------------------------------------------------------
    # Automatic naming
    # -----------------------------------------------------------------------

    async def set_auto_naming_enabled(self, enabled: bool) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME:AUTO:STATe <0|1>."""
        ok, err = await self._write(f":HCOPy:FILE:NAME:AUTO:STATe {self._bool_state(enabled)}")
        if ok:
            self._auto_naming = enabled
        return ok, err

    # -----------------------------------------------------------------------
    # Manual filename
    # -----------------------------------------------------------------------

    async def set_manual_filename(self, path: str) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME "<path>". Used when automatic naming is disabled."""
        if not path.strip():
            return False, "Manual filename is required when automatic naming is disabled."
        norm = self._norm(path)
        ok, err = await self._write(f":HCOPy:FILE:NAME {self._q(norm)}")
        if ok:
            self._manual_filename = norm
        return ok, err

    # -----------------------------------------------------------------------
    # Automatic naming – directory
    # -----------------------------------------------------------------------

    async def set_auto_directory(self, directory: str) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME:AUTO:DIRectory "<directory>"."""
        norm = self._norm(directory) or "/var/user"
        ok, err = await self._write(f":HCOPy:FILE:NAME:AUTO:DIRectory {self._q(norm)}")
        if ok:
            self._auto_directory = norm
        return ok, err

    async def clear_auto_directory(self) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME:AUTO:DIRectory:CLEar (event, no response).

        Deletes all .bmp/.jpg/.png/.xpm files in the configured auto directory.
        IMPORTANT: Caller must have shown a confirmation dialog before calling this.
        """
        return await self._write(":HCOPy:FILE:NAME:AUTO:DIRectory:CLEar")

    # -----------------------------------------------------------------------
    # Automatic naming – prefix
    # -----------------------------------------------------------------------

    async def set_prefix_enabled(self, enabled: bool) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME:AUTO:FILE:PREFix:STATe <0|1>."""
        ok, err = await self._write(
            f":HCOPy:FILE:NAME:AUTO:FILE:PREFix:STATe {self._bool_state(enabled)}"
        )
        if ok:
            self._prefix_enabled = enabled
        return ok, err

    async def set_prefix(self, prefix: str) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME:AUTO:FILE:PREFix "<prefix>"."""
        ok, err = await self._write(f":HCOPy:FILE:NAME:AUTO:FILE:PREFix {self._q(prefix)}")
        if ok:
            self._prefix = prefix
        return ok, err

    # -----------------------------------------------------------------------
    # Automatic naming – date components
    # -----------------------------------------------------------------------

    async def set_year_enabled(self, enabled: bool) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME:AUTO:FILE:YEAR:STATe <0|1>."""
        ok, err = await self._write(
            f":HCOPy:FILE:NAME:AUTO:FILE:YEAR:STATe {self._bool_state(enabled)}"
        )
        if ok:
            self._year_enabled = enabled
        return ok, err

    async def set_month_enabled(self, enabled: bool) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME:AUTO:FILE:MONTh:STATe <0|1>."""
        ok, err = await self._write(
            f":HCOPy:FILE:NAME:AUTO:FILE:MONTh:STATe {self._bool_state(enabled)}"
        )
        if ok:
            self._month_enabled = enabled
        return ok, err

    async def set_day_enabled(self, enabled: bool) -> tuple[bool, str | None]:
        """Send :HCOPy:FILE:NAME:AUTO:FILE:DAY:STATe <0|1>."""
        ok, err = await self._write(
            f":HCOPy:FILE:NAME:AUTO:FILE:DAY:STATe {self._bool_state(enabled)}"
        )
        if ok:
            self._day_enabled = enabled
        return ok, err

    # -----------------------------------------------------------------------
    # Automatic naming – queries
    # -----------------------------------------------------------------------

    async def get_auto_number(self) -> tuple[int | None, str | None]:
        """Query :HCOPy:FILE:NAME:AUTO:FILE:NUMBer? for the next auto number."""
        raw, err = await self._query(":HCOPy:FILE:NAME:AUTO:FILE:NUMBer?")
        if err:
            return None, err
        try:
            return int((raw or "").strip()), None
        except ValueError:
            return None, f"Unexpected auto number response: {raw!r}"

    async def get_auto_filename(self) -> tuple[str | None, str | None]:
        """Query :HCOPy:FILE:NAME:AUTO:FILE? for the auto-generated filename."""
        return await self._query(":HCOPy:FILE:NAME:AUTO:FILE?")

    async def get_auto_full_path(self) -> tuple[str | None, str | None]:
        """Query :HCOPy:FILE:NAME:AUTO? for the full auto-generated path."""
        return await self._query(":HCOPy:FILE:NAME:AUTO?")

    # -----------------------------------------------------------------------
    # Execute
    # -----------------------------------------------------------------------

    async def execute_to_file(self) -> dict[str, Any]:
        """Send :HCOPy:EXECute (event, saves screenshot to instrument file system).

        After execution:
        - If auto naming is ON, queries generated filename and full path.
        - Refresh of the MMEMory directory must be triggered by the caller.

        Returns dict with keys: ok, message, error, generated_path, generated_filename,
        auto_directory, timestamp.
        """
        ok, err = await self._write(":HCOPy:EXECute")
        timestamp = datetime.now().isoformat(timespec="seconds")
        if not ok:
            return {
                "ok": False,
                "message": None,
                "error": err,
                "generated_path": None,
                "generated_filename": None,
                "auto_directory": self._auto_directory,
                "timestamp": timestamp,
            }

        generated_path: str | None = None
        generated_filename: str | None = None

        if self._auto_naming:
            generated_filename, _fe = await self.get_auto_filename()
            generated_path, _pe = await self.get_auto_full_path()

        return {
            "ok": True,
            "message": f"Hardcopy saved on instrument at {generated_path or self._auto_directory}",
            "error": None,
            "generated_path": generated_path,
            "generated_filename": generated_filename,
            "auto_directory": self._auto_directory,
            "timestamp": timestamp,
        }

    # -----------------------------------------------------------------------
    # Capture directly to PC (binary block transfer)
    # -----------------------------------------------------------------------

    async def capture_data(
        self,
        local_dir: str | None = None,
        local_filename: str | None = None,
        timeout_ms: int = 10000,
    ) -> dict[str, Any]:
        """Send :HCOPy:DATA? and save the binary block data locally.

        The returned data is an SCPI definite-length block (#<n><len><bytes>).
        This method parses the block, validates it, and saves it to a local file.
        This does NOT write anything to the instrument file system.

        Returns dict with keys: ok, file_path, bytes_written, detected_type,
        message, error, timestamp.
        """
        timestamp = datetime.now().isoformat(timespec="seconds")

        if not self.scpi_service.transport.connected:
            return {
                "ok": False,
                "file_path": None,
                "bytes_written": 0,
                "detected_type": None,
                "message": None,
                "error": "Device is not connected",
                "timestamp": timestamp,
            }

        try:
            raw: bytes = await self.scpi_service.transport.query_bytes(
                ":HCOPy:DATA?", timeout_ms=timeout_ms
            )
        except Exception as ex:
            return {
                "ok": False,
                "file_path": None,
                "bytes_written": 0,
                "detected_type": None,
                "message": None,
                "error": f"HCOPy:DATA? transfer failed: {ex}",
                "timestamp": timestamp,
            }

        if not raw:
            return {
                "ok": False,
                "file_path": None,
                "bytes_written": 0,
                "detected_type": None,
                "message": None,
                "error": "Hardcopy data transfer failed or returned invalid block data.",
                "timestamp": timestamp,
            }

        # Parse SCPI definite-length block if present.
        payload = raw
        if raw.startswith(b"#") and len(raw) >= 2 and chr(raw[1]).isdigit():
            parsed, parse_err = self._parse_scpi_block(raw)
            if parse_err:
                return {
                    "ok": False,
                    "file_path": None,
                    "bytes_written": 0,
                    "detected_type": None,
                    "message": None,
                    "error": f"Hardcopy data transfer failed or returned invalid block data. Detail: {parse_err}",
                    "timestamp": timestamp,
                }
            payload = parsed

        detected = self._detect_type(payload)

        # Build local save path.
        ext = FORMAT_EXT.get(self._format, ".png")
        out_dir = Path(local_dir).expanduser() if local_dir else _DEFAULT_LOCAL_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        if local_filename:
            fn = local_filename if Path(local_filename).suffix else f"{local_filename}{ext}"
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fn = f"hardcopy_{ts}{ext}"

        out_path = out_dir / fn
        try:
            out_path.write_bytes(payload)
        except OSError as ex:
            return {
                "ok": False,
                "file_path": None,
                "bytes_written": 0,
                "detected_type": detected,
                "message": None,
                "error": f"Failed to save hardcopy: {ex}",
                "timestamp": timestamp,
            }

        return {
            "ok": True,
            "file_path": str(out_path),
            "bytes_written": len(payload),
            "detected_type": detected,
            "message": f"Captured {len(payload):,} bytes → {out_path}",
            "error": None,
            "timestamp": timestamp,
        }

    # -----------------------------------------------------------------------
    # State snapshot (for UI reflection)
    # -----------------------------------------------------------------------

    def settings_snapshot(self) -> dict[str, Any]:
        """Return current cached settings for UI reflection."""
        return {
            "format": self._format,
            "region": self._region,
            "auto_naming": self._auto_naming,
            "manual_filename": self._manual_filename,
            "auto_directory": self._auto_directory,
            "prefix_enabled": self._prefix_enabled,
            "prefix": self._prefix,
            "year_enabled": self._year_enabled,
            "month_enabled": self._month_enabled,
            "day_enabled": self._day_enabled,
        }

    # -----------------------------------------------------------------------
    # Internal: binary helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_scpi_block(raw: bytes) -> tuple[bytes, str | None]:
        """Parse SCPI definite-length block #<n><len><payload>."""
        if len(raw) < 2:
            return raw, "Block too short"
        n_digits = int(chr(raw[1]))
        if n_digits <= 0:
            return raw, "Indefinite-length block not supported"
        header_end = 2 + n_digits
        if len(raw) < header_end:
            return raw, "Truncated block header"
        length_str = raw[2:header_end].decode("ascii", errors="ignore")
        if not length_str.isdigit():
            return raw, "Block length field is not numeric"
        payload_length = int(length_str)
        payload = raw[header_end: header_end + payload_length]
        return payload, None

    @staticmethod
    def _detect_type(data: bytes) -> str:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "PNG"
        if data.startswith(b"\xff\xd8\xff"):
            return "JPEG"
        if data.startswith(b"BM"):
            return "BMP"
        if data.startswith(b"/* XPM */") or data.startswith(b"XPM"):
            return "XPM"
        return "UNKNOWN"
