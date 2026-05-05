from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse

from backend.app.core.catalog import catalog_summary, refresh_catalog_cache
from backend.app.core.areg_controller import AregSocketController
from backend.app.core.catalog_ingest import CatalogIngestor
from backend.app.core.command_registry import CommandRegistryService
from backend.app.core.scenario_compiler import ScenarioCompileError, ScenarioCompiler
from backend.app.core.scpi_service import ScpiService
from backend.app.core.scenario_player import ScenarioPlayerService
from backend.app.core.hardcopy_service import HardcopyService
from backend.app.core.scenario_generator_service import ScenarioGeneratorService
from backend.app.core.device_file_service import DeviceFileService
from backend.app.core.file_transfer_manager import AregFileTransferService, TransferConfig
from backend.app.core.scenario_inspector_service import ScenarioInspectorService
from backend.app.models.areg import (
    AregCommandLibraryResponse,
    AregCommandStep,
    AregStaticObjectRequest,
    AregStaticObjectResponse,
)
from backend.app.models.scenario import (
    CommandLogResponse,
    CommandLogEntry,
    ScanScenariosRequest,
    ScanScenariosResponse,
    ScenarioFile,
    ScenarioPlaybackStatus,
    ScenarioPlayerAction,
    ScenarioPlayerState,
    ReplayModeRequest,
    ScenarioInspectorDecodeRequest,
    ScenarioDecodeResultModel,
    ScenarioInspectorClearCacheResponse,
    SelectScenarioRequest,
    CompileScenarioResponse,
    ScenarioGraph,
)
from backend.app.models.scpi import (
    CommandRequest,
    CommandResponse,
    ConnectRequest,
    HardcopyRequest,
    HardcopyResponse,
    RangeSweepRequest,
    ConstantObjectRequest,
    MultiObjectRequest,
    AzimuthSweepRequest,
    ConstantEchoPowerRequest,
    GenerationResponse,
    GeneratorStatusResponse,
    SimulationOverviewResponse,
    ScenarioValidationRequest,
    ScenarioValidationResponse,
    ScenarioTransferRequest,
    ScenarioTransferResponse,
    SessionState,
    ScanDeviceFilesRequest,
    ScanDeviceFilesResponse,
    DiscoverDeviceDirectoriesResponse,
    DeviceOsiFileModel,
    UploadOsiFileRequest,
    UploadOsiFileResponse,
    FileTransferConfigModel,
    FileTransferOperationResponse,
    FileTransferListRequest,
    FileTransferListResponse,
    FileTransferRemoteFileModel,
    FileTransferUploadRequest,
    FileTransferDownloadRequest,
    ScenarioWorkspaceDownloadRequest,
    ScenarioWorkspaceDownloadResponse,
    FileTransferRenameRequest,
    FileTransferDeleteRequest,
    FileTransferMkdirRequest,
    FileTransferPreflightRequest,
    FileTransferPreflightResponse,
    FileTransferChecklistItemModel,
    FileTransferResultResponse,
    FileTransferHelpResponse,
)

router = APIRouter()
service = ScpiService()
compiler = ScenarioCompiler()
areg_controller = AregSocketController()
command_registry = CommandRegistryService()
scenario_player_service = ScenarioPlayerService(service, command_registry=command_registry)
hardcopy_service = HardcopyService(service)
generator_service = ScenarioGeneratorService()
device_file_service = DeviceFileService(service)
file_transfer_service = AregFileTransferService()
scenario_inspector_service = ScenarioInspectorService(
    project_root=Path(__file__).resolve().parents[3],
    transfer_service=file_transfer_service,
)


def _to_transfer_config(model: FileTransferConfigModel) -> TransferConfig:
    return TransferConfig(
        protocol=model.protocol,
        host=model.host,
        username=model.username,
        password=model.password,
        remote_dir=model.remote_dir,
        mapped_root=model.mapped_root,
        timeout_s=model.timeout_s,
        passive_mode=model.passive_mode,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/catalog/summary")
async def get_catalog_summary() -> dict[str, object]:
    return catalog_summary()


@router.get("/areg/library", response_model=AregCommandLibraryResponse)
async def get_command_library() -> AregCommandLibraryResponse:
    return AregCommandLibraryResponse.model_validate(command_registry.command_library())


@router.get("/commands/registry")
async def get_command_registry() -> dict[str, object]:
    return command_registry.command_library()


@router.get("/commands/lookup")
async def lookup_command(command: str) -> dict[str, object]:
    classification = service.classify_command(command)
    result = command_registry.lookup(command)
    return {
        "command": command,
        "command_type": classification.command_type,
        "expect_response": classification.expect_response,
        **result,
    }


@router.post("/catalog/ingest")
async def ingest_catalog() -> dict[str, object]:
    project_root = Path(__file__).resolve().parents[3]
    manuals = [
        project_root / "Remote_Control_SCPI_GettingStarted_en_04.pdf",
        project_root / "AREG_UserManual_en_08.pdf",
    ]
    missing = [str(path) for path in manuals if not path.exists()]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing manuals: {', '.join(missing)}")

    ingestor = CatalogIngestor(project_root)
    result = ingestor.ingest_manuals(manuals)
    refresh_catalog_cache()
    return result


@router.get("/session", response_model=SessionState)
async def get_session_state() -> SessionState:
    state = service.session_state()
    return SessionState.model_validate(state.__dict__)


@router.post("/session/connect", response_model=SessionState)
async def connect_session(payload: ConnectRequest) -> SessionState:
    state = await service.connect(host=payload.host, port=payload.port, protocol=payload.protocol)
    return SessionState.model_validate(state.__dict__)


@router.post("/session/disconnect", response_model=SessionState)
async def disconnect_session() -> SessionState:
    state = await service.disconnect()
    return SessionState.model_validate(state.__dict__)


@router.get("/simulation/overview", response_model=SimulationOverviewResponse)
async def simulation_overview() -> SimulationOverviewResponse:
    """Aggregate snapshot of AREG800A simulation state for the overview panel."""
    from datetime import datetime

    session = service.session_state()
    cmd_logs = scenario_player_service.logger.get_all()
    gen_logs = generator_service.get_generation_logs(limit=1)
    last_cmd = cmd_logs[-1] if cmd_logs else None
    last_gen = gen_logs[0] if gen_logs else None
    total_gen = len(generator_service.state.generation_logs)

    return SimulationOverviewResponse(
        connected=session.connected,
        host=session.host,
        port=session.port,
        transport=session.transport,
        playback_state=str(scenario_player_service.current_playback_state),
        current_scenario=scenario_player_service.selected_scenario,
        replay_mode=str(scenario_player_service.current_replay_mode),
        total_generated=total_gen,
        last_generated_file=last_gen.get("output_filename") if last_gen else None,
        last_generated_template=last_gen.get("template_type") if last_gen else None,
        log_entry_count=len(cmd_logs),
        last_command=last_cmd.command if last_cmd else None,
        last_command_ok=last_cmd.ok if last_cmd else None,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )


@router.post("/scpi/send", response_model=CommandResponse)
async def send_scpi_command(payload: CommandRequest) -> CommandResponse:
    try:
        result = await service.execute_with_classification(
            command=payload.command,
            timeout_ms=payload.timeout_ms,
        )
        state = service.session_state()
        return CommandResponse(
            command=result["command"],
            command_type=result["command_type"],
            response=result.get("response"),
            message=result.get("message"),
            ok=result["ok"],
            transport=state.transport,
            error=result.get("error"),
        )
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/areg/static-object/setup", response_model=AregStaticObjectResponse)
async def run_static_object_setup(payload: AregStaticObjectRequest) -> AregStaticObjectResponse:
    try:
        host = payload.host or areg_controller.settings.socket_host
        steps, errors = await areg_controller.run_static_object_setup(
            host=host,
            port=payload.port,
            source_hw=payload.source_hw,
            object_index=payload.object_index,
            range_value=payload.range_value,
            attenuation=payload.attenuation,
            rcs=payload.rcs,
            doppler_speed=payload.doppler_speed,
            doppler_frequency=payload.doppler_frequency,
            angle_horizontal=payload.angle_horizontal,
        )
        return AregStaticObjectResponse(
            host=host,
            port=payload.port,
            source_hw=payload.source_hw,
            object_index=payload.object_index,
            steps=[AregCommandStep(command=step.command, response=step.response, note=step.note) for step in steps],
            errors=errors,
        )
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/hardcopy/capture", response_model=HardcopyResponse)
async def capture_hardcopy(payload: HardcopyRequest) -> HardcopyResponse:
    """Capture a screenshot from the instrument and save it locally.
    
    Supports multiple formats (PNG, JPG, BMP) with automatic filename generation
    including optional timestamp. Handles binary image data transfer.
    """
    try:
        # Support legacy save_path parameter for backward compatibility
        save_dir = payload.save_dir
        if payload.save_path and not save_dir:
            # If legacy save_path is provided, use it as save_dir
            save_dir = str(Path(payload.save_path).parent)

        result = await hardcopy_service.capture_hardcopy(
            save_dir=save_dir,
            file_format=payload.file_format,
            filename_prefix=payload.filename_prefix,
            use_timestamp=payload.use_timestamp,
            timeout_ms=payload.timeout_ms,
        )

        return HardcopyResponse(
            ok=result["ok"],
            file_path=result["file_path"],
            file_format=result["file_format"],
            bytes_written=result["bytes_written"],
            payload_bytes=result.get("payload_bytes", 0),
            detected_type=result.get("detected_type"),
            validation_ok=result.get("validation_ok", False),
            diagnostics=result.get("diagnostics"),
            log=result.get("log", []),
            transport=service.session_state().transport,
            message=result.get("message"),
            error=result.get("error"),
        )
    except ValueError as ex:
        return HardcopyResponse(
            ok=False,
            file_path=None,
            file_format=payload.file_format,
            bytes_written=0,
            payload_bytes=0,
            detected_type=None,
            validation_ok=False,
            diagnostics=None,
            log=[],
            transport=service.session_state().transport,
            message=None,
            error=str(ex),
        )
    except Exception as ex:
        return HardcopyResponse(
            ok=False,
            file_path=None,
            file_format=payload.file_format,
            bytes_written=0,
            payload_bytes=0,
            detected_type=None,
            validation_ok=False,
            diagnostics=None,
            log=[],
            transport=service.session_state().transport,
            message=None,
            error=f"Unexpected error: {str(ex)}",
        )


@router.get("/hardcopy/formats")
async def get_hardcopy_formats() -> dict[str, list[str]]:
    """Get list of supported hardcopy image formats."""
    return {"formats": hardcopy_service.get_supported_formats()}


@router.get("/hardcopy/last-capture")
async def get_last_hardcopy() -> dict[str, object]:
    """Get information about the last successfully captured screenshot."""
    last_path = hardcopy_service.get_last_capture_path()
    last_analysis = hardcopy_service.get_last_analysis() or {}
    if last_path and last_path.exists():
        stat = last_path.stat()
        return {
            "ok": True,
            "file_path": str(last_path),
            "file_size": stat.st_size,
            "modified_time": stat.st_mtime,
            "validation_ok": last_analysis.get("validation_ok", False),
            "detected_type": last_analysis.get("detected_type"),
            "diagnostics": last_analysis.get("diagnostics"),
        }
    return {
        "ok": False,
        "file_path": None,
        "file_size": 0,
        "modified_time": None,
        "validation_ok": last_analysis.get("validation_ok", False),
        "detected_type": last_analysis.get("detected_type"),
        "diagnostics": last_analysis.get("diagnostics"),
    }


@router.get("/hardcopy/analyze")
async def analyze_hardcopy(file_path: str | None = Query(default=None)) -> dict[str, object]:
    """Analyze the last or specified hardcopy file and return diagnostics."""
    return hardcopy_service.analyze_file(file_path)


@router.get("/hardcopy/content")
async def get_hardcopy_content(file_path: str = Query(...)) -> FileResponse:
    """Serve a locally saved hardcopy image for UI preview."""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Hardcopy file not found: {file_path}")

    suffix = path.suffix.lower()
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".bmp": "image/bmp",
    }.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=400, detail=f"Unsupported preview type: {suffix}")

    return FileResponse(path=path, media_type=media_type, filename=path.name)


@router.post("/hardcopy/open-file")
async def open_hardcopy_file(payload: dict[str, str]) -> dict[str, object]:
    """Open the captured file in the platform file browser."""
    file_path = payload.get("file_path")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required")

    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return {"ok": True, "file_path": str(path)}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


# ============================================================================
# Scenario Player Endpoints
# ============================================================================


@router.post("/scenario/scan", response_model=ScanScenariosResponse)
async def scan_scenarios(payload: ScanScenariosRequest) -> ScanScenariosResponse:
    """Scan for available scenarios: local ./scenarios/ directory + instrument (when connected)."""
    from backend.app.models.scenario import ScenarioFile
    import datetime

    try:
        # --- Local scan: always include .osi files from ./scenarios/ ---
        local_scenarios: list[ScenarioFile] = []
        local_dir = Path("scenarios")
        if local_dir.exists():
            for osi_file in sorted(local_dir.glob("*.osi")):
                stat = osi_file.stat()
                local_scenarios.append(ScenarioFile(
                    name=osi_file.name,
                    path=str(osi_file.resolve()),
                    extension=".osi",
                    size_bytes=stat.st_size,
                    modified_time=datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    is_loadable=True,
                ))

        # --- Instrument scan: only when connected ---
        instrument_scenarios: list[ScenarioFile] = []
        instrument_error: str | None = None
        if scenario_player_service.scpi_service.transport.connected:
            instrument_scenarios, instrument_error = await scenario_player_service.scan_scenarios(
                force_refresh=payload.force_refresh
            )

        # Merge: local first, then instrument (deduplicate by name)
        seen_names: set[str] = {s.name for s in local_scenarios}
        for s in instrument_scenarios:
            if s.name not in seen_names:
                local_scenarios.append(s)
                seen_names.add(s.name)

        all_scenarios = local_scenarios
        scenario_player_service.cached_scenarios = all_scenarios
        # Surface instrument error only if no local results either
        if instrument_error and not all_scenarios:
            return ScanScenariosResponse(ok=False, scenarios=[], total_count=0, error=instrument_error)

        return ScanScenariosResponse(ok=True, scenarios=all_scenarios, total_count=len(all_scenarios))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/select")
async def select_scenario(payload: SelectScenarioRequest) -> dict[str, object]:
    """Select a scenario."""
    try:
        success, message = await scenario_player_service.select_scenario(payload.scenario_name)
        return {
            "ok": success,
            "message": message,
            "selected_scenario": payload.scenario_name if success else None,
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/load")
async def load_scenario(payload: SelectScenarioRequest) -> dict[str, object]:
    """Load a selected scenario."""
    try:
        success, message = await scenario_player_service.load_scenario(
            payload.scenario_name,
            replay_mode=payload.replay_mode,
        )
        return {"ok": success, "message": message}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/replay-mode")
async def set_scenario_replay_mode(payload: ReplayModeRequest) -> dict[str, object]:
    """Set replay mode (SINGle/LOOP)."""
    try:
        success, message = await scenario_player_service.set_scenario_replay_mode(payload.mode)
        return {
            "ok": success,
            "message": message,
            "replay_mode": scenario_player_service.current_replay_mode,
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.get("/scenario/replay-mode")
async def get_scenario_replay_mode() -> dict[str, object]:
    """Query replay mode from instrument."""
    try:
        mode = await scenario_player_service.query_scenario_replay_mode()
        return {"ok": True, "replay_mode": mode}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/inspector/decode-selected", response_model=ScenarioDecodeResultModel)
async def decode_selected_scenario(payload: ScenarioInspectorDecodeRequest) -> ScenarioDecodeResultModel:
    result = scenario_inspector_service.decode(
        remote_path=payload.remote_path,
        local_path=payload.local_path,
        transfer_config_payload=payload.transfer_config,
        force_redownload=payload.force_redownload,
        loaded_scenario_path=scenario_player_service.selected_scenario,
    )
    return ScenarioDecodeResultModel.model_validate(result)


@router.post("/scenario/inspector/decode-loaded", response_model=ScenarioDecodeResultModel)
async def decode_loaded_scenario(payload: ScenarioInspectorDecodeRequest) -> ScenarioDecodeResultModel:
    result = scenario_inspector_service.decode(
        remote_path=scenario_player_service.selected_scenario,
        local_path=payload.local_path,
        transfer_config_payload=payload.transfer_config,
        force_redownload=payload.force_redownload,
        loaded_scenario_path=scenario_player_service.selected_scenario,
    )
    return ScenarioDecodeResultModel.model_validate(result)


@router.post("/scenario/inspector/clear-cache", response_model=ScenarioInspectorClearCacheResponse)
async def clear_scenario_inspector_cache() -> ScenarioInspectorClearCacheResponse:
    removed, error = scenario_inspector_service.clear_cache()
    return ScenarioInspectorClearCacheResponse(
        ok=error is None,
        removed_files=removed,
        cache_dir=str(scenario_inspector_service.cache_dir),
        error=error,
    )


@router.post("/scenario/play")
async def play_scenario() -> dict[str, object]:
    """Start scenario playback."""
    try:
        success, message = await scenario_player_service.play()
        return {"ok": success, "message": message}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/pause")
async def pause_scenario() -> dict[str, object]:
    """Pause scenario playback."""
    try:
        success, message = await scenario_player_service.pause()
        return {"ok": success, "message": message}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/stop")
async def stop_scenario() -> dict[str, object]:
    """Stop scenario playback."""
    try:
        success, message = await scenario_player_service.stop()
        return {"ok": success, "message": message}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/restart")
async def restart_scenario() -> dict[str, object]:
    """Restart scenario playback."""
    try:
        success, message = await scenario_player_service.restart()
        return {"ok": success, "message": message}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/next")
async def next_scenario() -> dict[str, object]:
    """Select next scenario."""
    try:
        success, message = await scenario_player_service.next_scenario()
        return {"ok": success, "message": message}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/previous")
async def previous_scenario() -> dict[str, object]:
    """Select previous scenario."""
    try:
        success, message = await scenario_player_service.previous_scenario()
        return {"ok": success, "message": message}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.get("/scenario/status", response_model=ScenarioPlaybackStatus)
async def get_scenario_status() -> ScenarioPlaybackStatus:
    """Get current scenario playback status."""
    try:
        return await scenario_player_service.refresh_playback_state()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.get("/scenario/log", response_model=CommandLogResponse)
async def get_command_log() -> CommandLogResponse:
    """Get SCPI command log."""
    try:
        entries = scenario_player_service.get_command_log()
        return CommandLogResponse(log_entries=entries, total_entries=len(entries))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/log/clear")
async def clear_command_log() -> dict[str, str]:
    """Clear SCPI command log."""
    try:
        scenario_player_service.clear_command_log()
        return {"ok": True, "message": "Log cleared"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenario/check-errors-config")
async def set_check_errors_after_write(payload: dict[str, bool]) -> dict[str, object]:
    """Enable/disable optional error checking after write commands."""
    try:
        enabled = payload.get("enabled", False)
        scenario_player_service.set_check_errors_after_write(enabled)
        return {"ok": True, "check_errors_enabled": enabled}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/scenarios/compile", response_model=CompileScenarioResponse)
async def compile_scenario(graph: ScenarioGraph) -> CompileScenarioResponse:
    try:
        return compiler.compile(graph)
    except ScenarioCompileError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


# ============================================================================
# Scenario Generator Endpoints
# ============================================================================


@router.get("/generator/status", response_model=GeneratorStatusResponse)
async def get_generator_status() -> GeneratorStatusResponse:
    """Get scenario generator status and OSI availability."""
    status = generator_service.get_status()
    return GeneratorStatusResponse(
        osi_available=status["osi_available"],
        osi_error=status["osi_error"],
        last_generated_file=status["last_generated_file"],
        last_preview=status["last_preview"],
    )


@router.post("/generator/range-sweep", response_model=GenerationResponse)
async def generate_range_sweep(payload: RangeSweepRequest) -> GenerationResponse:
    """Generate a range sweep scenario (single object moving toward/away from radar)."""
    try:
        result = generator_service.generate_range_sweep(
            output_dir=payload.output_dir,
            output_filename=payload.output_filename,
            sensor_id=payload.sensor_id,
            update_interval_s=payload.update_interval_s,
            start_range_m=payload.start_range_m,
            stop_range_m=payload.stop_range_m,
            radial_velocity_mps=payload.radial_velocity_mps,
            rcs_dbsm=payload.rcs_dbsm,
            azimuth_deg=payload.azimuth_deg,
            elevation_deg=payload.elevation_deg,
            scenario_name=payload.scenario_name,
        )
        return GenerationResponse(
            ok=result["ok"],
            file_path=result["file_path"],
            message_count=result["message_count"],
            duration_s=result["duration_s"],
            preview=result["preview"],
            error=result["error"],
        )
    except Exception as ex:
        return GenerationResponse(
            ok=False,
            file_path=None,
            message_count=0,
            duration_s=0.0,
            preview=None,
            error=str(ex),
        )


@router.post("/generator/constant-object", response_model=GenerationResponse)
async def generate_constant_object(payload: ConstantObjectRequest) -> GenerationResponse:
    """Generate a constant object scenario (stationary or constant-velocity object)."""
    try:
        result = generator_service.generate_constant_object(
            output_dir=payload.output_dir,
            output_filename=payload.output_filename,
            sensor_id=payload.sensor_id,
            duration_s=payload.duration_s,
            update_interval_s=payload.update_interval_s,
            range_m=payload.range_m,
            radial_velocity_mps=payload.radial_velocity_mps,
            rcs_dbsm=payload.rcs_dbsm,
            azimuth_deg=payload.azimuth_deg,
            elevation_deg=payload.elevation_deg,
            scenario_name=payload.scenario_name,
        )
        return GenerationResponse(
            ok=result["ok"],
            file_path=result["file_path"],
            message_count=result["message_count"],
            duration_s=result["duration_s"],
            preview=result["preview"],
            error=result["error"],
        )
    except Exception as ex:
        return GenerationResponse(
            ok=False,
            file_path=None,
            message_count=0,
            duration_s=0.0,
            preview=None,
            error=str(ex),
        )


@router.post("/generator/multi-object", response_model=GenerationResponse)
async def generate_multi_object(payload: MultiObjectRequest) -> GenerationResponse:
    """Generate a multi-object scenario with independent parameters per object."""
    try:
        objects = [obj.model_dump() for obj in payload.objects]
        result = generator_service.generate_multi_object(
            output_dir=payload.output_dir,
            output_filename=payload.output_filename,
            sensor_id=payload.sensor_id,
            update_interval_s=payload.update_interval_s,
            duration_s=payload.duration_s,
            objects=objects,
            scenario_name=payload.scenario_name,
        )
        return GenerationResponse(
            ok=result["ok"],
            file_path=result["file_path"],
            message_count=result["message_count"],
            duration_s=result["duration_s"],
            preview=result["preview"],
            error=result["error"],
        )
    except Exception as ex:
        return GenerationResponse(
            ok=False,
            file_path=None,
            message_count=0,
            duration_s=0.0,
            preview=None,
            error=str(ex),
        )


@router.post("/generator/azimuth-sweep", response_model=GenerationResponse)
async def generate_azimuth_sweep(payload: AzimuthSweepRequest) -> GenerationResponse:
    """Generate an azimuth sweep scenario (object rotating around radar)."""
    try:
        result = generator_service.generate_azimuth_sweep(
            output_dir=payload.output_dir,
            output_filename=payload.output_filename,
            sensor_id=payload.sensor_id,
            update_interval_s=payload.update_interval_s,
            duration_s=payload.duration_s,
            range_m=payload.range_m,
            start_azimuth_deg=payload.start_azimuth_deg,
            stop_azimuth_deg=payload.stop_azimuth_deg,
            radial_velocity_mps=payload.radial_velocity_mps,
            rcs_dbsm=payload.rcs_dbsm,
            elevation_deg=payload.elevation_deg,
            scenario_name=payload.scenario_name,
        )
        return GenerationResponse(
            ok=result["ok"],
            file_path=result["file_path"],
            message_count=result["message_count"],
            duration_s=result["duration_s"],
            preview=result["preview"],
            error=result["error"],
        )
    except Exception as ex:
        return GenerationResponse(
            ok=False,
            file_path=None,
            message_count=0,
            duration_s=0.0,
            preview=None,
            error=str(ex),
        )


@router.post("/generator/constant-echo-power", response_model=GenerationResponse)
async def generate_constant_echo_power(payload: ConstantEchoPowerRequest) -> GenerationResponse:
    """Generate a constant echo power scenario.

    RCS is compensated per OSI frame via the R⁴ radar range equation so that the
    simulated received echo power at the radar sensor remains constant throughout
    the approach:

        RCS(R) [dBsm] = ref_rcs_dbsm + 40 · log₁₀(R / ref_range_m)
    """
    try:
        result = generator_service.generate_constant_echo_power(
            output_dir=payload.output_dir,
            output_filename=payload.output_filename,
            sensor_id=payload.sensor_id,
            update_interval_s=payload.update_interval_s,
            start_range_m=payload.start_range_m,
            stop_range_m=payload.stop_range_m,
            radial_velocity_mps=payload.radial_velocity_mps,
            ref_rcs_dbsm=payload.ref_rcs_dbsm,
            ref_range_m=payload.ref_range_m,
            azimuth_deg=payload.azimuth_deg,
            elevation_deg=payload.elevation_deg,
            rcs_min_dbsm=payload.rcs_min_dbsm,
            rcs_max_dbsm=payload.rcs_max_dbsm,
            scenario_name=payload.scenario_name,
        )
        return GenerationResponse(
            ok=result["ok"],
            file_path=result["file_path"],
            message_count=result["message_count"],
            duration_s=result["duration_s"],
            preview=result["preview"],
            rcs_table=result.get("rcs_table"),
            error=result["error"],
        )
    except Exception as ex:
        return GenerationResponse(
            ok=False,
            file_path=None,
            message_count=0,
            duration_s=0.0,
            preview=None,
            rcs_table=None,
            error=str(ex),
        )


@router.get("/generator/logs")
async def get_generation_logs(limit: int = 50) -> dict[str, object]:
    """Get scenario generation logs (most recent first)."""
    logs = generator_service.get_generation_logs(limit=limit)
    return {"logs": logs, "total": len(logs)}


@router.post("/generator/validate", response_model=ScenarioValidationResponse)
async def validate_generated_scenario(payload: ScenarioValidationRequest) -> ScenarioValidationResponse:
    """Validate a generated .osi file and return framing/message metadata."""
    result = generator_service.validate_osi_file(file_path=payload.file_path)
    return ScenarioValidationResponse(
        ok=result["ok"],
        file_path=result["file_path"],
        exists=result["exists"],
        size_bytes=result["size_bytes"],
        message_count=result["message_count"],
        error=result["error"],
    )


@router.post("/generator/transfer", response_model=ScenarioTransferResponse)
async def transfer_generated_scenario(payload: ScenarioTransferRequest) -> ScenarioTransferResponse:
    """Transfer a generated scenario file using a configured transfer adapter."""
    result = generator_service.transfer_file(
        local_path=payload.local_path,
        remote_path=payload.remote_path,
        transfer_method=payload.transfer_method,
    )
    return ScenarioTransferResponse(
        ok=result["ok"],
        local_path=result["local_path"],
        remote_path=result["remote_path"],
        transfer_method=result["transfer_method"],
        bytes_transferred=result["bytes_transferred"],
        error=result["error"],
    )


@router.get("/generator/transfer-logs")
async def get_transfer_logs(limit: int = 50) -> dict[str, object]:
    """Get scenario transfer logs (most recent first)."""
    logs = generator_service.get_transfer_logs(limit=limit)
    return {"logs": logs, "total": len(logs)}


# ============================================================================
# Device File Management Endpoints
# ============================================================================


@router.post("/device/files/scan", response_model=ScanDeviceFilesResponse)
async def scan_device_files(payload: ScanDeviceFilesRequest) -> ScanDeviceFilesResponse:
    """Scan the connected device file system for .osi scenario files.

    Uses SCPI MMEMory:CATalog? (or AREG-specific catalog command) to list
    files in the target directory and filters to only .osi entries.
    """
    try:
        files, error = await device_file_service.scan_device_osi_files(
            directory=payload.directory,
            force_refresh=payload.force_refresh,
        )
        file_models = [
            DeviceOsiFileModel(
                name=f.name,
                path=f.path,
                size_bytes=f.size_bytes,
                modified_time=f.modified_time,
            )
            for f in files
        ]
        return ScanDeviceFilesResponse(
            ok=error is None,
            files=file_models,
            total_count=len(file_models),
            directory=payload.directory,
            error=error,
        )
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.get("/device/files/discover", response_model=DiscoverDeviceDirectoriesResponse)
async def discover_device_directories() -> DiscoverDeviceDirectoriesResponse:
    """Discover reachable scenario directories on the connected device."""
    try:
        directories, error = await device_file_service.discover_device_directories()
        return DiscoverDeviceDirectoriesResponse(
            ok=error is None,
            directories=directories,
            error=error,
        )
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.post("/device/files/upload", response_model=UploadOsiFileResponse)
async def upload_device_file(payload: UploadOsiFileRequest) -> UploadOsiFileResponse:
    """Upload a local .osi file to the connected device via SCPI MMEMory:DATA.

    Validates the local file and streams it to the device using an IEEE 488.2
    definite-length binary block.  Automatically refreshes the device file cache
    after a successful upload.
    """
    try:
        result = await device_file_service.upload_osi_file(
            local_path=payload.local_path,
            remote_path=payload.remote_path,
        )
        return UploadOsiFileResponse(
            ok=result.ok,
            local_path=payload.local_path,
            remote_path=result.remote_path or payload.remote_path,
            bytes_transferred=result.bytes_transferred,
            error=result.error,
        )
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


@router.get("/device/files/list", response_model=ScanDeviceFilesResponse)
async def list_device_files() -> ScanDeviceFilesResponse:
    """Return the cached device file list without issuing a new SCPI query."""
    files = device_file_service.get_cached_files()
    file_models = [
        DeviceOsiFileModel(
            name=f.name,
            path=f.path,
            size_bytes=f.size_bytes,
            modified_time=f.modified_time,
        )
        for f in files
    ]
    return ScanDeviceFilesResponse(
        ok=True,
        files=file_models,
        total_count=len(file_models),
    )


@router.post("/device/files/upload-browser", response_model=UploadOsiFileResponse)
async def upload_device_file_from_browser(
    file: UploadFile = File(...),
    remote_path: str = Form(...),
) -> UploadOsiFileResponse:
    """Upload a .osi file sent directly from the browser to the connected device.

    The browser sends the file as multipart/form-data.  The backend reads the
    bytes in memory and forwards them to the device via SCPI MMEMory:DATA.
    """
    try:
        filename = file.filename or "upload.osi"
        if not filename.lower().endswith(".osi"):
            return UploadOsiFileResponse(
                ok=False,
                local_path=filename,
                remote_path=remote_path,
                error="File must have a .osi extension",
            )
        if not service.transport.connected:
            return UploadOsiFileResponse(
                ok=False,
                local_path=filename,
                remote_path=remote_path,
                error="Device is not connected",
            )

        data = await file.read()
        if len(data) == 0:
            return UploadOsiFileResponse(
                ok=False,
                local_path=filename,
                remote_path=remote_path,
                error="Uploaded file is empty",
            )

        upload_result = await device_file_service.upload_osi_bytes(data=data, remote_path=remote_path)

        return UploadOsiFileResponse(
            ok=upload_result.ok,
            local_path=filename,
            remote_path=upload_result.remote_path or remote_path,
            bytes_transferred=upload_result.bytes_transferred,
            error=upload_result.error,
        )
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex


# ============================================================================
# File Transfer Manager Endpoints
# ============================================================================


@router.get("/file-transfer/help", response_model=FileTransferHelpResponse)
async def get_file_transfer_help() -> FileTransferHelpResponse:
    help_data = file_transfer_service.setup_help()
    return FileTransferHelpResponse(
        ftp=help_data.get("ftp", []),
        smb=help_data.get("smb", []),
        usb=help_data.get("usb", []),
    )


@router.post("/file-transfer/test", response_model=FileTransferOperationResponse)
async def test_file_transfer_connection(payload: FileTransferConfigModel) -> FileTransferOperationResponse:
    result = file_transfer_service.test_connection(_to_transfer_config(payload))
    return FileTransferOperationResponse(
        ok=result.ok,
        message=result.message,
        error=result.error,
        warnings=result.warnings or [],
        likely_causes=file_transfer_service._guess_likely_causes(result.error) if not result.ok else [],
    )


@router.post("/file-transfer/list", response_model=FileTransferListResponse)
async def list_remote_files(payload: FileTransferListRequest) -> FileTransferListResponse:
    files, op = file_transfer_service.list_files(
        config=_to_transfer_config(payload.config),
        remote_dir=payload.remote_dir,
        file_filter=payload.file_filter,
        custom_ext=payload.custom_ext,
    )
    return FileTransferListResponse(
        ok=op.ok,
        files=[
            FileTransferRemoteFileModel(
                name=f.name,
                remote_path=f.remote_path,
                size=f.size,
                modified_time=f.modified_time,
                extension=f.extension,
                is_directory=f.is_directory,
            )
            for f in files
        ],
        total_count=len(files),
        remote_dir=payload.remote_dir,
        message=op.message,
        error=op.error,
        warnings=op.warnings or [],
        likely_causes=file_transfer_service._guess_likely_causes(op.error) if not op.ok else [],
    )


@router.post("/file-transfer/upload", response_model=FileTransferResultResponse)
async def upload_file_transfer(payload: FileTransferUploadRequest) -> FileTransferResultResponse:
    result = file_transfer_service.upload_file(
        config=_to_transfer_config(payload.config),
        local_path=payload.local_path,
        remote_dir=payload.remote_dir,
        overwrite=payload.overwrite,
    )
    return FileTransferResultResponse(
        ok=result.ok,
        message=result.message,
        local_path=result.local_path,
        remote_path=result.remote_path,
        bytes_transferred=result.bytes_transferred,
        duration=result.duration,
        error=result.error,
    )


@router.post("/file-transfer/upload-browser", response_model=FileTransferResultResponse)
async def upload_file_transfer_from_browser(
    file: UploadFile = File(...),
    protocol: str = Form("ftp"),
    host: str = Form(""),
    username: str = Form("instrument"),
    password: str = Form("instrument"),
    remote_dir: str = Form("/var/user/"),
    mapped_root: str = Form(""),
    timeout_s: int = Form(15),
    passive_mode: bool = Form(True),
    overwrite: bool = Form(False),
) -> FileTransferResultResponse:
    temp_root = Path(__file__).resolve().parents[3] / "temp_uploads"
    temp_root.mkdir(parents=True, exist_ok=True)
    local_name = file.filename or "upload.bin"
    temp_file = temp_root / local_name

    data = await file.read()
    temp_file.write_bytes(data)

    try:
        config = TransferConfig(
            protocol=protocol,  # type: ignore[arg-type]
            host=host or None,
            username=username,
            password=password,
            remote_dir=remote_dir,
            mapped_root=mapped_root or None,
            timeout_s=timeout_s,
            passive_mode=passive_mode,
        )
        result = file_transfer_service.upload_file(
            config=config,
            local_path=str(temp_file),
            remote_dir=remote_dir,
            overwrite=overwrite,
        )
        return FileTransferResultResponse(
            ok=result.ok,
            message=result.message,
            local_path=local_name,
            remote_path=result.remote_path,
            bytes_transferred=result.bytes_transferred,
            duration=result.duration,
            error=result.error,
        )
    finally:
        try:
            temp_file.unlink(missing_ok=True)
        except Exception:
            pass


@router.post("/file-transfer/download", response_model=FileTransferResultResponse)
async def download_file_transfer(payload: FileTransferDownloadRequest) -> FileTransferResultResponse:
    result = file_transfer_service.download_file(
        config=_to_transfer_config(payload.config),
        remote_path=payload.remote_path,
        local_dir=payload.local_dir,
        overwrite=payload.overwrite,
    )
    return FileTransferResultResponse(
        ok=result.ok,
        message=result.message,
        local_path=result.local_path,
        remote_path=result.remote_path,
        bytes_transferred=result.bytes_transferred,
        duration=result.duration,
        error=result.error,
    )


@router.post("/scenario/files/download", response_model=ScenarioWorkspaceDownloadResponse)
async def download_remote_scenario_to_workspace(payload: ScenarioWorkspaceDownloadRequest) -> ScenarioWorkspaceDownloadResponse:
    local_dir = payload.local_dir or "./scenarios"
    Path(local_dir).mkdir(parents=True, exist_ok=True)

    result = file_transfer_service.download_osi_file(
        config=_to_transfer_config(payload.config),
        remote_path=payload.remote_path,
        local_dir=local_dir,
        overwrite=payload.overwrite,
    )
    if not result.ok or not result.local_path:
        return ScenarioWorkspaceDownloadResponse(
            ok=False,
            message=result.message,
            local_path=result.local_path,
            remote_path=result.remote_path or payload.remote_path,
            bytes_transferred=result.bytes_transferred,
            duration=result.duration,
            validation_ok=False,
            size_bytes=0,
            message_count=0,
            error=result.error,
        )

    validation = generator_service.validate_osi_file(file_path=result.local_path)
    message = result.message or "Scenario downloaded to workspace"
    if payload.inspect_after_download:
        message = f"{message}; ready for local inspection"

    return ScenarioWorkspaceDownloadResponse(
        ok=True,
        message=message,
        local_path=result.local_path,
        remote_path=result.remote_path or payload.remote_path,
        bytes_transferred=result.bytes_transferred,
        duration=result.duration,
        validation_ok=bool(validation.get("ok")),
        size_bytes=int(validation.get("size_bytes") or 0),
        message_count=int(validation.get("message_count") or 0),
        error=validation.get("error"),
    )


@router.post("/file-transfer/mkdir", response_model=FileTransferOperationResponse)
async def mkdir_file_transfer(payload: FileTransferMkdirRequest) -> FileTransferOperationResponse:
    op = file_transfer_service.create_directory(_to_transfer_config(payload.config), payload.remote_dir)
    return FileTransferOperationResponse(ok=op.ok, message=op.message, error=op.error, warnings=op.warnings or [])


@router.post("/file-transfer/delete", response_model=FileTransferOperationResponse)
async def delete_file_transfer(payload: FileTransferDeleteRequest) -> FileTransferOperationResponse:
    op = file_transfer_service.delete_remote(_to_transfer_config(payload.config), payload.remote_path)
    return FileTransferOperationResponse(ok=op.ok, message=op.message, error=op.error, warnings=op.warnings or [])


@router.post("/file-transfer/rename", response_model=FileTransferOperationResponse)
async def rename_file_transfer(payload: FileTransferRenameRequest) -> FileTransferOperationResponse:
    op = file_transfer_service.rename_remote(_to_transfer_config(payload.config), payload.remote_path, payload.new_name)
    return FileTransferOperationResponse(ok=op.ok, message=op.message, error=op.error, warnings=op.warnings or [])


@router.post("/file-transfer/preflight", response_model=FileTransferPreflightResponse)
async def file_transfer_preflight(payload: FileTransferPreflightRequest) -> FileTransferPreflightResponse:
    result = file_transfer_service.preflight_checklist(
        config=_to_transfer_config(payload.config),
        remote_dir=payload.remote_dir,
        need_write=payload.need_write,
    )
    return FileTransferPreflightResponse(
        ok=bool(result.get("ok")),
        items=[
            FileTransferChecklistItemModel(name=item["name"], status=item["status"])
            for item in result.get("items", [])
        ],
        warnings=list(result.get("warnings", [])),
        likely_causes=list(result.get("likely_causes", [])),
        message=result.get("message"),
        error=result.get("error"),
    )


@router.post("/file-transfer/osi/scan", response_model=FileTransferListResponse)
async def scan_remote_osi_files(payload: FileTransferListRequest) -> FileTransferListResponse:
    files, op = file_transfer_service.scan_remote_osi_files(
        config=_to_transfer_config(payload.config),
        remote_dir=payload.remote_dir,
    )
    return FileTransferListResponse(
        ok=op.ok,
        files=[
            FileTransferRemoteFileModel(
                name=f.name,
                remote_path=f.remote_path,
                size=f.size,
                modified_time=f.modified_time,
                extension=f.extension,
                is_directory=f.is_directory,
            )
            for f in files
        ],
        total_count=len(files),
        remote_dir=payload.remote_dir,
        message=op.message,
        error=op.error,
        warnings=op.warnings or [],
        likely_causes=file_transfer_service._guess_likely_causes(op.error) if not op.ok else [],
    )

