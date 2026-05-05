"""Hardcopy/screenshot capture service for AREG800A."""

from __future__ import annotations

import string
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.core.scpi_service import ScpiService


class HardcopyService:
    """Orchestrates hardcopy/screenshot capture from the instrument."""

    # Supported image formats and their magic bytes for validation
    SUPPORTED_FORMATS = {
        "PNG": (b"\x89PNG\r\n\x1a\n", ".png"),
        "JPG": (b"\xff\xd8\xff", ".jpg"),
        "BMP": (b"BM", ".bmp"),
    }

    DEFAULT_SAVE_DIR = Path("./screenshots")
    DEFAULT_FORMAT = "PNG"
    DEFAULT_PREFIX = "AREG800A_screenshot"
    ASCII_PREVIEW_BYTES = 100
    HEX_PREVIEW_BYTES = 32

    def __init__(self, scpi_service: ScpiService):
        self.scpi_service = scpi_service
        self.last_capture_path: Path | None = None
        self.last_analysis: dict[str, Any] | None = None

    def _ascii_safe_preview(self, data: bytes, limit: int = ASCII_PREVIEW_BYTES) -> str:
        preview = data[:limit]
        allowed = set(string.printable) - {"\x0b", "\x0c", "\r", "\n", "\t"}
        return "".join(chr(b) if chr(b) in allowed else "." for b in preview)

    def _hex_preview(self, data: bytes, limit: int = HEX_PREVIEW_BYTES) -> str:
        return " ".join(f"{b:02X}" for b in data[:limit])

    def _looks_like_ascii_error(self, data: bytes) -> bool:
        if not data:
            return False
        preview = self._ascii_safe_preview(data, limit=min(len(data), self.ASCII_PREVIEW_BYTES)).lower()
        if not preview:
            return False
        keywords = ("error", "undefined", "invalid", "failed", "not allowed", "unknown", "syntax")
        mostly_ascii = sum(32 <= b <= 126 or b in {9, 10, 13} for b in data[:64]) >= max(1, len(data[:64]) * 0.8)
        return mostly_ascii and any(word in preview for word in keywords)

    def _detect_type(self, data: bytes) -> str:
        if not data:
            return "UNKNOWN"
        if data.startswith(self.SUPPORTED_FORMATS["PNG"][0]):
            return "PNG"
        if data.startswith(self.SUPPORTED_FORMATS["JPG"][0]):
            return "JPEG"
        if data.startswith(self.SUPPORTED_FORMATS["BMP"][0]):
            return "BMP"
        if data.startswith(b"#") and len(data) >= 2 and chr(data[1]).isdigit():
            return "SCPI_BLOCK"
        if self._looks_like_ascii_error(data):
            return "ASCII_ERROR"
        return "UNKNOWN"

    def _recommendation_for_type(self, detected_type: str, expected_format: str) -> str:
        recommendations = {
            "PNG": "Payload is a valid PNG image.",
            "JPEG": "Payload is a valid JPEG image.",
            "BMP": "Payload is a valid BMP image.",
            "SCPI_BLOCK": "Parse the SCPI definite-length block and save only the payload bytes.",
            "ASCII_ERROR": "Instrument returned ASCII text instead of image data. Check SCPI command order and instrument error queue.",
            "UNKNOWN": f"Payload does not match expected {expected_format} signature. Inspect the first bytes and instrument response.",
        }
        return recommendations.get(detected_type, f"Unexpected payload while expecting {expected_format} hardcopy data.")

    def _build_diagnostics(self, data: bytes, expected_format: str, payload_length: int | None = None) -> dict[str, Any]:
        detected_type = self._detect_type(data)
        return {
            "file_size": len(data),
            "payload_length": payload_length if payload_length is not None else len(data),
            "first_32_bytes_hex": self._hex_preview(data),
            "ascii_preview": self._ascii_safe_preview(data),
            "detected_type": detected_type,
            "recommendation": self._recommendation_for_type(detected_type, expected_format),
        }

    def _parse_scpi_block(self, raw: bytes) -> tuple[bytes | None, dict[str, Any] | None, str | None]:
        if not raw.startswith(b"#"):
            return raw, None, None
        if len(raw) < 2 or not chr(raw[1]).isdigit():
            return None, None, "Invalid SCPI block header"

        length_digits = int(chr(raw[1]))
        if length_digits <= 0:
            return None, None, "Indefinite-length SCPI block is not supported"

        header_end = 2 + length_digits
        if len(raw) < header_end:
            return None, None, "Truncated SCPI block length header"

        length_str = raw[2:header_end].decode("ascii", errors="ignore")
        if not length_str.isdigit():
            return None, None, "SCPI block length field is not numeric"

        payload_length = int(length_str)
        payload_end = header_end + payload_length
        if len(raw) < payload_end:
            return None, None, f"SCPI block truncated: expected {payload_length} payload bytes, received {max(len(raw) - header_end, 0)}"

        payload = raw[header_end:payload_end]
        trailing = raw[payload_end:]
        parse_info = {
            "length_digits": length_digits,
            "payload_length": payload_length,
            "trailing_bytes": len(trailing.rstrip(b"\r\n\0")),
        }
        return payload, parse_info, None

    def _validate_payload(self, payload: bytes, expected_format: str) -> tuple[bool, str]:
        detected_type = self._detect_type(payload)
        expected_type = "JPEG" if expected_format == "JPG" else expected_format
        if detected_type != expected_type:
            return False, f"Expected {expected_type} payload but detected {detected_type}"
        return True, "Payload signature validated"

    async def _run_command(self, command: str, timeout_ms: int, capture_log: list[dict[str, Any]]) -> dict[str, Any]:
        result = await self.scpi_service.execute_with_classification(command, timeout_ms=timeout_ms)
        capture_log.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "command": command,
                "command_type": result.get("command_type"),
                "ok": result.get("ok"),
                "response": result.get("response"),
                "message": result.get("message"),
                "error": result.get("error"),
            }
        )
        return result

    def _set_last_analysis(self, analysis: dict[str, Any]) -> None:
        self.last_analysis = analysis

    async def capture_hardcopy(
        self,
        save_dir: str | None = None,
        file_format: str = DEFAULT_FORMAT,
        filename_prefix: str = DEFAULT_PREFIX,
        use_timestamp: bool = True,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """
        Capture a screenshot from the instrument and save it locally.

        Implements the two-step process:
        1. Configure instrument for hardcopy (format, etc.)
        2. Execute hardcopy and retrieve binary image data

        Args:
            save_dir: Directory to save the file. Defaults to ./screenshots
            file_format: Image format (PNG, JPG, BMP). Defaults to PNG
            filename_prefix: Filename prefix. Defaults to AREG800A_screenshot
            use_timestamp: If True, adds timestamp to filename (YYYY-MM-DD_HH-MM-SS)
            timeout_ms: Command timeout in milliseconds

        Returns:
            Dictionary with keys:
            - ok: bool, success status
            - file_path: str, path to saved file (None if failed)
            - file_format: str, format that was used
            - bytes_written: int, number of bytes written
            - message: str, success message
            - error: str, error message if failed
        """
        capture_log: list[dict[str, Any]] = []
        try:
            # Validate inputs
            if not self.scpi_service.transport.connected:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": 0,
                    "detected_type": None,
                    "validation_ok": False,
                    "diagnostics": None,
                    "log": capture_log,
                    "message": None,
                    "error": "Instrument not connected",
                }
                self._set_last_analysis(result)
                return result

            file_format = file_format.upper()
            if file_format not in self.SUPPORTED_FORMATS:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": 0,
                    "detected_type": None,
                    "validation_ok": False,
                    "diagnostics": None,
                    "log": capture_log,
                    "message": None,
                    "error": f"Unsupported format: {file_format}. Supported: {', '.join(self.SUPPORTED_FORMATS.keys())}",
                }
                self._set_last_analysis(result)
                return result

            # Determine save directory
            if save_dir:
                output_dir = Path(save_dir).expanduser()
            else:
                output_dir = self.DEFAULT_SAVE_DIR

            # Create directory if it doesn't exist
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": 0,
                    "detected_type": None,
                    "validation_ok": False,
                    "diagnostics": None,
                    "log": capture_log,
                    "message": None,
                    "error": f"Failed to create save directory: {str(e)}",
                }
                self._set_last_analysis(result)
                return result

            # Generate filename
            file_extension = self.SUPPORTED_FORMATS[file_format][1]
            if use_timestamp:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"{filename_prefix}_{timestamp}{file_extension}"
            else:
                filename = f"{filename_prefix}{file_extension}"

            output_path = output_dir / filename
            capture_log.append(
                {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "command": "LOCAL_SAVE_PATH",
                    "command_type": "info",
                    "ok": True,
                    "response": None,
                    "message": str(output_path),
                    "error": None,
                }
            )

            # Configure hardcopy format on instrument
            try:
                timeout = timeout_ms if timeout_ms is not None else 5000
                config_result = await self._run_command(
                    f":HCOPy:DEVice:LANGuage {file_format}",
                    timeout,
                    capture_log,
                )
                if not config_result["ok"]:
                    result = {
                        "ok": False,
                        "file_path": None,
                        "file_format": file_format,
                        "bytes_written": 0,
                        "payload_bytes": 0,
                        "detected_type": None,
                        "validation_ok": False,
                        "diagnostics": None,
                        "log": capture_log,
                        "message": None,
                        "error": f"Failed to set hardcopy format: {config_result.get('error', 'Unknown error')}",
                    }
                    self._set_last_analysis(result)
                    return result

                auto_name_result = await self._run_command(
                    ":HCOPy:FILE:NAME:AUTO:STATe 1",
                    timeout,
                    capture_log,
                )
                if not auto_name_result["ok"]:
                    result = {
                        "ok": False,
                        "file_path": None,
                        "file_format": file_format,
                        "bytes_written": 0,
                        "payload_bytes": 0,
                        "detected_type": None,
                        "validation_ok": False,
                        "diagnostics": None,
                        "log": capture_log,
                        "message": None,
                        "error": f"Failed to enable hardcopy auto filename: {auto_name_result.get('error', 'Unknown error')}",
                    }
                    self._set_last_analysis(result)
                    return result
            except Exception as e:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": 0,
                    "detected_type": None,
                    "validation_ok": False,
                    "diagnostics": None,
                    "log": capture_log,
                    "message": None,
                    "error": f"Failed to configure format: {str(e)}",
                }
                self._set_last_analysis(result)
                return result

            # Execute hardcopy on instrument
            try:
                execute_result = await self._run_command(":HCOPy:EXECute", timeout, capture_log)
                if not execute_result["ok"]:
                    result = {
                        "ok": False,
                        "file_path": None,
                        "file_format": file_format,
                        "bytes_written": 0,
                        "payload_bytes": 0,
                        "detected_type": None,
                        "validation_ok": False,
                        "diagnostics": None,
                        "log": capture_log,
                        "message": None,
                        "error": f"Failed to execute hardcopy: {execute_result.get('error', 'Unknown error')}",
                    }
                    self._set_last_analysis(result)
                    return result
            except Exception as e:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": 0,
                    "detected_type": None,
                    "validation_ok": False,
                    "diagnostics": None,
                    "log": capture_log,
                    "message": None,
                    "error": f"Failed to execute hardcopy: {str(e)}",
                }
                self._set_last_analysis(result)
                return result

            # Retrieve image binary data
            try:
                capture_log.append(
                    {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "command": ":HCOPy:DATA?",
                        "command_type": "binary-query",
                        "ok": True,
                        "response": None,
                        "message": "Waiting for binary payload",
                        "error": None,
                    }
                )
                image_data = await self.scpi_service.transport.query_bytes(":HCOPy:DATA?", timeout_ms=timeout)
            except Exception as e:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": 0,
                    "detected_type": None,
                    "validation_ok": False,
                    "diagnostics": None,
                    "log": capture_log,
                    "message": None,
                    "error": f"Failed to retrieve image data: {str(e)}",
                }
                self._set_last_analysis(result)
                return result

            # Validate image data
            if not image_data or len(image_data) == 0:
                diagnostics = self._build_diagnostics(image_data, file_format)
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": 0,
                    "detected_type": diagnostics["detected_type"],
                    "validation_ok": False,
                    "diagnostics": diagnostics,
                    "log": capture_log,
                    "message": None,
                    "error": "Received empty image data from instrument",
                }
                self._set_last_analysis(result)
                return result

            raw_diagnostics = self._build_diagnostics(image_data, file_format)
            payload, block_info, parse_error = self._parse_scpi_block(image_data)
            if parse_error:
                diagnostics = dict(raw_diagnostics)
                diagnostics["recommendation"] = parse_error
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": 0,
                    "detected_type": diagnostics["detected_type"],
                    "validation_ok": False,
                    "diagnostics": diagnostics,
                    "log": capture_log,
                    "message": None,
                    "error": parse_error,
                }
                self._set_last_analysis(result)
                return result

            assert payload is not None
            payload_diagnostics = self._build_diagnostics(
                payload,
                file_format,
                payload_length=block_info["payload_length"] if block_info else len(payload),
            )
            if block_info:
                payload_diagnostics["scpi_block"] = block_info

            valid_payload, validation_message = self._validate_payload(payload, file_format)
            payload_diagnostics["validation_message"] = validation_message
            capture_log.append(
                {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "command": "VALIDATION_RESULT",
                    "command_type": "info",
                    "ok": valid_payload,
                    "response": None,
                    "message": f"Received {len(image_data)} raw bytes, extracted {len(payload)} payload bytes",
                    "error": None if valid_payload else validation_message,
                }
            )

            if not valid_payload:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": len(payload),
                    "detected_type": payload_diagnostics["detected_type"],
                    "validation_ok": False,
                    "diagnostics": payload_diagnostics,
                    "log": capture_log,
                    "message": None,
                    "error": validation_message,
                }
                self._set_last_analysis(result)
                return result

            # Save image file
            try:
                output_path.write_bytes(payload)
                capture_log.append(
                    {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "command": "WRITE_FILE",
                        "command_type": "info",
                        "ok": True,
                        "response": None,
                        "message": f"Wrote {len(payload)} bytes to {output_path}",
                        "error": None,
                    }
                )
            except OSError as e:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": len(payload),
                    "detected_type": payload_diagnostics["detected_type"],
                    "validation_ok": False,
                    "diagnostics": payload_diagnostics,
                    "log": capture_log,
                    "message": None,
                    "error": f"Failed to write image file: {str(e)}",
                }
                self._set_last_analysis(result)
                return result

            # Verify file was written
            if not output_path.exists() or output_path.stat().st_size == 0:
                result = {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "payload_bytes": len(payload),
                    "detected_type": payload_diagnostics["detected_type"],
                    "validation_ok": False,
                    "diagnostics": payload_diagnostics,
                    "log": capture_log,
                    "message": None,
                    "error": "Image file was not written correctly",
                }
                self._set_last_analysis(result)
                return result

            bytes_written = output_path.stat().st_size
            self.last_capture_path = output_path
            result = {
                "ok": True,
                "file_path": str(output_path),
                "file_format": file_format,
                "bytes_written": bytes_written,
                "payload_bytes": len(payload),
                "detected_type": payload_diagnostics["detected_type"],
                "validation_ok": True,
                "diagnostics": payload_diagnostics,
                "log": capture_log,
                "message": f"Screenshot saved successfully: {filename} ({bytes_written} bytes)",
                "error": None,
            }
            self._set_last_analysis(result)
            return result

        except Exception as e:
            result = {
                "ok": False,
                "file_path": None,
                "file_format": file_format,
                "bytes_written": 0,
                "payload_bytes": 0,
                "detected_type": None,
                "validation_ok": False,
                "diagnostics": None,
                "log": capture_log,
                "message": None,
                "error": f"Unexpected error during hardcopy: {str(e)}",
            }
            self._set_last_analysis(result)
            return result

    def get_supported_formats(self) -> list[str]:
        """Get list of supported image formats."""
        return list(self.SUPPORTED_FORMATS.keys())

    def get_last_capture_path(self) -> Path | None:
        """Get the path of the last successfully captured screenshot."""
        return self.last_capture_path

    def analyze_file(self, file_path: str | None = None) -> dict[str, Any]:
        target = Path(file_path) if file_path else self.last_capture_path
        if target is None:
            return {"ok": False, "error": "No hardcopy available for analysis"}
        if not target.exists():
            return {"ok": False, "error": f"File not found: {target}"}

        data = target.read_bytes()
        diagnostics = self._build_diagnostics(data, target.suffix.lstrip(".").upper() or self.DEFAULT_FORMAT)
        is_valid = diagnostics["detected_type"] in {"PNG", "JPEG", "BMP"}
        result = {
            "ok": True,
            "file_path": str(target),
            "validation_ok": is_valid,
            "diagnostics": diagnostics,
        }
        self.last_analysis = result
        return result

    def get_last_analysis(self) -> dict[str, Any] | None:
        return self.last_analysis

    def set_default_save_dir(self, save_dir: str) -> None:
        """Set the default save directory."""
        HardcopyService.DEFAULT_SAVE_DIR = Path(save_dir)
