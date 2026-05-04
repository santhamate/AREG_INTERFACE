from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from typing import Protocol


@dataclass
class FileTransferResult:
    ok: bool
    method: str
    local_path: str
    remote_path: str
    bytes_transferred: int
    error: str | None = None


class FileTransferAdapter(Protocol):
    name: str

    def transfer(self, local_path: Path, remote_path: Path) -> FileTransferResult:
        """Transfer a file from local_path to remote_path."""


class LocalCopyTransfer:
    """Simple transfer adapter that copies files on the local filesystem."""

    name = "local_copy"

    def transfer(self, local_path: Path, remote_path: Path) -> FileTransferResult:
        if not local_path.exists():
            return FileTransferResult(
                ok=False,
                method=self.name,
                local_path=str(local_path),
                remote_path=str(remote_path),
                bytes_transferred=0,
                error=f"Source file does not exist: {local_path}",
            )

        if not local_path.is_file():
            return FileTransferResult(
                ok=False,
                method=self.name,
                local_path=str(local_path),
                remote_path=str(remote_path),
                bytes_transferred=0,
                error=f"Source path is not a file: {local_path}",
            )

        try:
            remote_path.parent.mkdir(parents=True, exist_ok=True)
            copy2(local_path, remote_path)
            bytes_transferred = remote_path.stat().st_size
            return FileTransferResult(
                ok=True,
                method=self.name,
                local_path=str(local_path),
                remote_path=str(remote_path),
                bytes_transferred=bytes_transferred,
                error=None,
            )
        except OSError as ex:
            return FileTransferResult(
                ok=False,
                method=self.name,
                local_path=str(local_path),
                remote_path=str(remote_path),
                bytes_transferred=0,
                error=str(ex),
            )


class FileTransferService:
    """Registry-based transfer service for scenario files."""

    def __init__(self) -> None:
        self._adapters: dict[str, FileTransferAdapter] = {}
        self.register(LocalCopyTransfer())

    def register(self, adapter: FileTransferAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def available_methods(self) -> list[str]:
        return sorted(self._adapters.keys())

    def transfer(self, local_path: Path, remote_path: Path, method: str = "local_copy") -> FileTransferResult:
        adapter = self._adapters.get(method)
        if adapter is None:
            return FileTransferResult(
                ok=False,
                method=method,
                local_path=str(local_path),
                remote_path=str(remote_path),
                bytes_transferred=0,
                error=f"Unsupported transfer method: {method}",
            )
        return adapter.transfer(local_path, remote_path)
