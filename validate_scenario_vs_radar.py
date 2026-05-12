#!/usr/bin/env python3
"""Validate radar measured speeds against an AREG scenario file.

Usage example:
  python validate_scenario_vs_radar.py \
    --scenario scenarios/range_sweep_10ms.osi \
    --radar-csv C:/Users/santham/Downloads/tcv907_history_last_100_20260512_143807.csv \
    --tolerance-mode fixed_kmh \
    --tolerance-value 3.0
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from backend.app.core.file_transfer_manager import AregFileTransferService
from backend.app.core.scenario_inspector_service import ScenarioInspectorService


@dataclass
class ComparisonRow:
    index: int
    packet_number: int | None
    measured_kmh: float
    expected_kmh: float
    error_kmh: float
    tolerance_kmh: float
    passed: bool
    timestamp: str | None


def _calc_tolerance(expected_kmh: float, mode: str, value: float) -> float:
    if mode == "percentage":
        return abs(expected_kmh) * (value / 100.0)
    if mode == "custom_rule":
        return 3.0 if abs(expected_kmh) < 100.0 else abs(expected_kmh) * 0.03
    return value


def _load_radar_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # First try strict CSV parsing.
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=",")
            for raw in reader:
                if not raw:
                    continue
                speed_raw = (raw.get("speed_kmh") or "").strip().strip('"')
                if not speed_raw:
                    continue
                try:
                    speed_kmh = float(speed_raw)
                except ValueError:
                    continue
                packet_raw = (raw.get("packet_number") or "").strip().strip('"')
                packet_number = int(packet_raw) if packet_raw.isdigit() else None
                rows.append(
                    {
                        "packet_number": packet_number,
                        "speed_kmh": speed_kmh,
                        "timestamp": (raw.get("timestamp") or "").strip().strip('"') or None,
                    }
                )
    except Exception:
        rows = []

    if rows:
        return rows

    # Fallback parser for malformed legacy exports.
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]
    for line in lines:
        m_speed = re.search(r",\s*\"?([+-]?\d+\.\d+)\"?", line)
        if not m_speed:
            continue
        speed_kmh = float(m_speed.group(1))
        m_packet = re.match(r"\"?(\d+)", line)
        packet_number = int(m_packet.group(1)) if m_packet else None
        m_ts = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
        timestamp = m_ts.group(1) if m_ts else None
        rows.append({"packet_number": packet_number, "speed_kmh": speed_kmh, "timestamp": timestamp})

    return rows


def _extract_expected_series_kmh(scenario_path: Path, object_id: str | None) -> tuple[list[float], dict[str, Any]]:
    inspector = ScenarioInspectorService(project_root=Path.cwd(), transfer_service=AregFileTransferService())
    decoded = inspector.decode_from_bytes(
        data=scenario_path.read_bytes(),
        remote_path=str(scenario_path),
        loaded_scenario_path=str(scenario_path),
    )

    if not decoded.get("ok"):
        errors = decoded.get("errors") or []
        raise RuntimeError(f"Scenario decode failed: {errors}")

    objects = decoded.get("objects") or []
    if not objects:
        raise RuntimeError("No objects found in scenario")

    selected: dict[str, Any] | None = None
    if object_id:
        for obj in objects:
            if str(obj.get("object_id")) == object_id:
                selected = obj
                break
        if selected is None:
            raise RuntimeError(f"Object id '{object_id}' not found in scenario")
    else:
        selected = max(objects, key=lambda o: len((o.get("samples") or [])))

    samples = selected.get("samples") or []
    speeds_mps = [float(s["speed"]) for s in samples if isinstance(s, dict) and s.get("speed") is not None]

    # Fallback to aggregate speed field if per-sample values are missing.
    if not speeds_mps and selected.get("average_speed") is not None:
        speeds_mps = [float(selected["average_speed"])]

    if not speeds_mps:
        raise RuntimeError("No speed values found in selected scenario object")

    series_kmh = [v * 3.6 for v in speeds_mps]
    meta = {
        "scenario_name": decoded.get("scenario_name"),
        "format_detected": decoded.get("format_detected"),
        "object_id": selected.get("object_id"),
        "sample_count": len(samples),
        "expected_series_count": len(series_kmh),
    }
    return series_kmh, meta


def _target_kmh_from_filename(scenario_path: Path) -> float | None:
    # Expected token pattern from sweep generator: ..._p036_kmh.osi / ..._n040_mph.osi / ..._p010_ms.osi
    m = re.search(r"_([pn])(\d{3})_(kmh|mph|ms)\.osi$", scenario_path.name.lower())
    if not m:
        return None
    sign = 1.0 if m.group(1) == "p" else -1.0
    value = float(int(m.group(2)))
    unit = m.group(3)
    if unit == "kmh":
        return sign * value
    if unit == "mph":
        return sign * (value * 1.609344)
    return sign * (value * 3.6)


def _expected_for_index(expected_series: list[float], i: int, total: int) -> float:
    if len(expected_series) == 1 or total <= 1:
        return expected_series[0]
    pos = i * (len(expected_series) - 1) / (total - 1)
    idx = int(round(pos))
    idx = max(0, min(len(expected_series) - 1, idx))
    return expected_series[idx]


def _compare(
    radar_rows: list[dict[str, Any]],
    expected_series: list[float],
    tolerance_mode: str,
    tolerance_value: float,
) -> list[ComparisonRow]:
    out: list[ComparisonRow] = []
    total = len(radar_rows)
    for i, row in enumerate(radar_rows):
        measured = float(row["speed_kmh"])
        expected = _expected_for_index(expected_series, i, total)
        tol = _calc_tolerance(expected, tolerance_mode, tolerance_value)
        err = measured - expected
        out.append(
            ComparisonRow(
                index=i,
                packet_number=row.get("packet_number"),
                measured_kmh=measured,
                expected_kmh=expected,
                error_kmh=err,
                tolerance_kmh=tol,
                passed=abs(err) <= tol,
                timestamp=row.get("timestamp"),
            )
        )
    return out


def _build_summary(rows: list[ComparisonRow], tolerance_mode: str, tolerance_value: float) -> dict[str, Any]:
    if not rows:
        return {
            "ok": False,
            "error": "No comparison rows available",
            "tolerance_mode": tolerance_mode,
            "tolerance_value": tolerance_value,
        }

    pass_count = sum(1 for r in rows if r.passed)
    errors = [r.error_kmh for r in rows]
    abs_errors = [abs(e) for e in errors]
    expected_vals = [r.expected_kmh for r in rows]
    measured_vals = [r.measured_kmh for r in rows]

    return {
        "ok": True,
        "tolerance_mode": tolerance_mode,
        "tolerance_value": tolerance_value,
        "row_count": len(rows),
        "pass_count": pass_count,
        "fail_count": len(rows) - pass_count,
        "pass_rate_percent": (pass_count / len(rows)) * 100.0,
        "expected_mean_kmh": mean(expected_vals),
        "measured_mean_kmh": mean(measured_vals),
        "error_mean_kmh": mean(errors),
        "error_max_abs_kmh": max(abs_errors),
        "error_p95_abs_kmh": sorted(abs_errors)[int(0.95 * (len(abs_errors) - 1))],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate radar measured speed against scenario target speed")
    parser.add_argument("--scenario", required=True, help="Path to scenario file (.osi)")
    parser.add_argument("--radar-csv", required=True, help="Path to radar CSV export")
    parser.add_argument("--object-id", default=None, help="Optional scenario object id to validate")
    parser.add_argument("--target-kmh", type=float, default=None, help="Optional explicit target speed in km/h")
    parser.add_argument(
        "--tolerance-mode",
        default="fixed_kmh",
        choices=["fixed_kmh", "percentage", "custom_rule"],
        help="Tolerance mode",
    )
    parser.add_argument("--tolerance-value", type=float, default=3.0, help="Tolerance value (km/h or percent)")
    parser.add_argument("--report-json", default=None, help="Optional output report JSON path")
    parser.add_argument("--details-csv", default=None, help="Optional per-row comparison CSV path")
    args = parser.parse_args()

    scenario_path = Path(args.scenario)
    radar_csv_path = Path(args.radar_csv)

    if not scenario_path.exists():
        print(f"ERROR: Scenario file not found: {scenario_path}")
        return 1
    if not radar_csv_path.exists():
        print(f"ERROR: Radar CSV file not found: {radar_csv_path}")
        return 1

    radar_rows = _load_radar_csv(radar_csv_path)
    if not radar_rows:
        print("ERROR: No valid radar speed rows found in CSV")
        return 1

    expected_series: list[float]
    scenario_meta: dict[str, Any]
    try:
        expected_series, scenario_meta = _extract_expected_series_kmh(scenario_path, args.object_id)
    except Exception as ex:
        explicit_target = args.target_kmh
        filename_target = _target_kmh_from_filename(scenario_path)
        selected_target = explicit_target if explicit_target is not None else filename_target
        if selected_target is None:
            print(f"ERROR: {ex}")
            print("Hint: pass --target-kmh <value> or use sweep filename tokens like _p036_kmh.osi")
            return 1
        expected_series = [selected_target]
        scenario_meta = {
            "scenario_name": scenario_path.name,
            "format_detected": "fallback-target",
            "object_id": args.object_id,
            "sample_count": 0,
            "expected_series_count": 1,
            "target_source": "--target-kmh" if explicit_target is not None else "filename-token",
        }

    comparisons = _compare(radar_rows, expected_series, args.tolerance_mode, args.tolerance_value)
    summary = _build_summary(comparisons, args.tolerance_mode, args.tolerance_value)

    report = {
        "scenario": str(scenario_path),
        "radar_csv": str(radar_csv_path),
        "scenario_meta": scenario_meta,
        "summary": summary,
    }

    print("=" * 72)
    print("SCENARIO VS RADAR VALIDATION")
    print("=" * 72)
    print(f"Scenario:      {scenario_path}")
    print(f"Radar CSV:     {radar_csv_path}")
    print(f"Object:        {scenario_meta.get('object_id')}")
    print(f"Rows checked:  {summary.get('row_count')}")
    print(f"Pass rate:     {summary.get('pass_rate_percent', 0.0):.2f}%")
    print(f"Mean expected: {summary.get('expected_mean_kmh', 0.0):.3f} km/h")
    print(f"Mean measured: {summary.get('measured_mean_kmh', 0.0):.3f} km/h")
    print(f"Mean error:    {summary.get('error_mean_kmh', 0.0):.3f} km/h")
    print(f"Max |error|:   {summary.get('error_max_abs_kmh', 0.0):.3f} km/h")
    print(f"P95 |error|:   {summary.get('error_p95_abs_kmh', 0.0):.3f} km/h")

    if args.report_json:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report JSON:   {report_path}")

    if args.details_csv:
        details_path = Path(args.details_csv)
        details_path.parent.mkdir(parents=True, exist_ok=True)
        with details_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow([
                "index",
                "packet_number",
                "timestamp",
                "measured_kmh",
                "expected_kmh",
                "error_kmh",
                "tolerance_kmh",
                "passed",
            ])
            for r in comparisons:
                writer.writerow([
                    r.index,
                    r.packet_number,
                    r.timestamp,
                    f"{r.measured_kmh:.3f}",
                    f"{r.expected_kmh:.3f}",
                    f"{r.error_kmh:.3f}",
                    f"{r.tolerance_kmh:.3f}",
                    "pass" if r.passed else "fail",
                ])
        print(f"Details CSV:   {details_path}")

    # Return non-zero when any row fails criteria.
    return 0 if summary.get("fail_count", 1) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
