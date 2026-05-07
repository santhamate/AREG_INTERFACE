import React, { useEffect, useState } from "react";
import "./SimulationOverview.css";

const API_BASE = "http://127.0.0.1:8000/api";

interface OverviewData {
  connected: boolean;
  host: string | null;
  port: number | null;
  transport: string;
  playback_state: string;
  current_scenario: string | null;
  replay_mode: string;
  total_generated: number;
  last_generated_file: string | null;
  last_generated_template: string | null;
  log_entry_count: number;
  last_command: string | null;
  last_command_ok: boolean | null;
  timestamp: string;
  local_scenario_path: string | null;
}

interface ScenarioInspectorSample {
  timestamp: number | null;
  x: number | null;
  y: number | null;
  distance: number | null;
  lateral_offset: number | null;
  speed: number | null;
  heading: number | null;
  rcs: number | null;
}

interface ScenarioInspectorObject {
  object_id: string;
  object_name: string | null;
  object_type: string | null;
  valid_time_start: number | null;
  valid_time_end: number | null;
  samples: ScenarioInspectorSample[];
}

interface ScenarioDecodeResult {
  ok: boolean;
  scenario_name?: string | null;
  loaded_scenario_path?: string | null;
  file_path?: string | null;
  remote_path?: string | null;
  local_cached_path?: string | null;
  format_detected?: string | null;
  time_start?: number | null;
  time_end?: number | null;
  timestep_count?: number | null;
  warnings?: string[];
  errors?: string[];
  duration: number | null;
  object_count: number;
  objects: ScenarioInspectorObject[];
}

type PreviewState = "stopped" | "playing" | "paused";

const STATE_COLORS: Record<string, string> = {
  playing:    "#10b981",
  paused:     "#f59e0b",
  stopped:    "#ef4444",
  loaded:     "#3b82f6",
  error:      "#ef4444",
  not_loaded: "#64748b",
  unknown:    "#64748b",
};

const STATE_LABELS: Record<string, string> = {
  playing:    "Playing",
  paused:     "Paused",
  stopped:    "Stopped",
  loaded:     "Loaded",
  error:      "Error",
  not_loaded: "Not Loaded",
  unknown:    "Unknown",
};

function basename(path: string): string {
  return path.replace(/\\/g, "/").split("/").pop() ?? path;
}

function joinScenarioLocalFallback(remotePath: string | null): string | null {
  if (!remotePath) return null;
  const base = basename(remotePath);
  if (!base) return null;
  return `scenarios/${base}`;
}

export default function SimulationOverview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [decode, setDecode] = useState<ScenarioDecodeResult | null>(null);
  const [playbackSec, setPlaybackSec] = useState(0);
  const [manualPreview, setManualPreview] = useState(false);
  const [previewState, setPreviewState] = useState<PreviewState>("stopped");
  const [previewLoop, setPreviewLoop] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [lastScenario, setLastScenario] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const r = await fetch(`${API_BASE}/simulation/overview`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = (await r.json()) as OverviewData;
      setData(d);
      setLastRefresh(new Date());
      setFetchError(null);
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : "Fetch error");
    }
  };

  const deriveDuration = (decoded: ScenarioDecodeResult | null): number => {
    if (!decoded) return 0;
    if ((decoded.duration ?? 0) > 0) return decoded.duration ?? 0;
    let maxTs = 0;
    for (const obj of decoded.objects ?? []) {
      for (const s of obj.samples ?? []) {
        const t = s.timestamp ?? 0;
        if (Number.isFinite(t) && t > maxTs) maxTs = t;
      }
    }
    return maxTs;
  };

  const decodeScenario = async (scenarioPath: string | null) => {
    const fallbackLocalPath = data?.local_scenario_path ?? joinScenarioLocalFallback(scenarioPath);
    const decodePayload = {
      remote_path: scenarioPath,
      local_path: fallbackLocalPath,
      force_redownload: false,
      transfer_config: data?.connected && data?.host
        ? {
            protocol: "ftp",
            host: data.host,
            username: "instrument",
            password: "instrument",
            remote_dir: "/var/user/",
            timeout_s: 15,
            passive_mode: true,
          }
        : null,
    };

    const tryDecodeSelected = async () => {
      if (!scenarioPath) return false;
      const r = await fetch(`${API_BASE}/scenario/inspector/decode-selected`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decodePayload),
      });
      if (!r.ok) return false;
      const decoded = (await r.json()) as ScenarioDecodeResult;
      setDecode(decoded);
      if (!decoded.ok) return false;
      const d = deriveDuration(decoded);
      setPlaybackSec((prev) => (d > 0 ? Math.min(prev, d) : prev));
      return true;
    };

    const tryDecodeLoaded = async () => {
      const r = await fetch(`${API_BASE}/scenario/inspector/decode-loaded`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decodePayload),
      });
      if (!r.ok) return false;
      const decoded = (await r.json()) as ScenarioDecodeResult;
      setDecode(decoded);
      if (!decoded.ok) return false;
      const d = deriveDuration(decoded);
      setPlaybackSec((prev) => (d > 0 ? Math.min(prev, d) : prev));
      return true;
    };

    if (!scenarioPath && !data?.connected) {
      setDecode(null);
      setPlaybackSec(0);
      return;
    }

    try {
      const selectedOk = await tryDecodeSelected();
      if (!selectedOk) {
        const loadedOk = await tryDecodeLoaded();
        if (!loadedOk && !scenarioPath) {
          setDecode(null);
          setPlaybackSec(0);
        }
      }
    } catch {
      // Keep overview available even when decode endpoints are not ready.
    }
  };

  const sampleAtTime = (obj: ScenarioInspectorObject, t: number): ScenarioInspectorSample | null => {
    const samples = obj.samples;
    if (!samples || samples.length === 0) return null;
    if (samples.length === 1) return samples[0];

    let left = samples[0];
    let right = samples[samples.length - 1];

    for (let i = 0; i < samples.length - 1; i += 1) {
      const a = samples[i];
      const b = samples[i + 1];
      const ta = a.timestamp ?? 0;
      const tb = b.timestamp ?? 0;
      if (t >= ta && t <= tb) {
        left = a;
        right = b;
        break;
      }
    }

    const ta = left.timestamp ?? 0;
    const tb = right.timestamp ?? ta;
    const span = Math.max(tb - ta, 1e-6);
    const alpha = Math.min(1, Math.max(0, (t - ta) / span));
    const lerp = (a: number | null, b: number | null): number | null => {
      if (a == null && b == null) return null;
      const av = a ?? b ?? 0;
      const bv = b ?? a ?? 0;
      return av + (bv - av) * alpha;
    };

    return {
      timestamp: t,
      x: lerp(left.x, right.x),
      y: lerp(left.y, right.y),
      distance: lerp(left.distance, right.distance),
      lateral_offset: lerp(left.lateral_offset, right.lateral_offset),
      speed: lerp(left.speed, right.speed),
      heading: lerp(left.heading, right.heading),
      rcs: lerp(left.rcs, right.rcs),
    };
  };

  // Convert OSI sample to Cartesian (x=cross-range, y=range).
  // For radar detections: lateral_offset = azimuth (rad), distance = range (m).
  // For moving objects: x/y are already Cartesian meters.
  const sampleToCartesian = (s: ScenarioInspectorSample): { x: number; y: number; azimuth_rad: number | null } => {
    if (s.x != null && s.y != null) {
      const az = (s.distance != null && s.distance > 0) ? Math.atan2(s.x, s.y) : (s.lateral_offset ?? null);
      return { x: s.x, y: s.y, azimuth_rad: az };
    }
    if (s.lateral_offset != null && s.distance != null) {
      const az = s.lateral_offset;
      const r = s.distance;
      return { x: r * Math.sin(az), y: r * Math.cos(az), azimuth_rad: az };
    }
    const x = s.lateral_offset ?? 0;
    const y = s.distance ?? 0;
    return { x, y, azimuth_rad: null };
  };

  const objectState = (obj: ScenarioInspectorObject, t: number) => {
    const s = sampleAtTime(obj, t);
    if (!s) return null;
    const { x: px, y: py, azimuth_rad } = sampleToCartesian(s);
    const radius = Math.hypot(px, py);
    const azimuth_deg = azimuth_rad != null ? azimuth_rad * (180 / Math.PI) : Math.atan2(px, py) * (180 / Math.PI);
    return {
      id: obj.object_id,
      label: obj.object_name ?? obj.object_id,
      type: obj.object_type ?? "obj",
      x: px,
      y: py,
      radius,
      azimuth_deg,
      speed: s.speed,
      heading: s.heading,
      rcs: s.rcs,
    };
  };

  const pointFromSample = (s: ScenarioInspectorSample | null) => {
    if (!s) return null;
    const { x, y } = sampleToCartesian(s);
    return { x, y, radius: Math.hypot(x, y) };
  };

  useEffect(() => {
    void refresh();
    const id = setInterval(() => { void refresh(); }, 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    void decodeScenario(data?.current_scenario ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.current_scenario, data?.local_scenario_path, data?.connected, data?.host]);

  useEffect(() => {
    const current = data?.current_scenario ?? null;
    if (current !== lastScenario) {
      setPlaybackSec(0);
      setPreviewState("stopped");
      setLastScenario(current);
    }
  }, [data?.current_scenario, lastScenario]);

  useEffect(() => {
    if (manualPreview) {
      return;
    }
    if (previewState !== "playing") {
      return;
    }
    const duration = deriveDuration(decode);
    if (!(duration > 0)) {
      return;
    }
    const id = setInterval(() => {
      setPlaybackSec((prev) => {
        const next = prev + 0.1;
        if (previewLoop) {
          return next > duration ? 0 : next;
        }
        return Math.min(next, duration);
      });
    }, 100);
    return () => clearInterval(id);
  }, [previewState, previewLoop, decode, manualPreview]);

  useEffect(() => {
    const duration = deriveDuration(decode);
    if (previewState === "playing" && !previewLoop && duration > 0 && playbackSec >= duration) {
      setPreviewState("paused");
    }
  }, [playbackSec, previewState, previewLoop, decode]);

  const stateKey = previewState;
  const stateColor = STATE_COLORS[stateKey] ?? "#64748b";
  const stateLabel = STATE_LABELS[stateKey] ?? stateKey;
  const duration = deriveDuration(decode);
  const hasDecodedScenario = (decode?.objects?.length ?? 0) > 0;
  const loadedScenarioPath =
    decode?.loaded_scenario_path
    ?? decode?.file_path
    ?? decode?.remote_path
    ?? data?.current_scenario
    ?? null;
  const objectTotal = decode?.object_count ?? decode?.objects?.length ?? 0;
  const sampleTotal = (decode?.objects ?? []).reduce((sum, obj) => sum + (obj.samples?.length ?? 0), 0);
  const inferredTimeStart = (decode?.objects ?? []).flatMap((obj) => obj.samples ?? [])
    .map((s) => s.timestamp)
    .filter((t): t is number => typeof t === "number" && Number.isFinite(t))
    .reduce((min, t) => Math.min(min, t), Number.POSITIVE_INFINITY);
  const inferredTimeEnd = (decode?.objects ?? []).flatMap((obj) => obj.samples ?? [])
    .map((s) => s.timestamp)
    .filter((t): t is number => typeof t === "number" && Number.isFinite(t))
    .reduce((max, t) => Math.max(max, t), Number.NEGATIVE_INFINITY);
  const timeStart = Number.isFinite(decode?.time_start) ? (decode?.time_start as number) : (Number.isFinite(inferredTimeStart) ? inferredTimeStart : null);
  const timeEnd = Number.isFinite(decode?.time_end) ? (decode?.time_end as number) : (Number.isFinite(inferredTimeEnd) ? inferredTimeEnd : null);
  const currentStates = (decode?.objects ?? [])
    .map((obj) => objectState(obj, playbackSec))
    .filter((v): v is NonNullable<typeof v> => v !== null)
    .filter((v) => Number.isFinite(v.radius));

  const trajectoryRadii = (decode?.objects ?? []).flatMap((obj) => {
    if (!obj.samples || obj.samples.length === 0) return [] as number[];
    const startPoint = pointFromSample(obj.samples[0]);
    const endPoint = pointFromSample(obj.samples[obj.samples.length - 1]);
    return [startPoint?.radius, endPoint?.radius].filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  });

  const maxRange = Math.max(50, ...trajectoryRadii, ...currentStates.map((s) => s.radius));
  const primary = currentStates[0] ?? null;

  const primaryObject = decode?.objects?.[0] ?? null;
  const primaryStart = primaryObject && primaryObject.samples.length > 0 ? pointFromSample(primaryObject.samples[0]) : null;
  const primaryEnd = primaryObject && primaryObject.samples.length > 0
    ? pointFromSample(primaryObject.samples[primaryObject.samples.length - 1])
    : null;
  const scale = 120 / maxRange;

  return (
    <div className="sim-overview">
      <div className="sim-polar-layout">
        <div className="sim-polar-card">
          <svg viewBox="0 0 280 280" className="sim-polar-svg" role="img" aria-label="Polar simulation view">
            <circle cx="140" cy="140" r="120" className="sim-polar-ring" />
            <circle cx="140" cy="140" r="90" className="sim-polar-ring" />
            <circle cx="140" cy="140" r="60" className="sim-polar-ring" />
            <circle cx="140" cy="140" r="30" className="sim-polar-ring" />
            <line x1="20" y1="140" x2="260" y2="140" className="sim-polar-axis" />
            <line x1="140" y1="20" x2="140" y2="260" className="sim-polar-axis" />
            <circle cx="140" cy="140" r="6" className="sim-radar-origin" />

            {currentStates.map((obj, idx) => {
              const x = 140 + obj.x * scale;
              const y = 140 - obj.y * scale;
              const hue = (idx * 57) % 360;
              const color = `hsl(${hue}, 84%, 64%)`;
              // Azimuth spoke: thin line from origin toward target
              const az_rad = obj.azimuth_deg * (Math.PI / 180);
              const spokeLen = 120;
              const spokeX = 140 + Math.sin(az_rad) * spokeLen;
              const spokeY = 140 - Math.cos(az_rad) * spokeLen;
              // Heading arrow: short arrow showing velocity direction.
              // If the object has an explicit heading field use it; otherwise derive
              // from azimuth + radial velocity sign (approaching → toward origin).
              const arrowLen = 14;
              const hRad = obj.heading != null
                ? obj.heading
                : az_rad + ((obj.speed != null && obj.speed < 0) ? Math.PI : 0);
              const arrowX = x + Math.sin(hRad) * arrowLen;
              const arrowY = y - Math.cos(hRad) * arrowLen;
              return (
                <g key={obj.id}>
                  {/* Azimuth spoke */}
                  <line x1="140" y1="140" x2={spokeX} y2={spokeY}
                    stroke={color} strokeWidth="0.6" strokeDasharray="3 3" opacity="0.45" />
                  {/* Heading arrow */}
                  <line x1={x} y1={y} x2={arrowX} y2={arrowY}
                    stroke={color} strokeWidth="1.5" markerEnd={`url(#arr${idx})`} />
                  <defs>
                    <marker id={`arr${idx}`} markerWidth="4" markerHeight="4" refX="2" refY="2" orient="auto">
                      <path d="M0,0 L0,4 L4,2 Z" fill={color} />
                    </marker>
                  </defs>
                  <circle cx={x} cy={y} r="5" fill={color} className="sim-target-dot" />
                  <text x={x + 7} y={y - 7} className="sim-target-label">
                    {obj.id} {obj.azimuth_deg.toFixed(1)}°
                  </text>
                </g>
              );
            })}
          </svg>
          <div className="sim-range-label">Range scale: 0 to {maxRange.toFixed(1)} m</div>
        </div>

        <div className="sim-stats-card">
          <div className="sim-preview-header">
            <span className="sim-preview-title">Scenario Preview Details</span>
            <span className="sim-state-badge" style={{ background: stateColor }}>{stateLabel}</span>
          </div>
          <div className="sim-stat-grid">
            <div className="sim-stat">
              <span className="sim-label">Loaded Scenario</span>
              <span className="sim-val" title={loadedScenarioPath ?? "-"}>
                {loadedScenarioPath ? basename(loadedScenarioPath) : "-"}
              </span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Source Path</span>
              <span className="sim-val" title={loadedScenarioPath ?? "-"}>
                {loadedScenarioPath ?? "-"}
              </span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Format</span>
              <span className="sim-val">{decode?.format_detected ?? "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Duration</span>
              <span className="sim-val">{duration > 0 ? `${duration.toFixed(3)} s` : "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Time Start</span>
              <span className="sim-val">{timeStart != null ? `${timeStart.toFixed(3)} s` : "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Time End</span>
              <span className="sim-val">{timeEnd != null ? `${timeEnd.toFixed(3)} s` : "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Timestep Count</span>
              <span className="sim-val">{decode?.timestep_count ?? "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Object Count</span>
              <span className="sim-val">{objectTotal}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Sample Count</span>
              <span className="sim-val">{sampleTotal}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Azimuth</span>
              <span className="sim-val">{primary?.azimuth_deg != null ? `${primary.azimuth_deg.toFixed(2)}°` : "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Speed</span>
              <span className="sim-val">{primary?.speed != null ? `${primary.speed.toFixed(1)} m/s` : "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Distance</span>
              <span className="sim-val">{primary ? `${primary.radius.toFixed(1)} m` : "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">RCS</span>
              <span className="sim-val">{primary?.rcs != null ? `${primary.rcs.toFixed(2)} m²` : "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">Start Point</span>
              <span className="sim-val">{primaryStart ? `${primaryStart.x.toFixed(1)}, ${primaryStart.y.toFixed(1)} m` : "-"}</span>
            </div>
            <div className="sim-stat">
              <span className="sim-label">End Point</span>
              <span className="sim-val">{primaryEnd ? `${primaryEnd.x.toFixed(1)}, ${primaryEnd.y.toFixed(1)} m` : "-"}</span>
            </div>
          </div>
          <div className="sim-timeline-row">
            <label className="sim-timeline-label">
              Preview Time {playbackSec.toFixed(2)} s
            </label>
            <div className="sim-preview-controls" role="group" aria-label="Preview Controls">
              <button
                type="button"
                className="sim-preview-btn play"
                onClick={() => setPreviewState("playing")}
                disabled={!hasDecodedScenario}
              >
                Preview Play
              </button>
              <button
                type="button"
                className="sim-preview-btn"
                onClick={() => setPreviewState("paused")}
                disabled={!hasDecodedScenario || previewState !== "playing"}
              >
                Preview Pause
              </button>
              <button
                type="button"
                className="sim-preview-btn stop"
                onClick={() => {
                  setPreviewState("stopped");
                  setPlaybackSec(0);
                }}
                disabled={!hasDecodedScenario}
              >
                Preview Stop
              </button>
              <button
                type="button"
                className="sim-preview-btn"
                onClick={() => {
                  setPlaybackSec(0);
                  setPreviewState("playing");
                }}
                disabled={!hasDecodedScenario}
              >
                Preview Restart
              </button>
              <label className="sim-preview-loop">
                <input
                  type="checkbox"
                  checked={previewLoop}
                  onChange={(e) => setPreviewLoop(e.target.checked)}
                  disabled={!hasDecodedScenario}
                />
                Loop
              </label>
            </div>
            <input
              type="range"
              min={0}
              max={duration > 0 ? duration : 1}
              step={0.05}
              value={Math.min(playbackSec, duration > 0 ? duration : 1)}
              onMouseDown={() => setManualPreview(true)}
              onMouseUp={() => setManualPreview(false)}
              onChange={(e) => setPlaybackSec(Number(e.target.value))}
            />
          </div>
          {(decode?.warnings?.length ?? 0) > 0 && (
            <div className="sim-footnotes">
              <span className="sim-count">Warnings: {decode?.warnings?.join(" | ")}</span>
            </div>
          )}
          {(decode?.errors?.length ?? 0) > 0 && (
            <div className="sim-footnotes">
              <span className="sim-footer-err">Decode Errors: {decode?.errors?.join(" | ")}</span>
            </div>
          )}
        </div>
      </div>

      <div className="sim-footer">
        {fetchError ? (
          <span className="sim-footer-err">Overview unavailable: {fetchError}</span>
        ) : lastRefresh ? (
          <span className="sim-footer-ts">
            Updated {lastRefresh.toLocaleTimeString()} · auto-refresh every 3 s
          </span>
        ) : (
          <span className="sim-dim">Loading…</span>
        )}
      </div>
    </div>
  );
}
