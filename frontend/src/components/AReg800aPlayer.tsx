import React, { useState, useEffect } from "react";
import ScenarioPlayer from "./ScenarioPlayer";
import CommandBuilder from "./CommandBuilder";
import SimulationOverview from "./SimulationOverview";
import ScenarioGenerator from "./ScenarioGenerator";
import "./AReg800aPlayer.css";

type Protocol = "hislip" | "socket" | "vxi11" | "rsib" | "mdns";

interface SessionState {
  connected: boolean;
  host: string | null;
  port: number | null;
  transport: string;
}

const CONNECTION_OPTIONS = [
  { value: "hislip" as Protocol, label: "HiSLIP", defaultPort: 4880, supported: true },
  { value: "socket" as Protocol, label: "Socket (SCPI/TCP)", defaultPort: 5025, supported: true },
];

export default function AReg800aPlayer() {
  const [protocol, setProtocol] = useState<Protocol>("hislip");
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState("4880");
  const [session, setSession] = useState<SessionState>({
    connected: false,
    host: null,
    port: null,
    transport: "hislip",
  });
  const [connecting, setConnecting] = useState(false);
  const [connError, setConnError] = useState<string | null>(null);
  const [showCommandBuilder, setShowCommandBuilder] = useState(false);
  const [showGenerator, setShowGenerator] = useState(true);
  const [command, setCommand] = useState("");
  const [playerBusy, setPlayerBusy] = useState(false);
  const [playerMsg, setPlayerMsg] = useState<string | null>(null);

  // Check connection status periodically
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch("http://127.0.0.1:8000/api/session", {
          method: "GET",
        });
        if (response.ok) {
          const state = await response.json();
          setSession(state);
        }
      } catch (err) {
        // Silently handle connection check errors
      }
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const connectDevice = async () => {
    setConnecting(true);
    setConnError(null);
    try {
      const response = await fetch("http://127.0.0.1:8000/api/session/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          host,
          port: parseInt(port, 10),
          protocol,
        }),
      });

      if (!response.ok) throw new Error("Connection failed");

      const state = await response.json();
      setSession(state);
    } catch (err) {
      setConnError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setConnecting(false);
    }
  };

  const disconnectDevice = async () => {
    try {
      await fetch("http://127.0.0.1:8000/api/session/disconnect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      setSession({
        connected: false,
        host: null,
        port: null,
        transport: "hislip",
      });
    } catch (err) {
      console.error("Disconnect failed", err);
    }
  };

  const scenarioAction = async (label: string, endpoint: string) => {
    setPlayerBusy(true);
    setPlayerMsg(null);
    try {
      const response = await fetch(`http://127.0.0.1:8000/api${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        throw new Error(`${label} failed (${response.status})`);
      }
      const data = await response.json();
      setPlayerMsg(data?.message ?? `${label} command sent`);
    } catch (err) {
      setPlayerMsg(err instanceof Error ? err.message : `${label} failed`);
    } finally {
      setPlayerBusy(false);
    }
  };

  return (
    <div className="areg-player-shell">
      {/* Top Bar - Connection */}
      <div className="areg-topbar">
        <div className="areg-topbar-left">
          <span className="areg-device-label">AREG 800A</span>
        </div>

        <div className="areg-topbar-controls">
          <label>
            Protocol
            <select
              value={protocol}
              onChange={(e) => {
                const next = e.target.value as Protocol;
                const opt = CONNECTION_OPTIONS.find((o) => o.value === next);
                setProtocol(next);
                setPort(String(opt?.defaultPort ?? 4880));
              }}
              disabled={session.connected}
            >
              {CONNECTION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value} disabled={!o.supported}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Host
            <input
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="192.168.1.50"
              disabled={session.connected}
            />
          </label>

          <label>
            Port
            <input
              value={port}
              onChange={(e) => setPort(e.target.value)}
              inputMode="numeric"
              disabled={session.connected}
              style={{ width: 60 }}
            />
          </label>

          <button
            className={`areg-btn ${session.connected ? "disconnect" : "connect"}`}
            onClick={session.connected ? disconnectDevice : connectDevice}
            disabled={connecting}
          >
            {connecting ? "…" : session.connected ? "✓ Connected" : "Connect"}
          </button>

          {session.connected && (
            <span className="areg-connection-badge">
              {session.host}:{session.port} ({session.transport})
            </span>
          )}

          {connError && <span className="areg-error-message">{connError}</span>}
        </div>
      </div>

      {/* Main Player Layout (Spotify-style) */}
      <div className="areg-player-layout">
        {/* Left Sidebar - Scenario List */}
        <div className="areg-sidebar-left">
          <div className="areg-sidebar-header">📋 Scenarios</div>
          <div className="areg-scenario-list-wrapper">
            <ScenarioPlayer />
          </div>
        </div>

        {/* Center - Main Player Area */}
        <div className="areg-center">
          {/* Simulation Overview at Top */}
          <div className="areg-overview-panel">
            <div className="areg-overview-header">📊 Live Simulation</div>
            <SimulationOverview />
          </div>

          {/* Play Controls Panel */}
          <div className="areg-controls-panel">
            <div className="areg-controls-header">Playback Controls</div>
            <div className="areg-player-buttons">
              <button className="areg-control-btn prev-btn" title="Previous" onClick={() => void scenarioAction("Previous", "/scenario/previous")} disabled={playerBusy}>
                ⏮
              </button>
              <button className="areg-control-btn play-btn" title="Play" onClick={() => void scenarioAction("Play", "/scenario/play")} disabled={playerBusy}>
                ▶
              </button>
              <button className="areg-control-btn pause-btn" title="Pause" onClick={() => void scenarioAction("Pause", "/scenario/pause")} disabled={playerBusy}>
                ⏸
              </button>
              <button className="areg-control-btn stop-btn" title="Stop" onClick={() => void scenarioAction("Stop", "/scenario/stop")} disabled={playerBusy}>
                ⏹
              </button>
              <button className="areg-control-btn restart-btn" title="Restart" onClick={() => void scenarioAction("Restart", "/scenario/restart")} disabled={playerBusy}>
                🔄
              </button>
              <button className="areg-control-btn next-btn" title="Next" onClick={() => void scenarioAction("Next", "/scenario/next")} disabled={playerBusy}>
                ⏭
              </button>
            </div>
            {playerMsg && <div className="areg-player-msg">{playerMsg}</div>}
          </div>

          {/* Command Builder */}
          <div className="areg-commands-panel">
            <div className="areg-commands-header">
              🔧 SCPI Commands
              <button
                className="areg-mini-btn"
                onClick={() => setShowCommandBuilder(!showCommandBuilder)}
              >
                {showCommandBuilder ? "▼" : "▶"}
              </button>
            </div>
            {showCommandBuilder && (
              <div className="areg-commands-content">
                <CommandBuilder command={command} onCommandChange={setCommand} />
              </div>
            )}
          </div>

          <div className="areg-commands-panel">
            <div className="areg-commands-header">
              🎬 Scenario Generator (offline ready)
              <button
                className="areg-mini-btn"
                onClick={() => setShowGenerator(!showGenerator)}
              >
                {showGenerator ? "▼" : "▶"}
              </button>
            </div>
            {showGenerator && (
              <div className="areg-commands-content">
                <ScenarioGenerator />
              </div>
            )}
          </div>
        </div>

        {/* Right Sidebar - Info Panel */}
        <div className="areg-sidebar-right">
          <div className="areg-sidebar-header">ℹ️ Device Info</div>
          <div className="areg-info-box">
            <div className="areg-info-row">
              <span className="label">Status</span>
              <span className={`status-badge ${session.connected ? "online" : "offline"}`}>
                {session.connected ? "Online" : "Offline"}
              </span>
            </div>
            <div className="areg-info-row">
              <span className="label">Host</span>
              <span className="value">{session.host || "—"}</span>
            </div>
            <div className="areg-info-row">
              <span className="label">Port</span>
              <span className="value">{session.port || "—"}</span>
            </div>
            <div className="areg-info-row">
              <span className="label">Protocol</span>
              <span className="value">{session.transport || "—"}</span>
            </div>
          </div>

          <div className="areg-sidebar-section">
            <div className="areg-sidebar-subheader">Quick Actions</div>
            <button className="areg-action-btn">📄 Generate Scenario</button>
            <button className="areg-action-btn">🖼️ Hardcopy</button>
            <button className="areg-action-btn">📊 Inspector</button>
          </div>
        </div>
      </div>
    </div>
  );
}
