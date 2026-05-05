"""Scenario player service - orchestrates scenario discovery, selection, and playback."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.core.command_registry import CommandRegistryService
from backend.app.core.scpi_service import ScpiService
from backend.app.models.scenario import (
    CommandLogEntry,
    ScenarioReplayMode,
    ScenarioFile,
    ScenarioPlaybackState,
    ScenarioPlaybackStatus,
)


class CommandLogger:
    """Manages SCPI command logging."""

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self.log_entries: list[CommandLogEntry] = []

    def add_entry(self, entry: CommandLogEntry) -> None:
        """Add a log entry, maintaining max size."""
        self.log_entries.append(entry)
        if len(self.log_entries) > self.max_entries:
            self.log_entries.pop(0)

    def log_command(
        self,
        command: str,
        command_type: str,
        ok: bool,
        response: str | None = None,
        message: str | None = None,
        error: str | None = None,
        is_query: bool = False,
        waited_for_response: bool = False,
    ) -> None:
        """Log a command execution."""
        entry = CommandLogEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command=command,
            command_type=command_type,  # type: ignore
            ok=ok,
            response=response,
            message=message,
            error=error,
            is_query=is_query,
            waited_for_response=waited_for_response,
        )
        self.add_entry(entry)

    def get_all(self) -> list[CommandLogEntry]:
        """Get all log entries."""
        return self.log_entries.copy()

    def clear(self) -> None:
        """Clear all log entries."""
        self.log_entries.clear()


class ScenarioPlayerService:
    """Orchestrates scenario playback and control."""

    def __init__(self, scpi_service: ScpiService, command_registry: CommandRegistryService | None = None):
        self.scpi_service = scpi_service
        self.command_registry = command_registry or CommandRegistryService()
        self.logger = CommandLogger()
        self.selected_scenario: str | None = None
        self.current_playback_state: ScenarioPlaybackState = "unknown"
        self.current_replay_mode: ScenarioReplayMode = "UNKNOWN"
        self.desired_replay_mode: ScenarioReplayMode = "SINGle"
        self.cached_scenarios: list[ScenarioFile] = []
        self.synced_to_instrument = False
        self.check_errors_after_write = False  # Optional feature for error checking

    def _registry_command(self, key: str, **values: object) -> str:
        return self.command_registry.resolve(key, values)

    def _is_connected(self) -> bool:
        return bool(getattr(self.scpi_service.transport, "connected", False))

    def _log_local_action(self, action: str, message: str) -> None:
        self.logger.log_command(
            command=f"LOCAL:{action}",
            command_type="action",
            ok=True,
            message=message,
            is_query=False,
            waited_for_response=False,
        )

    async def execute_scpi_command(self, command: str) -> dict[str, Any]:
        """Execute SCPI command through central executor and log it.
        
        This is the core method that enforces the write/query separation rule:
        - Commands ending with ? are queries (wait for response)
        - Commands not ending with ? are writes (don't wait)
        """
        result = await self.scpi_service.execute_with_classification(command)

        # Log the command
        self.logger.log_command(
            command=result["command"],
            command_type=result["command_type"],
            ok=result["ok"],
            response=result.get("response"),
            message=result.get("message"),
            error=result.get("error"),
            is_query=result.get("command_type") in {"query", "binary-query"},
            waited_for_response=result.get("command_type") in {"query", "binary-query"},
        )

        # Optional: Check errors after write commands if enabled
        if self.check_errors_after_write and result["command_type"] in {"write", "action"} and result["ok"]:
            await self._check_errors_optional()

        return result

    async def _check_errors_optional(self) -> None:
        """Optional error check after write command. Logged as separate command."""
        try:
            result = await self.scpi_service.execute_with_classification("SYSTem:ERRor?")
            self.logger.log_command(
                command=result["command"],
                command_type=result["command_type"],
                ok=result["ok"],
                response=result.get("response"),
                error=result.get("error"),
                is_query=result.get("command_type") in {"query", "binary-query"},
                waited_for_response=result.get("command_type") in {"query", "binary-query"},
            )
        except Exception:
            pass  # Silently ignore optional error check failures

    async def scan_scenarios(self, force_refresh: bool = False, directory: str | None = None) -> tuple[list[ScenarioFile], str | None]:
        """Scan for available .osi scenario files on the instrument.

        Uses the AREG-specific FILE:CATalog? query, falling back to generic
        MMEMory:CATalog?.  Results are cached until force_refresh is True.

        Returns:
            Tuple of (scenarios list, error message or None)
        """
        if self.cached_scenarios and not force_refresh:
            return self.cached_scenarios, None

        if not self._is_connected():
            return [], "Device not connected"

        target_dir = directory or "/osi"
        scenarios: list[ScenarioFile] = []

        # Try AREG-specific command first
        for cmd in [
            self._registry_command("scenario.catalog", source_hw=1, directory=target_dir),
            f':MMEMory:CATalog? "{target_dir}"',
        ]:
            try:
                result = await self.execute_scpi_command(cmd)
                if result["ok"] and result.get("response"):
                    scenarios = self._parse_scenario_catalog(str(result["response"]), target_dir)
                    if scenarios:
                        break
                    # Empty response is valid (no files) – stop trying
                    break
            except Exception:
                continue

        self.cached_scenarios = scenarios
        return scenarios, None

    def _parse_scenario_catalog(self, response: str, base_dir: str) -> list[ScenarioFile]:
        """Parse a SCPI catalog response into ScenarioFile list (only .osi entries)."""
        import re
        files: list[ScenarioFile] = []
        if not response:
            return files

        # Newline-only list
        if "\n" in response and '"' not in response:
            for line in response.splitlines():
                name = line.strip()
                if name.lower().endswith(".osi"):
                    files.append(ScenarioFile(
                        name=name,
                        path=f"{base_dir.rstrip('/')}/{name}",
                        extension=".osi",
                        is_loadable=True,
                    ))
            return files

        parts = re.split(r'",\s*"', response.strip('"'))
        for part in parts:
            sub = [s.strip().strip('"') for s in part.split(",")]
            if not sub:
                continue
            name = sub[0]
            if not name.lower().endswith(".osi"):
                continue
            size_bytes: int | None = None
            for candidate in sub[1:]:
                try:
                    size_bytes = int(candidate.strip())
                    break
                except ValueError:
                    continue
            files.append(ScenarioFile(
                name=name,
                path=f"{base_dir.rstrip('/')}/{name}",
                extension=".osi",
                size_bytes=size_bytes,
                is_loadable=True,
            ))
        return files

    async def set_scenario_replay_mode(self, mode: str) -> tuple[bool, str]:
        """Set scenario replay mode to SINGle or LOOP."""
        if mode not in ("SINGle", "LOOP"):
            return False, f"Invalid replay mode: {mode}"

        # Always keep desired mode for preview/offline operation.
        self.desired_replay_mode = mode  # type: ignore[assignment]

        if not self._is_connected():
            self.current_replay_mode = mode  # type: ignore[assignment]
            self._log_local_action("replay-mode", f"Preview replay mode set to {mode}")
            return True, f"Preview replay mode set to {mode}"

        try:
            result = await self.execute_scpi_command(
                self._registry_command("scenario.replay_mode.set", source_hw=1, mode=mode)
            )
            if not result["ok"]:
                return False, f"Replay mode set failed: {result.get('error', 'Unknown error')}"

            self.current_replay_mode = mode  # type: ignore[assignment]
            return True, f"Replay mode set to {mode}"
        except Exception as ex:
            return False, f"Replay mode set failed: {str(ex)}"

    async def query_scenario_replay_mode(self) -> ScenarioReplayMode:
        """Query current replay mode from instrument."""
        if not self._is_connected():
            # In preview mode, use local mode.
            if self.current_replay_mode == "UNKNOWN":
                self.current_replay_mode = self.desired_replay_mode
            return self.current_replay_mode

        try:
            result = await self.execute_scpi_command(
                self._registry_command("scenario.replay_mode.query", source_hw=1)
            )
            if not result["ok"]:
                self.current_replay_mode = "UNKNOWN"
                return "UNKNOWN"

            raw = str(result.get("response") or "").strip().strip('"').upper()
            if "LOOP" in raw:
                self.current_replay_mode = "LOOP"
                return "LOOP"
            if "SING" in raw:
                self.current_replay_mode = "SINGle"
                return "SINGle"

            self.current_replay_mode = "UNKNOWN"
            return "UNKNOWN"
        except Exception:
            self.current_replay_mode = "UNKNOWN"
            return "UNKNOWN"

    async def apply_scenario_playback_settings(self, mode: str | None = None) -> tuple[bool, str]:
        """Apply selected playback settings (currently replay mode only)."""
        target_mode = mode or self.desired_replay_mode
        if target_mode not in ("SINGle", "LOOP"):
            return False, f"Invalid replay mode: {target_mode}"
        return await self.set_scenario_replay_mode(target_mode)

    async def load_scenario(self, scenario_name: str, replay_mode: str | None = None) -> tuple[bool, str]:
        """Load a scenario file on the instrument.

        Sends the AREG-specific FILE command.  The scenario_name may be either a
        bare filename (e.g. ``"target.osi"``) or a full remote path.

        Returns:
            Tuple of (success, message)
        """
        self.selected_scenario = scenario_name

        # When disconnected, always allow local preview loading.
        if not self._is_connected():
            self.synced_to_instrument = False
            self.current_playback_state = "loaded"
            if replay_mode is not None:
                ok, msg = await self.apply_scenario_playback_settings(replay_mode)
                if not ok:
                    return False, f"Scenario loaded in preview mode but replay mode failed: {msg}"
                self._log_local_action("load", f"Scenario '{scenario_name}' loaded in preview mode; {msg}")
                return True, f"Scenario '{scenario_name}' loaded in preview mode; {msg}"
            self._log_local_action("load", f"Scenario '{scenario_name}' loaded in preview mode")
            return True, f"Scenario '{scenario_name}' loaded in preview mode"

        try:
            result = await self.execute_scpi_command(
                self._registry_command("scenario.file", source_hw=1, scenario_name=scenario_name)
            )
            if result["ok"]:
                self.synced_to_instrument = True
                self.current_playback_state = "loaded"
                if replay_mode is not None:
                    ok, msg = await self.apply_scenario_playback_settings(replay_mode)
                    if not ok:
                        return False, f"Scenario loaded but replay mode failed: {msg}"
                    return True, f"Scenario '{scenario_name}' loaded and synced; {msg}"
                return True, f"Scenario '{scenario_name}' loaded and synced"

            # If device load fails, keep preview capability available.
            self.synced_to_instrument = False
            self.current_playback_state = "loaded"
            fallback = f"Load on instrument failed: {result.get('error', 'Unknown error')}"
            self._log_local_action("load-fallback", f"{fallback}; preview mode active")
            return True, f"{fallback}. Preview mode active for '{scenario_name}'"
        except Exception as e:
            self.synced_to_instrument = False
            self.current_playback_state = "loaded"
            self._log_local_action("load-fallback", f"Load exception: {str(e)}; preview mode active")
            return True, f"Load on instrument failed ({str(e)}). Preview mode active for '{scenario_name}'"

    async def play(self) -> tuple[bool, str]:
        """Start scenario playback."""
        if not self.selected_scenario:
            return False, "No scenario selected"

        if self.current_playback_state in {"not_loaded", "unknown"}:
            loaded_ok, loaded_msg = await self.load_scenario(self.selected_scenario)
            if not loaded_ok:
                return False, loaded_msg

        if not self._is_connected() or not self.synced_to_instrument:
            self.current_playback_state = "playing"
            self._log_local_action("play", "Preview playback started")
            return True, "Preview playback started"

        try:
            result = await self.execute_scpi_command(self._registry_command("scenario.play", source_hw=1))

            if result["ok"]:
                self.current_playback_state = "playing"
                return True, "Playback started"
            else:
                return False, f"Play failed: {result.get('error', 'Unknown error')}"

        except Exception as e:
            return False, f"Play failed: {str(e)}"

    async def pause(self) -> tuple[bool, str]:
        """Pause scenario playback."""
        if not self._is_connected() or not self.synced_to_instrument:
            if self.current_playback_state != "playing":
                return False, "Cannot pause: playback is not running"
            self.current_playback_state = "paused"
            self._log_local_action("pause", "Preview playback paused")
            return True, "Preview playback paused"

        try:
            result = await self.execute_scpi_command(self._registry_command("scenario.pause", source_hw=1))

            if result["ok"]:
                self.current_playback_state = "paused"
                return True, "Playback paused"
            else:
                return False, f"Pause failed: {result.get('error', 'Unknown error')}"

        except Exception as e:
            return False, f"Pause failed: {str(e)}"

    async def stop(self) -> tuple[bool, str]:
        """Stop scenario playback."""
        if not self._is_connected() or not self.synced_to_instrument:
            self.current_playback_state = "stopped"
            self._log_local_action("stop", "Preview playback stopped")
            return True, "Preview playback stopped"

        try:
            result = await self.execute_scpi_command(self._registry_command("scenario.stop", source_hw=1))

            if result["ok"]:
                self.current_playback_state = "stopped"
                return True, "Playback stopped"
            else:
                return False, f"Stop failed: {result.get('error', 'Unknown error')}"

        except Exception as e:
            return False, f"Stop failed: {str(e)}"

    async def restart(self) -> tuple[bool, str]:
        """Restart scenario playback (stop + play)."""
        try:
            if not self.selected_scenario:
                return False, "No scenario selected"

            # Stop first
            stop_ok, stop_msg = await self.stop()
            if not stop_ok:
                return False, f"Restart failed during stop: {stop_msg}"

            # Reload selected scenario to reset position to start.
            load_ok, load_msg = await self.load_scenario(self.selected_scenario)
            if not load_ok:
                return False, f"Restart failed during reload: {load_msg}"

            # Then play from beginning.
            play_ok, play_msg = await self.play()
            if play_ok:
                self._log_local_action("restart", f"Restarted from beginning: {self.selected_scenario}")
            return play_ok, play_msg

        except Exception as e:
            return False, f"Restart failed: {str(e)}"

    async def refresh_playback_state(self) -> ScenarioPlaybackStatus:
        """Query current playback state from instrument.

        Sends ``SOURce1:AREGenerator:SCENario:STATe?`` and maps the response to
        a known playback state.  Falls back to in-memory state on error.
        """
        try:
            if self._is_connected() and self.synced_to_instrument:
                result = await self.execute_scpi_command(
                    self._registry_command("scenario.state", source_hw=1)
                )
                if result["ok"] and result.get("response"):
                    raw = str(result["response"]).strip().lower()
                    # Map instrument response strings to our playback states
                    state_map = {
                        "run": "playing",
                        "running": "playing",
                        "play": "playing",
                        "pause": "paused",
                        "paused": "paused",
                        "stop": "stopped",
                        "stopped": "stopped",
                        "load": "loaded",
                        "loaded": "loaded",
                        "idle": "not_loaded",
                    }
                    self.current_playback_state = state_map.get(raw, self.current_playback_state)  # type: ignore
        except Exception:
            pass  # Keep in-memory state on error

        return ScenarioPlaybackStatus(
            state=self.current_playback_state,
            current_scenario=self.selected_scenario,
            replay_mode=self.current_replay_mode,
        )

    async def select_scenario(self, scenario_name: str) -> tuple[bool, str]:
        """Select a scenario without loading it.

        Accepts bare filenames and full remote paths.  If the name is not in the
        cached list the selection still succeeds (the user may have typed the
        path manually or the list is stale).
        """
        resolved = next(
            (
                s.path
                for s in self.cached_scenarios
                if s.name == scenario_name or s.path == scenario_name
            ),
            scenario_name,
        )
        self.selected_scenario = resolved
        self.synced_to_instrument = False
        return True, f"Scenario '{resolved}' selected"

    async def next_scenario(self) -> tuple[bool, str]:
        """Select next scenario in list."""
        if not self.cached_scenarios:
            return False, "No scenarios available"

        if not self.selected_scenario:
            return await self.select_scenario(self.cached_scenarios[0].name)

        current_index = next(
            (i for i, s in enumerate(self.cached_scenarios) if s.name == self.selected_scenario), -1
        )

        if current_index == -1 or current_index >= len(self.cached_scenarios) - 1:
            return False, "Already at last scenario"

        return await self.select_scenario(self.cached_scenarios[current_index + 1].name)

    async def previous_scenario(self) -> tuple[bool, str]:
        """Select previous scenario in list."""
        if not self.cached_scenarios:
            return False, "No scenarios available"

        if not self.selected_scenario:
            return await self.select_scenario(self.cached_scenarios[-1].name)

        current_index = next(
            (i for i, s in enumerate(self.cached_scenarios) if s.name == self.selected_scenario), -1
        )

        if current_index <= 0:
            return False, "Already at first scenario"

        return await self.select_scenario(self.cached_scenarios[current_index - 1].name)

    def get_command_log(self) -> list[CommandLogEntry]:
        """Get command log entries."""
        return self.logger.get_all()

    def clear_command_log(self) -> None:
        """Clear command log."""
        self.logger.clear()

    def set_check_errors_after_write(self, enabled: bool) -> None:
        """Enable/disable optional error checking after write commands."""
        self.check_errors_after_write = enabled
