from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.file_transfer_manager import AregFileTransferService, TransferConfig
from backend.app.core.scenario_inspector_service import ScenarioInspectorService


def make_service(tmp_path: Path) -> ScenarioInspectorService:
    transfer = AregFileTransferService()
    return ScenarioInspectorService(project_root=tmp_path, transfer_service=transfer)


def test_detect_osi_file_type_json_like(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    p = tmp_path / "scenario.osi"
    p.write_text('{"objects": []}', encoding="utf-8")
    fmt = svc.detect_format(p, p.read_bytes())
    assert fmt == "json-like"


def test_detect_unsupported_file(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    p = tmp_path / "scenario.osi"
    p.write_bytes(b"\x00\xff\x12\x99\x10\x11")
    fmt = svc.detect_format(p, p.read_bytes())
    assert fmt in ("unknown-binary", "osi-framed-binary")


def test_handling_corrupted_file(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    p = tmp_path / "corrupt.osi"
    p.write_bytes(b"\x20\x00\x00\x00abc")

    res = svc.decode(remote_path=None, local_path=str(p), transfer_config_payload=None, force_redownload=False, loaded_scenario_path=None)
    assert res["ok"] is False
    assert len(res["errors"]) >= 1


def test_extract_object_count_and_speed_distance_fields(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    p = tmp_path / "valid.osi"
    p.write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "object_id": "car_1",
                        "type": "car",
                        "samples": [
                            {"timestamp": 0.0, "distance": 50.0, "speed": 10.0, "rcs": 12.0},
                            {"timestamp": 1.0, "distance": 40.0, "speed": 12.0, "rcs": 11.0},
                        ],
                    },
                    {
                        "object_id": "truck_1",
                        "type": "truck",
                        "samples": [
                            {"timestamp": 0.0, "distance": 80.0, "speed": 8.0},
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    res = svc.decode(remote_path=None, local_path=str(p), transfer_config_payload=None, force_redownload=False, loaded_scenario_path=None)
    assert res["ok"] is True
    assert res["object_count"] == 2
    assert res["objects"][0]["initial_speed"] == 10.0
    assert res["objects"][0]["min_distance"] == 40.0
    assert res["objects"][0]["max_distance"] == 50.0


def test_cache_reuse(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    remote = "/var/user/test.osi"
    cache = svc._cache_file_path(remote)
    cache.write_text('{"objects": []}', encoding="utf-8")

    res = svc.decode(remote_path=remote, local_path=None, transfer_config_payload=None, force_redownload=False, loaded_scenario_path=None)
    assert res["ok"] is True
    assert res["local_cached_path"] == str(cache)


def test_download_remote_scenario_before_decode(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    remote = "/var/user/from_remote.osi"

    def fake_download_file(config: TransferConfig, remote_path: str, local_dir: str, overwrite: bool = False):
        from backend.app.core.file_transfer_manager import TransferResult

        local = Path(local_dir) / Path(remote_path).name
        local.write_text('{"objects": [{"object_id":"o1","samples":[{"timestamp":0,"distance":10,"speed":2}]}]}', encoding="utf-8")
        return TransferResult(ok=True, local_path=str(local), remote_path=remote_path, bytes_transferred=local.stat().st_size)

    svc.transfer_service.download_file = fake_download_file  # type: ignore[method-assign]

    payload = {
        "protocol": "ftp",
        "host": "127.0.0.1",
        "username": "instrument",
        "password": "instrument",
        "remote_dir": "/var/user/",
        "mapped_root": None,
        "timeout_s": 15,
        "passive_mode": True,
    }
    res = svc.decode(remote_path=remote, local_path=None, transfer_config_payload=payload, force_redownload=True, loaded_scenario_path=remote)
    assert res["ok"] is True
    assert res["object_count"] == 1


def test_ui_state_when_no_scenario_selected(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    res = svc.decode(remote_path=None, local_path=None, transfer_config_payload=None, force_redownload=False, loaded_scenario_path=None)
    assert res["ok"] is False
    assert "No scenario selected" in res["errors"]


def test_ui_state_when_decode_fails(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    p = tmp_path / "broken.osi"
    p.write_text("{ bad json", encoding="utf-8")
    res = svc.decode(remote_path=None, local_path=str(p), transfer_config_payload=None, force_redownload=False, loaded_scenario_path=None)
    assert res["ok"] is False
    assert len(res["errors"]) >= 1
