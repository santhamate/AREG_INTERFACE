from __future__ import annotations

import ftplib
import os
import posixpath
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol


TransferProtocol = Literal["ftp", "smb", "mapped_folder", "manual_usb"]


@dataclass
class TransferConfig:
    protocol: TransferProtocol
    host: str | None = None
    username: str = "instrument"
    password: str = "instrument"
    remote_dir: str = "/var/user/"
    mapped_root: str | None = None
    timeout_s: int = 15
    passive_mode: bool = True


@dataclass
class RemoteFile:
    name: str
    remote_path: str
    size: int | None
    modified_time: str | None
    extension: str
    is_directory: bool


@dataclass
class OperationResult:
    ok: bool
    message: str | None = None
    error: str | None = None
    warnings: list[str] | None = None


@dataclass
class TransferResult:
    ok: bool
    message: str | None = None
    local_path: str | None = None
    remote_path: str | None = None
    bytes_transferred: int = 0
    duration: float = 0.0
    error: str | None = None


class FileTransferBackend(Protocol):
    def connect(self, config: TransferConfig) -> OperationResult: ...

    def list_files(self, config: TransferConfig, remote_dir: str, filter_ext: str | None = None) -> list[RemoteFile]: ...

    def upload(self, config: TransferConfig, local_path: str, remote_dir: str, overwrite: bool = False) -> TransferResult: ...

    def download(self, config: TransferConfig, remote_path: str, local_dir: str, overwrite: bool = False) -> TransferResult: ...

    def mkdir(self, config: TransferConfig, remote_dir: str) -> OperationResult: ...

    def delete(self, config: TransferConfig, remote_path: str) -> OperationResult: ...

    def rename(self, config: TransferConfig, remote_path: str, new_name: str) -> OperationResult: ...

    def exists(self, config: TransferConfig, remote_path: str) -> bool: ...


class FtpTransferBackend:
    name = "ftp"

    def _connect(self, config: TransferConfig) -> ftplib.FTP:
        host = (config.host or "").strip()
        if not host:
            raise ValueError("FTP host is required")

        ftp = ftplib.FTP()
        ftp.connect(host=host, port=21, timeout=max(1, int(config.timeout_s)))
        ftp.login(config.username, config.password)
        ftp.set_pasv(config.passive_mode)
        return ftp

    @staticmethod
    def _join_remote(remote_dir: str, file_name: str) -> str:
        base = remote_dir.strip() or "/"
        if not base.startswith("/"):
            base = f"/{base}"
        return posixpath.join(base, file_name)

    @staticmethod
    def _to_iso_mdtm(mdtm_raw: str | None) -> str | None:
        if not mdtm_raw:
            return None
        if len(mdtm_raw) >= 14 and mdtm_raw[:14].isdigit():
            dt = datetime.strptime(mdtm_raw[:14], "%Y%m%d%H%M%S")
            return dt.isoformat()
        return None

    def connect(self, config: TransferConfig) -> OperationResult:
        try:
            ftp = self._connect(config)
            ftp.quit()
            return OperationResult(ok=True, message="FTP connection succeeded")
        except ValueError as ex:
            return OperationResult(ok=False, error=str(ex))
        except ftplib.error_perm as ex:
            return OperationResult(ok=False, error=f"FTP login/permission failed: {ex}")
        except OSError as ex:
            return OperationResult(ok=False, error=f"FTP connection failed: {ex}")

    def list_files(self, config: TransferConfig, remote_dir: str, filter_ext: str | None = None) -> list[RemoteFile]:
        files: list[RemoteFile] = []
        target = remote_dir.strip() or "/"

        with self._connect(config) as ftp:
            try:
                entries = list(ftp.mlsd(target))
                for name, facts in entries:
                    if name in (".", ".."):
                        continue
                    is_dir = facts.get("type") == "dir"
                    ext = Path(name).suffix.lower()
                    if filter_ext and filter_ext != "*" and ext != filter_ext.lower():
                        continue
                    size = int(facts["size"]) if facts.get("size", "").isdigit() else None
                    modified = self._to_iso_mdtm(facts.get("modify"))
                    files.append(
                        RemoteFile(
                            name=name,
                            remote_path=self._join_remote(target, name),
                            size=size,
                            modified_time=modified,
                            extension=ext,
                            is_directory=is_dir,
                        )
                    )
                return files
            except Exception:
                # Fallback for servers without MLSD support.
                names = ftp.nlst(target)
                for item in names:
                    name = posixpath.basename(item.rstrip("/"))
                    if name in (".", ".."):
                        continue
                    ext = Path(name).suffix.lower()
                    if filter_ext and filter_ext != "*" and ext != filter_ext.lower():
                        continue
                    size: int | None = None
                    modified: str | None = None
                    try:
                        size_raw = ftp.size(item)
                        if size_raw is not None:
                            size = int(size_raw)
                    except Exception:
                        pass
                    try:
                        modified = self._to_iso_mdtm(ftp.sendcmd(f"MDTM {item}").split(" ")[-1])
                    except Exception:
                        pass

                    files.append(
                        RemoteFile(
                            name=name,
                            remote_path=item,
                            size=size,
                            modified_time=modified,
                            extension=ext,
                            is_directory=False,
                        )
                    )
                return files

    def exists(self, config: TransferConfig, remote_path: str) -> bool:
        with self._connect(config) as ftp:
            try:
                if ftp.size(remote_path) is not None:
                    return True
            except Exception:
                pass

            parent = posixpath.dirname(remote_path) or "/"
            name = posixpath.basename(remote_path)
            try:
                return any(posixpath.basename(entry.rstrip("/")) == name for entry in ftp.nlst(parent))
            except Exception:
                return False

    def upload(self, config: TransferConfig, local_path: str, remote_dir: str, overwrite: bool = False) -> TransferResult:
        src = Path(local_path)
        if not src.exists() or not src.is_file():
            return TransferResult(ok=False, error=f"Local path missing: {local_path}")
        if src.stat().st_size == 0:
            return TransferResult(ok=False, error="Zero-byte files are not allowed")

        remote_path = self._join_remote(remote_dir, src.name)

        start = time.perf_counter()
        try:
            with self._connect(config) as ftp:
                if self.exists(config, remote_path) and not overwrite:
                    return TransferResult(
                        ok=False,
                        local_path=str(src),
                        remote_path=remote_path,
                        error="Remote file already exists (overwrite disabled)",
                    )

                with src.open("rb") as handle:
                    ftp.storbinary(f"STOR {remote_path}", handle)

            return TransferResult(
                ok=True,
                message="Upload completed",
                local_path=str(src),
                remote_path=remote_path,
                bytes_transferred=src.stat().st_size,
                duration=time.perf_counter() - start,
            )
        except ftplib.error_perm as ex:
            return TransferResult(ok=False, local_path=str(src), remote_path=remote_path, error=f"Permission denied: {ex}")
        except TimeoutError:
            return TransferResult(ok=False, local_path=str(src), remote_path=remote_path, error="Upload timeout")
        except OSError as ex:
            return TransferResult(ok=False, local_path=str(src), remote_path=remote_path, error=f"Upload failed: {ex}")

    def download(self, config: TransferConfig, remote_path: str, local_dir: str, overwrite: bool = False) -> TransferResult:
        dst_dir = Path(local_dir)
        if not dst_dir.exists() or not dst_dir.is_dir():
            return TransferResult(ok=False, remote_path=remote_path, local_path=local_dir, error=f"Local directory missing: {local_dir}")

        dst = dst_dir / posixpath.basename(remote_path)
        if dst.exists() and not overwrite:
            return TransferResult(ok=False, remote_path=remote_path, local_path=str(dst), error="Local file already exists (overwrite disabled)")

        start = time.perf_counter()
        bytes_count = 0
        try:
            with self._connect(config) as ftp:
                with dst.open("wb") as handle:
                    def _writer(chunk: bytes) -> None:
                        nonlocal bytes_count
                        bytes_count += len(chunk)
                        handle.write(chunk)

                    ftp.retrbinary(f"RETR {remote_path}", _writer)

            return TransferResult(
                ok=True,
                message="Download completed",
                local_path=str(dst),
                remote_path=remote_path,
                bytes_transferred=bytes_count,
                duration=time.perf_counter() - start,
            )
        except ftplib.error_perm as ex:
            return TransferResult(ok=False, remote_path=remote_path, local_path=str(dst), error=f"Permission denied: {ex}")
        except TimeoutError:
            return TransferResult(ok=False, remote_path=remote_path, local_path=str(dst), error="Download timeout")
        except OSError as ex:
            return TransferResult(ok=False, remote_path=remote_path, local_path=str(dst), error=f"Download failed: {ex}")

    def mkdir(self, config: TransferConfig, remote_dir: str) -> OperationResult:
        try:
            with self._connect(config) as ftp:
                ftp.mkd(remote_dir)
            return OperationResult(ok=True, message=f"Created directory: {remote_dir}")
        except ftplib.error_perm as ex:
            return OperationResult(ok=False, error=f"Cannot create directory: {ex}")
        except OSError as ex:
            return OperationResult(ok=False, error=f"Create directory failed: {ex}")

    def delete(self, config: TransferConfig, remote_path: str) -> OperationResult:
        try:
            with self._connect(config) as ftp:
                ftp.delete(remote_path)
            return OperationResult(ok=True, message=f"Deleted: {remote_path}")
        except ftplib.error_perm as ex:
            return OperationResult(ok=False, error=f"Cannot delete file: {ex}")
        except OSError as ex:
            return OperationResult(ok=False, error=f"Delete failed: {ex}")

    def rename(self, config: TransferConfig, remote_path: str, new_name: str) -> OperationResult:
        if not new_name.strip():
            return OperationResult(ok=False, error="New name is empty")
        target = posixpath.join(posixpath.dirname(remote_path), new_name)
        try:
            with self._connect(config) as ftp:
                ftp.rename(remote_path, target)
            return OperationResult(ok=True, message=f"Renamed to: {target}")
        except ftplib.error_perm as ex:
            return OperationResult(ok=False, error=f"Rename denied: {ex}")
        except OSError as ex:
            return OperationResult(ok=False, error=f"Rename failed: {ex}")


class MappedFolderTransferBackend:
    name = "mapped_folder"

    @staticmethod
    def _root(config: TransferConfig) -> Path:
        root = (config.mapped_root or "").strip()
        if not root:
            raise ValueError("Mapped root path is required for SMB/mapped-folder mode")
        return Path(root)

    @staticmethod
    def _resolve_under_root(root: Path, remote_path: str) -> Path:
        rel = remote_path.replace("\\", "/").lstrip("/")
        target = (root / rel).resolve()
        root_resolved = root.resolve()

        if os.path.commonpath([str(root_resolved), str(target)]) != str(root_resolved):
            raise ValueError("Path escapes mapped root")
        return target

    def connect(self, config: TransferConfig) -> OperationResult:
        try:
            root = self._root(config)
            if not root.exists() or not root.is_dir():
                return OperationResult(ok=False, error=f"Mapped folder not accessible: {root}")
            return OperationResult(ok=True, message="Mapped folder is accessible")
        except Exception as ex:
            return OperationResult(ok=False, error=str(ex))

    def list_files(self, config: TransferConfig, remote_dir: str, filter_ext: str | None = None) -> list[RemoteFile]:
        root = self._root(config)
        target_dir = self._resolve_under_root(root, remote_dir or "/")
        if not target_dir.exists() or not target_dir.is_dir():
            return []

        files: list[RemoteFile] = []
        for child in target_dir.iterdir():
            ext = child.suffix.lower()
            if filter_ext and filter_ext != "*" and ext != filter_ext.lower():
                continue
            stat = child.stat()
            files.append(
                RemoteFile(
                    name=child.name,
                    remote_path=f"/{child.relative_to(root).as_posix()}",
                    size=None if child.is_dir() else stat.st_size,
                    modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    extension=ext,
                    is_directory=child.is_dir(),
                )
            )
        return sorted(files, key=lambda item: (item.is_directory is False, item.name.lower()))

    def exists(self, config: TransferConfig, remote_path: str) -> bool:
        root = self._root(config)
        target = self._resolve_under_root(root, remote_path)
        return target.exists()

    def upload(self, config: TransferConfig, local_path: str, remote_dir: str, overwrite: bool = False) -> TransferResult:
        src = Path(local_path)
        if not src.exists() or not src.is_file():
            return TransferResult(ok=False, local_path=local_path, error=f"Local path missing: {local_path}")
        if src.stat().st_size == 0:
            return TransferResult(ok=False, local_path=local_path, error="Zero-byte files are not allowed")

        root = self._root(config)
        dst_dir = self._resolve_under_root(root, remote_dir or "/")
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name

        if dst.exists() and not overwrite:
            return TransferResult(ok=False, local_path=str(src), remote_path=f"/{dst.relative_to(root).as_posix()}", error="Remote file already exists (overwrite disabled)")

        start = time.perf_counter()
        shutil.copy2(src, dst)
        return TransferResult(
            ok=True,
            message="Upload completed",
            local_path=str(src),
            remote_path=f"/{dst.relative_to(root).as_posix()}",
            bytes_transferred=dst.stat().st_size,
            duration=time.perf_counter() - start,
        )

    def download(self, config: TransferConfig, remote_path: str, local_dir: str, overwrite: bool = False) -> TransferResult:
        root = self._root(config)
        src = self._resolve_under_root(root, remote_path)
        if not src.exists() or not src.is_file():
            return TransferResult(ok=False, remote_path=remote_path, error=f"Remote file missing: {remote_path}")

        dst_dir = Path(local_dir)
        if not dst_dir.exists() or not dst_dir.is_dir():
            return TransferResult(ok=False, remote_path=remote_path, local_path=local_dir, error=f"Local directory missing: {local_dir}")

        dst = dst_dir / src.name
        if dst.exists() and not overwrite:
            return TransferResult(ok=False, remote_path=remote_path, local_path=str(dst), error="Local file already exists (overwrite disabled)")

        start = time.perf_counter()
        shutil.copy2(src, dst)
        return TransferResult(
            ok=True,
            message="Download completed",
            local_path=str(dst),
            remote_path=remote_path,
            bytes_transferred=dst.stat().st_size,
            duration=time.perf_counter() - start,
        )

    def mkdir(self, config: TransferConfig, remote_dir: str) -> OperationResult:
        root = self._root(config)
        target = self._resolve_under_root(root, remote_dir)
        target.mkdir(parents=True, exist_ok=True)
        return OperationResult(ok=True, message=f"Created directory: {remote_dir}")

    def delete(self, config: TransferConfig, remote_path: str) -> OperationResult:
        root = self._root(config)
        target = self._resolve_under_root(root, remote_path)
        if not target.exists():
            return OperationResult(ok=False, error=f"Path does not exist: {remote_path}")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return OperationResult(ok=True, message=f"Deleted: {remote_path}")

    def rename(self, config: TransferConfig, remote_path: str, new_name: str) -> OperationResult:
        if not new_name.strip():
            return OperationResult(ok=False, error="New name is empty")

        root = self._root(config)
        src = self._resolve_under_root(root, remote_path)
        if not src.exists():
            return OperationResult(ok=False, error=f"Path does not exist: {remote_path}")

        dst = src.with_name(new_name)
        src.rename(dst)
        return OperationResult(ok=True, message=f"Renamed to: /{dst.relative_to(root).as_posix()}")


class AregFileTransferService:
    """Protocol-independent file transfer manager for AREG workflows."""

    DEFAULT_USER = "instrument"
    DEFAULT_PASSWORD = "instrument"

    def __init__(self) -> None:
        self._ftp = FtpTransferBackend()
        self._mapped = MappedFolderTransferBackend()

    def _resolve_backend(self, protocol: TransferProtocol) -> FileTransferBackend:
        if protocol == "ftp":
            return self._ftp
        if protocol in ("smb", "mapped_folder"):
            return self._mapped
        raise ValueError(f"Unsupported transfer protocol: {protocol}")

    @staticmethod
    def _filter_ext_value(file_filter: str, custom_ext: str | None = None) -> str | None:
        mapping = {
            "all": None,
            "osi": ".osi",
            "scpi": ".scpi",
            "txt": ".txt",
            "csv": ".csv",
        }
        if file_filter == "custom":
            if not custom_ext:
                return None
            ext = custom_ext.strip().lower()
            return ext if ext.startswith(".") else f".{ext}"
        return mapping.get(file_filter, None)

    @staticmethod
    def _credential_warning(config: TransferConfig) -> list[str]:
        if config.username == AregFileTransferService.DEFAULT_USER and config.password == AregFileTransferService.DEFAULT_PASSWORD:
            return [
                "Factory default credentials are in use (instrument/instrument). "
                "Rohde & Schwarz recommends changing this password before using network file access."
            ]
        return []

    @staticmethod
    def _guess_likely_causes(error: str | None) -> list[str]:
        text = (error or "").lower()
        causes: list[str] = []
        if any(token in text for token in ("login", "530", "authentication", "credential")):
            causes.append("Wrong username/password or FTP login disabled")
        if any(token in text for token in ("timed out", "timeout", "unreachable", "refused")):
            causes.append("Wrong IP address, LAN service disabled, or firewall is blocking access")
        if any(token in text for token in ("permission", "denied", "protected", "read-only")):
            causes.append("Write protection may still be active; enable Volatile Mode and reboot if requested")
        if "not found" in text or "missing" in text:
            causes.append("Target directory or path does not exist")
        if "samba" in text or "mapped" in text:
            causes.append("SMB share is not mapped or not accessible from Windows")
        if not causes:
            causes.append("Verify FTP/SMB services are enabled and LAN settings are correct on the instrument")
        return causes

    def test_connection(self, config: TransferConfig) -> OperationResult:
        warnings = self._credential_warning(config)

        if config.protocol == "manual_usb":
            return OperationResult(ok=True, message="Manual USB workflow selected", warnings=warnings)

        try:
            backend = self._resolve_backend(config.protocol)
            result = backend.connect(config)
            result.warnings = (result.warnings or []) + warnings
            return result
        except Exception as ex:
            return OperationResult(ok=False, error=str(ex), warnings=warnings)

    def list_files(
        self,
        config: TransferConfig,
        remote_dir: str,
        file_filter: str = "all",
        custom_ext: str | None = None,
    ) -> tuple[list[RemoteFile], OperationResult]:
        warnings = self._credential_warning(config)

        if config.protocol == "manual_usb":
            return [], OperationResult(
                ok=False,
                error="Manual USB mode does not support direct remote listing from the app",
                warnings=warnings,
            )

        try:
            backend = self._resolve_backend(config.protocol)
            ext = self._filter_ext_value(file_filter, custom_ext)
            files = backend.list_files(config, remote_dir=remote_dir, filter_ext=ext)
            return files, OperationResult(ok=True, message=f"Found {len(files)} item(s)", warnings=warnings)
        except Exception as ex:
            err = str(ex)
            return [], OperationResult(ok=False, error=err, warnings=warnings + self._guess_likely_causes(err))

    def upload_file(self, config: TransferConfig, local_path: str, remote_dir: str, overwrite: bool = False) -> TransferResult:
        if not local_path:
            return TransferResult(ok=False, error="Local path missing")

        if config.protocol == "manual_usb":
            return TransferResult(ok=False, error="Manual USB mode: copy files using AREG File Manager, then refresh")

        try:
            backend = self._resolve_backend(config.protocol)
            return backend.upload(config, local_path=local_path, remote_dir=remote_dir, overwrite=overwrite)
        except Exception as ex:
            err = str(ex)
            return TransferResult(ok=False, local_path=local_path, remote_path=remote_dir, error=err)

    def download_file(self, config: TransferConfig, remote_path: str, local_dir: str, overwrite: bool = False) -> TransferResult:
        if config.protocol == "manual_usb":
            return TransferResult(ok=False, error="Manual USB mode: copy files directly from USB device")

        try:
            backend = self._resolve_backend(config.protocol)
            return backend.download(config, remote_path=remote_path, local_dir=local_dir, overwrite=overwrite)
        except Exception as ex:
            return TransferResult(ok=False, remote_path=remote_path, local_path=local_dir, error=str(ex))

    def create_directory(self, config: TransferConfig, remote_dir: str) -> OperationResult:
        if config.protocol == "manual_usb":
            return OperationResult(ok=False, error="Manual USB mode does not support remote directory creation")
        try:
            backend = self._resolve_backend(config.protocol)
            return backend.mkdir(config, remote_dir)
        except Exception as ex:
            return OperationResult(ok=False, error=str(ex))

    def delete_remote(self, config: TransferConfig, remote_path: str) -> OperationResult:
        if config.protocol == "manual_usb":
            return OperationResult(ok=False, error="Manual USB mode does not support remote delete")
        try:
            backend = self._resolve_backend(config.protocol)
            return backend.delete(config, remote_path)
        except Exception as ex:
            return OperationResult(ok=False, error=str(ex))

    def rename_remote(self, config: TransferConfig, remote_path: str, new_name: str) -> OperationResult:
        if config.protocol == "manual_usb":
            return OperationResult(ok=False, error="Manual USB mode does not support remote rename")
        try:
            backend = self._resolve_backend(config.protocol)
            return backend.rename(config, remote_path, new_name)
        except Exception as ex:
            return OperationResult(ok=False, error=str(ex))

    def scan_remote_osi_files(self, config: TransferConfig, remote_dir: str = "/var/user/") -> tuple[list[RemoteFile], OperationResult]:
        return self.list_files(config=config, remote_dir=remote_dir, file_filter="osi")

    def upload_osi_file(self, config: TransferConfig, local_path: str, remote_dir: str = "/var/user/", overwrite: bool = False) -> TransferResult:
        if not local_path.lower().endswith(".osi"):
            return TransferResult(ok=False, local_path=local_path, error="Only .osi files are allowed for OSI upload")
        return self.upload_file(config=config, local_path=local_path, remote_dir=remote_dir, overwrite=overwrite)

    def download_osi_file(self, config: TransferConfig, remote_path: str, local_dir: str, overwrite: bool = False) -> TransferResult:
        if not remote_path.lower().endswith(".osi"):
            return TransferResult(ok=False, remote_path=remote_path, error="Selected remote file is not an .osi file")
        return self.download_file(config=config, remote_path=remote_path, local_dir=local_dir, overwrite=overwrite)

    def preflight_checklist(self, config: TransferConfig, remote_dir: str, need_write: bool) -> dict[str, object]:
        test = self.test_connection(config)

        items = [
            {
                "name": "Instrument IP/hostname is provided",
                "status": "pass" if bool((config.host or "").strip()) or config.protocol in ("smb", "mapped_folder", "manual_usb") else "fail",
            },
            {
                "name": "Target protocol service is enabled on AREG (FTP/SMB)",
                "status": "pass" if test.ok else "warn",
            },
            {
                "name": "Credentials are configured",
                "status": "pass" if bool(config.username.strip()) and bool(config.password.strip()) else "fail",
            },
            {
                "name": "Target directory is set (recommended: /var/user/)",
                "status": "pass" if bool((remote_dir or "").strip()) else "fail",
            },
            {
                "name": "Connection test passed",
                "status": "pass" if test.ok else "fail",
            },
        ]

        if need_write:
            items.append(
                {
                    "name": "Write permission enabled (Volatile Mode, reboot if requested)",
                    "status": "warn",
                }
            )

        likely_causes = self._guess_likely_causes(test.error) if not test.ok else []

        return {
            "ok": test.ok,
            "items": items,
            "warnings": test.warnings or [],
            "likely_causes": likely_causes,
            "message": test.message,
            "error": test.error,
        }

    @staticmethod
    def setup_help() -> dict[str, list[str]]:
        return {
            "ftp": [
                "On AREG, enable write permission (Volatile Mode) under Security > Disk & Memory.",
                "Enable LAN and FTP service in Security > LAN Services.",
                "Reboot if requested by AREG after security change.",
                "Use ftp://<instrument_ip> and instrument credentials.",
                "Use /var/user/ as the preferred working directory.",
            ],
            "smb": [
                "Enable write permission (Volatile Mode) and LAN Interface.",
                "Enable Samba Services and SMB Client/Server (1.0/2.0 as required).",
                "Map //<instrument_ip>/user or //<hostname>/user as a Windows drive.",
                "Use mapped drive/folder path in the app (Mapped Folder mode).",
            ],
            "usb": [
                "Enable USB Storage and write permission on AREG.",
                "Use AREG File Manager to copy files from /usb/ to /var/user/.",
                "Prefer running scenarios from /var/user/ rather than directly from USB.",
            ],
        }
