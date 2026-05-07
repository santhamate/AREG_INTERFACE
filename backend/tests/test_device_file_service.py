"""Tests for DeviceFileService.

Covers:
- Filtering .osi files from catalog responses
- Parsing various SCPI catalog response formats
- Upload validation (extension, empty, no connection, remote path)
- SCPI query vs action command distinction
- Scenario state transitions
- Command timeout behaviour in ScpiService
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile

from backend.app.core.device_file_service import DeviceFileService, DeviceOsiFile, UploadResult
from backend.app.core.scpi_service import ScpiService


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def make_mock_scpi(connected: bool = True) -> ScpiService:
    """Create a ScpiService with a mocked transport."""
    svc = ScpiService.__new__(ScpiService)
    svc.settings = MagicMock()
    svc.settings.command_timeout_ms = 5000
    transport = MagicMock()
    transport.connected = connected
    svc.transport = transport
    svc.transport_name = "mock"
    svc.host = "127.0.0.1"
    svc.port = 5025
    svc.protocol = "socket"
    return svc


# ---------------------------------------------------------------------------
# 1. Filtering .osi files
# ---------------------------------------------------------------------------

class TestOsiFileFiltering:
    """Ensure only .osi files are returned from catalog responses."""

    def test_filters_osi_extension(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"scenario.osi,ASC,1024","readme.txt,ASC,512","calib.dat,ASC,256"'
        files = svc._parse_catalog_response(resp, "/osi")
        names = [f.name for f in files]
        assert "scenario.osi" in names
        assert "readme.txt" not in names
        assert "calib.dat" not in names

    def test_case_insensitive_extension(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"UPPER.OSI,ASC,500","lower.osi,ASC,200","Mixed.Osi,ASC,300"'
        files = svc._parse_catalog_response(resp, "/osi")
        assert len(files) == 3

    def test_empty_response_returns_empty(self):
        svc = DeviceFileService(make_mock_scpi())
        assert svc._parse_catalog_response("", "/osi") == []

    def test_no_osi_files_in_response(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"log.txt,ASC,100","config.ini,ASC,50"'
        files = svc._parse_catalog_response(resp, "/osi")
        assert files == []

    def test_only_osi_files_returned(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"a.osi,ASC,100","b.osi,ASC,200","c.txt,ASC,50"'
        files = svc._parse_catalog_response(resp, "/osi")
        assert len(files) == 2


# ---------------------------------------------------------------------------
# 2. Parsing catalog response formats
# ---------------------------------------------------------------------------

class TestCatalogResponseParsing:
    """Parse various SCPI catalog response formats."""

    def test_areg_compact_format(self):
        """AREG format: "name,type,size" entries."""
        svc = DeviceFileService(make_mock_scpi())
        resp = '"target.osi,ASC,4096","sweep.osi,ASC,8192"'
        files = svc._parse_catalog_response(resp, "/osi")
        assert len(files) == 2
        assert files[0].name == "target.osi"
        assert files[0].size_bytes == 4096
        assert files[0].path == "/osi/target.osi"

    def test_mmemory_standard_format_with_free_total(self):
        """MMEMory:CATalog? prepends a free/total entry – should be skipped."""
        svc = DeviceFileService(make_mock_scpi())
        # First entry is free/total (no .osi suffix → filtered out)
        resp = '"10000000,20000000","scenario.osi,ASC,1024"'
        files = svc._parse_catalog_response(resp, "/mass_storage")
        assert len(files) == 1
        assert files[0].name == "scenario.osi"

    def test_newline_separated_format(self):
        """Some instruments return newline-separated filenames."""
        svc = DeviceFileService(make_mock_scpi())
        resp = "alpha.osi\nbeta.osi\ngamma.txt"
        files = svc._parse_catalog_response(resp, "/osi")
        names = [f.name for f in files]
        assert "alpha.osi" in names
        assert "beta.osi" in names
        assert "gamma.txt" not in names

    def test_size_bytes_parsed_correctly(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"bigfile.osi,ASC,123456"'
        files = svc._parse_catalog_response(resp, "/osi")
        assert files[0].size_bytes == 123456

    def test_missing_size_returns_none(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"nosize.osi"'
        files = svc._parse_catalog_response(resp, "/osi")
        assert files[0].size_bytes is None

    def test_path_construction(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"demo.osi,ASC,512"'
        files = svc._parse_catalog_response(resp, "/areg/scenarios")
        assert files[0].path == "/areg/scenarios/demo.osi"

    def test_trailing_slash_in_dir(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"demo.osi,ASC,512"'
        files = svc._parse_catalog_response(resp, "/osi/")
        assert files[0].path == "/osi/demo.osi"  # No double slash


# ---------------------------------------------------------------------------
# 3. Upload validation
# ---------------------------------------------------------------------------

class TestUploadValidation:
    """Validate inputs before upload."""

    @pytest.mark.asyncio
    async def test_rejects_non_osi_extension(self, tmp_path: Path):
        svc = DeviceFileService(make_mock_scpi())
        f = tmp_path / "file.txt"
        f.write_bytes(b"data")
        result = await svc.upload_osi_file(str(f), "/osi/file.txt")
        assert result.ok is False
        assert ".osi" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_rejects_missing_local_file(self):
        svc = DeviceFileService(make_mock_scpi())
        result = await svc.upload_osi_file("/tmp/nonexistent.osi", "/osi/nonexistent.osi")
        assert result.ok is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_rejects_empty_file(self, tmp_path: Path):
        svc = DeviceFileService(make_mock_scpi())
        f = tmp_path / "empty.osi"
        f.write_bytes(b"")
        result = await svc.upload_osi_file(str(f), "/osi/empty.osi")
        assert result.ok is False
        assert "empty" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_rejects_when_not_connected(self, tmp_path: Path):
        svc = DeviceFileService(make_mock_scpi(connected=False))
        f = tmp_path / "test.osi"
        f.write_bytes(b"\x00" * 100)
        result = await svc.upload_osi_file(str(f), "/osi/test.osi")
        assert result.ok is False
        assert "not connected" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_rejects_remote_path_without_osi_extension(self, tmp_path: Path):
        svc = DeviceFileService(make_mock_scpi())
        f = tmp_path / "test.osi"
        f.write_bytes(b"\x00" * 100)
        result = await svc.upload_osi_file(str(f), "/osi/test.txt")
        assert result.ok is False
        assert ".osi" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_rejects_empty_remote_path(self, tmp_path: Path):
        svc = DeviceFileService(make_mock_scpi())
        f = tmp_path / "test.osi"
        f.write_bytes(b"\x00" * 100)
        result = await svc.upload_osi_file(str(f), "")
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_successful_upload(self, tmp_path: Path):
        scpi = make_mock_scpi()
        scpi.upload_binary_file = AsyncMock(return_value={"ok": True, "bytes_transferred": 100, "error": None})
        svc = DeviceFileService(scpi)
        f = tmp_path / "valid.osi"
        f.write_bytes(b"\x00" * 100)
        result = await svc.upload_osi_file(str(f), "/osi/valid.osi")
        assert result.ok is True
        assert result.bytes_transferred == 100

    @pytest.mark.asyncio
    async def test_upload_clears_cache_on_success(self, tmp_path: Path):
        scpi = make_mock_scpi()
        scpi.upload_binary_file = AsyncMock(return_value={"ok": True, "bytes_transferred": 50, "error": None})
        svc = DeviceFileService(scpi)
        # Pre-populate cache
        svc._cached_files = [DeviceOsiFile(name="old.osi", path="/osi/old.osi")]
        f = tmp_path / "new.osi"
        f.write_bytes(b"\x00" * 50)
        await svc.upload_osi_file(str(f), "/osi/new.osi")
        assert svc._cached_files == []  # Cache cleared


# ---------------------------------------------------------------------------
# 4. SCPI query vs action command distinction
# ---------------------------------------------------------------------------

class TestScpiQueryVsAction:
    """Ensure the service correctly distinguishes queries from write commands."""

    @pytest.mark.asyncio
    async def test_query_command_expects_response(self):
        scpi = ScpiService.__new__(ScpiService)
        scpi.settings = MagicMock()
        scpi.settings.command_timeout_ms = 1000
        transport = MagicMock()
        transport.connected = True
        transport.send = AsyncMock(return_value="IDN_RESPONSE")
        scpi.transport = transport
        result = await scpi.execute_with_classification("*IDN?")
        assert result["command_type"] == "query"
        assert result["ok"] is True
        transport.send.assert_called_once()
        call_args = transport.send.call_args
        assert call_args[1]["expect_response"] is True

    @pytest.mark.asyncio
    async def test_write_command_no_response(self):
        scpi = ScpiService.__new__(ScpiService)
        scpi.settings = MagicMock()
        scpi.settings.command_timeout_ms = 1000
        transport = MagicMock()
        transport.connected = True
        transport.send = AsyncMock(return_value=None)
        scpi.transport = transport
        result = await scpi.execute_with_classification("SOURce1:AREGenerator:SCENario:STARt")
        assert result["command_type"] == "write"
        assert result["ok"] is True
        call_args = transport.send.call_args
        assert call_args[1]["expect_response"] is False

    @pytest.mark.asyncio
    async def test_empty_command_returns_error(self):
        scpi = ScpiService.__new__(ScpiService)
        scpi.settings = MagicMock()
        scpi.settings.command_timeout_ms = 1000
        transport = MagicMock()
        transport.connected = True
        scpi.transport = transport
        result = await scpi.execute_with_classification("   ")
        assert result["ok"] is False
        assert result["command_type"] == "empty"

    @pytest.mark.asyncio
    async def test_scpi_state_query_is_query(self):
        """SOURce1:AREGenerator:SCENario:STATe? ends with ? so must be a query."""
        scpi = ScpiService.__new__(ScpiService)
        scpi.settings = MagicMock()
        scpi.settings.command_timeout_ms = 1000
        transport = MagicMock()
        transport.connected = True
        transport.send = AsyncMock(return_value="RUN")
        scpi.transport = transport
        result = await scpi.execute_with_classification("SOURce1:AREGenerator:SCENario:STATe?")
        assert result["command_type"] == "query"
        call_args = transport.send.call_args
        assert call_args[1]["expect_response"] is True

    @pytest.mark.asyncio
    async def test_mmemory_catalog_query_is_query(self):
        scpi = ScpiService.__new__(ScpiService)
        scpi.settings = MagicMock()
        scpi.settings.command_timeout_ms = 1000
        transport = MagicMock()
        transport.connected = True
        transport.send = AsyncMock(return_value='"file.osi,ASC,512"')
        scpi.transport = transport
        result = await scpi.execute_with_classification(':MMEMory:CATalog? "/osi"')
        assert result["command_type"] == "query"
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# 5. Scenario selection state
# ---------------------------------------------------------------------------

class TestScenarioPlayerState:
    """Scenario player state transitions."""

    @pytest.mark.asyncio
    async def test_select_scenario_sets_name(self):
        from backend.app.core.scenario_player import ScenarioPlayerService
        player = ScenarioPlayerService(make_mock_scpi())
        ok, _ = await player.select_scenario("/osi/target.osi")
        assert ok
        assert player.selected_scenario == "/osi/target.osi"

    @pytest.mark.asyncio
    async def test_load_sends_scpi_command(self):
        from backend.app.core.scenario_player import ScenarioPlayerService
        scpi = make_mock_scpi()
        scpi.execute_with_classification = AsyncMock(return_value={
            "ok": True, "command": 'SOURce1:AREGenerator:SCENario:FILE "/osi/t.osi"',
            "command_type": "write", "response": None, "message": "Command sent", "error": None,
        })
        player = ScenarioPlayerService(scpi)
        ok, msg = await player.load_scenario("/osi/t.osi")
        assert ok
        assert player.current_playback_state == "loaded"
        scpi.execute_with_classification.assert_called_once()
        call_cmd = scpi.execute_with_classification.call_args[0][0]
        assert "/osi/t.osi" in call_cmd

    @pytest.mark.asyncio
    async def test_play_updates_state_on_success(self):
        from backend.app.core.scenario_player import ScenarioPlayerService
        scpi = make_mock_scpi()
        scpi.execute_with_classification = AsyncMock(return_value={
            "ok": True, "command": "SOURce1:AREGenerator:SCENario:STARt",
            "command_type": "write", "response": None, "message": "Command sent", "error": None,
        })
        player = ScenarioPlayerService(scpi)
        player.selected_scenario = "/osi/t.osi"
        player.current_playback_state = "loaded"
        player.synced_to_instrument = True
        ok, _ = await player.play()
        assert ok
        assert player.current_playback_state == "playing"

    @pytest.mark.asyncio
    async def test_stop_updates_state_on_success(self):
        from backend.app.core.scenario_player import ScenarioPlayerService
        scpi = make_mock_scpi()
        scpi.execute_with_classification = AsyncMock(return_value={
            "ok": True, "command": "SOURce1:AREGenerator:SCENario:STOP",
            "command_type": "write", "response": None, "message": "Command sent", "error": None,
        })
        player = ScenarioPlayerService(scpi)
        player.current_playback_state = "playing"
        ok, _ = await player.stop()
        assert ok
        assert player.current_playback_state == "stopped"


# ---------------------------------------------------------------------------
# 6. Command timeout behaviour
# ---------------------------------------------------------------------------

class TestCommandTimeout:
    """Verify that transport timeouts are mapped to error results, not exceptions."""

    @pytest.mark.asyncio
    async def test_query_timeout_returns_error_dict(self):
        from backend.app.core.hislip import ScpiTransportError
        scpi = ScpiService.__new__(ScpiService)
        scpi.settings = MagicMock()
        scpi.settings.command_timeout_ms = 500
        transport = MagicMock()
        transport.connected = True
        transport.send = AsyncMock(side_effect=ScpiTransportError("Command timeout: *IDN?"))
        scpi.transport = transport
        result = await scpi.execute_with_classification("*IDN?")
        assert result["ok"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_write_timeout_returns_error_dict(self):
        from backend.app.core.hislip import ScpiTransportError
        scpi = ScpiService.__new__(ScpiService)
        scpi.settings = MagicMock()
        scpi.settings.command_timeout_ms = 500
        transport = MagicMock()
        transport.connected = True
        transport.send = AsyncMock(side_effect=ScpiTransportError("Write timeout"))
        scpi.transport = transport
        result = await scpi.execute_with_classification("SOURce1:AREGenerator:SCENario:STARt")
        assert result["ok"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_upload_transport_error_returns_upload_result(self, tmp_path: Path):
        from backend.app.core.hislip import ScpiTransportError
        scpi = make_mock_scpi()
        scpi.upload_binary_file = AsyncMock(side_effect=ScpiTransportError("Connection lost"))
        svc = DeviceFileService(scpi)
        f = tmp_path / "t.osi"
        f.write_bytes(b"\x00" * 64)
        result = await svc.upload_osi_file(str(f), "/osi/t.osi")
        assert result.ok is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# 7. Scan with no connection
# ---------------------------------------------------------------------------

class TestScanNotConnected:
    @pytest.mark.asyncio
    async def test_scan_returns_error_when_disconnected(self):
        svc = DeviceFileService(make_mock_scpi(connected=False))
        files, error = await svc.scan_device_osi_files()
        assert files == []
        assert error is not None


# ---------------------------------------------------------------------------
# 8. Auto upload destination resolution
# ---------------------------------------------------------------------------

class TestUploadDestinationResolution:
    @pytest.mark.asyncio
    async def test_resolve_upload_remote_path_prefers_usb_directory(self):
        svc = DeviceFileService(make_mock_scpi())

        async def fake_discover():
            return (["/sdcard", "/usb1", "/mass_storage"], None)

        svc.discover_device_directories = fake_discover  # type: ignore[method-assign]

        remote_path, error = await svc.resolve_upload_remote_path("scenario.osi")
        assert error is None
        assert remote_path == "/usb1/scenario.osi"

    @pytest.mark.asyncio
    async def test_resolve_upload_remote_path_uses_preferred_when_reachable(self):
        svc = DeviceFileService(make_mock_scpi())

        async def fake_is_reachable(directory: str) -> bool:
            return directory == "/custom_usb"

        svc._is_directory_reachable = fake_is_reachable  # type: ignore[method-assign]

        remote_path, error = await svc.resolve_upload_remote_path(
            filename="scenario.osi",
            preferred_directory="/custom_usb",
        )
        assert error is None
        assert remote_path == "/custom_usb/scenario.osi"

    @pytest.mark.asyncio
    async def test_resolve_upload_remote_path_rejects_non_osi_filename(self):
        svc = DeviceFileService(make_mock_scpi())
        remote_path, error = await svc.resolve_upload_remote_path("scenario.txt")
        assert remote_path is None
        assert error is not None
        assert ".osi" in error

    @pytest.mark.asyncio
    async def test_scan_uses_cache_when_available(self):
        scpi = make_mock_scpi()
        svc = DeviceFileService(scpi)
        svc._cached_files = [DeviceOsiFile(name="cached.osi", path="/osi/cached.osi")]
        files, error = await svc.scan_device_osi_files(force_refresh=False)
        assert len(files) == 1
        assert files[0].name == "cached.osi"

    @pytest.mark.asyncio
    async def test_scan_force_refresh_bypasses_cache(self):
        scpi = make_mock_scpi()
        scpi.execute_with_classification = AsyncMock(return_value={
            "ok": True, "command_type": "query",
            "response": '"fresh.osi,ASC,100"', "error": None,
        })
        svc = DeviceFileService(scpi)
        svc._cached_files = [DeviceOsiFile(name="stale.osi", path="/osi/stale.osi")]
        files, _ = await svc.scan_device_osi_files(force_refresh=True)
        names = [f.name for f in files]
        assert "fresh.osi" in names


# ---------------------------------------------------------------------------
# 8. Directory discovery / SD card visibility
# ---------------------------------------------------------------------------

class TestDirectoryDiscovery:
    def test_extract_directories_from_catalog_response(self):
        svc = DeviceFileService(make_mock_scpi())
        resp = '"sdcard,DIR,0","osi,DIR,0","scenario.osi,ASC,120"'
        dirs = svc._extract_directories_from_catalog_response(resp, base_dir="/")
        assert "/sdcard" in dirs
        assert "/osi" in dirs
        assert "/scenario.osi" not in dirs

    @pytest.mark.asyncio
    async def test_discover_device_directories_prioritizes_sd_paths(self):
        scpi = make_mock_scpi()

        async def fake_exec(command: str, timeout_ms: int | None = None):
            if 'CATalog? "/"' in command:
                return {
                    "ok": True,
                    "response": '"sdcard,DIR,0","osi,DIR,0"',
                    "command_type": "query",
                    "error": None,
                }
            if 'CATalog? "/sdcard"' in command or 'CATalog? "/osi"' in command:
                return {
                    "ok": True,
                    "response": '"demo.osi,ASC,100"',
                    "command_type": "query",
                    "error": None,
                }
            return {
                "ok": False,
                "response": None,
                "command_type": "query",
                "error": "not found",
            }

        scpi.execute_with_classification = AsyncMock(side_effect=fake_exec)
        svc = DeviceFileService(scpi)

        dirs, error = await svc.discover_device_directories()
        assert error is None
        assert "/sdcard" in dirs
        assert "/osi" in dirs
        assert dirs.index("/sdcard") < dirs.index("/osi")

    @pytest.mark.asyncio
    async def test_discover_device_directories_not_connected(self):
        svc = DeviceFileService(make_mock_scpi(connected=False))
        dirs, error = await svc.discover_device_directories()
        assert dirs == []
        assert error is not None
        assert "not connected" in error.lower()


class TestUploadPathCompatibility:
    def test_build_remote_path_candidates_for_usb(self):
        candidates = DeviceFileService._build_remote_path_candidates("/usb/demo.osi")
        assert "/usb/demo.osi" in candidates
        assert "USB:/demo.osi" in candidates

    @pytest.mark.asyncio
    async def test_upload_osi_bytes_retries_on_string_data_not_allowed(self):
        scpi = make_mock_scpi()

        async def fake_upload(remote_path: str, data: bytes, timeout_ms: int | None = None):
            if remote_path.startswith("/usb/"):
                return {"ok": False, "bytes_transferred": 0, "error": 'String data "/usb" not allowed'}
            if remote_path.startswith("USB:"):
                return {"ok": True, "bytes_transferred": len(data), "error": None}
            return {"ok": False, "bytes_transferred": 0, "error": "Unsupported path"}

        scpi.upload_binary_file = AsyncMock(side_effect=fake_upload)
        svc = DeviceFileService(scpi)

        result = await svc.upload_osi_bytes(b"\x00" * 32, "/usb/test.osi")
        assert result.ok is True
        assert result.remote_path is not None
        assert result.remote_path.startswith("USB:")

    @pytest.mark.asyncio
    async def test_upload_osi_bytes_media_protected_message(self):
        scpi = make_mock_scpi()
        scpi.upload_binary_file = AsyncMock(return_value={
            "ok": False,
            "bytes_transferred": 0,
            "error": "Media protected",
        })
        svc = DeviceFileService(scpi)

        result = await svc.upload_osi_bytes(b"\x00" * 64, "/sdcard/test.osi")
        assert result.ok is False
        assert result.error is not None
        assert "write-protected" in result.error.lower()
