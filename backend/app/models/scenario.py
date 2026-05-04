from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


NodeKind = Literal["start", "configure", "delay", "trigger", "readback", "assert", "stop"]
StepKind = Literal["scpi", "delay", "assert", "lifecycle"]


class ScenarioNode(BaseModel):
    id: str
    kind: NodeKind
    label: str
    params: dict[str, Any] = Field(default_factory=dict)


class ScenarioEdge(BaseModel):
    source: str
    target: str


class ScenarioGraph(BaseModel):
    name: str = "untitled"
    nodes: list[ScenarioNode]
    edges: list[ScenarioEdge]


class ExecutionStep(BaseModel):
    index: int
    node_id: str
    kind: StepKind
    description: str
    scpi: str | None = None
    delay_ms: int | None = None


class CompileScenarioResponse(BaseModel):
    scenario_name: str
    ordered_node_ids: list[str]
    steps: list[ExecutionStep]


# ============================================================================
# Scenario Player Models
# ============================================================================

ScenarioPlaybackState = Literal["unknown", "not_loaded", "loaded", "playing", "paused", "stopped", "error"]
ScenarioReplayMode = Literal["SINGle", "LOOP", "UNKNOWN"]


class ScenarioFile(BaseModel):
    """Represents a scenario file discovered on the instrument."""

    name: str = Field(description="Scenario filename")
    path: str | None = Field(default=None, description="Full file path if available")
    extension: str | None = Field(default=None, description="File extension/type")
    size_bytes: int | None = Field(default=None, description="File size in bytes")
    modified_time: str | None = Field(default=None, description="Last modified timestamp")
    is_loadable: bool = Field(default=True, description="Whether this scenario can be loaded")


class ScenarioPlaybackStatus(BaseModel):
    """Current state of scenario playback."""

    state: ScenarioPlaybackState = Field(default="unknown", description="Current playback state")
    current_scenario: str | None = Field(default=None, description="Currently loaded scenario name")
    replay_mode: ScenarioReplayMode = Field(default="UNKNOWN", description="Current replay mode")
    playback_progress: float | None = Field(default=None, description="Playback progress 0-100%")
    error_message: str | None = Field(default=None, description="Error message if state is error")


class ReplayModeRequest(BaseModel):
    """Set/query replay mode payload."""

    mode: Literal["SINGle", "LOOP"] = Field(description="Replay mode to apply")


class ScanScenariosRequest(BaseModel):
    """Request to scan for available scenarios."""

    force_refresh: bool = Field(default=False, description="Force fresh scan even if cached")
    search_pattern: str | None = Field(default=None, description="Optional pattern to filter results")


class ScanScenariosResponse(BaseModel):
    """Response from scenario scan."""

    ok: bool = Field(description="Scan succeeded")
    scenarios: list[ScenarioFile] = Field(default_factory=list, description="Found scenarios")
    total_count: int = Field(default=0, description="Total scenarios found")
    error: str | None = Field(default=None, description="Error message if scan failed")


class SelectScenarioRequest(BaseModel):
    """Request to select a scenario."""

    scenario_name: str = Field(description="Name of scenario to select")
    auto_load: bool = Field(default=False, description="Automatically load after selection")
    replay_mode: Literal["SINGle", "LOOP"] | None = Field(default=None, description="Optional replay mode to apply on load")


class ScenarioPlayerAction(BaseModel):
    """A scenario player action/command."""

    action: Literal["load", "play", "pause", "stop", "restart", "next", "previous", "refresh_state"] = Field(
        description="Player action to perform"
    )
    scenario_name: str | None = Field(default=None, description="Scenario name for load action")


class CommandLogEntry(BaseModel):
    """A single entry in the SCPI command log."""

    timestamp: str = Field(description="ISO timestamp")
    command: str = Field(description="SCPI command")
    command_type: Literal["query", "write", "empty"] = Field(description="Command type")
    ok: bool = Field(description="Command succeeded")
    response: str | None = Field(default=None, description="Query response if applicable")
    message: str | None = Field(default=None, description="Success message")
    error: str | None = Field(default=None, description="Error message if failed")
    is_query: bool = Field(default=False, description="True when SCPI command was a query")
    waited_for_response: bool = Field(default=False, description="True when transport waited for response")


class CommandLogResponse(BaseModel):
    """Response containing command log history."""

    log_entries: list[CommandLogEntry] = Field(description="Log entries")
    total_entries: int = Field(description="Total number of entries")
    max_entries: int = Field(default=100, description="Maximum number of entries kept")


class ScenarioPlayerState(BaseModel):
    """Current state of the scenario player UI."""

    connected: bool = Field(description="Is device connected")
    instrument_id: str | None = Field(default=None, description="Instrument identification")
    current_mode: str | None = Field(default=None, description="Current operation mode")
    scenarios: list[ScenarioFile] = Field(default_factory=list, description="Available scenarios")
    selected_scenario: str | None = Field(default=None, description="Currently selected scenario")
    playback_state: ScenarioPlaybackState = Field(default="unknown", description="Scenario playback state")
    error_message: str | None = Field(default=None, description="Current error message if any")


# ============================================================================
# Scenario Inspector Models
# ============================================================================


class ObjectStateSampleModel(BaseModel):
    timestamp: float | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    distance: float | None = None
    lateral_offset: float | None = None
    speed: float | None = None
    vx: float | None = None
    vy: float | None = None
    vz: float | None = None
    acceleration: float | None = None
    heading: float | None = None
    yaw: float | None = None
    rcs: float | None = None
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class ScenarioObjectModel(BaseModel):
    object_id: str
    object_name: str | None = None
    object_type: str | None = None
    initial_position: dict[str, float | None] = Field(default_factory=dict)
    final_position: dict[str, float | None] = Field(default_factory=dict)
    min_distance: float | None = None
    max_distance: float | None = None
    initial_speed: float | None = None
    max_speed: float | None = None
    average_speed: float | None = None
    acceleration_summary: dict[str, float | None] = Field(default_factory=dict)
    heading_summary: dict[str, float | None] = Field(default_factory=dict)
    rcs_summary: dict[str, float | None] = Field(default_factory=dict)
    valid_time_start: float | None = None
    valid_time_end: float | None = None
    samples: list[ObjectStateSampleModel] = Field(default_factory=list)
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class ScenarioDecodeResultModel(BaseModel):
    ok: bool
    scenario_name: str | None = None
    file_path: str | None = None
    remote_path: str | None = None
    local_cached_path: str | None = None
    loaded_scenario_path: str | None = None
    format_detected: str = "unknown"
    duration: float | None = None
    time_start: float | None = None
    time_end: float | None = None
    timestep_count: int = 0
    object_count: int = 0
    objects: list[ScenarioObjectModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    raw_summary: dict[str, Any] = Field(default_factory=dict)


class ScenarioInspectorDecodeRequest(BaseModel):
    remote_path: str | None = None
    local_path: str | None = None
    force_redownload: bool = False
    transfer_config: dict[str, Any] | None = None


class ScenarioInspectorClearCacheResponse(BaseModel):
    ok: bool
    removed_files: int = 0
    cache_dir: str | None = None
    error: str | None = None
