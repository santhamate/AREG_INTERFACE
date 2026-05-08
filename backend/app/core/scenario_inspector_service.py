from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.core.file_transfer_manager import AregFileTransferService, TransferConfig


@dataclass
class ObjectStateSample:
    timestamp: float | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    distance: float | None = None
    lateral_offset: float | None = None
    speed: float | None = None
    vx: float | None = None
    vy: float | None = None
    vz: float | None = None
    acceleration: float | None = None
    heading: float | None = None
    yaw: float | None = None
    rcs: float | None = None
    raw_fields: dict[str, Any] | None = None


@dataclass
class ScenarioObject:
    object_id: str
    object_name: str | None = None
    object_type: str | None = None
    samples: list[ObjectStateSample] | None = None
    raw_fields: dict[str, Any] | None = None


class ScenarioInspectorService:
    def __init__(self, project_root: Path, transfer_service: AregFileTransferService) -> None:
        self.project_root = project_root
        self.transfer_service = transfer_service
        self.cache_dir = self.project_root / ".scenario_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def clear_cache(self) -> tuple[int, str | None]:
        removed = 0
        err: str | None = None
        for p in self.cache_dir.glob("*"):
            try:
                if p.is_file():
                    p.unlink()
                    removed += 1
            except Exception as ex:
                err = str(ex)
        return removed, err

    @staticmethod
    def detect_format(file_path: Path, data: bytes) -> str:
        if len(data) == 0:
            return "empty"

        ext = file_path.suffix.lower()
        if data.startswith(b"PK\x03\x04"):
            return "zip"
        if data.startswith(b"\x1f\x8b"):
            return "gzip"
        if data.startswith(b"\xfd7zXZ\x00"):
            return "xz"

        if ext == ".json":
            return "json"

        head = data[:4096]
        try:
            text = head.decode("utf-8", errors="strict").strip()
            if text.startswith("{") or text.startswith("["):
                return "json-like"
            if any(token in text for token in ("sensor_id", "timestamp", "feature_data", "radar_sensor")):
                return "text-protobuf"
        except UnicodeDecodeError:
            pass

        if len(data) >= 8:
            first_len = struct.unpack("<I", data[:4])[0]
            if 0 < first_len < len(data):
                return "osi-framed-binary"

        return "unknown-binary"

    @staticmethod
    def _to_transfer_config(payload: dict[str, Any] | None) -> TransferConfig | None:
        if not payload:
            return None
        try:
            return TransferConfig(
                protocol=payload.get("protocol", "ftp"),
                host=payload.get("host"),
                username=payload.get("username", "instrument"),
                password=payload.get("password", "instrument"),
                remote_dir=payload.get("remote_dir", "/var/user/"),
                mapped_root=payload.get("mapped_root"),
                timeout_s=int(payload.get("timeout_s", 15)),
                passive_mode=bool(payload.get("passive_mode", True)),
            )
        except Exception:
            return None

    def _cache_file_path(self, remote_path: str) -> Path:
        digest = hashlib.sha1(remote_path.encode("utf-8")).hexdigest()
        suffix = Path(remote_path).suffix or ".osi"
        return self.cache_dir / f"{digest}{suffix}"

    def _resolve_local_file(
        self,
        remote_path: str | None,
        local_path: str | None,
        transfer_config: TransferConfig | None,
        force_redownload: bool,
    ) -> tuple[Path | None, str | None, str | None]:
        if local_path:
            candidate = Path(local_path)
            if candidate.exists() and candidate.is_file():
                return candidate, str(candidate), None

        if not remote_path:
            return None, None, "No scenario selected"

        cache_path = self._cache_file_path(remote_path)
        if cache_path.exists() and not force_redownload:
            return cache_path, str(cache_path), None

        if transfer_config is None:
            return None, None, "No transfer configuration available to download remote scenario"

        # Recreate cache dir in case it was removed while the server was running.
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        dl = self.transfer_service.download_file(
            config=transfer_config,
            remote_path=remote_path,
            local_dir=str(self.cache_dir),
            overwrite=True,
        )
        if not dl.ok or not dl.local_path:
            raw_err = dl.error or "Download failed"
            # Normalise FTP 550 "No such file" — not a real permission error.
            if "550" in raw_err or "no such file" in raw_err.lower() or "not found" in raw_err.lower():
                return None, None, f"File not found on device: {remote_path}"
            return None, None, raw_err

        downloaded = Path(dl.local_path)
        if downloaded != cache_path:
            try:
                if cache_path.exists():
                    cache_path.unlink()
                downloaded.rename(cache_path)
            except Exception:
                # Keep downloaded file if rename fails.
                cache_path = downloaded

        return cache_path, str(cache_path), None

    @staticmethod
    def _build_object_summary(obj_id: str, samples: list[ObjectStateSample]) -> dict[str, Any]:
        distances = [s.distance for s in samples if s.distance is not None]
        speeds = [s.speed for s in samples if s.speed is not None]
        accelerations = [s.acceleration for s in samples if s.acceleration is not None]
        headings = [s.heading for s in samples if s.heading is not None]
        rcs_values = [s.rcs for s in samples if s.rcs is not None]
        timestamps = [s.timestamp for s in samples if s.timestamp is not None]

        def _avg(values: list[float]) -> float | None:
            return (sum(values) / len(values)) if values else None

        first = samples[0] if samples else ObjectStateSample()
        last = samples[-1] if samples else ObjectStateSample()

        return {
            "object_id": obj_id,
            "object_name": obj_id,
            "object_type": None,
            "initial_position": {
                "x": first.x,
                "y": first.y,
                "z": first.z,
                "distance": first.distance,
                "lateral_offset": first.lateral_offset,
            },
            "final_position": {
                "x": last.x,
                "y": last.y,
                "z": last.z,
                "distance": last.distance,
                "lateral_offset": last.lateral_offset,
            },
            "min_distance": min(distances) if distances else None,
            "max_distance": max(distances) if distances else None,
            "initial_speed": first.speed,
            "max_speed": max(speeds) if speeds else None,
            "average_speed": _avg(speeds),
            "acceleration_summary": {
                "min": min(accelerations) if accelerations else None,
                "max": max(accelerations) if accelerations else None,
                "avg": _avg(accelerations),
            },
            "heading_summary": {
                "min": min(headings) if headings else None,
                "max": max(headings) if headings else None,
                "avg": _avg(headings),
            },
            "rcs_summary": {
                "min": min(rcs_values) if rcs_values else None,
                "max": max(rcs_values) if rcs_values else None,
                "avg": _avg(rcs_values),
            },
            "valid_time_start": min(timestamps) if timestamps else None,
            "valid_time_end": max(timestamps) if timestamps else None,
            "samples": [
                {
                    "timestamp": s.timestamp,
                    "x": s.x,
                    "y": s.y,
                    "z": s.z,
                    "distance": s.distance,
                    "lateral_offset": s.lateral_offset,
                    "speed": s.speed,
                    "vx": s.vx,
                    "vy": s.vy,
                    "vz": s.vz,
                    "acceleration": s.acceleration,
                    "heading": s.heading,
                    "yaw": s.yaw,
                    "rcs": s.rcs,
                    "raw_fields": s.raw_fields or {},
                }
                for s in samples
            ],
            "raw_fields": {},
        }

    def _decode_json_like(self, text: str) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any]]:
        warnings: list[str] = []
        errors: list[str] = []
        raw_summary: dict[str, Any] = {}

        try:
            payload = json.loads(text)
        except Exception as ex:
            return [], warnings, [f"JSON-like parse failed: {ex}"], raw_summary

        objects_payload = payload.get("objects") if isinstance(payload, dict) else None
        if not isinstance(objects_payload, list):
            return [], ["JSON payload does not contain objects[]; metadata only"], [], {
                "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else [],
            }

        decoded_objects: list[dict[str, Any]] = []
        for idx, obj in enumerate(objects_payload):
            if not isinstance(obj, dict):
                continue
            obj_id = str(obj.get("object_id") or obj.get("id") or f"obj_{idx}")
            obj_type = obj.get("object_type") or obj.get("type")
            samples_data = obj.get("samples") if isinstance(obj.get("samples"), list) else []

            samples: list[ObjectStateSample] = []
            for sample in samples_data:
                if not isinstance(sample, dict):
                    continue
                vx = sample.get("vx")
                vy = sample.get("vy")
                vz = sample.get("vz")
                speed = sample.get("speed")
                if speed is None and all(isinstance(v, (int, float)) for v in (vx, vy, vz)):
                    speed = (float(vx) ** 2 + float(vy) ** 2 + float(vz) ** 2) ** 0.5

                samples.append(
                    ObjectStateSample(
                        timestamp=sample.get("timestamp"),
                        x=sample.get("x"),
                        y=sample.get("y"),
                        z=sample.get("z"),
                        distance=sample.get("distance"),
                        lateral_offset=sample.get("lateral_offset"),
                        speed=speed,
                        vx=vx,
                        vy=vy,
                        vz=vz,
                        acceleration=sample.get("acceleration"),
                        heading=sample.get("heading"),
                        yaw=sample.get("yaw"),
                        rcs=sample.get("rcs"),
                        raw_fields={k: v for k, v in sample.items() if k not in {
                            "timestamp", "x", "y", "z", "distance", "lateral_offset", "speed",
                            "vx", "vy", "vz", "acceleration", "heading", "yaw", "rcs",
                        }},
                    )
                )

            summary = self._build_object_summary(obj_id, samples)
            summary["object_type"] = obj_type
            summary["raw_fields"] = {k: v for k, v in obj.items() if k not in {"object_id", "id", "object_type", "type", "samples"}}
            decoded_objects.append(summary)

        raw_summary["top_level_keys"] = list(payload.keys()) if isinstance(payload, dict) else []
        return decoded_objects, warnings, errors, raw_summary

    def _decode_osi_framed_binary(self, data: bytes) -> tuple[list[dict[str, Any]], int, float | None, float | None, list[str], list[str], dict[str, Any]]:
        warnings: list[str] = []
        errors: list[str] = []
        raw_summary: dict[str, Any] = {}

        frames: list[bytes] = []
        offset = 0
        while offset + 4 <= len(data):
            frame_len = struct.unpack("<I", data[offset: offset + 4])[0]
            offset += 4
            if frame_len <= 0 or offset + frame_len > len(data):
                errors.append("Corrupted framed .osi data")
                break
            frames.append(data[offset: offset + frame_len])
            offset += frame_len

        timestep_count = len(frames)
        raw_summary["frame_count"] = timestep_count

        try:
            from osi3.osi_sensordata_pb2 import SensorData  # type: ignore
            osi_available = True
        except Exception:
            osi_available = False
            SensorData = None  # type: ignore

        if not osi_available:
            warnings.append("OSI protobuf dependency not available; showing metadata only")
            return [], timestep_count, None, None, warnings, errors, raw_summary

        objects: dict[str, list[ObjectStateSample]] = {}
        ts_values: list[float] = []

        for frame in frames:
            msg = SensorData()
            try:
                msg.ParseFromString(frame)
            except Exception:
                continue

            ts = float(msg.timestamp.seconds) + (float(msg.timestamp.nanos) / 1_000_000_000.0)
            ts_values.append(ts)

            for radar in msg.feature_data.radar_sensor:
                for idx, det in enumerate(radar.detection):
                    obj_id = f"obj_{idx}"
                    samples = objects.setdefault(obj_id, [])
                    samples.append(
                        ObjectStateSample(
                            timestamp=ts,
                            distance=float(det.position.distance),
                            lateral_offset=float(det.position.azimuth),
                            z=float(det.position.elevation),
                            speed=float(det.radial_velocity),
                            rcs=float(det.rcs),
                            raw_fields={},
                        )
                    )

        decoded = [self._build_object_summary(obj_id, samples) for obj_id, samples in objects.items()]
        time_start = min(ts_values) if ts_values else None
        time_end = max(ts_values) if ts_values else None
        return decoded, timestep_count, time_start, time_end, warnings, errors, raw_summary

    @staticmethod
    def _strip_ieee488_block_header(data: bytes) -> bytes:
        """Strip the IEEE 488.2 definite-length binary block header (#N<N digits><payload>)
        that instruments prepend to binary query responses (e.g. MMEMory:DATA?)."""
        if len(data) < 2 or data[0:1] != b"#":
            return data
        digit_count = int(chr(data[1]))
        if digit_count == 0:
            # Indefinite block: #0 … <newline> — just drop the 2-byte prefix.
            return data[2:]
        header_len = 2 + digit_count
        if len(data) < header_len:
            return data  # malformed — leave as-is
        return data[header_len:]

    def decode_from_bytes(
        self,
        data: bytes,
        remote_path: str | None,
        loaded_scenario_path: str | None,
    ) -> dict[str, Any]:
        """Decode a scenario directly from raw bytes (e.g. fetched via SCPI MMEMory:DATA?)."""
        data = self._strip_ieee488_block_header(data)
        name = Path(remote_path or "scenario.osi").name
        if len(data) == 0:
            return {
                "ok": False, "scenario_name": name, "file_path": None,
                "remote_path": remote_path, "local_cached_path": None,
                "loaded_scenario_path": loaded_scenario_path, "format_detected": "empty",
                "duration": None, "time_start": None, "time_end": None,
                "timestep_count": 0, "object_count": 0, "objects": [],
                "warnings": [], "errors": ["Scenario file is empty"], "raw_summary": {"size_bytes": 0},
            }

        # Use a synthetic path just for format detection (extension matters).
        synthetic_path = Path(name)
        fmt = self.detect_format(synthetic_path, data)
        objects: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        raw_summary: dict[str, Any] = {"size_bytes": len(data), "magic_header_hex": data[:16].hex()}
        timestep_count = 0
        time_start: float | None = None
        time_end: float | None = None

        if fmt in ("json", "json-like"):
            text = data.decode("utf-8", errors="replace")
            objects, w, e, raw = self._decode_json_like(text)
            warnings.extend(w); errors.extend(e); raw_summary.update(raw)
            timestep_count = max((len(obj.get("samples", [])) for obj in objects), default=0)
            starts = [obj.get("valid_time_start") for obj in objects if obj.get("valid_time_start") is not None]
            ends = [obj.get("valid_time_end") for obj in objects if obj.get("valid_time_end") is not None]
            time_start = min(starts) if starts else None
            time_end = max(ends) if ends else None
        elif fmt == "osi-framed-binary":
            objs, steps, ts0, ts1, w, e, raw = self._decode_osi_framed_binary(data)
            objects = objs; timestep_count = steps; time_start = ts0; time_end = ts1
            warnings.extend(w); errors.extend(e); raw_summary.update(raw)
        elif fmt in ("zip", "gzip", "xz"):
            warnings.append("Compressed scenario format detected; automatic decompression is not implemented yet")
        else:
            errors.append("Unsupported or unknown binary scenario format")

        duration = (time_end - time_start) if (time_start is not None and time_end is not None) else None
        return {
            "ok": len(errors) == 0, "scenario_name": name, "file_path": None,
            "remote_path": remote_path, "local_cached_path": None,
            "loaded_scenario_path": loaded_scenario_path, "format_detected": fmt,
            "duration": duration, "time_start": time_start, "time_end": time_end,
            "timestep_count": timestep_count, "object_count": len(objects), "objects": objects,
            "warnings": warnings, "errors": errors, "raw_summary": raw_summary,
        }

    def decode(
        self,
        remote_path: str | None,
        local_path: str | None,
        transfer_config_payload: dict[str, Any] | None,
        force_redownload: bool,
        loaded_scenario_path: str | None,
    ) -> dict[str, Any]:
        transfer_config = self._to_transfer_config(transfer_config_payload)
        resolved_file, cache_path, resolve_error = self._resolve_local_file(
            remote_path=remote_path,
            local_path=local_path,
            transfer_config=transfer_config,
            force_redownload=force_redownload,
        )

        if resolve_error:
            return {
                "ok": False,
                "scenario_name": Path(remote_path or local_path or "").name or None,
                "file_path": local_path,
                "remote_path": remote_path,
                "local_cached_path": cache_path,
                "loaded_scenario_path": loaded_scenario_path,
                "format_detected": "unknown",
                "duration": None,
                "time_start": None,
                "time_end": None,
                "timestep_count": 0,
                "object_count": 0,
                "objects": [],
                "warnings": [],
                "errors": [resolve_error],
                "raw_summary": {},
            }

        assert resolved_file is not None
        try:
            data = resolved_file.read_bytes()
        except PermissionError as exc:
            return {
                "ok": False,
                "scenario_name": resolved_file.name,
                "file_path": str(resolved_file),
                "remote_path": remote_path,
                "local_cached_path": cache_path,
                "loaded_scenario_path": loaded_scenario_path,
                "format_detected": "unknown",
                "duration": None,
                "time_start": None,
                "time_end": None,
                "timestep_count": 0,
                "object_count": 0,
                "objects": [],
                "warnings": [],
                "errors": [f"Permission denied reading scenario file: {exc}"],
                "raw_summary": {},
            }
        except OSError as exc:
            return {
                "ok": False,
                "scenario_name": resolved_file.name,
                "file_path": str(resolved_file),
                "remote_path": remote_path,
                "local_cached_path": cache_path,
                "loaded_scenario_path": loaded_scenario_path,
                "format_detected": "unknown",
                "duration": None,
                "time_start": None,
                "time_end": None,
                "timestep_count": 0,
                "object_count": 0,
                "objects": [],
                "warnings": [],
                "errors": [f"OS error reading scenario file: {exc}"],
                "raw_summary": {},
            }
        if len(data) == 0:
            return {
                "ok": False,
                "scenario_name": resolved_file.name,
                "file_path": str(resolved_file),
                "remote_path": remote_path,
                "local_cached_path": cache_path,
                "loaded_scenario_path": loaded_scenario_path,
                "format_detected": "empty",
                "duration": None,
                "time_start": None,
                "time_end": None,
                "timestep_count": 0,
                "object_count": 0,
                "objects": [],
                "warnings": [],
                "errors": ["Scenario file is empty"],
                "raw_summary": {
                    "size_bytes": 0,
                },
            }

        fmt = self.detect_format(resolved_file, data)

        objects: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        raw_summary: dict[str, Any] = {
            "size_bytes": len(data),
            "magic_header_hex": data[:16].hex(),
        }
        timestep_count = 0
        time_start: float | None = None
        time_end: float | None = None

        if fmt in ("json", "json-like"):
            text = data.decode("utf-8", errors="replace")
            objects, w, e, raw = self._decode_json_like(text)
            warnings.extend(w)
            errors.extend(e)
            raw_summary.update(raw)
            # Estimate timesteps from max sample count.
            timestep_count = max((len(obj.get("samples", [])) for obj in objects), default=0)
            starts = [obj.get("valid_time_start") for obj in objects if obj.get("valid_time_start") is not None]
            ends = [obj.get("valid_time_end") for obj in objects if obj.get("valid_time_end") is not None]
            time_start = min(starts) if starts else None
            time_end = max(ends) if ends else None
        elif fmt == "osi-framed-binary":
            objs, steps, ts0, ts1, w, e, raw = self._decode_osi_framed_binary(data)
            objects = objs
            timestep_count = steps
            time_start = ts0
            time_end = ts1
            warnings.extend(w)
            errors.extend(e)
            raw_summary.update(raw)
        elif fmt == "text-protobuf":
            warnings.append("Text protobuf decode is not implemented yet; showing metadata only")
        elif fmt in ("zip", "gzip", "xz"):
            warnings.append("Compressed scenario format detected; automatic decompression is not implemented yet")
        else:
            errors.append("Unsupported or unknown binary scenario format")
            warnings.append("Metadata/raw summary shown because full decode is unavailable")

        duration = (time_end - time_start) if (time_start is not None and time_end is not None) else None

        return {
            "ok": len(errors) == 0,
            "scenario_name": resolved_file.name,
            "file_path": str(resolved_file),
            "remote_path": remote_path,
            "local_cached_path": cache_path,
            "loaded_scenario_path": loaded_scenario_path,
            "format_detected": fmt,
            "duration": duration,
            "time_start": time_start,
            "time_end": time_end,
            "timestep_count": timestep_count,
            "object_count": len(objects),
            "objects": objects,
            "warnings": warnings,
            "errors": errors,
            "raw_summary": raw_summary,
        }
