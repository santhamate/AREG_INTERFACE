import React, { useState } from "react";
import ScenarioSweepPanel from "./ScenarioSweepPanel";
import "./TCV907Page.css";

export default function TCV907Page() {
  const [connected, setConnected] = useState(false);

  return (
    <div className="tcv907-page">
      <div className="tcv907-header">
        <h1>📡 TCV907 Radar Validation</h1>
        <p>Remote control and measurement interface for TCV907 radar receiver validation</p>
      </div>

      <div className="tcv907-grid">
        {/* Automated Scenario Sweep */}
        <div className="tcv907-card tcv907-card--wide">
          <div className="tcv907-card-header">Automated Scenario Sweep</div>
          <div className="tcv907-card-content">
            <ScenarioSweepPanel connected={connected} mode="full" />
          </div>
        </div>

        {/* Connection Panel */}
        <div className="tcv907-card">
          <div className="tcv907-card-header">Connection Status</div>
          <div className="tcv907-card-content">
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
                placeholder="192.168.1.100"
                disabled={connected}
                defaultValue="127.0.0.1"
                className="input-field"
              />
            </div>
            <div className="connection-row">
              <span className="label">Port:</span>
              <input
                type="number"
                placeholder="5025"
                disabled={connected}
                defaultValue="5025"
                className="input-field"
                style={{ width: "80px" }}
              />
            </div>
            <button
              onClick={() => setConnected(!connected)}
              className={`action-button ${connected ? "disconnect" : "connect"}`}
            >
              {connected ? "Disconnect" : "Connect"}
            </button>
          </div>
        </div>

        {/* Command Interface */}
        <div className="tcv907-card">
          <div className="tcv907-card-header">Command Interface</div>
          <div className="tcv907-card-content">
            <div className="coming-soon">
              <p>🔨 Command interface coming in Step 12</p>
              <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "8px" }}>
                Remote command execution and response monitoring
              </p>
            </div>
          </div>
        </div>

        {/* Measurements */}
        <div className="tcv907-card">
          <div className="tcv907-card-header">Radar Measurements</div>
          <div className="tcv907-card-content">
            <div className="coming-soon">
              <p>📊 Measurement panel coming in Step 12</p>
              <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "8px" }}>
                Real-time RCS, frequency, and validation data
              </p>
            </div>
          </div>
        </div>

        {/* Data Logging */}
        <div className="tcv907-card">
          <div className="tcv907-card-header">Data Logging</div>
          <div className="tcv907-card-content">
            <div className="coming-soon">
              <p>📝 Data logger coming in Step 12</p>
              <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "8px" }}>
                Capture and export validation measurements
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
