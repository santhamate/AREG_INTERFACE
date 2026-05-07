from __future__ import annotations

from backend.app.core.memory_manager import MemoryManager


class StorageScanner:
    """Discover visible instrument/removable storage roots using MMEMory catalog commands."""

    CANDIDATE_ROOTS = [
        "/var/user",
        "./usb",
        "./usb0",
        "./usb1",
        "./sd",
        "./sdcard",
        "/usb",
        "/usb0",
        "/usb1",
        "/sd",
        "/sdcard",
        "/mmc",
    ]

    def __init__(self, memory_manager: MemoryManager) -> None:
        self.memory_manager = memory_manager

    async def discover_visible_roots(self) -> tuple[list[str], list[str]]:
        visible: list[str] = []
        errors: list[str] = []
        for root in self.CANDIDATE_ROOTS:
            entries, error = await self.memory_manager.list_directory(root)
            if error:
                errors.append(f"{root}: {error}")
                continue
            # successful response (including empty dir) counts as visible
            _ = entries
            visible.append(self.memory_manager.normalize_path(root))
        return list(dict.fromkeys(visible)), errors
