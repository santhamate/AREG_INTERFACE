import React, { useEffect, useRef, useState } from "react";
import "./TCV907Page.css";

const API_BASE = "http://127.0.0.1:8000/api";
const PREPARED_SWEEP_STORAGE_KEY = "areg.preparedSpeedSweep";

interface RadarMeasurement {
  speed_kmh: number;
  timestamp: string;
  packet_number: number;
  raw_data_hex: string;
}

interface RadarStatistics {
  packets_received: number;
  bytes_received: number;
  speeds_parsed: number;
  parse_errors: number;
  uptime_seconds: number;
  packet_rate_per_second: number;
  speed_history_count: number;
}

interface RadarStatus {
  ok: boolean;
  connected: boolean;
  state: string;
  last_speed?: RadarMeasurement | null;
  statistics: RadarStatistics;
  last_error?: string | null;
}

type ToleranceMode = "fixed_kmh" | "percentage" | "custom_rule";

interface ComparisonRow {
  packet_number: number;
  timestamp: string;
  measured_kmh: number;
  expected_kmh: number;
  error_kmh: number;
  tolerance_kmh: number;
  passed: boolean;
}

interface PreparedSweepScenario {
  index: number;
  filename: string;
  aregPath: string;
  targetKmh: number;
}

interface PreparedSweepPayload {
  timestamp: string;
  count: number;
  scenarios: PreparedSweepScenario[];
}

const DEFAULT_STATUS: RadarStatus = {
  ok: true,
  connected: false,
  state: "disconnected",
  last_speed: null,
  statistics: {
    packets_received: 0,
    bytes_received: 0,
    speeds_parsed: 0,
    parse_errors: 0,
    uptime_seconds: 0,
    packet_rate_per_second: 0,
    speed_history_count: 0,
  },
  last_error: null,
};

export default function TCV907Page() {
  const [radarIp, setRadarIp] = useState("192.168.4.1");
  const [radarPort, setRadarPort] = useState(20000);
  const [connected, setConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [radarStatus, setRadarStatus] = useState<RadarStatus>(DEFAULT_STATUS);
  const [sessionMeasurements, setSessionMeasurements] = useState<RadarMeasurement[]>([]);
  const [expectedTargetKmh, setExpectedTargetKmh] = useState(36);
  const [toleranceMode, setToleranceMode] = useState<ToleranceMode>("fixed_kmh");
  const [toleranceValue, setToleranceValue] = useState(3);
  const [comparisonRunning, setComparisonRunning] = useState(false);
  const [comparisonRows, setComparisonRows] = useState<ComparisonRow[]>([]);
  const [preparedScenarios, setPreparedScenarios] = useState<PreparedSweepScenario[]>([]);
  const [selectedScenarios, setSelectedScenarios] = useState<Record<string, boolean>>({});
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const [scenarioStatus, setScenarioStatus] = useState<string | null>(null);
  const intervalRef = useRef<number | null>(null);
  const comparisonTableRef = useRef<HTMLDivElement | null>(null);
  const autoScrollRef = useRef(true);

  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  const loadPreparedSweep = () => {
    try {
      const raw = localStorage.getItem(PREPARED_SWEEP_STORAGE_KEY);
      if (!raw) {
        setPreparedScenarios([]);
        setScenarioStatus("No prepared sweep found. Prepare Speed Sweep in AREG800A page first.");
        return;
      }
      const parsed = JSON.parse(raw) as PreparedSweepPayload;
      const list = Array.isArray(parsed.scenarios) ? parsed.scenarios : [];
      setPreparedScenarios(list);
      setSelectedScenarios(Object.fromEntries(list.map((s) => [s.aregPath, true])));
      setScenarioStatus(`Loaded prepared sweep: ${list.length} scenario(s) from ${parsed.timestamp}`);
    } catch {
      setPreparedScenarios([]);
      setScenarioStatus("Prepared sweep data is invalid. Re-prepare sweep in AREG800A page.");
    }
  };

  const fetchRadarStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/tcv907/status`);
      if (!response.ok) {
        throw new Error("Failed to fetch radar status");
      }

      const data = (await response.json()) as RadarStatus;
      setRadarStatus(data);
      setConnected(data.connected);
      setError(data.last_error ?? null);

      if (data.last_speed) {
        setSessionMeasurements((prev) => {
          if (prev.some((m) => m.packet_number === data.last_speed!.packet_number)) {
            return prev;
          }
          return [...prev, data.last_speed!];
        });
      }
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      setError(message);
    }
  };

  const refreshRadarData = async () => {
    await fetchRadarStatus();
  };

  useEffect(() => {
    void refreshRadarData();
    loadPreparedSweep();
  }, []);

  useEffect(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!connected) {
      return;
    }

    intervalRef.current = window.setInterval(() => {
      void fetchRadarStatus();
    }, 500);

    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [connected]);

  const exportHistoryToCsv = (rows: RadarMeasurement[], prefix = "tcv907_session_measurements") => {
    if (!rows.length) {
      return;
    }

    const header = ["packet_number", "speed_kmh", "timestamp", "raw_data_hex"];
    const escapeCell = (value: string) => `"${value.replace(/"/g, '""')}"`;
    const lines = rows.map((row) =>
      [String(row.packet_number), row.speed_kmh.toFixed(2), row.timestamp, row.raw_data_hex.toUpperCase()]
        .map(escapeCell)
        .join(",")
    );
    // Keep comma as the CSV delimiter and hint Excel to use comma.
    const csv = ["sep=,", header.join(","), ...lines].join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);

    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
    const filename = `${prefix}_${rows.length}_${stamp}.csv`;

    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleConnectionToggle = async () => {
    setIsLoading(true);
    setError(null);

    try {
      if (connected) {
        const response = await fetch(`${API_BASE}/tcv907/disconnect`, { method: "POST" });
        if (!response.ok) {
          throw new Error("Disconnect failed");
        }
        setConnected(false);
        setRadarStatus(DEFAULT_STATUS);
        setComparisonRunning(false);
        return;
      }

      const response = await fetch(`${API_BASE}/tcv907/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip: radarIp, port: radarPort }),
      });

      if (!response.ok) {
        throw new Error("Connect failed");
      }

      setSessionMeasurements([]);
      setComparisonRows([]);
      setComparisonRunning(false);
      await refreshRadarData();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefresh = () => {
    void refreshRadarData();
  };

  const handleClearHistory = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/tcv907/speed/clear`, { method: "POST" });
      if (!response.ok) {
        throw new Error("Failed to clear speed history");
      }

      setSessionMeasurements([]);
      setComparisonRows([]);
      setComparisonRunning(false);
      await fetchRadarStatus();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const calculateTolerance = (expectedKmh: number) => {
    if (toleranceMode === "percentage") {
      return Math.abs(expectedKmh) * (toleranceValue / 100);
    }
    if (toleranceMode === "custom_rule") {
      return Math.abs(expectedKmh) < 100 ? 3 : Math.abs(expectedKmh) * 0.03;
    }
    return toleranceValue;
  };

  useEffect(() => {
    if (!comparisonRunning) {
      return;
    }

    if (!sessionMeasurements.length) {
      setComparisonRows([]);
      return;
    }

    const rows = sessionMeasurements.map((m) => {
      const expected = expectedTargetKmh;
      const measured = m.speed_kmh;
      const tolerance = calculateTolerance(expected);
      const errorKmh = measured - expected;
      return {
        packet_number: m.packet_number,
        timestamp: m.timestamp,
        measured_kmh: measured,
        expected_kmh: expected,
        error_kmh: errorKmh,
        tolerance_kmh: tolerance,
        passed: Math.abs(errorKmh) <= tolerance,
      };
    });

    setComparisonRows(rows);
  }, [comparisonRunning, sessionMeasurements, expectedTargetKmh, toleranceMode, toleranceValue]);

  const handleSaveSessionMeasurements = () => {
    exportHistoryToCsv(sessionMeasurements, "tcv907_session_measurements");
  };

  const toggleScenarioSelection = (key: string) => {
    setSelectedScenarios((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const runSelectedScenarios = async () => {
    const selected = preparedScenarios.filter((s) => selectedScenarios[s.aregPath]);
    if (!selected.length) {
      setScenarioStatus("No scenarios selected");
      return;
    }

    setScenarioBusy(true);
    setScenarioStatus("Setting replay mode to SINGle...");
    setComparisonRunning(true);

    try {
      const replayResponse = await fetch(`${API_BASE}/scenario/replay-mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "SINGle" }),
      });
      if (!replayResponse.ok) {
        throw new Error("Failed to set replay mode SINGle");
      }

      for (let i = 0; i < selected.length; i += 1) {
        const scenario = selected[i];
        const scenarioPath = scenario.aregPath;
        const displayName = scenario.filename;
        setExpectedTargetKmh(scenario.targetKmh);

        setScenarioStatus(`Running ${i + 1}/${selected.length}: ${displayName}`);

        const loadResponse = await fetch(`${API_BASE}/scenario/load`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario_name: scenarioPath, replay_mode: "SINGle" }),
        });
        if (!loadResponse.ok) {
          throw new Error(`Failed to load scenario: ${displayName}`);
        }
        const loadData = await loadResponse.json();
        if (!loadData.ok) {
          throw new Error(loadData.message ?? `Failed to load scenario: ${displayName}`);
        }

        const playResponse = await fetch(`${API_BASE}/scenario/play`, { method: "POST" });
        if (!playResponse.ok) {
          throw new Error(`Failed to play scenario: ${displayName}`);
        }

        // Required delay between scenario executions.
        await sleep(500);
      }

      setScenarioStatus(`Completed ${selected.length} scenario(s)`);
    } catch (e) {
      setScenarioStatus(e instanceof Error ? e.message : "Scenario run failed");
    } finally {
      setScenarioBusy(false);
    }
  };

  const comparisonPassCount = comparisonRows.filter((r) => r.passed).length;
  const comparisonFailCount = comparisonRows.length - comparisonPassCount;
  const comparisonPassRate = comparisonRows.length ? (comparisonPassCount / comparisonRows.length) * 100 : 0;
  const comparisonAvgError = comparisonRows.length
    ? comparisonRows.reduce((sum, row) => sum + row.error_kmh, 0) / comparisonRows.length
    : 0;

  useEffect(() => {
    const el = comparisonTableRef.current;
    if (!el || !autoScrollRef.current) {
      return;
    }
    el.scrollTop = el.scrollHeight;
  }, [comparisonRows.length]);

  const handleComparisonScroll = () => {
    const el = comparisonTableRef.current;
    if (!el) {
      return;
    }

    const thresholdPx = 28;
    const distanceFromBottom = el.scrollHeight - (el.scrollTop + el.clientHeight);
    autoScrollRef.current = distanceFromBottom <= thresholdPx;
  };

  const formatTimestamp = (timestamp: string) =>
    new Date(timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

  return (
    <div className="tcv907-page">
      <div className="tcv907-header">
        <h1>📡 TCV907 Radar Validation</h1>
        <p>Radar-client-backed connection, live speed capture, and measurement history</p>
      </div>

      <div className="tcv907-toolbar">
        <button className="action-button secondary" onClick={handleRefresh} disabled={isLoading}>
          Refresh Now
        </button>
      </div>

      <div className="tcv907-grid">
        <div className="tcv907-card">
          <div className="tcv907-card-header">Connection Status</div>
          <div className="tcv907-card-content">
            {error ? <div className="error-message">{error}</div> : null}
            <div className="status-summary">{radarStatus.state}</div>

            <div className="connection-row">
              <span className="label">Status:</span>
              <span className={`status-badge ${connected ? "online" : "offline"}`}>
                {connected ? "Connected" : "Disconnected"}
              </span>
            </div>

            <div className="connection-row">
              <span className="label">Host:</span>
              <input
                type="text"
                placeholder="192.168.4.1"
                value={radarIp}
                onChange={(event) => setRadarIp(event.target.value)}
                disabled={connected}
                className="input-field"
              />
            </div>

            <div className="connection-row">
              <span className="label">Port:</span>
              <input
                type="number"
                placeholder="20000"
                value={radarPort}
                onChange={(event) => setRadarPort(Number(event.target.value))}
                disabled={connected}
                className="input-field"
                style={{ width: "80px" }}
              />
            </div>

            <button
              onClick={() => {
                void handleConnectionToggle();
              }}
              disabled={isLoading}
              className={`action-button ${connected ? "disconnect" : "connect"}`}
            >
              {isLoading ? "Working..." : connected ? "Disconnect" : "Connect"}
            </button>
          </div>
        </div>

        <div className="tcv907-card">
          <div className="tcv907-card-header">Live Measurement</div>
          <div className="tcv907-card-content">
            {connected && radarStatus.last_speed ? (
              <div className="measurement-panel">
                <div className="raw-hex-display">
                  <div className="raw-hex-label">Raw Packet (Hex):</div>
                  <div className="raw-hex-value">{radarStatus.last_speed.raw_data_hex.toUpperCase()}</div>
                  <div className="raw-hex-meta">
                    Length: {(radarStatus.last_speed.raw_data_hex.length / 2).toFixed(0)} bytes | 
                    Packet #{radarStatus.last_speed.packet_number} | 
                    {formatTimestamp(radarStatus.last_speed.timestamp)}
                  </div>
                </div>
                <div className="speed-readout">{radarStatus.last_speed.speed_kmh.toFixed(2)} km/h</div>
              </div>
            ) : (
              <div className="coming-soon">
                <p>{connected ? "Waiting for speed data..." : "Connect radar to view measurements"}</p>
              </div>
            )}
          </div>
        </div>

        <div className="tcv907-card">
          <div className="tcv907-card-header">Statistics</div>
          <div className="tcv907-card-content">
            {connected ? (
              <div>
                <div className="stat-row">
                  <span className="stat-label">Packets Received</span>
                  <span className="stat-value">{radarStatus.statistics.packets_received}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Bytes Received</span>
                  <span className="stat-value">{radarStatus.statistics.bytes_received}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Speeds Parsed</span>
                  <span className="stat-value">{radarStatus.statistics.speeds_parsed}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Parse Errors</span>
                  <span className="stat-value">{radarStatus.statistics.parse_errors}</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Packet Rate</span>
                  <span className="stat-value">{radarStatus.statistics.packet_rate_per_second.toFixed(1)} pps</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">Uptime</span>
                  <span className="stat-value">{Math.floor(radarStatus.statistics.uptime_seconds)}s</span>
                </div>
                <div className="stat-row">
                  <span className="stat-label">History Count</span>
                  <span className="stat-value">{radarStatus.statistics.speed_history_count}</span>
                </div>
              </div>
            ) : (
              <div className="coming-soon">
                <p>Connect radar to log data</p>
              </div>
            )}
          </div>
        </div>

        <div className="tcv907-card tcv907-card--wide">
          <div className="tcv907-card-header">Scenario vs Radar Validation</div>
          <div className="tcv907-card-content">
            <div className="history-controls">
              <button className="action-button secondary" onClick={loadPreparedSweep} disabled={scenarioBusy}>
                Load Prepared Sweep
              </button>
              <button className="action-button secondary" onClick={() => void runSelectedScenarios()} disabled={scenarioBusy || !preparedScenarios.length}>
                Run Selected (Single)
              </button>
              <div className="connection-row">
                <span className="label">Target Speed (km/h):</span>
                <input
                  type="number"
                  step="0.1"
                  value={expectedTargetKmh}
                  onChange={(event) => setExpectedTargetKmh(Number(event.target.value))}
                  className="input-field input-field--compact"
                />
              </div>
              <div className="connection-row">
                <span className="label">Tolerance Mode:</span>
                <select
                  value={toleranceMode}
                  onChange={(event) => setToleranceMode(event.target.value as ToleranceMode)}
                  className="input-field"
                >
                  <option value="fixed_kmh">Fixed (km/h)</option>
                  <option value="percentage">Percentage (%)</option>
                  <option value="custom_rule">Custom Rule</option>
                </select>
              </div>
              <div className="connection-row">
                <span className="label">Tolerance Value:</span>
                <input
                  type="number"
                  step="0.1"
                  value={toleranceValue}
                  onChange={(event) => setToleranceValue(Number(event.target.value))}
                  className="input-field input-field--compact"
                  disabled={toleranceMode === "custom_rule"}
                />
              </div>
              <button className="action-button secondary" onClick={handleSaveSessionMeasurements} disabled={!sessionMeasurements.length}>
                Save Session Measurements
              </button>
              <button
                className="action-button secondary"
                onClick={() => setComparisonRunning(true)}
                disabled={!sessionMeasurements.length || comparisonRunning}
              >
                Start Comparison
              </button>
              <button
                className="action-button danger"
                onClick={() => setComparisonRunning(false)}
                disabled={!comparisonRunning}
              >
                Stop Comparison
              </button>
              <button className="action-button danger" onClick={() => void handleClearHistory()} disabled={!connected || isLoading}>
                Clear Session
              </button>
            </div>

            {preparedScenarios.length > 0 ? (
              <div className="history-table-wrap history-table-wrap--fixed-10rows" style={{ marginBottom: "12px" }}>
                <table className="history-table">
                  <thead>
                    <tr>
                      <th>Select</th>
                      <th>Scenario</th>
                      <th>Target (prepared)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preparedScenarios.map((scenario) => {
                      const key = scenario.aregPath;
                      return (
                        <tr key={key}>
                          <td>
                            <input
                              type="checkbox"
                              checked={!!selectedScenarios[key]}
                              onChange={() => toggleScenarioSelection(key)}
                            />
                          </td>
                          <td>{scenario.filename}</td>
                          <td>{scenario.targetKmh.toFixed(2)} km/h</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}

            {scenarioStatus ? <div className="status-summary">{scenarioStatus}</div> : null}

            {comparisonRows.length > 0 ? (
              <>
                <div className="comparison-summary">
                  <div className="stat-row">
                    <span className="stat-label">Rows Compared</span>
                    <span className="stat-value">{comparisonRows.length}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Pass</span>
                    <span className="stat-value pass">{comparisonPassCount}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Fail</span>
                    <span className="stat-value fail">{comparisonFailCount}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Pass Rate</span>
                    <span className="stat-value">{comparisonPassRate.toFixed(2)}%</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Average Error</span>
                    <span className="stat-value">{comparisonAvgError.toFixed(2)} km/h</span>
                  </div>
                </div>

                <div
                  className="history-table-wrap history-table-wrap--fixed-10rows"
                  ref={comparisonTableRef}
                  onScroll={handleComparisonScroll}
                >
                  <table className="history-table">
                    <thead>
                      <tr>
                        <th>Packet</th>
                        <th>Timestamp</th>
                        <th>Expected</th>
                        <th>Measured</th>
                        <th>Error</th>
                        <th>Tolerance</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparisonRows.map((row) => (
                        <tr key={`${row.packet_number}-${row.timestamp}`}>
                          <td>#{row.packet_number}</td>
                          <td>{formatTimestamp(row.timestamp)}</td>
                          <td>{row.expected_kmh.toFixed(2)} km/h</td>
                          <td>{row.measured_kmh.toFixed(2)} km/h</td>
                          <td>{row.error_kmh.toFixed(2)} km/h</td>
                          <td>{row.tolerance_kmh.toFixed(2)} km/h</td>
                          <td>
                            <span className={`status-badge ${row.passed ? "online" : "offline"}`}>
                              {row.passed ? "PASS" : "FAIL"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="coming-soon">
                <p>{comparisonRunning ? "Waiting for measurements..." : "Click Start Comparison to begin."}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
