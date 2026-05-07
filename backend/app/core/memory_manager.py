from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.core.command_registry import CommandRegistryService
from backend.app.core.scpi_service import ScpiService


@dataclass
class MemoryEntry:
    name: str
    kind: str
    size: int | None
    full_path: str
    extension: str


class MemoryManager:
    """Manual-aligned MMEMory manager for AREG800A file and directory operations."""

    def __init__(self, scpi_service: ScpiService, command_registry: CommandRegistryService | None = None) -> None:
        self.scpi_service = scpi_service
        self.command_registry = command_registry or CommandRegistryService()

    @staticmethod
    def normalize_path(path: str) -> str:
        value = (path or "").strip().replace("\\", "/")
        value = re.sub(r"/{2,}", "/", value)
        if not value:
            return "/var/user"
        if value.startswith("./"):
            return value.rstrip("/") or "./"
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/") or "/"

    @staticmethod
    def _q(path: str) -> str:
        safe = path.replace('"', '""')
        return f'"{safe}"'

    async def _query(self, command: str) -> tuple[bool, str | None, str | None]:
        result = await self.scpi_service.execute_with_classification(command)
        if not result.get("ok"):
            return False, None, str(result.get("error") or "Command failed")
        return True, str(result.get("response") or ""), None

    async def _write(self, command: str) -> tuple[bool, str | None]:
        result = await self.scpi_service.execute_with_classification(command)
        if not result.get("ok"):
            return False, str(result.get("error") or "Command failed")
        return True, None

    async def get_current_directory(self) -> tuple[str | None, str | None]:
        cmd = self.command_registry.resolve("memory.cdir.query")
        ok, response, error = await self._query(cmd)
        if not ok:
            return None, error
        return (response or "").strip().strip('"') or None, None

    async def set_default_directory(self, path: str) -> tuple[bool, str | None]:
        normalized = self.normalize_path(path)
        cmd = self.command_registry.resolve("memory.cdir.set", {"path": normalized})
        return await self._write(cmd)

    async def list_directory(self, path: str | None = None) -> tuple[list[MemoryEntry], str | None]:
        if path:
            normalized = self.normalize_path(path)
            cmd = self.command_registry.resolve("memory.catalog", {"path": normalized})
        else:
            cmd = "MMEMory:CATalog?"
            normalized = "/"

        ok, response, error = await self._query(cmd)
        if not ok:
            return [], error
        return self._parse_catalog(response or "", normalized), None

    async def list_subdirectories(self, path: str) -> tuple[list[str], str | None]:
        normalized = self.normalize_path(path)
        cmd = self.command_registry.resolve("memory.dcatalog", {"path": normalized})
        ok, response, error = await self._query(cmd)
        if not ok:
            return [], error

        dirs: list[str] = []
        for item in self._split_catalog_records(response or ""):
            if not item:
                continue
            name = item[0]
            if name in {".", ".."}:
                continue
            if name.startswith("/"):
                dirs.append(name)
            else:
                base = normalized.rstrip("/") or "/"
                dirs.append(f"{base}/{name}" if base != "/" else f"/{name}")
        return list(dict.fromkeys(dirs)), None

    async def count_files(self, path: str) -> tuple[int | None, str | None]:
        normalized = self.normalize_path(path)
        cmd = self.command_registry.resolve("memory.catalog.length", {"path": normalized})
        ok, response, error = await self._query(cmd)
        if not ok:
            return None, error
        try:
            return int((response or "").strip().strip('"')), None
        except ValueError:
            return None, f"Unexpected file count response: {response}"

    async def count_subdirectories(self, path: str) -> tuple[int | None, str | None]:
        normalized = self.normalize_path(path)
        cmd = self.command_registry.resolve("memory.dcatalog.length", {"path": normalized})
        ok, response, error = await self._query(cmd)
        if not ok:
            return None, error
        try:
            return int((response or "").strip().strip('"')), None
        except ValueError:
            return None, f"Unexpected subdirectory count response: {response}"

    async def create_directory(self, path: str) -> tuple[bool, str | None]:
        normalized = self.normalize_path(path)
        cmd = self.command_registry.resolve("memory.mkdir", {"path": normalized})
        return await self._write(cmd)

    async def copy_file(self, src: str, dst: str) -> tuple[bool, str | None]:
        cmd = self.command_registry.resolve(
            "memory.copy",
            {"src": self.normalize_path(src), "dst": self.normalize_path(dst)},
        )
        return await self._write(cmd)

    async def rename_or_move(self, src: str, dst: str) -> tuple[bool, str | None]:
        cmd = self.command_registry.resolve(
            "memory.move",
            {"src": self.normalize_path(src), "dst": self.normalize_path(dst)},
        )
        return await self._write(cmd)

    async def delete_file(self, path: str) -> tuple[bool, str | None]:
        # TODO(manual): Delete-file MMEMory command is not explicitly documented in the
        # provided manual excerpt. Implement once the exact command is confirmed.
        return False, "Delete file command is not implemented: missing explicit manual reference"

    async def delete_empty_directory(self, path: str) -> tuple[bool, str | None]:
        normalized = self.normalize_path(path)
        cmd = self.command_registry.resolve("memory.rdir", {"path": normalized})
        return await self._write(cmd)

    async def delete_directory_recursive(self, path: str) -> tuple[bool, str | None]:
        normalized = self.normalize_path(path)
        cmd = self.command_registry.resolve("memory.rdir.recursive", {"path": normalized})
        return await self._write(cmd)

    @staticmethod
    def _split_catalog_records(response: str) -> list[list[str]]:
        clean = (response or "").strip()
        if not clean:
            return []
        if "\n" in clean and '"' not in clean:
            return [[line.strip()] for line in clean.splitlines() if line.strip()]

        parts = re.split(r'",\s*"', clean.strip('"'))
        rows: list[list[str]] = []
        for part in parts:
            if not part:
                continue
            rows.append([token.strip().strip('"') for token in part.split(",")])
        return rows

    def _parse_catalog(self, response: str, base_dir: str) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        rows = self._split_catalog_records(response)
        base = self.normalize_path(base_dir)
        for row in rows:
            if not row:
                continue
            name = row[0].strip()
            if not name or name in {".", ".."}:
                continue

            # Skip free/total header rows from some MMEMory responses.
            if name.isdigit() and len(row) > 1 and row[1].isdigit():
                continue

            raw_kind = row[1].strip().upper() if len(row) > 1 else ""
            size: int | None = None
            for token in row[2:] if len(row) > 2 else []:
                try:
                    size = int(token)
                    break
                except ValueError:
                    continue

            if name.startswith("/") or name.startswith("./"):
                full_path = self.normalize_path(name)
            else:
                root = base.rstrip("/") or "/"
                full_path = f"{root}/{name}" if root != "/" else f"/{name}"

            ext = ""
            if "." in name and not raw_kind.startswith("DIR"):
                ext = f".{name.split('.')[-1].lower()}"

            entries.append(
                MemoryEntry(
                    name=name,
                    kind=("DIR" if raw_kind.startswith("DIR") else (raw_kind or "FILE")),
                    size=size,
                    full_path=full_path,
                    extension=ext,
                )
            )
        return entries
