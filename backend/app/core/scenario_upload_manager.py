from __future__ import annotations

from backend.app.core.memory_manager import MemoryManager


class ScenarioUploadManager:
    """Upload/copy helper that enforces copy-to-/var/user workflow before playback."""

    def __init__(self, memory_manager: MemoryManager) -> None:
        self.memory_manager = memory_manager

    @staticmethod
    def _join(dst_dir: str, file_name: str) -> str:
        base = dst_dir.rstrip("/") or "/"
        if base == "/":
            return f"/{file_name}"
        return f"{base}/{file_name}"

    async def copy_to_user_directory(self, source_path: str, target_dir: str = "/var/user") -> tuple[str | None, str | None]:
        src = self.memory_manager.normalize_path(source_path)
        dst_root = self.memory_manager.normalize_path(target_dir)
        filename = src.split("/")[-1]
        dst = self._join(dst_root, filename)

        ok, error = await self.memory_manager.copy_file(src, dst)
        if not ok:
            return None, error
        return dst, None
