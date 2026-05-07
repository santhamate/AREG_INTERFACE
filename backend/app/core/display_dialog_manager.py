from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.app.core.scpi_service import ScpiService


@dataclass
class DialogPreset:
    name: str
    dialog_id: str
    region: str


class DisplayDialogManager:
    """Manage documented AREG display dialog commands before hardcopy capture."""

    def __init__(self, scpi_service: ScpiService) -> None:
        self.scpi_service = scpi_service
        self._presets: dict[str, DialogPreset] = {}
        self._last_dialogs: list[dict[str, Any]] = []

    @staticmethod
    def _ts() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _quote(value: str) -> str:
        escaped = value.replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _parse_dialog_tokens(raw_dialog_id: str) -> dict[str, Any]:
        tokens = [t for t in raw_dialog_id.split(":") if t]
        dialog_name = tokens[0] if tokens else raw_dialog_id
        qualifier = tokens[1] if len(tokens) > 1 else None
        instance_data = tokens[2] if len(tokens) > 2 else None
        tab_data = tokens[3] if len(tokens) > 3 else None

        def unescape(token: str | None) -> str | None:
            if token is None:
                return None
            return token.replace("$$", " ")

        display_name = unescape(dialog_name) or raw_dialog_id
        pieces = [display_name]
        if qualifier:
            pieces.append(f"[{unescape(qualifier)}]")
        if tab_data:
            pieces.append(f"tab={unescape(tab_data)}")

        return {
            "raw_id": raw_dialog_id,
            "dialog_name": dialog_name,
            "qualifier": qualifier,
            "instance_data": instance_data,
            "tab_data": tab_data,
            "user_label": " ".join(pieces),
        }

    @staticmethod
    def _parse_dialog_id_response(raw: str) -> list[str]:
        text = raw.strip()
        if not text:
            return []
        # Instrument returns a quoted string; strip surrounding quotes if present.
        # Dialog IDs are always whitespace-separated — no commas, ever.
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return [token for token in text.split() if token]

    async def query_open_dialogs(self) -> dict[str, Any]:
        log: list[dict[str, Any]] = []
        result = await self.scpi_service.execute_with_classification(":DISPlay:DIALog:ID?")
        log.append({
            "timestamp": self._ts(),
            "command": ":DISPlay:DIALog:ID?",
            "ok": result.get("ok", False),
            "command_type": result.get("command_type"),
            "response": result.get("response"),
            "error": result.get("error"),
        })

        if not result.get("ok"):
            return {
                "ok": False,
                "dialogs": [],
                "raw_response": None,
                "error": result.get("error") or "Dialog query failed",
                "log": log,
            }

        raw_response = str(result.get("response") or "").strip()
        dialog_ids = self._parse_dialog_id_response(raw_response)
        dialogs = [self._parse_dialog_tokens(dialog_id) for dialog_id in dialog_ids]
        self._last_dialogs = dialogs

        return {
            "ok": True,
            "dialogs": dialogs,
            "raw_response": raw_response,
            "error": None,
            "log": log,
        }

    async def open_dialog(self, dialog_id: str, delay_ms: int = 500, verify: bool = False) -> dict[str, Any]:
        dialog_id = dialog_id.strip()
        if not dialog_id:
            return {"ok": False, "error": "Dialog ID is required.", "log": [], "verified": None, "dialogs": []}

        command = f":DISPlay:DIALog:OPEN {self._quote(dialog_id)}"
        log: list[dict[str, Any]] = []

        open_result = await self.scpi_service.execute_with_classification(command)
        log.append({
            "timestamp": self._ts(),
            "command": command,
            "ok": open_result.get("ok", False),
            "command_type": open_result.get("command_type"),
            "response": open_result.get("response"),
            "error": open_result.get("error"),
        })

        if not open_result.get("ok"):
            return {
                "ok": False,
                "error": open_result.get("error") or "Failed to open dialog",
                "log": log,
                "verified": None,
                "dialogs": [],
            }

        await asyncio.sleep(max(0, delay_ms) / 1000)

        if not verify:
            return {"ok": True, "error": None, "log": log, "verified": None, "dialogs": []}

        verify_result = await self.query_open_dialogs()
        log.extend(verify_result.get("log", []))
        dialogs = verify_result.get("dialogs", [])
        verified = any(d.get("raw_id") == dialog_id for d in dialogs)

        return {
            "ok": verify_result.get("ok", False) and verified,
            "error": None if verified else "Dialog open verification failed.",
            "log": log,
            "verified": verified,
            "dialogs": dialogs,
        }

    async def close_dialog(self, dialog_id: str) -> dict[str, Any]:
        dialog_id = dialog_id.strip()
        if not dialog_id:
            return {"ok": False, "error": "Dialog ID is required.", "log": []}

        command = f":DISPlay:DIALog:CLOSe {self._quote(dialog_id)}"
        result = await self.scpi_service.execute_with_classification(command)
        return {
            "ok": bool(result.get("ok")),
            "error": None if result.get("ok") else result.get("error") or "Failed to close dialog",
            "log": [{
                "timestamp": self._ts(),
                "command": command,
                "ok": result.get("ok", False),
                "command_type": result.get("command_type"),
                "response": result.get("response"),
                "error": result.get("error"),
            }],
        }

    async def close_all_dialogs(self) -> dict[str, Any]:
        command = ":DISPlay:DIALog:CLOSe:ALL"
        result = await self.scpi_service.execute_with_classification(command)
        return {
            "ok": bool(result.get("ok")),
            "error": None if result.get("ok") else result.get("error") or "Failed to close all dialogs",
            "log": [{
                "timestamp": self._ts(),
                "command": command,
                "ok": result.get("ok", False),
                "command_type": result.get("command_type"),
                "response": result.get("response"),
                "error": result.get("error"),
            }],
        }

    def create_dialog_preset(self, name: str, dialog_id: str, region: str) -> dict[str, Any]:
        preset_name = name.strip()
        preset_dialog_id = dialog_id.strip()
        preset_region = region.strip().upper()

        if not preset_name:
            return {"ok": False, "error": "Preset name is required.", "preset": None}
        if not preset_dialog_id:
            return {"ok": False, "error": "Dialog ID is required.", "preset": None}
        if preset_region not in {"ALL", "DIALOG"}:
            return {"ok": False, "error": "Region must be ALL or DIALOG.", "preset": None}

        self._presets[preset_name] = DialogPreset(
            name=preset_name,
            dialog_id=preset_dialog_id,
            region="DIALog" if preset_region == "DIALOG" else preset_region,
        )
        return {"ok": True, "error": None, "preset": self._preset_to_dict(self._presets[preset_name])}

    def list_dialog_presets(self) -> list[dict[str, Any]]:
        return [self._preset_to_dict(p) for p in self._presets.values()]

    def get_dialog_preset(self, name: str) -> dict[str, Any] | None:
        preset = self._presets.get(name)
        return self._preset_to_dict(preset) if preset else None

    async def run_pre_hardcopy_navigation(
        self,
        target_type: str,
        dialog_id: str | None,
        preset_name: str | None,
        delay_ms: int,
        verify: bool,
    ) -> dict[str, Any]:
        normalized = (target_type or "current_screen").strip().lower()

        if normalized in {"current_screen", "current_active_dialog"}:
            return {"ok": True, "error": None, "target_dialog_id": None, "log": [], "dialogs": []}

        selected_dialog_id = (dialog_id or "").strip()
        if normalized == "preset":
            preset = self._presets.get((preset_name or "").strip())
            if not preset:
                return {
                    "ok": False,
                    "error": "Dialog ID for this screen is not known. Open it manually once, scan open dialogs, then save it as a preset.",
                    "target_dialog_id": None,
                    "log": [],
                    "dialogs": [],
                }
            selected_dialog_id = preset.dialog_id

        if not selected_dialog_id:
            return {
                "ok": False,
                "error": "Dialog ID for this screen is not known. Open it manually once, scan open dialogs, then save it as a preset.",
                "target_dialog_id": None,
                "log": [],
                "dialogs": [],
            }

        open_result = await self.open_dialog(selected_dialog_id, delay_ms=delay_ms, verify=verify)
        return {
            "ok": open_result.get("ok", False),
            "error": open_result.get("error"),
            "target_dialog_id": selected_dialog_id,
            "log": open_result.get("log", []),
            "dialogs": open_result.get("dialogs", []),
            "verified": open_result.get("verified"),
        }

    @staticmethod
    def _preset_to_dict(preset: DialogPreset | None) -> dict[str, Any] | None:
        if preset is None:
            return None
        return {
            "name": preset.name,
            "dialog_id": preset.dialog_id,
            "region": preset.region,
        }
