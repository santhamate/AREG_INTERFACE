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
  command_type: "query" | "binary-query" | "write" | "action" | "empty";
  ok: boolean;
  response?: string | null;
  message?: string | null;
  error?: string | null;
};

const API_BASE = "http://127.0.0.1:8000/api";

export default function ScenarioPlayer() {
  const [scenarios, setScenarios] = useState<ScenarioFile[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);
  const [selectedScenarioPath, setSelectedScenarioPath] = useState<string | null>(null);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("unknown");
  const [isLoading, setIsLoading] = useState(false);
  const [connected, setConnected] = useState(false);
  const [instrumentId, setInstrumentId] = useState<string | null>(null);
  const [commandLog, setCommandLog] = useState<CommandLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [checkErrorsEnabled, setCheckErrorsEnabled] = useState(false);
  const [playlistMode, setPlaylistMode] = useState(false);
  const [playlist, setPlaylist] = useState<string[]>([]);
  const [currentPlaylistIndex, setCurrentPlaylistIndex] = useState(0);

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
  const selectScenarioHandler = async (name: string, path?: string) => {
    const target = path || name;
    setSelectedScenario(name);
    setSelectedScenarioPath(target);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_name: target, auto_load: false }),
      });

      if (!response.ok) throw new Error("Selection failed");
      void refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Selection failed");
    }
  };

  // Load scenario
  const loadScenarioHandler = async (scenarioToLoad?: string) => {
    const targetScenario = scenarioToLoad ?? selectedScenarioPath ?? selectedScenario;
    if (!targetScenario) {
      setError("No scenario selected");
      return;
    }

    if (scenarioToLoad && scenarioToLoad !== selectedScenarioPath && scenarioToLoad !== selectedScenario) {
      setSelectedScenario(scenarioToLoad);
      setSelectedScenarioPath(scenarioToLoad);
    }

    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/scenario/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_name: targetScenario }),
      });

      if (!response.ok) throw new Error("Load failed");

      const data = await response.json();
      if (data.ok) {
        setPlaybackState("loaded");
      } else {
        setError(data.message || "Load failed");
      }
      void refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setIsLoading(false);
    }
  };

  // Play
  const playHandler = async () => {
    if (!selectedScenario && !selectedScenarioPath) {
      setError("No scenario selected");
      return;
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
      void refreshCommandLog();
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
      void refreshCommandLog();
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
      void refreshCommandLog();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stop failed");
    } finally {
      setIsLoading(false);
    }
  };

  // Restart
  const restartHandler = async () => {
    if (!selectedScenario && !selectedScenarioPath) {
      setError("No scenario selected");
      return;
    }

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
      void refreshCommandLog();
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
      void refreshCommandLog();
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
      void refreshCommandLog();
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

  // Playlist handlers
  const togglePlaylistMode = () => {
    setPlaylistMode(!playlistMode);
    if (playlistMode) {
      setPlaylist([]);
      setCurrentPlaylistIndex(0);
    }
  };

  const toggleScenarioInPlaylist = (scenarioName: string) => {
    setPlaylist((prev) => {
      if (prev.includes(scenarioName)) {
        return prev.filter((s) => s !== scenarioName);
      } else {
        return [...prev, scenarioName];
      }
    });
  };

  const removeFromPlaylist = (index: number) => {
    setPlaylist((prev) => prev.filter((_, i) => i !== index));
    if (currentPlaylistIndex >= playlist.length - 1 && currentPlaylistIndex > 0) {
      setCurrentPlaylistIndex(currentPlaylistIndex - 1);
    }
  };

  const movePlaylistItem = (fromIndex: number, toIndex: number) => {
    const newPlaylist = [...playlist];
    const [removed] = newPlaylist.splice(fromIndex, 1);
    newPlaylist.splice(toIndex, 0, removed);
    setPlaylist(newPlaylist);
  };

  const clearPlaylist = () => {
    setPlaylist([]);
    setCurrentPlaylistIndex(0);
  };

  const loadAllInPlaylist = async () => {
    if (playlist.length === 0) return;
    setIsLoading(true);
    setError(null);
    for (const scenario of playlist) {
      try {
        // find path for this scenario name
        const found = scenarios.find((s) => s.name === scenario);
        const target = found?.path || scenario;
        const response = await fetch(`${API_BASE}/scenario/load`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario_name: target }),
        });
        if (!response.ok) throw new Error(`Load failed for ${scenario}`);
        const data = await response.json();
        if (!data.ok) setError(data.message || `Load failed for ${scenario}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : `Load failed for ${scenario}`);
      }
    }
    setIsLoading(false);
    void refreshCommandLog();
  };

  const playPlaylist = async () => {
    if (playlist.length === 0) return;
    setCurrentPlaylistIndex(0);
    const found = scenarios.find((s) => s.name === playlist[0]);
    const target = found?.path || playlist[0];
    setSelectedScenario(playlist[0]);
    setSelectedScenarioPath(target);
    await loadScenarioHandler(target);
    setTimeout(() => void playHandler(), 500);
  };

  const playNextInPlaylist = async () => {
    if (!playlistMode || playlist.length === 0) return;
    
    if (currentPlaylistIndex < playlist.length - 1) {
      const nextIndex = currentPlaylistIndex + 1;
      setCurrentPlaylistIndex(nextIndex);
      await selectScenarioHandler(playlist[nextIndex]);
      setTimeout(() => playHandler(), 500);
    } else {
      // Playlist finished
      setPlaybackState("stopped");
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

          {/* Playlist Mode Toggle */}
          <div className="playlist-mode-toggle">
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={playlistMode}
                onChange={togglePlaylistMode}
              />
              <span className="toggle-text">Playlist Mode</span>
            </label>
          </div>

          <div className="scenario-list">
            {scenarios.length === 0 ? (
              <div className="empty-state">No scenarios found. Click "Scan" to discover.</div>
            ) : (
              scenarios.map((scenario) => (
                <div
                  key={scenario.name}
                  className={`scenario-item ${selectedScenario === scenario.name ? "selected" : ""} ${
                    playlistMode && playlist.includes(scenario.name) ? "in-playlist" : ""
                  }`}
                >
                  {playlistMode ? (
                    <label className="scenario-checkbox">
                      <input
                        type="checkbox"
                        checked={playlist.includes(scenario.name)}
                        onChange={() => toggleScenarioInPlaylist(scenario.name)}
                      />
                      <div className="scenario-name">{scenario.name}</div>
                      {scenario.extension && <div className="scenario-ext">{scenario.extension}</div>}
                    </label>
                  ) : (
                    <>
                      <div className="scenario-row-actions">
                        <div
                          className="scenario-name"
                          onClick={() => selectScenarioHandler(scenario.name, scenario.path)}
                        >
                          {scenario.name}
                        </div>
                        <button
                          className="scenario-load-btn"
                          disabled={isLoading}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedScenario(scenario.name);
                            setSelectedScenarioPath(scenario.path || scenario.name);
                            void loadScenarioHandler(scenario.path || scenario.name);
                          }}
                          title={connected ? "Load scenario" : "Load to offline player"}
                        >
                          Load
                        </button>
                      </div>
                      {scenario.extension && <div className="scenario-ext">{scenario.extension}</div>}
                    </>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Center Panel: Player Controls */}
        <div className="center-panel">
          <div className="scenario-title">{selectedScenario || "No Scenario Selected"}</div>

          <div className="player-controls">
            <button onClick={prevHandler} disabled={isLoading} className="control-btn nav-btn" title="Previous">
              ⏮
            </button>
            <button onClick={playHandler} disabled={isLoading} className="control-btn play-btn" title="Play">
              ▶
            </button>
            <button onClick={pauseHandler} disabled={isLoading} className="control-btn pause-btn" title="Pause">
              ⏸
            </button>
            <button onClick={stopHandler} disabled={isLoading} className="control-btn stop-btn" title="Stop">
              ⏹
            </button>
            <button onClick={restartHandler} disabled={isLoading} className="control-btn restart-btn" title="Restart">
              🔄
            </button>
            <button onClick={nextHandler} disabled={isLoading} className="control-btn nav-btn" title="Next">
              ⏭
            </button>
          </div>

          <div className="quick-actions">
            <button onClick={() => void loadScenarioHandler()} disabled={!selectedScenario || isLoading} className="action-btn">
              {connected ? "Load Scenario" : "Load to Offline Player"}
            </button>
          </div>
        </div>

        {/* Right Panel: Details & Settings */}
        <div className="right-panel">
          {playlistMode ? (
            <>
              <div className="panel-header">
                <h3>Playlist Queue ({playlist.length})</h3>
              </div>

              {playlist.length === 0 ? (
                <div className="empty-state">Select scenarios to add to playlist</div>
              ) : (
                <>
                  <div className="playlist-queue">
                    {playlist.map((scenario, index) => (
                      <div
                        key={index}
                        className={`playlist-item ${index === currentPlaylistIndex ? "current" : ""}`}
                      >
                        <div className="playlist-index">{index + 1}</div>
                        <div className="playlist-name">{scenario}</div>
                        <button
                          onClick={() => removeFromPlaylist(index)}
                          className="remove-btn"
                          title="Remove"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="playlist-actions">
                    <button
                      onClick={() => void loadAllInPlaylist()}
                      disabled={isLoading || playlist.length === 0}
                      className="action-btn"
                    >
                      Load All
                    </button>
                    <button
                      onClick={() => void playPlaylist()}
                      disabled={isLoading || playlist.length === 0}
                      className="action-btn play-btn"
                    >
                      ▶ Play Playlist
                    </button>
                    <button
                      onClick={clearPlaylist}
                      className="action-btn clear-btn"
                    >
                      Clear
                    </button>
                  </div>
                </>
              )}
            </>
          ) : (
            <>
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
            </>
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
