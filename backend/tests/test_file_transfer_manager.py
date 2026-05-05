from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.file_transfer_manager import (
    AregFileTransferService,
    FtpTransferBackend,
    TransferConfig,
)


def test_ftp_connection_config_validation_missing_host() -> None:
    backend = FtpTransferBackend()
    cfg = TransferConfig(protocol="ftp", host="", username="instrument", password="instrument")
    result = backend.connect(cfg)
    assert result.ok is False
    assert result.error is not None
    assert "host" in result.error.lower() or "connection" in result.error.lower()


def test_filtering_only_osi_files_with_mapped_folder(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    remote_root.mkdir()
    (remote_root / "a.osi").write_bytes(b"abc")
    (remote_root / "b.txt").write_text("x", encoding="utf-8")

    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="mapped_folder", mapped_root=str(remote_root))

    files, op = svc.list_files(cfg, remote_dir="/", file_filter="osi")
    assert op.ok
    assert len(files) == 1
    assert files[0].name == "a.osi"


def test_local_to_remote_path_conversion_mapped_mode(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    remote_root.mkdir()

    local_file = tmp_path / "scenario.osi"
    local_file.write_bytes(b"1234")

    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="mapped_folder", mapped_root=str(remote_root))

    result = svc.upload_file(cfg, local_path=str(local_file), remote_dir="/var/user", overwrite=False)
    assert result.ok
    assert result.remote_path is not None
    assert result.remote_path.endswith("/var/user/scenario.osi")


def test_overwrite_protection(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    target_dir = remote_root / "var" / "user"
    target_dir.mkdir(parents=True)
    (target_dir / "scenario.osi").write_bytes(b"old")

    local_file = tmp_path / "scenario.osi"
    local_file.write_bytes(b"new")

    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="mapped_folder", mapped_root=str(remote_root))

    result = svc.upload_file(cfg, local_path=str(local_file), remote_dir="/var/user", overwrite=False)
    assert result.ok is False
    assert result.error is not None
    assert "exists" in result.error.lower()


def test_remote_file_list_parsing_mdtm_iso() -> None:
    assert FtpTransferBackend._to_iso_mdtm("20260427130045") == "2026-04-27T13:00:45"


def test_invalid_credentials_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="ftp", host="192.0.2.1", username="bad", password="bad")

    def fake_connect(_config: TransferConfig):
        from backend.app.core.file_transfer_manager import OperationResult

        return OperationResult(ok=False, error="FTP login/permission failed: 530 Login incorrect")

    monkeypatch.setattr(svc._ftp, "connect", fake_connect)

    result = svc.test_connection(cfg)
    assert result.ok is False
    assert result.error is not None
    assert "login" in result.error.lower()


def test_missing_remote_directory_handling(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    remote_root.mkdir()

    local_dir = tmp_path / "downloads"
    local_dir.mkdir()

    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="mapped_folder", mapped_root=str(remote_root))

    result = svc.download_file(cfg, remote_path="/missing/file.osi", local_dir=str(local_dir), overwrite=False)
    assert result.ok is False
    assert result.error is not None
    assert "missing" in result.error.lower() or "not exist" in result.error.lower()


def test_zero_byte_file_rejection(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    remote_root.mkdir()

    local_file = tmp_path / "empty.osi"
    local_file.write_bytes(b"")

    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="mapped_folder", mapped_root=str(remote_root))

    result = svc.upload_file(cfg, local_path=str(local_file), remote_dir="/", overwrite=False)
    assert result.ok is False
    assert result.error is not None
    assert "zero-byte" in result.error.lower() or "empty" in result.error.lower()


def test_upload_then_refresh_osi_dropdown_workflow(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    remote_root.mkdir()

    local_file = tmp_path / "new_scenario.osi"
    local_file.write_bytes(b"abc")

    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="mapped_folder", mapped_root=str(remote_root))

    upload_result = svc.upload_osi_file(cfg, local_path=str(local_file), remote_dir="/var/user", overwrite=False)
    assert upload_result.ok

    files, op = svc.scan_remote_osi_files(cfg, remote_dir="/var/user")
    assert op.ok
    assert any(f.name == "new_scenario.osi" for f in files)


def test_download_osi_file_to_workspace(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    remote_file_dir = remote_root / "var" / "user"
    remote_file_dir.mkdir(parents=True)
    (remote_file_dir / "capture.osi").write_bytes(b"osi-data")

    local_dir = tmp_path / "workspace"
    local_dir.mkdir()

    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="mapped_folder", mapped_root=str(remote_root))

    result = svc.download_osi_file(cfg, remote_path="/var/user/capture.osi", local_dir=str(local_dir), overwrite=False)
    assert result.ok
    assert result.local_path is not None
    assert Path(result.local_path).exists()
    assert Path(result.local_path).read_bytes() == b"osi-data"


def test_download_osi_file_rejects_non_osi(tmp_path: Path) -> None:
    remote_root = tmp_path / "remote"
    remote_root.mkdir()
    local_dir = tmp_path / "workspace"
    local_dir.mkdir()

    svc = AregFileTransferService()
    cfg = TransferConfig(protocol="mapped_folder", mapped_root=str(remote_root))

    result = svc.download_osi_file(cfg, remote_path="/var/user/readme.txt", local_dir=str(local_dir), overwrite=False)
    assert result.ok is False
    assert result.error is not None
    assert ".osi" in result.error.lower()
