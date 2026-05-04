import React, { useEffect, useState } from "react";
import "./Hardcopy.css";

type HardcopyResponse = {
  ok: boolean;
  file_path: string | null;
  file_format: string | null;
  bytes_written: number;
  transport: string | null;
  message: string | null;
  error: string | null;
};

type LastCaptureInfo = {
  ok: boolean;
  file_path: string | null;
  file_size: number;
  modified_time: number | null;
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

      if (result.ok && result.file_path) {
        setStatus("success");
        setStatusMessage(`Screenshot saved: ${result.file_path} (${result.bytes_written} bytes)`);
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
          </div>
        ) : (
          <div className="no-capture">No screenshots captured yet</div>
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
          • <code>:HCOPY:IMAGE:FORMAT</code> - Sets the image format (PNG, JPG, BMP)
          <br />
          • <code>:HCOPY:EXECUTE</code> - Triggers the hardcopy operation on the instrument
          <br />
          • <code>:HCOPY:DATA?</code> - Retrieves the binary image data
        </p>
      </div>
    </div>
  );
}
