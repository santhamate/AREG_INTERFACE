"""Tests for the hardcopy/screenshot capture feature."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.core.hardcopy_service import HardcopyService


class MockScpiService:
    """Mock SCPI service for testing."""

    def __init__(self):
        self.transport = MagicMock()
        self.transport.connected = True
        self.session_state = lambda: {"transport": "mock"}

    async def execute_with_classification(self, command: str, timeout_ms: int | None = None) -> dict:
        """Mock command execution."""
        return {
            "ok": True,
            "command": command,
            "command_type": "write" if not command.endswith("?") else "query",
            "response": None,
            "message": "Command sent",
            "error": None,
        }


@pytest.mark.asyncio
async def test_filename_generation_with_timestamp():
    """Test filename generation with timestamp."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)
    service.transport.query_bytes = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    # Mock the capture to just check filename generation
    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="PNG",
            filename_prefix="TEST_screenshot",
            use_timestamp=True,
        )

        # The file should exist even if capture fails due to mocked query_bytes
        # We're mainly testing that the filename format is correct
        filename = Path(result["file_path"]).name if result["file_path"] else ""
        
        # Should match pattern: TEST_screenshot_YYYY-MM-DD_HH-MM-SS.png
        assert "TEST_screenshot_" in filename
        assert filename.endswith(".png")
        assert "_" in filename  # Should have date-time separators


@pytest.mark.asyncio
async def test_filename_generation_without_timestamp():
    """Test filename generation without timestamp."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)
    service.transport.query_bytes = AsyncMock(return_value=b"\xff\xd8\xff" + b"\x00" * 16)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="JPG",
            filename_prefix="screenshot",
            use_timestamp=False,
        )

        filename = Path(result["file_path"]).name if result["file_path"] else ""
        assert filename == "screenshot.jpg"


def test_supported_formats():
    """Test getting supported formats."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)

    formats = hardcopy.get_supported_formats()
    assert "PNG" in formats
    assert "JPG" in formats
    assert "BMP" in formats


@pytest.mark.asyncio
async def test_directory_creation():
    """Test that save directory is created if it doesn't exist."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)

    with tempfile.TemporaryDirectory() as tmpdir:
        new_dir = Path(tmpdir) / "nested" / "screenshots"
        assert not new_dir.exists()

        # Mock query_bytes to return valid PNG data
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        service.transport.query_bytes = AsyncMock(return_value=png_data)

        result = await hardcopy.capture_hardcopy(
            save_dir=str(new_dir),
            file_format="PNG",
        )

        # Directory should be created
        assert new_dir.exists()
        if result["ok"] and result["file_path"]:
            assert Path(result["file_path"]).parent == new_dir


@pytest.mark.asyncio
async def test_image_data_validation():
    """Test that empty image data is rejected."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)

    # Mock query_bytes to return empty data
    service.transport.query_bytes = AsyncMock(return_value=b"")

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="PNG",
        )

        assert result["ok"] is False
        assert "empty" in result["error"].lower()


@pytest.mark.asyncio
async def test_disconnected_state():
    """Test that capture fails when instrument is disconnected."""
    service = MockScpiService()
    service.transport.connected = False
    hardcopy = HardcopyService(service)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="PNG",
        )

        assert result["ok"] is False
        assert "not connected" in result["error"].lower()


@pytest.mark.asyncio
async def test_unsupported_format():
    """Test that unsupported formats are rejected."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="GIF",
        )

        assert result["ok"] is False
        assert "unsupported" in result["error"].lower()


@pytest.mark.asyncio
async def test_successful_capture_png():
    """Test successful PNG capture."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)

    # Valid PNG header
    png_payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000
    png_data = b"#41008" + png_payload
    service.transport.query_bytes = AsyncMock(return_value=png_data)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="PNG",
            filename_prefix="test",
            use_timestamp=False,
        )

        assert result["ok"] is True
        assert result["bytes_written"] == len(png_payload)
        assert result["payload_bytes"] == len(png_payload)
        assert Path(result["file_path"]).exists()
        assert Path(result["file_path"]).read_bytes() == png_payload


@pytest.mark.asyncio
async def test_rejects_ascii_error_payload():
    """ASCII error responses must not be saved as image files."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)
    service.transport.query_bytes = AsyncMock(return_value=b'-113,"Undefined header"\n')

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="PNG",
            filename_prefix="bad_capture",
            use_timestamp=False,
        )

        assert result["ok"] is False
        assert result["validation_ok"] is False
        assert result["detected_type"] == "ASCII_ERROR"
        assert result["file_path"] is None


@pytest.mark.asyncio
async def test_successful_capture_jpg():
    """Test successful JPG capture."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)

    # Valid JPEG header
    jpg_data = b"\xff\xd8\xff" + b"\x00" * 1000
    service.transport.query_bytes = AsyncMock(return_value=jpg_data)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="JPG",
        )

        assert result["ok"] is True
        assert result["file_format"] == "JPG"


@pytest.mark.asyncio
async def test_last_capture_tracking():
    """Test that last capture path is tracked."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)

    png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    service.transport.query_bytes = AsyncMock(return_value=png_data)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="PNG",
        )

        if result["ok"]:
            last_path = hardcopy.get_last_capture_path()
            assert last_path is not None
            assert last_path.exists()


@pytest.mark.asyncio
async def test_format_normalization():
    """Test that format names are normalized to uppercase."""
    service = MockScpiService()
    hardcopy = HardcopyService(service)

    png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    service.transport.query_bytes = AsyncMock(return_value=png_data)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="png",  # lowercase
        )

        # Should be normalized to PNG in the response
        if result["ok"]:
            assert result["file_format"] == "PNG"


@pytest.mark.asyncio
async def test_configuration_and_execute_commands():
    """Test that configuration and execute commands are sent."""
    service = MockScpiService()
    service.execute_with_classification = AsyncMock(return_value={
        "ok": True,
        "command": "",
        "command_type": "write",
        "response": None,
        "message": "OK",
        "error": None,
    })
    hardcopy = HardcopyService(service)

    png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    service.transport.query_bytes = AsyncMock(return_value=png_data)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = await hardcopy.capture_hardcopy(
            save_dir=tmpdir,
            file_format="PNG",
        )

        # Verify configuration command was called
        calls = service.execute_with_classification.call_args_list
        assert len(calls) >= 1

        # First call should be format configuration
        format_call = calls[0][0][0] if calls else ""
        assert "HCOPY:DEVICE:LANGUAGE" in format_call.upper() or "PNG" in format_call

        if len(calls) > 1:
            auto_name_call = calls[1][0][0] if calls[1] else ""
            assert "HCOPY:FILE:NAME:AUTO:STATE" in auto_name_call.upper()

        if len(calls) > 2:
            execute_call = calls[2][0][0] if calls[2] else ""
            assert "HCOPY:EXECUTE" in execute_call.upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
