from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.core.command_registry import CommandRegistryService
from backend.app.core.scpi_service import ScpiService


@dataclass
class ScenarioCatalogEntry:
    name: str
    path: str
    extension: str
    size_bytes: int | None = None


class ScenarioManager:
    """Manual-aligned scenario manager for catalog/load/playback control."""

    def __init__(self, scpi_service: ScpiService, command_registry: CommandRegistryService | None = None) -> None:
        self.scpi_service = scpi_service
        self.command_registry = command_registry or CommandRegistryService()

    @staticmethod
    def _normalize_path(path: str) -> str:
        value = (path or "").strip().replace("\\", "/")
        value = re.sub(r"/{2,}", "/", value)
        if not value.startswith("/"):
            value = f"/{value}"
        return value

    async def _run(self, command: str) -> dict[str, object]:
        return await self.scpi_service.execute_with_classification(command)

    async def catalog_scenarios(self) -> tuple[list[ScenarioCatalogEntry], str | None]:
        cmd = self.command_registry.resolve("scenario.catalog", {"source_hw": 1})
        result = await self._run(cmd)
        if not result.get("ok"):
            return [], str(result.get("error") or "Catalog query failed")

        response = str(result.get("response") or "")
        return self._parse_catalog(response), None

    def _parse_catalog(self, response: str) -> list[ScenarioCatalogEntry]:
        clean = (response or "").strip()
        if not clean:
            return []

        # Accept formats like "name.osi,ASC,123" or newline/quoted name lists.
        parts = re.split(r'",\s*"', clean.strip('"'))
        entries: list[ScenarioCatalogEntry] = []
        for part in parts:
            if not part.strip():
                continue
            cols = [c.strip().strip('"') for c in part.split(",") if c.strip()]
            if not cols:
                continue
            name = cols[0]
            lower = name.lower()
            if not (lower.endswith(".osi") or lower.endswith(".sm")):
                continue

            size: int | None = None
            for token in cols[1:]:
                try:
                    size = int(token)
                    break
                except ValueError:
                    continue

            path = name if name.startswith("/") else f"/var/user/{name}"
            ext = ".osi" if lower.endswith(".osi") else ".sm"
            entries.append(ScenarioCatalogEntry(name=name.split("/")[-1], path=path, extension=ext, size_bytes=size))
        return entries

    async def load_scenario(self, path: str) -> tuple[bool, str | None]:
        cmd = self.command_registry.resolve("scenario.file", {"source_hw": 1, "scenario_name": self._normalize_path(path)})
        result = await self._run(cmd)
        if not result.get("ok"):
            return False, str(result.get("error") or "Load failed")
        return True, None

    async def play(self) -> tuple[bool, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.play", {"source_hw": 1}))
        return bool(result.get("ok")), None if result.get("ok") else str(result.get("error") or "Play failed")

    async def pause(self) -> tuple[bool, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.pause", {"source_hw": 1}))
        return bool(result.get("ok")), None if result.get("ok") else str(result.get("error") or "Pause failed")

    async def stop(self) -> tuple[bool, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.stop", {"source_hw": 1}))
        return bool(result.get("ok")), None if result.get("ok") else str(result.get("error") or "Stop failed")

    async def reset(self) -> tuple[bool, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.reset", {"source_hw": 1}))
        return bool(result.get("ok")), None if result.get("ok") else str(result.get("error") or "Reset failed")

    async def get_status(self) -> tuple[str | None, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.status", {"source_hw": 1}))
        if not result.get("ok"):
            return None, str(result.get("error") or "Status query failed")
        return str(result.get("response") or "").strip(), None

    async def get_progress(self) -> tuple[float | None, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.progress", {"source_hw": 1}))
        if not result.get("ok"):
            return None, str(result.get("error") or "Progress query failed")
        raw = str(result.get("response") or "").strip().strip('"')
        try:
            return float(raw), None
        except ValueError:
            return None, f"Unexpected progress response: {raw}"

    async def get_actual_position(self) -> tuple[int | None, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.position.actual", {"source_hw": 1}))
        if not result.get("ok"):
            return None, str(result.get("error") or "Actual position query failed")
        raw = str(result.get("response") or "").strip().strip('"')
        try:
            return int(raw), None
        except ValueError:
            return None, f"Unexpected actual position response: {raw}"

    async def set_start_position(self, value: int) -> tuple[bool, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.position.start", {"source_hw": 1, "value": int(value)}))
        return bool(result.get("ok")), None if result.get("ok") else str(result.get("error") or "Set start position failed")

    async def set_stop_position(self, value: int) -> tuple[bool, str | None]:
        result = await self._run(self.command_registry.resolve("scenario.position.stop", {"source_hw": 1, "value": int(value)}))
        return bool(result.get("ok")), None if result.get("ok") else str(result.get("error") or "Set stop position failed")

    async def set_replay_mode(self, mode: str) -> tuple[bool, str | None]:
        mode_value = mode.strip() if mode else ""
        result = await self._run(self.command_registry.resolve("scenario.replay_mode.set", {"source_hw": 1, "mode": mode_value}))
        return bool(result.get("ok")), None if result.get("ok") else str(result.get("error") or "Set replay mode failed")
