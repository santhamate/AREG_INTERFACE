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
