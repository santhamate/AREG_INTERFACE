import React, { useEffect, useState } from "react";
import "./ScenarioPlayer.css";

type ScenarioFile = {
  name: string;
  path?: string;
  extension?: string;
  size_bytes?: number;
  modified_time?: string;
  is_loadable?: boolean;
};

type PlaybackState = "unknown" | "not_loaded" | "loaded" | "playing" | "paused" | "stopped" | "error";

type CommandLogEntry = {
  timestamp: string;
  command: string;
  command_type: "query" | "write" | "empty";
  ok: boolean;
  response?: string | null;
  message?: string | null;
  error?: string | null;
};

const API_BASE = "http://127.0.0.1:8000/api";

export default function ScenarioPlayer() {
  const [scenarios, setScenarios] = useState<ScenarioFile[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("unknown");
  const [isLoading, setIsLoading] = useState(false);
  const [connected, setConnected] = useState(false);
  const [instrumentId, setInstrumentId] = useState<string | null>(null);
  const [commandLog, setCommandLog] = useState<CommandLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [checkErrorsEnabled, setCheckErrorsEnabled] = useState(false);

  // Initial load and auto-refresh
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/session`, { method: "GET" });
        if (response.ok) {
          const state = await response.json();
          setConnected(state.connected);
        }
      } catch (err) {
        // Silently handle connection check errors
      }
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  // Fetch command log
  const refreshCommandLog = async () => {
    try {
      const response = await fetch(`${API_BASE}/scenario/log`, { method: "GET" });
      if (response.ok) {
        const data = await response.json();
        setCommandLog(data.log_entries);
      }
    } catch (err) {
      console.error("Failed to fetch command log", err);
    }
  };

  // Scan scenarios
  const scanScenarios = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_refresh: true }),
      });

      if (!response.ok) throw new Error("Scan failed");

      const data = await response.json();
      if (data.ok) {
        setScenarios(data.scenarios);
      } else {
        setError(data.error || "Scan failed");
      }
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setIsLoading(false);
    }
  };

  // Select scenario
  const selectScenarioHandler = async (name: string) => {
    setSelectedScenario(name);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_name: name, auto_load: false }),
      });

      if (!response.ok) throw new Error("Selection failed");
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Selection failed");
    }
  };

  // Load scenario
  const loadScenarioHandler = async () => {
    if (!selectedScenario) {
      setError("No scenario selected");
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_name: selectedScenario }),
      });

      if (!response.ok) throw new Error("Load failed");

      const data = await response.json();
      if (data.ok) {
        setPlaybackState("loaded");
      } else {
        setError(data.message || "Load failed");
      }
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setIsLoading(false);
    }
  };

  // Play
  const playHandler = async () => {
    if (!selectedScenario) {
      setError("No scenario selected");
      return;
    }

    if (playbackState === "not_loaded" || playbackState === "unknown") {
      await loadScenarioHandler();
    }

    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/play`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Play failed");

      const data = await response.json();
      if (data.ok) {
        setPlaybackState("playing");
      } else {
        setError(data.message || "Play failed");
      }
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Play failed");
    } finally {
      setIsLoading(false);
    }
  };

  // Pause
  const pauseHandler = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/pause`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Pause failed");

      const data = await response.json();
      if (data.ok) {
        setPlaybackState("paused");
      } else {
        setError(data.message || "Pause failed");
      }
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pause failed");
    } finally {
      setIsLoading(false);
    }
  };

  // Stop
  const stopHandler = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Stop failed");

      const data = await response.json();
      if (data.ok) {
        setPlaybackState("stopped");
      } else {
        setError(data.message || "Stop failed");
      }
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stop failed");
    } finally {
      setIsLoading(false);
    }
  };

  // Restart
  const restartHandler = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/restart`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Restart failed");

      const data = await response.json();
      if (data.ok) {
        setPlaybackState("playing");
      } else {
        setError(data.message || "Restart failed");
      }
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restart failed");
    } finally {
      setIsLoading(false);
    }
  };

  // Next
  const nextHandler = async () => {
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/next`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Next failed");

      const data = await response.json();
      if (!data.ok) {
        setError(data.message || "Next failed");
      }
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Next failed");
    }
  };

  // Previous
  const prevHandler = async () => {
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/previous`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error("Previous failed");

      const data = await response.json();
      if (!data.ok) {
        setError(data.message || "Previous failed");
      }
      await refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Previous failed");
    }
  };

  // Clear log
  const clearLogHandler = async () => {
    try {
      const response = await fetch(`${API_BASE}/scenario/log/clear`, { method: "POST" });
      if (response.ok) {
        setCommandLog([]);
      }
    } catch (err) {
      console.error("Failed to clear log", err);
    }
  };

  const getStateColor = (state: PlaybackState): string => {
    switch (state) {
      case "playing":
        return "#4ade80";
      case "paused":
        return "#fbbf24";
      case "stopped":
        return "#ef4444";
      case "loaded":
        return "#60a5fa";
      case "error":
        return "#ef4444";
      default:
        return "#9ca3af";
    }
  };

  const getStateLabel = (state: PlaybackState): string => {
    switch (state) {
      case "not_loaded":
        return "Not Loaded";
      case "unknown":
        return "Unknown";
      default:
        return state.charAt(0).toUpperCase() + state.slice(1);
    }
  };

  return (
    <div className="scenario-player">
      {/* Top Bar */}
      <div className="top-bar">
        <div className="connection-info">
          <span className={`status-dot ${connected ? "connected" : "disconnected"}`}></span>
          <span>{connected ? "Connected" : "Disconnected"}</span>
        </div>
        <div className="playback-state" style={{ backgroundColor: getStateColor(playbackState) }}>
          {getStateLabel(playbackState)}
        </div>
        {error && <div className="error-message">{error}</div>}
      </div>

      <div className="main-layout">
        {/* Left Panel: Scenario List */}
        <div className="left-panel">
          <div className="panel-header">
            <h3>Scenarios</h3>
            <button onClick={scanScenarios} disabled={isLoading} className="refresh-btn">
              {isLoading ? "Scanning..." : "Scan"}
            </button>
          </div>

          <div className="scenario-list">
            {scenarios.length === 0 ? (
              <div className="empty-state">No scenarios found. Click "Scan" to discover.</div>
            ) : (
              scenarios.map((scenario) => (
                <div
                  key={scenario.name}
                  className={`scenario-item ${selectedScenario === scenario.name ? "selected" : ""}`}
                  onClick={() => selectScenarioHandler(scenario.name)}
                >
                  <div className="scenario-name">{scenario.name}</div>
                  {scenario.extension && <div className="scenario-ext">{scenario.extension}</div>}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Center Panel: Player Controls */}
        <div className="center-panel">
          <div className="scenario-title">{selectedScenario || "No Scenario Selected"}</div>

          <div className="player-controls">
            <button onClick={prevHandler} disabled={!connected} className="control-btn nav-btn" title="Previous">
              ⏮
            </button>
            <button onClick={playHandler} disabled={!connected || isLoading} className="control-btn play-btn" title="Play">
              ▶
            </button>
            <button onClick={pauseHandler} disabled={!connected || isLoading} className="control-btn pause-btn" title="Pause">
              ⏸
            </button>
            <button onClick={stopHandler} disabled={!connected || isLoading} className="control-btn stop-btn" title="Stop">
              ⏹
            </button>
            <button onClick={restartHandler} disabled={!connected || isLoading} className="control-btn restart-btn" title="Restart">
              🔄
            </button>
            <button onClick={nextHandler} disabled={!connected} className="control-btn nav-btn" title="Next">
              ⏭
            </button>
          </div>

          <div className="quick-actions">
            <button onClick={loadScenarioHandler} disabled={!connected || !selectedScenario || isLoading} className="action-btn">
              Load Scenario
            </button>
          </div>
        </div>

        {/* Right Panel: Details & Settings */}
        <div className="right-panel">
          <div className="panel-header">
            <h3>Settings</h3>
          </div>

          <div className="settings-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={checkErrorsEnabled}
                onChange={(e) => setCheckErrorsEnabled(e.target.checked)}
              />
              Check errors after write
            </label>
          </div>

          {selectedScenario && (
            <div className="scenario-details">
              <div className="detail-item">
                <span className="label">Selected:</span>
                <span className="value">{selectedScenario}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Panel: Command Log */}
      <div className="bottom-panel">
        <div className="log-header">
          <h3>Command Log</h3>
          <button onClick={clearLogHandler} className="clear-btn">
            Clear
          </button>
        </div>

        <div className="command-log">
          {commandLog.length === 0 ? (
            <div className="empty-log">No commands executed yet</div>
          ) : (
            <table className="log-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Type</th>
                  <th>Command</th>
                  <th>Response/Message</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {commandLog.map((entry, idx) => (
                  <tr key={idx} className={entry.ok ? "success" : "error"}>
                    <td className="timestamp">{entry.timestamp}</td>
                    <td className="command-type">{entry.command_type}</td>
                    <td className="command">{entry.command}</td>
                    <td className="response">{entry.response || entry.message || entry.error || "-"}</td>
                    <td className="status">{entry.ok ? "✓" : "✗"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
