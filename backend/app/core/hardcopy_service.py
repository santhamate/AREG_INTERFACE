"""Hardcopy/screenshot capture service for AREG800A."""

from __future__ import annotations

import struct
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

    def __init__(self, scpi_service: ScpiService):
        self.scpi_service = scpi_service
        self.last_capture_path: Path | None = None

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
        try:
            # Validate inputs
            if not self.scpi_service.transport.connected:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": "Instrument not connected",
                }

            file_format = file_format.upper()
            if file_format not in self.SUPPORTED_FORMATS:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": f"Unsupported format: {file_format}. Supported: {', '.join(self.SUPPORTED_FORMATS.keys())}",
                }

            # Determine save directory
            if save_dir:
                output_dir = Path(save_dir).expanduser()
            else:
                output_dir = self.DEFAULT_SAVE_DIR

            # Create directory if it doesn't exist
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": f"Failed to create save directory: {str(e)}",
                }

            # Generate filename
            file_extension = self.SUPPORTED_FORMATS[file_format][1]
            if use_timestamp:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"{filename_prefix}_{timestamp}{file_extension}"
            else:
                filename = f"{filename_prefix}{file_extension}"

            output_path = output_dir / filename

            # Configure hardcopy format on instrument
            try:
                timeout = timeout_ms if timeout_ms is not None else 5000
                config_result = await self.scpi_service.execute_with_classification(
                    f":HCOPY:IMAGE:FORMAT {file_format}",
                    timeout_ms=timeout,
                )
                if not config_result["ok"]:
                    return {
                        "ok": False,
                        "file_path": None,
                        "file_format": file_format,
                        "bytes_written": 0,
                        "message": None,
                        "error": f"Failed to set hardcopy format: {config_result.get('error', 'Unknown error')}",
                    }
            except Exception as e:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": f"Failed to configure format: {str(e)}",
                }

            # Execute hardcopy on instrument
            try:
                execute_result = await self.scpi_service.execute_with_classification(
                    ":HCOPY:EXECUTE",
                    timeout_ms=timeout,
                )
                if not execute_result["ok"]:
                    return {
                        "ok": False,
                        "file_path": None,
                        "file_format": file_format,
                        "bytes_written": 0,
                        "message": None,
                        "error": f"Failed to execute hardcopy: {execute_result.get('error', 'Unknown error')}",
                    }
            except Exception as e:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": f"Failed to execute hardcopy: {str(e)}",
                }

            # Retrieve image binary data
            try:
                image_data = await self.scpi_service.transport.query_bytes(
                    ":HCOPY:DATA?",
                    timeout_ms=timeout,
                )
            except Exception as e:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": f"Failed to retrieve image data: {str(e)}",
                }

            # Validate image data
            if not image_data or len(image_data) == 0:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": "Received empty image data from instrument",
                }

            # Optional: Validate image signature/magic bytes
            magic_bytes = self.SUPPORTED_FORMATS[file_format][0]
            if not image_data.startswith(magic_bytes):
                # Warn but don't fail - sometimes there's leading/trailing data
                pass

            # Save image file
            try:
                output_path.write_bytes(image_data)
            except OSError as e:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": f"Failed to write image file: {str(e)}",
                }

            # Verify file was written
            if not output_path.exists() or output_path.stat().st_size == 0:
                return {
                    "ok": False,
                    "file_path": None,
                    "file_format": file_format,
                    "bytes_written": 0,
                    "message": None,
                    "error": "Image file was not written correctly",
                }

            bytes_written = output_path.stat().st_size
            self.last_capture_path = output_path

            return {
                "ok": True,
                "file_path": str(output_path),
                "file_format": file_format,
                "bytes_written": bytes_written,
                "message": f"Screenshot saved successfully: {filename} ({bytes_written} bytes)",
                "error": None,
            }

        except Exception as e:
            return {
                "ok": False,
                "file_path": None,
                "file_format": file_format,
                "bytes_written": 0,
                "message": None,
                "error": f"Unexpected error during hardcopy: {str(e)}",
            }

    def get_supported_formats(self) -> list[str]:
        """Get list of supported image formats."""
        return list(self.SUPPORTED_FORMATS.keys())

    def get_last_capture_path(self) -> Path | None:
        """Get the path of the last successfully captured screenshot."""
        return self.last_capture_path

    def set_default_save_dir(self, save_dir: str) -> None:
        """Set the default save directory."""
        HardcopyService.DEFAULT_SAVE_DIR = Path(save_dir)
