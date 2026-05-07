import React, { useEffect, useState } from "react";
import "./Hardcopy.css";

type HardcopyDiagnostics = {
  file_size: number;
  payload_length?: number;
  first_32_bytes_hex: string;
  ascii_preview: string;
  detected_type: string;
  recommendation: string;
  validation_message?: string;
  scpi_block?: {
    length_digits: number;
    payload_length: number;
    trailing_bytes: number;
  };
};

type HardcopyLogEntry = {
  timestamp: string;
  command: string;
  command_type: string;
  ok: boolean;
  response?: string | null;
  message?: string | null;
  error?: string | null;
};

type HardcopyResponse = {
  ok: boolean;
  file_path: string | null;
  file_format: string | null;
  bytes_written: number;
  payload_bytes: number;
  detected_type: string | null;
  validation_ok: boolean;
  diagnostics: HardcopyDiagnostics | null;
  log: HardcopyLogEntry[];
  transport: string | null;
  message: string | null;
  error: string | null;
};

type LastCaptureInfo = {
  ok: boolean;
  file_path: string | null;
  file_size: number;
  modified_time: number | null;
  validation_ok?: boolean;
  detected_type?: string | null;
  diagnostics?: HardcopyDiagnostics | null;
};

type HardcopyAnalysis = {
  ok: boolean;
  file_path?: string | null;
  validation_ok?: boolean;
  diagnostics?: HardcopyDiagnostics | null;
  error?: string;
};

type DialogEntry = {
  raw_id: string;
  dialog_name: string;
  qualifier?: string | null;
  instance_data?: string | null;
  tab_data?: string | null;
  user_label: string;
};

type DialogPreset = {
  name: string;
  dialog_id: string;
  region: "ALL" | "DIALog";
};

type CaptureTargetType = "current_screen" | "current_active_dialog" | "preset" | "manual";
type CaptureRegion = "ALL" | "DIALog";
type CaptureMode = "execute" | "data";

const API_BASE = "http://127.0.0.1:8000/api";

export default function Hardcopy() {
  const [formats, setFormats] = useState<string[]>(["PNG", "JPG", "BMP"]);
  const [selectedFormat, setSelectedFormat] = useState("PNG");
  const [saveDir, setSaveDir] = useState("./screenshots");
  const [filenamePrefix, setFilenamePrefix] = useState("AREG800A_screenshot");
  const [useTimestamp, setUseTimestamp] = useState(true);
  const [openAfterSave, setOpenAfterSave] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [status, setStatus] = useState<"idle" | "capturing" | "success" | "error">("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const [lastCapture, setLastCapture] = useState<LastCaptureInfo | null>(null);
  const [connected, setConnected] = useState(false);
  const [analysis, setAnalysis] = useState<HardcopyAnalysis | null>(null);
  const [captureLog, setCaptureLog] = useState<HardcopyLogEntry[]>([]);
  const [targetType, setTargetType] = useState<CaptureTargetType>("current_screen");
  const [captureRegion, setCaptureRegion] = useState<CaptureRegion>("ALL");
  const [captureMode, setCaptureMode] = useState<CaptureMode>("execute");
  const [screenSwitchDelayMs, setScreenSwitchDelayMs] = useState(500);
  const [verifyDialogOpened, setVerifyDialogOpened] = useState(false);
  const [closeDialogAfterCapture, setCloseDialogAfterCapture] = useState(false);
  const [dialogs, setDialogs] = useState<DialogEntry[]>([]);
  const [selectedDialogId, setSelectedDialogId] = useState("");
  const [manualDialogId, setManualDialogId] = useState("");
  const [presets, setPresets] = useState<DialogPreset[]>([]);
  const [selectedPresetName, setSelectedPresetName] = useState("");
  const [newPresetName, setNewPresetName] = useState("");
  const [dialogStatus, setDialogStatus] = useState("");

  // Fetch supported formats on mount
  useEffect(() => {
    const fetchFormats = async () => {
      try {
        const response = await fetch(`${API_BASE}/hardcopy/formats`);
        if (response.ok) {
          const data = await response.json();
          setFormats(data.formats);
        }
      } catch (err) {
        console.error("Failed to fetch supported formats", err);
      }
    };

    fetchFormats();
  }, []);

  // Check connection status
  useEffect(() => {
    const checkConnection = async () => {
      try {
        const response = await fetch(`${API_BASE}/session`);
        if (response.ok) {
          const state = await response.json();
          setConnected(state.connected);
        }
      } catch (err) {
        setConnected(false);
      }
    };

    checkConnection();
    const interval = setInterval(checkConnection, 2000);
    return () => clearInterval(interval);
  }, []);

  // Fetch last capture info
  const refreshLastCapture = async () => {
    try {
      const response = await fetch(`${API_BASE}/hardcopy/last-capture`);
      if (response.ok) {
        const data = await response.json();
        setLastCapture(data);
        if (data.diagnostics) {
          setAnalysis({
            ok: true,
            file_path: data.file_path,
            validation_ok: data.validation_ok,
            diagnostics: data.diagnostics,
          });
        }
      }
    } catch (err) {
      console.error("Failed to fetch last capture info", err);
    }
  };

  useEffect(() => {
    refreshLastCapture();
  }, []);

  const loadPresets = async () => {
    try {
      const response = await fetch(`${API_BASE}/hcopy/dialog-presets`);
      if (!response.ok) return;
      const data = await response.json();
      const next: DialogPreset[] = Array.isArray(data.presets) ? data.presets : [];
      setPresets(next);
      if (next.length > 0 && !selectedPresetName) {
        setSelectedPresetName(next[0].name);
      }
    } catch {
      // Best effort
    }
  };

  useEffect(() => {
    void loadPresets();
  }, []);

  const handleScanOpenDialogs = async () => {
    try {
      const response = await fetch(`${API_BASE}/hcopy/dialogs/open`);
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setDialogStatus(data.error || "Failed to query open dialogs.");
        return;
      }
      const nextDialogs: DialogEntry[] = Array.isArray(data.dialogs) ? data.dialogs : [];
      setDialogs(nextDialogs);
      if (nextDialogs.length > 0) {
        setSelectedDialogId(nextDialogs[0].raw_id);
      }
      setDialogStatus(nextDialogs.length > 0 ? `Found ${nextDialogs.length} open dialogs.` : "No open dialogs detected.");
    } catch (err) {
      setDialogStatus(`Dialog scan failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const handleOpenDialog = async (dialogId: string) => {
    try {
      const response = await fetch(`${API_BASE}/hcopy/dialogs/open`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dialog_id: dialogId, delay_ms: screenSwitchDelayMs, verify: verifyDialogOpened }),
      });
      const data = await response.json();
      setDialogStatus(data.ok ? `Opened dialog ${dialogId}` : `Open failed for ${dialogId}: ${data.error || "Unknown error"}`);
      if (data.ok && verifyDialogOpened) {
        setDialogs(Array.isArray(data.dialogs) ? data.dialogs : dialogs);
      }
    } catch (err) {
      setDialogStatus(`Open failed for ${dialogId}: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const handleCloseDialog = async (dialogId: string) => {
    try {
      const response = await fetch(`${API_BASE}/hcopy/dialogs/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dialog_id: dialogId }),
      });
      const data = await response.json();
      setDialogStatus(data.ok ? `Closed dialog ${dialogId}` : `Close failed for ${dialogId}: ${data.error || "Unknown error"}`);
    } catch (err) {
      setDialogStatus(`Close failed for ${dialogId}: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const handleCloseAllDialogs = async () => {
    const confirmed = window.confirm("Close all open dialogs before capture?");
    if (!confirmed) return;
    try {
      const response = await fetch(`${API_BASE}/hcopy/dialogs/close-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      const data = await response.json();
      setDialogStatus(data.ok ? "Closed all dialogs." : `Close all failed: ${data.error || "Unknown error"}`);
      if (data.ok) {
        setDialogs([]);
      }
    } catch (err) {
      setDialogStatus(`Close all failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const handleSavePreset = async (dialogId: string, region: CaptureRegion) => {
    const name = (newPresetName || window.prompt("Preset name", "") || "").trim();
    if (!name) {
      setDialogStatus("Preset name is required.");
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/hcopy/dialog-presets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, dialog_id: dialogId, region }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setDialogStatus(data.error || "Failed to save preset.");
        return;
      }
      setDialogStatus(`Saved preset ${name}.`);
      setNewPresetName("");
      await loadPresets();
      setSelectedPresetName(name);
    } catch (err) {
      setDialogStatus(`Failed to save preset: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const getTargetDialogId = (): string | undefined => {
    if (targetType === "manual") return manualDialogId.trim() || undefined;
    if (targetType === "current_active_dialog") return selectedDialogId || undefined;
    return undefined;
  };

  const handleCaptureSelectedScreen = async (overrideDialogId?: string) => {
    if (!connected) {
      setStatus("error");
      setStatusMessage("Instrument not connected");
      return;
    }

    setIsCapturing(true);
    setStatus("capturing");
    setStatusMessage("Switching screen and capturing hardcopy...");

    try {
      const targetDialogId = overrideDialogId || getTargetDialogId();
      const response = await fetch(`${API_BASE}/hcopy/capture-selected`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: targetType,
          dialog_id: targetDialogId,
          preset_name: targetType === "preset" ? selectedPresetName : undefined,
          mode: captureMode,
          region: captureRegion,
          screen_switch_delay_ms: screenSwitchDelayMs,
          verify_dialog_opened: verifyDialogOpened,
          close_dialog_after_capture: closeDialogAfterCapture,
          format: selectedFormat,
          auto_naming: useTimestamp,
          auto_directory: saveDir.trim() || undefined,
          local_dir: saveDir.trim() || undefined,
          local_filename: filenamePrefix.trim() || undefined,
        }),
      });
      const result = await response.json();

      const logs: HardcopyLogEntry[] = Array.isArray(result.log)
        ? result.log.map((entry: Record<string, unknown>) => ({
            timestamp: String(entry.timestamp ?? new Date().toISOString()),
            command: String(entry.command ?? ""),
            command_type: String(entry.command_type ?? "action"),
            ok: Boolean(entry.ok),
            response: entry.response == null ? null : String(entry.response),
            message: entry.message == null ? null : String(entry.message),
            error: entry.error == null ? null : String(entry.error),
          }))
        : [];
      setCaptureLog(logs);

      if (result.ok) {
        setStatus("success");
        setStatusMessage(result.message || "Capture completed.");
        await refreshLastCapture();
      } else {
        setStatus("error");
        setStatusMessage(`Capture failed: ${result.error || "Unknown error"}`);
      }
    } catch (err) {
      setStatus("error");
      setStatusMessage(`Capture failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setIsCapturing(false);
    }
  };

  const handleCapture = async () => {
    if (!connected) {
      setStatus("error");
      setStatusMessage("Instrument not connected");
      return;
    }

    setIsCapturing(true);
    setStatus("capturing");
    setStatusMessage("Capturing screenshot...");

    try {
      const response = await fetch(`${API_BASE}/hardcopy/capture`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          save_dir: saveDir.trim() || undefined,
          file_format: selectedFormat,
          filename_prefix: filenamePrefix.trim() || "AREG800A_screenshot",
          use_timestamp: useTimestamp,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        setStatus("error");
        setStatusMessage(`Error: ${error.detail || "Capture failed"}`);
        return;
      }

      const result: HardcopyResponse = await response.json();
      setCaptureLog(result.log ?? []);
      if (result.diagnostics) {
        setAnalysis({
          ok: true,
          file_path: result.file_path,
          validation_ok: result.validation_ok,
          diagnostics: result.diagnostics,
        });
      } else {
        setAnalysis(null);
      }

      if (result.ok && result.file_path) {
        setStatus("success");
        setStatusMessage(`Screenshot saved: ${result.file_path} (${result.bytes_written} bytes, detected ${result.detected_type ?? "UNKNOWN"})`);
        await refreshLastCapture();

        if (openAfterSave) {
          // Open file explorer showing the file (Windows)
          try {
            await fetch(`${API_BASE}/hardcopy/open-file`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ file_path: result.file_path }),
            });
          } catch (err) {
            console.error("Failed to open file", err);
          }
        }
      } else {
        setStatus("error");
        setStatusMessage(`Capture failed: ${result.error || "Unknown error"}`);
      }
    } catch (err) {
      setStatus("error");
      setStatusMessage(`Error: ${err instanceof Error ? err.message : "Capture failed"}`);
    } finally {
      setIsCapturing(false);
    }
  };

  const handleAnalyzeLast = async () => {
    const filePath = lastCapture?.file_path;
    if (!filePath) {
      setStatus("error");
      setStatusMessage("No capture available to analyze");
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/hardcopy/analyze?file_path=${encodeURIComponent(filePath)}`);
      const result: HardcopyAnalysis = await response.json();
      setAnalysis(result);
      if (result.ok) {
        setStatus(result.validation_ok ? "success" : "error");
        setStatusMessage(result.validation_ok ? "Capture analysis: valid image payload" : "Capture analysis: invalid image payload");
      } else {
        setStatus("error");
        setStatusMessage(`Analyze failed: ${result.error || "Unknown error"}`);
      }
    } catch (err) {
      setStatus("error");
      setStatusMessage(`Analyze failed: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const handleChangeSaveDir = () => {
    const newDir = window.prompt("Enter save directory (e.g., ./screenshots or C:\\Users\\Pictures\\Screenshots):", saveDir);
    if (newDir !== null && newDir.trim()) {
      setSaveDir(newDir.trim());
    }
  };

  const getStatusColor = (state: typeof status): string => {
    switch (state) {
      case "capturing":
        return "#3b82f6";
      case "success":
        return "#10b981";
      case "error":
        return "#ef4444";
      default:
        return "#64748b";
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
  };

  const formatTime = (timestamp: number | null): string => {
    if (!timestamp) return "N/A";
    return new Date(timestamp * 1000).toLocaleString();
  };

  const previewUrl = lastCapture?.file_path && lastCapture.validation_ok
    ? `${API_BASE}/hardcopy/content?file_path=${encodeURIComponent(lastCapture.file_path)}`
    : null;

  const activeDiagnostics = analysis?.diagnostics ?? lastCapture?.diagnostics ?? null;

  return (
    <div className="hardcopy-panel">
      <div className="hardcopy-header">
        <h2>📸 Hardcopy / Screenshot Capture</h2>
        <div className="connection-indicator" style={{ backgroundColor: connected ? "#10b981" : "#ef4444" }}>
          {connected ? "Connected" : "Disconnected"}
        </div>
      </div>

      <div className="hardcopy-controls">
        <div className="control-group">
          <label htmlFor="format">Image Format:</label>
          <select id="format" value={selectedFormat} onChange={(e) => setSelectedFormat(e.target.value)} disabled={isCapturing}>
            {formats.map((fmt) => (
              <option key={fmt} value={fmt}>
                {fmt}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label htmlFor="save-dir">Save Directory:</label>
          <div className="dir-input">
            <input
              id="save-dir"
              type="text"
              value={saveDir}
              onChange={(e) => setSaveDir(e.target.value)}
              placeholder="./screenshots"
              disabled={isCapturing}
            />
            <button onClick={handleChangeSaveDir} disabled={isCapturing} className="browse-btn">
              Browse
            </button>
          </div>
        </div>

        <div className="control-group">
          <label htmlFor="prefix">Filename Prefix:</label>
          <input
            id="prefix"
            type="text"
            value={filenamePrefix}
            onChange={(e) => setFilenamePrefix(e.target.value)}
            placeholder="AREG800A_screenshot"
            disabled={isCapturing}
          />
        </div>

        <div className="checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={useTimestamp}
              onChange={(e) => setUseTimestamp(e.target.checked)}
              disabled={isCapturing}
            />
            Add timestamp to filename
          </label>
          <label>
            <input
              type="checkbox"
              checked={openAfterSave}
              onChange={(e) => setOpenAfterSave(e.target.checked)}
              disabled={isCapturing}
            />
            Open after save
          </label>
        </div>
      </div>

      <div className="hardcopy-dialog-section">
        <h3>Screen / Dialog Selection Before Capture</h3>
        <div className="hardcopy-dialog-grid">
          <div className="control-group">
            <label htmlFor="capture-target">Target</label>
            <select
              id="capture-target"
              value={targetType}
              onChange={(e) => setTargetType(e.target.value as CaptureTargetType)}
              disabled={isCapturing}
            >
              <option value="current_screen">Current screen</option>
              <option value="current_active_dialog">Current active dialog</option>
              <option value="preset">Saved dialog preset</option>
              <option value="manual">Manually entered dialog ID</option>
            </select>
          </div>

          {targetType === "preset" ? (
            <div className="control-group">
              <label htmlFor="preset-name">Preset</label>
              <select
                id="preset-name"
                value={selectedPresetName}
                onChange={(e) => setSelectedPresetName(e.target.value)}
                disabled={isCapturing}
              >
                <option value="">Select preset</option>
                {presets.map((preset) => (
                  <option key={preset.name} value={preset.name}>{preset.name}</option>
                ))}
              </select>
            </div>
          ) : null}

          {targetType === "manual" ? (
            <div className="control-group">
              <label htmlFor="manual-dialog-id">Manual dialog ID</label>
              <input
                id="manual-dialog-id"
                type="text"
                value={manualDialogId}
                onChange={(e) => setManualDialogId(e.target.value)}
                placeholder="DialogId from :DISPlay:DIALog:ID?"
                disabled={isCapturing}
              />
            </div>
          ) : null}

          <div className="control-group">
            <label htmlFor="capture-region">Capture region</label>
            <select
              id="capture-region"
              value={captureRegion}
              onChange={(e) => setCaptureRegion(e.target.value as CaptureRegion)}
              disabled={isCapturing}
            >
              <option value="ALL">Full screen</option>
              <option value="DIALog">Active dialog only</option>
            </select>
          </div>

          <div className="control-group">
            <label htmlFor="capture-mode">Output mode</label>
            <select
              id="capture-mode"
              value={captureMode}
              onChange={(e) => setCaptureMode(e.target.value as CaptureMode)}
              disabled={isCapturing}
            >
              <option value="execute">Save to instrument (:HCOPy:EXECute)</option>
              <option value="data">Capture to PC (:HCOPy:DATA?)</option>
            </select>
          </div>

          <div className="control-group">
            <label htmlFor="switch-delay">Screen switch delay (ms)</label>
            <input
              id="switch-delay"
              type="number"
              min={0}
              value={screenSwitchDelayMs}
              onChange={(e) => setScreenSwitchDelayMs(Math.max(0, Number(e.target.value) || 0))}
              disabled={isCapturing}
            />
          </div>

          <div className="checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={verifyDialogOpened}
                onChange={(e) => setVerifyDialogOpened(e.target.checked)}
                disabled={isCapturing}
              />
              Verify dialog opened before hardcopy
            </label>
            <label>
              <input
                type="checkbox"
                checked={closeDialogAfterCapture}
                onChange={(e) => setCloseDialogAfterCapture(e.target.checked)}
                disabled={isCapturing}
              />
              Close dialog after hardcopy
            </label>
          </div>
        </div>

        <div className="hardcopy-dialog-actions">
          <button onClick={handleScanOpenDialogs} disabled={!connected || isCapturing} className="analyze-btn">Scan open dialogs</button>
          <button onClick={handleCloseAllDialogs} disabled={!connected || isCapturing} className="analyze-btn">Close all dialogs</button>
          <button onClick={() => void handleCaptureSelectedScreen()} disabled={!connected || isCapturing} className="capture-btn">
            {isCapturing ? "Capturing..." : "Capture selected screen"}
          </button>
        </div>

        {dialogStatus ? <div className="status-message">{dialogStatus}</div> : null}

        <div className="control-group">
          <label htmlFor="new-preset-name">Preset name for selected dialog</label>
          <input
            id="new-preset-name"
            type="text"
            value={newPresetName}
            onChange={(e) => setNewPresetName(e.target.value)}
            placeholder="e.g. Scenario screen"
            disabled={isCapturing}
          />
        </div>

        <div className="hardcopy-dialog-table-wrap">
          <table className="hardcopy-dialog-table">
            <thead>
              <tr>
                <th>Raw dialog ID</th>
                <th>Dialog name</th>
                <th>Qualifier</th>
                <th>Instance/Tab</th>
                <th>User label</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {dialogs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="no-capture">No open dialogs detected.</td>
                </tr>
              ) : dialogs.map((dialog) => (
                <tr key={dialog.raw_id}>
                  <td>{dialog.raw_id}</td>
                  <td>{dialog.dialog_name}</td>
                  <td>{dialog.qualifier || "-"}</td>
                  <td>{dialog.instance_data || dialog.tab_data || "-"}</td>
                  <td>{dialog.user_label}</td>
                  <td>
                    <div className="hardcopy-dialog-row-actions">
                      <button className="analyze-btn" onClick={() => void handleOpenDialog(dialog.raw_id)} disabled={isCapturing}>Open</button>
                      <button className="analyze-btn" onClick={() => void handleCloseDialog(dialog.raw_id)} disabled={isCapturing}>Close</button>
                      <button className="analyze-btn" onClick={() => void handleSavePreset(dialog.raw_id, captureRegion)} disabled={isCapturing}>Save preset</button>
                      <button
                        className="capture-btn"
                        onClick={() => {
                          setTargetType("manual");
                          setManualDialogId(dialog.raw_id);
                          void handleCaptureSelectedScreen(dialog.raw_id);
                        }}
                        disabled={isCapturing}
                      >
                        Capture this dialog
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="hardcopy-preview">
        <div className="filename-preview">
          <span className="label">Preview filename:</span>
          <span className="filename">
            {filenamePrefix}
            {useTimestamp ? "_YYYY-MM-DD_HH-MM-SS" : ""}
            .{selectedFormat.toLowerCase()}
          </span>
        </div>
      </div>

      <div className="hardcopy-actions">
        <button
          onClick={handleCapture}
          disabled={!connected || isCapturing}
          className="capture-btn"
          style={{
            background: isCapturing ? "#3b82f6" : connected ? "#059669" : "#9ca3af",
            cursor: connected && !isCapturing ? "pointer" : "not-allowed",
          }}
        >
          {isCapturing ? "🔄 Capturing..." : "📸 Capture Screenshot"}
        </button>
        <button
          onClick={handleAnalyzeLast}
          disabled={!lastCapture?.file_path || isCapturing}
          className="analyze-btn"
        >
          Analyze Last Capture
        </button>
      </div>

      <div className="status-area">
        <div className="status-message" style={{ color: getStatusColor(status), borderColor: getStatusColor(status) }}>
          {statusMessage || (status === "idle" ? "Ready to capture" : "Status will appear here")}
        </div>
      </div>

      <div className="last-capture-info">
        <h3>Last Capture</h3>
        {lastCapture && lastCapture.ok && lastCapture.file_path ? (
          <div className="capture-details">
            <div className="detail-row">
              <span className="label">File:</span>
              <span className="value">{lastCapture.file_path}</span>
            </div>
            <div className="detail-row">
              <span className="label">Size:</span>
              <span className="value">{formatBytes(lastCapture.file_size)}</span>
            </div>
            <div className="detail-row">
              <span className="label">Time:</span>
              <span className="value">{formatTime(lastCapture.modified_time)}</span>
            </div>
            <div className="detail-row">
              <span className="label">Validation:</span>
              <span className="value">{lastCapture.validation_ok ? "VALID" : "INVALID"}</span>
            </div>
            <div className="detail-row">
              <span className="label">Detected:</span>
              <span className="value">{lastCapture.detected_type || "UNKNOWN"}</span>
            </div>
          </div>
        ) : (
          <div className="no-capture">No screenshots captured yet</div>
        )}
      </div>

      <div className="hardcopy-result-grid">
        <div className="hardcopy-preview-card">
          <h3>Preview</h3>
          {previewUrl ? (
            <img src={previewUrl} alt="Last hardcopy capture" className="hardcopy-image-preview" />
          ) : (
            <div className="no-preview">No valid image preview available</div>
          )}
          {lastCapture?.file_path ? <div className="preview-path">{lastCapture.file_path}</div> : null}
        </div>

        <div className="hardcopy-diagnostics-card">
          <h3>Diagnostics</h3>
          {activeDiagnostics ? (
            <div className="diagnostics-grid">
              <div className="detail-row">
                <span className="label">Detected Type:</span>
                <span className="value">{activeDiagnostics.detected_type}</span>
              </div>
              <div className="detail-row">
                <span className="label">File Size:</span>
                <span className="value">{formatBytes(activeDiagnostics.file_size)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Payload Length:</span>
                <span className="value">{activeDiagnostics.payload_length ?? activeDiagnostics.file_size} bytes</span>
              </div>
              <div className="detail-row diagnostics-block-row">
                <span className="label">First 32 Bytes:</span>
                <span className="value code-block">{activeDiagnostics.first_32_bytes_hex || "N/A"}</span>
              </div>
              <div className="detail-row diagnostics-block-row">
                <span className="label">ASCII Preview:</span>
                <span className="value code-block">{activeDiagnostics.ascii_preview || "N/A"}</span>
              </div>
              {activeDiagnostics.validation_message ? (
                <div className="detail-row diagnostics-block-row">
                  <span className="label">Validation:</span>
                  <span className="value">{activeDiagnostics.validation_message}</span>
                </div>
              ) : null}
              {activeDiagnostics.scpi_block ? (
                <div className="detail-row diagnostics-block-row">
                  <span className="label">SCPI Block:</span>
                  <span className="value">
                    digits={activeDiagnostics.scpi_block.length_digits}, payload={activeDiagnostics.scpi_block.payload_length}, trailing={activeDiagnostics.scpi_block.trailing_bytes}
                  </span>
                </div>
              ) : null}
              <div className="diagnostic-recommendation">{activeDiagnostics.recommendation}</div>
            </div>
          ) : (
            <div className="no-preview">Run a capture or analyze the last file to see diagnostics.</div>
          )}
        </div>
      </div>

      <div className="hardcopy-log-card">
        <h3>Hardcopy Log</h3>
        {captureLog.length > 0 ? (
          <div className="hardcopy-log-list">
            {captureLog.map((entry, index) => (
              <div key={`${entry.timestamp}-${index}`} className={`hardcopy-log-entry ${entry.ok ? "ok" : "error"}`}>
                <div className="hardcopy-log-head">
                  <span>{entry.timestamp}</span>
                  <span>{entry.command_type}</span>
                </div>
                <div className="hardcopy-log-command">{entry.command}</div>
                {entry.message ? <div className="hardcopy-log-message">{entry.message}</div> : null}
                {entry.error ? <div className="hardcopy-log-error">{entry.error}</div> : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="no-capture">No hardcopy log entries yet</div>
        )}
      </div>

      <div className="hardcopy-info">
        <h4>ℹ️ About Hardcopy Capture</h4>
        <p>
          This feature captures the current screen display from the AREG800A instrument and saves it as a local image file. The
          instrument will store the screenshot in memory and transfer it to your PC.
        </p>
        <p>
          <strong>Supported formats:</strong> {formats.join(", ")}
        </p>
        <p>
          <strong>SCPI Commands Used:</strong>
          <br />
          • <code>:HCOPy:DEVice:LANGuage</code> - Sets the image format (PNG, JPG, BMP)
          <br />
          • <code>:HCOPy:FILE:NAME:AUTO:STATe 1</code> - Lets the instrument generate the hardcopy name internally
          <br />
          • <code>:HCOPy:EXECute</code> - Triggers the hardcopy operation on the instrument
          <br />
          • <code>:HCOPy:DATA?</code> - Retrieves the definite-length SCPI binary image payload
        </p>
      </div>
    </div>
  );
}
