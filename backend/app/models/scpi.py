from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CommandType = Literal["set", "query", "action"]
VerificationStatus = Literal["manual-verified", "extracted", "pending-review"]


class CommandParameter(BaseModel):
    name: str
    type: str = "string"
    required: bool = False
    unit: str | None = None
    min: float | None = None
    max: float | None = None


class ScpiCommand(BaseModel):
    key: str = Field(description="Canonical key for UI and execution")
    command: str = Field(description="SCPI command pattern")
    type: CommandType
    description: str
    example: str | None = None
    parameters: list[CommandParameter] = Field(default_factory=list)
    verified: bool = False
    verification_status: VerificationStatus = "pending-review"
    source: str | None = None


class Catalog(BaseModel):
    instrument: str
    version: str
    generated_on: str
    commands: list[ScpiCommand]


class ConnectRequest(BaseModel):
    protocol: Literal["hislip", "socket", "vxi11", "rsib", "mdns"] = "hislip"
    host: str | None = None
    port: int | None = None


class CommandRequest(BaseModel):
    command: str
    expect_response: bool | None = None
    timeout_ms: int | None = None


class CommandResponse(BaseModel):
    command: str
    command_type: Literal["query", "binary-query", "write", "action", "empty"] = "write"
    response: str | None = None
    message: str | None = None
    ok: bool
    transport: str
    error: str | None = None


class HardcopyRequest(BaseModel):
    """Request to capture a hardcopy/screenshot from the instrument."""

    save_dir: str | None = None  # If None, uses default screenshots directory
    file_format: str = "PNG"  # PNG, JPG, BMP, etc.
    filename_prefix: str = "AREG800A_screenshot"
    use_timestamp: bool = True
    timeout_ms: int | None = None
    # Legacy: For backward compatibility
    save_path: str | None = None


class HardcopyResponse(BaseModel):
    """Response from hardcopy capture."""

    ok: bool
    file_path: str | None = None
    file_format: str | None = None
    bytes_written: int = 0
    payload_bytes: int = 0
    detected_type: str | None = None
    validation_ok: bool = False
    diagnostics: dict[str, Any] | None = None
    log: list[dict[str, Any]] = Field(default_factory=list)
    transport: str | None = None
    message: str | None = None
    error: str | None = None


class SessionState(BaseModel):
    connected: bool
    host: str | None = None
    port: int | None = None
    transport: str


# ============================================================================
# Scenario Generation Models
# ============================================================================


class RangeSweepRequest(BaseModel):
    """Request to generate a range sweep scenario."""
    output_dir: str = "./scenarios"
    output_filename: str | None = None
    sensor_id: int = 1
    update_interval_s: float = 0.1
    start_range_m: float = 120.0
    stop_range_m: float = 20.0
    radial_velocity_mps: float = -10.0
    rcs_dbsm: float = 10.0
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    scenario_name: str = "range_sweep"


class ConstantObjectRequest(BaseModel):
    """Request to generate a constant object scenario."""
    output_dir: str = "./scenarios"
    output_filename: str | None = None
    sensor_id: int = 1
    duration_s: float = 10.0
    update_interval_s: float = 0.1
    range_m: float = 100.0
    radial_velocity_mps: float = 0.0
    rcs_dbsm: float = 10.0
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    scenario_name: str = "constant_object"


class MultiObjectParams(BaseModel):
    """Single object definition for multi-object scenario."""
    name: str
    enabled: bool = True
    start_range_m: float
    stop_range_m: float
    radial_velocity_mps: float
    rcs_dbsm: float
    azimuth_deg: float
    elevation_deg: float


class MultiObjectRequest(BaseModel):
    """Request to generate a multi-object scenario."""
    output_dir: str = "./scenarios"
    output_filename: str | None = None
    sensor_id: int = 1
    update_interval_s: float = 0.1
    duration_s: float = 10.0
    objects: list[MultiObjectParams]
    scenario_name: str = "multi_object"


class AzimuthSweepRequest(BaseModel):
    """Request to generate an azimuth sweep scenario."""
    output_dir: str = "./scenarios"
    output_filename: str | None = None
    sensor_id: int = 1
    update_interval_s: float = 0.1
    duration_s: float = 10.0
    range_m: float = 100.0
    start_azimuth_deg: float = -180.0
    stop_azimuth_deg: float = 180.0
    radial_velocity_mps: float = 0.0
    rcs_dbsm: float = 10.0
    elevation_deg: float = 0.0
    scenario_name: str = "azimuth_sweep"


class ConstantEchoPowerRequest(BaseModel):
    """Request to generate a constant echo power scenario.

    RCS is compensated per-step to maintain constant received echo power at the
    radar receiver via the R⁴ radar range equation:

        RCS(R) [dBsm] = ref_rcs_dbsm + 40 * log10(R / ref_range_m)
    """
    output_dir: str = "./scenarios"
    output_filename: str | None = None
    sensor_id: int = 1
    update_interval_s: float = 0.1
    start_range_m: float = 120.0
    stop_range_m: float = 20.0
    radial_velocity_mps: float = -10.0
    ref_rcs_dbsm: float = 10.0
    ref_range_m: float = 100.0
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    rcs_min_dbsm: float = -30.0
    rcs_max_dbsm: float = 60.0
    scenario_name: str = "constant_echo_power"


class ScenarioPreview(BaseModel):
    """Preview metadata for a generated scenario."""
    duration_s: float
    message_count: int
    object_count: int
    min_range_m: float
    max_range_m: float
    min_azimuth_deg: float
    max_azimuth_deg: float
    min_velocity_mps: float
    max_velocity_mps: float
    min_rcs_dbsm: float
    max_rcs_dbsm: float
    estimated_file_size_bytes: int
    warnings: list[str] = []


class RcsTableEntry(BaseModel):
    """Single entry in a RCS compensation table."""
    range_m: float
    rcs_dbsm: float


class GenerationResponse(BaseModel):
    """Response from scenario generation."""
    ok: bool
    file_path: str | None = None
    message_count: int = 0
    duration_s: float = 0.0
    preview: ScenarioPreview | None = None
    rcs_table: list[RcsTableEntry] | None = None
    error: str | None = None


class GeneratorStatusResponse(BaseModel):
    """Status of scenario generator."""
    osi_available: bool
    osi_error: str | None = None
    last_generated_file: str | None = None
    last_preview: ScenarioPreview | None = None


class SimulationOverviewResponse(BaseModel):
    """Aggregated snapshot of AREG800A simulation state for the overview panel."""
    # Connection
    connected: bool = False
    host: str | None = None
    port: int | None = None
    transport: str = "unknown"
    # Playback
    playback_state: str = "unknown"
    current_scenario: str | None = None
    replay_mode: str = "UNKNOWN"
    # Generator
    total_generated: int = 0
    last_generated_file: str | None = None
    last_generated_template: str | None = None
    # Command log
    log_entry_count: int = 0
    last_command: str | None = None
    last_command_ok: bool | None = None
    # Metadata
    timestamp: str = ""
    # Local file mapping (same basename found in scenarios/ directory)
    local_scenario_path: str | None = None


class ScenarioValidationRequest(BaseModel):
    """Request to validate a generated .osi file."""
    file_path: str | None = None


class ScenarioValidationResponse(BaseModel):
    """Response from .osi file validation."""
    ok: bool
    file_path: str | None = None
    exists: bool = False
    size_bytes: int = 0
    message_count: int = 0
    error: str | None = None


class ScenarioTransferRequest(BaseModel):
    """Request to transfer a generated scenario file."""
    local_path: str | None = None
    remote_path: str
    transfer_method: Literal["local_copy"] = "local_copy"


class ScenarioTransferResponse(BaseModel):
    """Response from scenario file transfer."""
    ok: bool
    local_path: str | None = None
    remote_path: str | None = None
    transfer_method: str
    bytes_transferred: int = 0
    error: str | None = None


# ============================================================================
# Device File Management Models
# ============================================================================


class DeviceOsiFileModel(BaseModel):
    """An .osi file discovered on the connected device."""

    name: str = Field(description="Filename (e.g. target.osi)")
    path: str = Field(description="Full remote path on the device")
    size_bytes: int | None = Field(default=None, description="File size in bytes if available")
    modified_time: str | None = Field(default=None, description="Last-modified timestamp if available")


class ScanDeviceFilesRequest(BaseModel):
    """Request to scan the device file system for .osi files."""

    directory: str | None = Field(default=None, description="Remote directory to scan (default /osi)")
    force_refresh: bool = Field(default=False, description="Bypass cache and re-query the device")


class ScanDeviceFilesResponse(BaseModel):
    """Response from device file scan."""

    ok: bool
    files: list[DeviceOsiFileModel] = Field(default_factory=list)
    total_count: int = 0
    directory: str | None = None
    error: str | None = None


class DiscoverDeviceDirectoriesResponse(BaseModel):
    """Response containing discovered candidate directories on device."""

    ok: bool
    directories: list[str] = Field(default_factory=list)
    error: str | None = None


class UploadOsiFileRequest(BaseModel):
    """Request to upload a local .osi file to the device."""

    local_path: str = Field(description="Absolute or relative local file path")
    remote_path: str | None = Field(default=None, description="Destination path on the device (must end with .osi). If omitted, backend auto-selects an available directory (USB preferred).")
    preferred_directory: str | None = Field(default=None, description="Optional preferred destination directory (for example /usb). Used only when remote_path is omitted.")


class UploadOsiFileResponse(BaseModel):
    """Response from OSI file upload."""

    ok: bool
    local_path: str | None = None
    remote_path: str | None = None
    bytes_transferred: int = 0
    error: str | None = None


# ============================================================================
# File Transfer Manager Models
# ============================================================================


class FileTransferConfigModel(BaseModel):
    protocol: Literal["ftp", "smb", "mapped_folder", "manual_usb"] = "ftp"
    host: str | None = None
    username: str = "instrument"
    password: str = "instrument"
    remote_dir: str = "/var/user/"
    mapped_root: str | None = None
    timeout_s: int = 15
    passive_mode: bool = True


class FileTransferRemoteFileModel(BaseModel):
    name: str
    remote_path: str
    size: int | None = None
    modified_time: str | None = None
    extension: str = ""
    is_directory: bool = False


class FileTransferOperationResponse(BaseModel):
    ok: bool
    message: str | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    likely_causes: list[str] = Field(default_factory=list)


class FileTransferListRequest(BaseModel):
    config: FileTransferConfigModel
    remote_dir: str = "/var/user/"
    file_filter: Literal["all", "osi", "scpi", "txt", "csv", "custom"] = "all"
    custom_ext: str | None = None


class FileTransferListResponse(BaseModel):
    ok: bool
    files: list[FileTransferRemoteFileModel] = Field(default_factory=list)
    total_count: int = 0
    remote_dir: str = "/var/user/"
    message: str | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    likely_causes: list[str] = Field(default_factory=list)


class FileTransferUploadRequest(BaseModel):
    config: FileTransferConfigModel
    local_path: str
    remote_dir: str = "/var/user/"
    overwrite: bool = False


class FileTransferDownloadRequest(BaseModel):
    config: FileTransferConfigModel
    remote_path: str
    local_dir: str
    overwrite: bool = False


class ScenarioWorkspaceDownloadRequest(BaseModel):
    config: FileTransferConfigModel
    remote_path: str
    local_dir: str = "./scenarios"
    overwrite: bool = False
    inspect_after_download: bool = True


class FileTransferRenameRequest(BaseModel):
    config: FileTransferConfigModel
    remote_path: str
    new_name: str


class FileTransferDeleteRequest(BaseModel):
    config: FileTransferConfigModel
    remote_path: str


class FileTransferMkdirRequest(BaseModel):
    config: FileTransferConfigModel
    remote_dir: str


class FileTransferPreflightRequest(BaseModel):
    config: FileTransferConfigModel
    remote_dir: str = "/var/user/"
    need_write: bool = True


class FileTransferChecklistItemModel(BaseModel):
    name: str
    status: Literal["pass", "warn", "fail"]


class FileTransferPreflightResponse(BaseModel):
    ok: bool
    items: list[FileTransferChecklistItemModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    likely_causes: list[str] = Field(default_factory=list)
    message: str | None = None
    error: str | None = None


class FileTransferResultResponse(BaseModel):
    ok: bool
    message: str | None = None
    local_path: str | None = None
    remote_path: str | None = None
    bytes_transferred: int = 0
    duration: float = 0.0
    error: str | None = None


class ScenarioWorkspaceDownloadResponse(BaseModel):
    ok: bool
    message: str | None = None
    local_path: str | None = None
    remote_path: str | None = None
    bytes_transferred: int = 0
    duration: float = 0.0
    validation_ok: bool = False
    size_bytes: int = 0
    message_count: int = 0
    error: str | None = None


class FileTransferHelpResponse(BaseModel):
    ftp: list[str] = Field(default_factory=list)
    smb: list[str] = Field(default_factory=list)
    usb: list[str] = Field(default_factory=list)
