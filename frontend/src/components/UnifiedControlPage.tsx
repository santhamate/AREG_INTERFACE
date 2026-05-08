/**
 * UnifiedControlPage
 *
 * Single-page control interface for AREG800A Radar Target Simulator.
 * Replaces the previous multi-page tab layout with collapsible sections.
 *
 * Sections:
 *   1. Top bar   – connection, transport, connect/disconnect
 *   2. File Mgmt – device directory, OSI file scan, upload
 *   3. Player    – scenario selection, load/play/pause/stop/reset controls
 *   4. Generator – scenario generation (embedded ScenarioGenerator)
 *   5. SCPI      – manual SCPI console + command builder
 *   6. Logs      – command history / diagnostics
 */

import { useCallback, useEffect, useRef, useState } from "react";
import CommandBuilder from "./CommandBuilder";
import ScenarioGenerator from "./ScenarioGenerator";
import SimulationOverview from "./SimulationOverview";
import ScenarioSweepPanel from "./ScenarioSweepPanel";
import "./UnifiedControlPage.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Protocol = "hislip" | "socket" | "vxi11" | "rsib" | "mdns";
type PlaybackState =
  | "unknown"
  | "not_loaded"
  | "loaded"
  | "playing"
  | "paused"
  | "stopped"
  | "error";

type ReplayMode = "SINGle" | "LOOP" | "UNKNOWN";

type TransferProtocol = "ftp" | "smb" | "mapped_folder" | "manual_usb";

type FileFilterType = "all" | "osi" | "scpi" | "txt" | "csv" | "custom";

interface SessionState {
  connected: boolean;
  host: string | null;
  port: number | null;
  transport: string;
}

interface DeviceOsiFile {
  name: string;
  path: string;
  size_bytes: number | null;
  modified_time: string | null;
}

interface DiscoverDeviceDirectoriesResponse {
  ok: boolean;
  directories: string[];
  error?: string;
}

interface TransferRemoteFile {
  name: string;
  remote_path: string;
  size: number | null;
  modified_time: string | null;
  extension: string;
  is_directory: boolean;
}

interface TransferChecklistItem {
  name: string;
  status: "pass" | "warn" | "fail";
}

interface ScenarioInspectorSample {
  timestamp: number | null;
  x: number | null;
  y: number | null;
  z: number | null;
  distance: number | null;
  lateral_offset: number | null;
  speed: number | null;
  acceleration: number | null;
  heading: number | null;
  yaw: number | null;
  rcs: number | null;
  raw_fields: Record<string, unknown>;
}

interface ScenarioInspectorObject {
  object_id: string;
  object_name: string | null;
  object_type: string | null;
  min_distance: number | null;
  max_distance: number | null;
  initial_speed: number | null;
  max_speed: number | null;
  average_speed: number | null;
  valid_time_start: number | null;
  valid_time_end: number | null;
  initial_position: Record<string, number | null>;
  final_position: Record<string, number | null>;
  rcs_summary: Record<string, number | null>;
  heading_summary: Record<string, number | null>;
  acceleration_summary: Record<string, number | null>;
  raw_fields: Record<string, unknown>;
  samples: ScenarioInspectorSample[];
}

interface ScenarioDecodeResult {
  ok: boolean;
  scenario_name: string | null;
  file_path: string | null;
  remote_path: string | null;
  local_cached_path: string | null;
  loaded_scenario_path: string | null;
  format_detected: string;
  duration: number | null;
  time_start: number | null;
  time_end: number | null;
  timestep_count: number;
  object_count: number;
  objects: ScenarioInspectorObject[];
  warnings: string[];
  errors: string[];
  raw_summary: Record<string, unknown>;
}

interface CommandLogEntry {
  timestamp: string;
  command: string;
  command_type: "query" | "binary-query" | "write" | "action" | "empty";
  ok: boolean;
  response?: string | null;
  message?: string | null;
  error?: string | null;
}

interface CommandResult {
  command: string;
  command_type: "query" | "binary-query" | "write" | "action" | "empty";
  response: string | null;
  message: string | null;
  ok: boolean;
  transport: string;
  error: string | null;
}

interface ScenarioWorkspaceDownloadResult {
  ok: boolean;
  message?: string;
  local_path?: string | null;
  remote_path?: string | null;
  bytes_transferred: number;
  duration: number;
  validation_ok: boolean;
  size_bytes: number;
  message_count: number;
  error?: string | null;
}

type HcopyTargetType = "current_screen" | "current_active_dialog" | "preset" | "manual";
type HcopyCaptureMode = "execute" | "data";

interface HcopyDialogEntry {
  raw_id: string;
  dialog_name: string;
  qualifier?: string | null;
  instance_data?: string | null;
  tab_data?: string | null;
  user_label: string;
}

interface HcopyDialogPreset {
  name: string;
  dialog_id: string;
  region: "ALL" | "DIALog";
}

interface HcopyWorkflowLogEntry {
  timestamp?: string;
  command: string;
  command_type?: string;
  ok: boolean;
  response?: string | null;
  message?: string | null;
  error?: string | null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE = "http://127.0.0.1:8000/api";
const SCPI_HISTORY_STORAGE_KEY = "areg-scpi-history";

const CONNECTION_OPTIONS: { label: string; value: Protocol; defaultPort: number; supported: boolean }[] = [
  { label: "HiSLIP (4880)", value: "hislip", defaultPort: 4880, supported: true },
  { label: "Socket (5025)", value: "socket", defaultPort: 5025, supported: true },
  { label: "VXI-11 (111)", value: "vxi11", defaultPort: 111, supported: false },
  { label: "RSIB (2525)", value: "rsib", defaultPort: 2525, supported: false },
  { label: "mDNS (5353)", value: "mdns", defaultPort: 5353, supported: false },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stateColor(state: PlaybackState): string {
  switch (state) {
    case "playing": return "#10b981";
    case "paused":  return "#f59e0b";
    case "stopped": return "#ef4444";
    case "loaded":  return "#3b82f6";
    case "error":   return "#ef4444";
    default:        return "#64748b";
  }
}

function stateLabel(state: PlaybackState): string {
  const map: Record<PlaybackState, string> = {
    unknown: "Unknown",
    not_loaded: "Not Loaded",
    loaded: "Loaded",
    playing: "Playing",
    paused: "Paused",
    stopped: "Stopped",
    error: "Error",
  };
  return map[state] ?? state;
}

function formatBytes(n: number | null): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Section wrapper with collapse
// ---------------------------------------------------------------------------

function Section({
  icon,
  title,
  defaultOpen = true,
  children,
  badge,
}: {
  icon: string;
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  badge?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="ucp-section">
      <div className="ucp-section-header" onClick={() => setOpen((v) => !v)}>
        <span className="ucp-section-icon">{icon}</span>
        <span className="ucp-section-title">{title}</span>
        {badge}
        <span className={`ucp-section-toggle ${open ? "open" : ""}`}>▼</span>
      </div>
      <div className={`ucp-section-body ${open ? "" : "hidden"}`}>{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function UnifiedControlPage() {
  // -- Connection --
  const [protocol, setProtocol] = useState<Protocol>("hislip");
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState("4880");
  const [session, setSession] = useState<SessionState>({
    connected: false, host: null, port: null, transport: "hislip",
  });
  const [connError, setConnError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  // -- Device files --
  const [deviceDir, setDeviceDir] = useState("/var/user");
  const [deviceFiles, setDeviceFiles] = useState<DeviceOsiFile[]>([]);
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [selectedScanDirectory, setSelectedScanDirectory] = useState<string | null>(null);

  // -- Upload --
  const [localFile, setLocalFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadMsg, setUploadMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [selectedUploadDirectory, setSelectedUploadDirectory] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // -- File Transfer Manager --
  const [transferProtocol, setTransferProtocol] = useState<TransferProtocol>("ftp");
  const [transferHost, setTransferHost] = useState("127.0.0.1");
  const [transferUser, setTransferUser] = useState("instrument");
  const [transferPassword, setTransferPassword] = useState("instrument");
  const [transferRemoteDir, setTransferRemoteDir] = useState("/var/user/");
  const [transferMappedRoot, setTransferMappedRoot] = useState("");
  const [transferFilter, setTransferFilter] = useState<FileFilterType>("all");
  const [transferCustomFilter, setTransferCustomFilter] = useState("");
  const [transferFiles, setTransferFiles] = useState<TransferRemoteFile[]>([]);
  const [transferSelectedPath, setTransferSelectedPath] = useState("");
  const [transferLocalFile, setTransferLocalFile] = useState<File | null>(null);
  const [transferDownloadDir, setTransferDownloadDir] = useState("./downloads");
  const [transferWorkspaceDir, setTransferWorkspaceDir] = useState("./scenarios");
  const [transferNewFolder, setTransferNewFolder] = useState("");
  const [transferRenameTo, setTransferRenameTo] = useState("");
  const [transferBusy, setTransferBusy] = useState(false);
  const [transferStatus, setTransferStatus] = useState<string>("Idle");
  const [transferError, setTransferError] = useState<string | null>(null);
  const [transferWarnings, setTransferWarnings] = useState<string[]>([]);
  const [transferLikelyCauses, setTransferLikelyCauses] = useState<string[]>([]);
  const [transferChecklist, setTransferChecklist] = useState<TransferChecklistItem[]>([]);
  const [transferLogs, setTransferLogs] = useState<string[]>([]);
  const [transferHelp, setTransferHelp] = useState<{ ftp: string[]; smb: string[]; usb: string[] }>({ ftp: [], smb: [], usb: [] });
  const [generatorMode, setGeneratorMode] = useState<"simple" | "speed_sweep">("simple");

  // -- Scenario Inspector --
  const [inspectorResult, setInspectorResult] = useState<ScenarioDecodeResult | null>(null);
  const [inspectorBusy, setInspectorBusy] = useState(false);
  const [inspectorError, setInspectorError] = useState<string | null>(null);
  const [selectedInspectorObjectId, setSelectedInspectorObjectId] = useState<string | null>(null);
  const [estimatedPlaybackSec, setEstimatedPlaybackSec] = useState<number | null>(null);
  const [playbackStartAt, setPlaybackStartAt] = useState<number | null>(null);

  // -- Player --
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("unknown");
  const [playerBusy, setPlayerBusy] = useState(false);
  const [playerMsg, setPlayerMsg] = useState<string | null>(null);
  const [lastCmd, setLastCmd] = useState<string | null>(null);
  const [lastResp, setLastResp] = useState<string | null>(null);
  const [replayMode, setReplayMode] = useState<ReplayMode>("SINGle");
  const [lastAppliedReplayMode, setLastAppliedReplayMode] = useState<ReplayMode>("UNKNOWN");

  // -- SCPI console --
  const [scpiCommand, setScpiCommand] = useState("*IDN?");
  const [scpiResult, setScpiResult] = useState<CommandResult | null>(null);
  const [scpiRunning, setScpiRunning] = useState(false);
  const [scpiError, setScpiError] = useState<string | null>(null);
  const [scpiTimeoutMs, setScpiTimeoutMs] = useState(3000);
  const [scpiHistory, setScpiHistory] = useState<string[]>([]);

  // -- Logs --
  const [commandLog, setCommandLog] = useState<CommandLogEntry[]>([]);
  const storagePanelRef = useRef<HTMLDivElement>(null);
  const [storagePanelHeight, setStoragePanelHeight] = useState<number | null>(null);

  // -- HCOPy --
  const [hcopyFormat, setHcopyFormat] = useState("PNG");
  const [hcopyRegion, setHcopyRegion] = useState("ALL");
  const [hcopyAutoNaming, setHcopyAutoNaming] = useState(true);
  const [hcopyManualFilename, setHcopyManualFilename] = useState("");
  const [hcopyAutoDir, setHcopyAutoDir] = useState("/var/user");
  const [hcopyPrefixEnabled, setHcopyPrefixEnabled] = useState(false);
  const [hcopyPrefix, setHcopyPrefix] = useState("");
  const [hcopyYearEnabled, setHcopyYearEnabled] = useState(false);
  const [hcopyMonthEnabled, setHcopyMonthEnabled] = useState(false);
  const [hcopyDayEnabled, setHcopyDayEnabled] = useState(false);
  const [hcopyAutoNumber, setHcopyAutoNumber] = useState<number | null>(null);
  const [hcopyAutoFilename, setHcopyAutoFilename] = useState<string | null>(null);
  const [hcopyAutoFullPath, setHcopyAutoFullPath] = useState<string | null>(null);
  const [hcopyBusy, setHcopyBusy] = useState(false);
  const [hcopyMsg, setHcopyMsg] = useState<string | null>(null);
  const [hcopyMsgErr, setHcopyMsgErr] = useState(false);
  const [hcopyLastCapture, setHcopyLastCapture] = useState<string | null>(null);
  const [hcopyTargetType, setHcopyTargetType] = useState<HcopyTargetType>("current_screen");
  const [hcopyCaptureMode, setHcopyCaptureMode] = useState<HcopyCaptureMode>("execute");
  const [hcopyScreenSwitchDelayMs, setHcopyScreenSwitchDelayMs] = useState(500);
  const [hcopyVerifyDialogOpened, setHcopyVerifyDialogOpened] = useState(false);
  const [hcopyCloseDialogAfterCapture, setHcopyCloseDialogAfterCapture] = useState(false);
  const [hcopyDialogs, setHcopyDialogs] = useState<HcopyDialogEntry[]>([]);
  const [hcopySelectedDialogId, setHcopySelectedDialogId] = useState("");
  const [hcopyManualDialogId, setHcopyManualDialogId] = useState("");
  const [hcopyPresets, setHcopyPresets] = useState<HcopyDialogPreset[]>([]);
  const [hcopySelectedPresetName, setHcopySelectedPresetName] = useState("");
  const [hcopyNewPresetName, setHcopyNewPresetName] = useState("");
  const [hcopyDialogMsg, setHcopyDialogMsg] = useState<string | null>(null);
  const [hcopyWorkflowLog, setHcopyWorkflowLog] = useState<HcopyWorkflowLogEntry[]>([]);
  const [hcopyQuickOpen, setHcopyQuickOpen] = useState(false);

  // -------------------------------------------------------------------------
  // Session polling
  // -------------------------------------------------------------------------

  useEffect(() => {
    const poll = async () => {
      try {
        const r = await fetch(`${API_BASE}/session`);
        if (r.ok) {
          const s: SessionState = await r.json();
          setSession(s);
        }
      } catch {
        // Silent – no connection
      }
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(SCPI_HISTORY_STORAGE_KEY);
      if (!stored) {
        return;
      }
      const parsed = JSON.parse(stored) as unknown;
      if (Array.isArray(parsed)) {
        setScpiHistory(parsed.filter((item): item is string => typeof item === "string").slice(0, 12));
      }
    } catch {
      // Ignore invalid local storage state.
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(SCPI_HISTORY_STORAGE_KEY, JSON.stringify(scpiHistory.slice(0, 12)));
    } catch {
      // Ignore local storage errors.
    }
  }, [scpiHistory]);

  useEffect(() => {
    const el = storagePanelRef.current;
    if (!el) {
      setStoragePanelHeight(null);
      return;
    }

    const updateHeight = () => {
      const next = Math.round(el.getBoundingClientRect().height);
      setStoragePanelHeight(next > 0 ? next : null);
    };

    updateHeight();
    const ro = new ResizeObserver(() => updateHeight());
    ro.observe(el);

    return () => {
      ro.disconnect();
    };
  }, [deviceFiles.length, selectedScenario, scanning, uploading, uploadMsg, scanError, scanMsg]);

  // Auto-scan on connect
  const prevConnectedRef = useRef(false);
  useEffect(() => {
    if (session.connected && !prevConnectedRef.current) {
      void scanDeviceFiles(true);
      void refreshLog();
    }
    prevConnectedRef.current = session.connected;
  }, [session.connected]);

  // -------------------------------------------------------------------------
  // Connection
  // -------------------------------------------------------------------------

  const connectDevice = async () => {
    const opt = CONNECTION_OPTIONS.find((o) => o.value === protocol);
    if (!opt?.supported) {
      setConnError("That protocol is not yet implemented. Use HiSLIP or Socket.");
      return;
    }
    setConnecting(true);
    setConnError(null);
    try {
      const r = await fetch(`${API_BASE}/session/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ protocol, host: host.trim() || null, port: Number(port) || null }),
      });
      if (!r.ok) {
        const p = await r.json() as { detail?: string };
        throw new Error(p.detail ?? "Connect failed");
      }
      setSession(await r.json() as SessionState);
    } catch (e) {
      setConnError(e instanceof Error ? e.message : "Connect failed");
    } finally {
      setConnecting(false);
    }
  };

  const disconnectDevice = async () => {
    setConnError(null);
    try {
      const r = await fetch(`${API_BASE}/session/disconnect`, { method: "POST" });
      if (r.ok) setSession(await r.json() as SessionState);
    } catch (e) {
      setConnError(e instanceof Error ? e.message : "Disconnect failed");
    }
  };

  // -------------------------------------------------------------------------
  // Device file scan
  // -------------------------------------------------------------------------

  const scanDeviceFiles = useCallback(async (silent = false, directoryOverride?: string) => {
    if (!silent) setScanError(null);
    setScanning(true);
    setSelectedScanDirectory(null);
    let targetDir = directoryOverride ?? deviceDir;
    try {
      if (!targetDir.trim() && session.connected) {
        const discover = await fetch(`${API_BASE}/device/files/discover`);
        if (discover.ok) {
          const info = await discover.json() as DiscoverDeviceDirectoriesResponse;
          if (info.ok && info.directories.length > 0) {
            const sorted = [...info.directories].sort((a, b) => {
              const al = a.toLowerCase();
              const bl = b.toLowerCase();
              const ar = al.includes("usb") ? 0 : (al.includes("sd") || al.includes("mmc") || al.includes("mass_storage") ? 1 : 2);
              const br = bl.includes("usb") ? 0 : (bl.includes("sd") || bl.includes("mmc") || bl.includes("mass_storage") ? 1 : 2);
              if (ar !== br) return ar - br;
              return al.localeCompare(bl);
            });
            targetDir = sorted[0] ?? targetDir;
            if (targetDir) {
              setDeviceDir(targetDir);
              setSelectedScanDirectory(targetDir);
            }
          }
        }
      }

      const r = await fetch(`${API_BASE}/device/files/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directory: targetDir, force_refresh: true }),
      });
      const data = await r.json() as { ok: boolean; files: DeviceOsiFile[]; error?: string };
      if (data.ok) {
        setDeviceFiles(data.files);
        if (!silent) setScanMsg(`Found ${data.files.length} .osi/.sm file(s)`);
      } else {
        if (!silent) setScanError(data.error ?? "Scan failed");
      }
    } catch (e) {
      if (!silent) setScanError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }, [deviceDir, session.connected]);

  const discoverPreferredUploadDirectory = useCallback(async (): Promise<string | null> => {
    if (!session.connected) return null;
    try {
      const r = await fetch(`${API_BASE}/device/files/discover`);
      const data = await r.json() as DiscoverDeviceDirectoriesResponse;
      if (!r.ok || !data.ok || !Array.isArray(data.directories) || data.directories.length === 0) {
        return null;
      }
      const sorted = [...data.directories].sort((a, b) => {
        const ax = a.toLowerCase();
        const bx = b.toLowerCase();
        const aUsb = ax.includes("usb") ? 0 : (ax.includes("sd") || ax.includes("mmc") || ax.includes("mass_storage") ? 1 : 2);
        const bUsb = bx.includes("usb") ? 0 : (bx.includes("sd") || bx.includes("mmc") || bx.includes("mass_storage") ? 1 : 2);
        if (aUsb !== bUsb) return aUsb - bUsb;
        return ax.localeCompare(bx);
      });
      return sorted[0] ?? null;
    } catch {
      return null;
    }
  }, [session.connected]);

  const appendTransferLog = useCallback((message: string) => {
    const ts = new Date().toLocaleTimeString();
    setTransferLogs((prev) => [`${ts} ${message}`, ...prev].slice(0, 80));
  }, []);

  const buildTransferConfigForInspector = useCallback(() => ({
    protocol: transferProtocol,
    host: transferProtocol === "mapped_folder" || transferProtocol === "manual_usb" ? null : (transferHost.trim() || null),
    username: transferUser,
    password: transferPassword,
    remote_dir: transferRemoteDir,
    mapped_root: transferMappedRoot.trim() || null,
    timeout_s: 15,
    passive_mode: true,
  }), [transferProtocol, transferHost, transferUser, transferPassword, transferRemoteDir, transferMappedRoot]);

  const transferConfigPayload = useCallback(() => ({
    protocol: transferProtocol,
    host: transferProtocol === "mapped_folder" || transferProtocol === "manual_usb" ? null : (transferHost.trim() || null),
    username: transferUser,
    password: transferPassword,
    remote_dir: transferRemoteDir,
    mapped_root: transferMappedRoot.trim() || null,
    timeout_s: 15,
    passive_mode: true,
  }), [transferProtocol, transferHost, transferUser, transferPassword, transferRemoteDir, transferMappedRoot]);

  useEffect(() => {
    const loadHelp = async () => {
      try {
        const r = await fetch(`${API_BASE}/file-transfer/help`);
        if (!r.ok) return;
        const data = await r.json() as { ftp: string[]; smb: string[]; usb: string[] };
        setTransferHelp(data);
      } catch {
        // silent
      }
    };
    void loadHelp();
  }, []);

  const testTransferConnection = async () => {
    setTransferBusy(true);
    setTransferError(null);
    setTransferLikelyCauses([]);
    try {
      const r = await fetch(`${API_BASE}/file-transfer/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(transferConfigPayload()),
      });
      const data = await r.json() as {
        ok: boolean;
        message?: string;
        error?: string;
        warnings?: string[];
        likely_causes?: string[];
      };
      setTransferWarnings(data.warnings ?? []);
      setTransferLikelyCauses(data.likely_causes ?? []);
      setTransferStatus(data.ok ? (data.message ?? "Connection OK") : "Connection failed");
      if (!data.ok) setTransferError(data.error ?? "Connection test failed");
      appendTransferLog(`Test connection: ${data.ok ? "OK" : "FAILED"}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Connection test failed";
      setTransferError(msg);
      appendTransferLog(`Test connection error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  const runTransferPreflight = async () => {
    setTransferBusy(true);
    setTransferError(null);
    try {
      const r = await fetch(`${API_BASE}/file-transfer/preflight`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: transferConfigPayload(),
          remote_dir: transferRemoteDir,
          need_write: true,
        }),
      });
      const data = await r.json() as {
        ok: boolean;
        items: TransferChecklistItem[];
        warnings?: string[];
        likely_causes?: string[];
        error?: string;
      };
      setTransferChecklist(data.items ?? []);
      setTransferWarnings(data.warnings ?? []);
      setTransferLikelyCauses(data.likely_causes ?? []);
      if (!data.ok) setTransferError(data.error ?? "Preflight check failed");
      appendTransferLog(`Preflight: ${data.ok ? "PASS" : "CHECK WARNINGS"}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Preflight failed";
      setTransferError(msg);
      appendTransferLog(`Preflight error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  const refreshTransferFiles = async (osiOnly = false) => {
    setTransferBusy(true);
    setTransferError(null);
    try {
      const endpoint = osiOnly ? "/file-transfer/osi/scan" : "/file-transfer/list";
      const r = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: transferConfigPayload(),
          remote_dir: transferRemoteDir,
          file_filter: transferFilter,
          custom_ext: transferCustomFilter || null,
        }),
      });
      const data = await r.json() as {
        ok: boolean;
        files: TransferRemoteFile[];
        warnings?: string[];
        likely_causes?: string[];
        error?: string;
      };
      if (!data.ok) {
        setTransferError(data.error ?? "Remote list failed");
      }
      setTransferWarnings(data.warnings ?? []);
      setTransferLikelyCauses(data.likely_causes ?? []);
      setTransferFiles(data.files ?? []);
      setTransferStatus(`Listed ${data.files?.length ?? 0} item(s)`);
      appendTransferLog(`Refresh list (${osiOnly ? "OSI" : "all"}): ${data.ok ? "OK" : "FAILED"}`);

      // Keep scenario dropdown in sync with remote OSI files.
      const remoteOsi = (data.files ?? [])
        .filter((f) => !f.is_directory && (f.name.toLowerCase().endsWith(".osi") || f.name.toLowerCase().endsWith(".sm")))
        .map((f) => ({ name: f.name, path: f.remote_path, size_bytes: f.size, modified_time: f.modified_time }));
      if (remoteOsi.length > 0) {
        setDeviceFiles(remoteOsi);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Remote list failed";
      setTransferError(msg);
      appendTransferLog(`Refresh list error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  const uploadTransferFile = async () => {
    if (!transferLocalFile) {
      setTransferError("Select a local file first");
      return;
    }
    setTransferBusy(true);
    setTransferError(null);
    try {
      const formData = new FormData();
      formData.append("file", transferLocalFile);
      formData.append("protocol", transferProtocol);
      formData.append("host", transferHost);
      formData.append("username", transferUser);
      formData.append("password", transferPassword);
      formData.append("remote_dir", transferRemoteDir);
      formData.append("mapped_root", transferMappedRoot);
      formData.append("timeout_s", "15");
      formData.append("passive_mode", "true");
      formData.append("overwrite", "false");

      const r = await fetch(`${API_BASE}/file-transfer/upload-browser`, {
        method: "POST",
        body: formData,
      });
      const data = await r.json() as {
        ok: boolean;
        message?: string;
        error?: string;
        remote_path?: string;
        bytes_transferred?: number;
      };
      if (!data.ok) {
        setTransferError(data.error ?? "Upload failed");
        appendTransferLog(`Upload failed: ${data.error ?? "unknown error"}`);
        return;
      }

      setTransferStatus(data.message ?? `Uploaded ${data.bytes_transferred ?? 0} bytes`);
      appendTransferLog(`Uploaded: ${transferLocalFile.name} -> ${data.remote_path ?? transferRemoteDir}`);

      // Auto-refresh file table and OSI dropdown workflow.
      await refreshTransferFiles(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Upload failed";
      setTransferError(msg);
      appendTransferLog(`Upload error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  const downloadTransferFile = async () => {
    if (!transferSelectedPath) {
      setTransferError("Select a remote file to download");
      return;
    }
    setTransferBusy(true);
    setTransferError(null);
    try {
      const r = await fetch(`${API_BASE}/file-transfer/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: transferConfigPayload(),
          remote_path: transferSelectedPath,
          local_dir: transferDownloadDir,
          overwrite: false,
        }),
      });
      const data = await r.json() as { ok: boolean; message?: string; error?: string; local_path?: string };
      if (!data.ok) {
        setTransferError(data.error ?? "Download failed");
        appendTransferLog(`Download failed: ${data.error ?? "unknown error"}`);
        return;
      }
      setTransferStatus(data.message ?? "Download completed");
      appendTransferLog(`Downloaded: ${transferSelectedPath} -> ${data.local_path ?? transferDownloadDir}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Download failed";
      setTransferError(msg);
      appendTransferLog(`Download error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  const importScenarioToWorkspace = async () => {
    if (!transferSelectedPath) {
      setTransferError("Select a remote .osi file to import");
      return;
    }
    setTransferBusy(true);
    setTransferError(null);
    try {
      const r = await fetch(`${API_BASE}/scenario/files/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: transferConfigPayload(),
          remote_path: transferSelectedPath,
          local_dir: transferWorkspaceDir,
          overwrite: false,
          inspect_after_download: true,
        }),
      });
      const data = await r.json() as ScenarioWorkspaceDownloadResult;
      if (!data.ok || !data.local_path) {
        setTransferError(data.error ?? "Scenario import failed");
        appendTransferLog(`Import failed: ${data.error ?? "unknown error"}`);
        return;
      }

      setTransferStatus(data.message ?? "Scenario imported to workspace");
      appendTransferLog(
        `Imported scenario: ${data.remote_path ?? transferSelectedPath} -> ${data.local_path} (${data.message_count} frames)`
      );
      await decodeScenario(false, false, data.local_path);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Scenario import failed";
      setTransferError(msg);
      appendTransferLog(`Import error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  const createTransferDirectory = async () => {
    if (!transferNewFolder.trim()) {
      setTransferError("Enter a folder name/path");
      return;
    }
    setTransferBusy(true);
    setTransferError(null);
    try {
      const r = await fetch(`${API_BASE}/file-transfer/mkdir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: transferConfigPayload(), remote_dir: transferNewFolder }),
      });
      const data = await r.json() as { ok: boolean; message?: string; error?: string };
      if (!data.ok) {
        setTransferError(data.error ?? "Create folder failed");
      }
      appendTransferLog(data.ok ? `Created folder: ${transferNewFolder}` : `Create folder failed: ${data.error ?? "unknown"}`);
      await refreshTransferFiles();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Create folder failed";
      setTransferError(msg);
      appendTransferLog(`Create folder error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  const deleteTransferFile = async () => {
    if (!transferSelectedPath) {
      setTransferError("Select a remote file to delete");
      return;
    }
    if (!window.confirm(`Delete remote file ${transferSelectedPath}?`)) {
      return;
    }
    setTransferBusy(true);
    setTransferError(null);
    try {
      const r = await fetch(`${API_BASE}/file-transfer/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: transferConfigPayload(), remote_path: transferSelectedPath }),
      });
      const data = await r.json() as { ok: boolean; message?: string; error?: string };
      if (!data.ok) {
        setTransferError(data.error ?? "Delete failed");
      }
      appendTransferLog(data.ok ? `Deleted: ${transferSelectedPath}` : `Delete failed: ${data.error ?? "unknown"}`);
      await refreshTransferFiles();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Delete failed";
      setTransferError(msg);
      appendTransferLog(`Delete error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  const renameTransferFile = async () => {
    if (!transferSelectedPath) {
      setTransferError("Select a remote file to rename");
      return;
    }
    if (!transferRenameTo.trim()) {
      setTransferError("Enter a new file name");
      return;
    }
    setTransferBusy(true);
    setTransferError(null);
    try {
      const r = await fetch(`${API_BASE}/file-transfer/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: transferConfigPayload(),
          remote_path: transferSelectedPath,
          new_name: transferRenameTo,
        }),
      });
      const data = await r.json() as { ok: boolean; message?: string; error?: string };
      if (!data.ok) {
        setTransferError(data.error ?? "Rename failed");
      }
      appendTransferLog(data.ok ? `Renamed: ${transferSelectedPath} -> ${transferRenameTo}` : `Rename failed: ${data.error ?? "unknown"}`);
      await refreshTransferFiles();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Rename failed";
      setTransferError(msg);
      appendTransferLog(`Rename error: ${msg}`);
    } finally {
      setTransferBusy(false);
    }
  };

  // -------------------------------------------------------------------------
  // Upload
  // -------------------------------------------------------------------------

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setLocalFile(f);
    if (f) {
      setUploadMsg(null);
    }
  };

  const uploadFile = async () => {
    if (!localFile) {
      setUploadMsg({ text: "No file selected", ok: false });
      return;
    }
    if (!session.connected) {
      setUploadMsg({ text: "Device not connected", ok: false });
      return;
    }
    setUploading(true);
    setUploadProgress(10);
    setUploadMsg(null);
    setSelectedUploadDirectory(null);

    try {
      const discoveredUploadDir = deviceDir.trim() ? null : await discoverPreferredUploadDirectory();
      const preferredDir = deviceDir.trim() || discoveredUploadDir || "";
      if (discoveredUploadDir) {
        setSelectedUploadDirectory(discoveredUploadDir);
      }
      if (preferredDir && preferredDir !== deviceDir) {
        setDeviceDir(preferredDir);
      }
      const remotePath = preferredDir ? `${preferredDir.replace(/\/$/, "")}/${localFile.name}` : "";

      // Write local file to a temp path the backend can read
      // We send via multipart-like approach: first save locally then call the API.
      // Since the backend upload API takes a local_path, we instruct the user to
      // provide a path accessible to the backend.  For files selected in the
      // browser we send the content via a dedicated raw-upload helper endpoint.
      const formData = new FormData();
      formData.append("file", localFile);
      if (remotePath) {
        formData.append("remote_path", remotePath);
      }
      if (preferredDir) {
        formData.append("preferred_directory", preferredDir);
      }

      setUploadProgress(30);

      const r = await fetch(`${API_BASE}/device/files/upload-browser`, {
        method: "POST",
        body: formData,
      });

      setUploadProgress(80);

      if (r.ok) {
        const data = await r.json() as { ok: boolean; bytes_transferred: number; error?: string; remote_path?: string };
        if (data.ok) {
          setUploadMsg({ text: `Uploaded ${formatBytes(data.bytes_transferred)} → ${data.remote_path ?? remotePath}`, ok: true });
          // Refresh file list
          await scanDeviceFiles(true, preferredDir || undefined);
        } else {
          setUploadMsg({ text: data.error ?? "Upload failed", ok: false });
        }
      } else {
        // Fallback: if the browser-upload endpoint doesn't exist (older backend),
        // show a message asking the user to use local_path API.
        const p = await r.json().catch(() => ({})) as { detail?: string };
        setUploadMsg({ text: p.detail ?? "Upload endpoint unavailable – use the path-based API.", ok: false });
      }
    } catch (e) {
      setUploadMsg({ text: e instanceof Error ? e.message : "Upload failed", ok: false });
    } finally {
      setUploadProgress(100);
      setUploading(false);
    }
  };

  // -------------------------------------------------------------------------
  // Player actions
  // -------------------------------------------------------------------------

  const playerAction = async (action: string, endpoint: string) => {
    setPlayerBusy(true);
    setPlayerMsg(null);
    setLastCmd(action);
    setLastResp(null);
    try {
      const r = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await r.json() as { ok: boolean; message?: string; error?: string };
      setLastResp(data.message ?? data.error ?? null);
      if (!data.ok) setPlayerMsg(data.message ?? data.error ?? `${action} failed`);
      else {
        // Optimistic state update
        const stateMap: Record<string, PlaybackState> = {
          Load: "loaded", Play: "playing", Pause: "paused", Stop: "stopped", Restart: "playing",
        };
        if (stateMap[action]) setPlaybackState(stateMap[action]);
      }
      await refreshLog();
    } catch (e) {
      setPlayerMsg(e instanceof Error ? e.message : `${action} failed`);
    } finally {
      setPlayerBusy(false);
    }
  };

  // Stop: immediately reflect stopped state in UI, then fire-and-forget the SCPI
  // command so the button is never blocked by network latency.
  const stopScenario = () => {
    setPlaybackState("stopped");
    setPlayerMsg(null);
    setLastCmd("Stop");
    setLastResp(null);
    // Fire async in background — don't await so UI stays responsive
    void (async () => {
      try {
        const r = await fetch(`${API_BASE}/scenario/stop`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        const data = await r.json() as { ok: boolean; message?: string; error?: string };
        setLastResp(data.message ?? data.error ?? null);
        if (!data.ok) setPlayerMsg(data.error ?? data.message ?? "Stop failed");
        // Sync actual state from instrument
        try {
          const sr = await fetch(`${API_BASE}/scenario/status`);
          const sd = await sr.json() as { state: PlaybackState; current_scenario: string | null; replay_mode?: ReplayMode };
          setPlaybackState(sd.state);
          if (sd.replay_mode) setReplayMode(sd.replay_mode);
        } catch { /* silent */ }
        await refreshLog();
      } catch (e) {
        setPlayerMsg(e instanceof Error ? e.message : "Stop failed");
      }
    })();
  };

  const loadScenario = async () => {
    if (!selectedScenario) { setPlayerMsg("No scenario selected"); return; }
    setPlayerBusy(true);
    setPlayerMsg(null);
    try {
      const r = await fetch(`${API_BASE}/scenario/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_name: selectedScenario, replay_mode: replayMode }),
      });
      const data = await r.json() as { ok: boolean; message?: string };
      if (data.ok) {
        setPlaybackState("loaded");
        if (replayMode !== "UNKNOWN") setLastAppliedReplayMode(replayMode);
      }
      else setPlayerMsg(data.message ?? "Load failed");
      await refreshLog();
    } catch (e) {
      setPlayerMsg(e instanceof Error ? e.message : "Load failed");
    } finally {
      setPlayerBusy(false);
    }
  };

  const setReplayModeOnDevice = async (mode: ReplayMode) => {
    if (mode === "UNKNOWN") return;
    setPlayerBusy(true);
    setPlayerMsg(null);
    try {
      const r = await fetch(`${API_BASE}/scenario/replay-mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      const data = await r.json() as { ok: boolean; message?: string; replay_mode?: ReplayMode };
      if (!data.ok) {
        setPlayerMsg(data.message ?? "Failed to set replay mode");
        return;
      }
      setReplayMode((data.replay_mode ?? mode) as ReplayMode);
      setLastAppliedReplayMode((data.replay_mode ?? mode) as ReplayMode);
      await refreshLog();
    } catch (e) {
      setPlayerMsg(e instanceof Error ? e.message : "Failed to set replay mode");
    } finally {
      setPlayerBusy(false);
    }
  };

  const queryReplayMode = async () => {
    setPlayerBusy(true);
    setPlayerMsg(null);
    try {
      const r = await fetch(`${API_BASE}/scenario/replay-mode`);
      const data = await r.json() as { ok: boolean; replay_mode?: ReplayMode };
      if (!data.ok) {
        setReplayMode("UNKNOWN");
        setPlayerMsg("Failed to query replay mode");
      } else {
        const mode = (data.replay_mode ?? "UNKNOWN") as ReplayMode;
        setReplayMode(mode);
        if (mode !== "UNKNOWN") setLastAppliedReplayMode(mode);
        else setPlayerMsg("Replay mode query returned unexpected response; mode set to Unknown. Check command log diagnostics.");
      }
      await refreshLog();
    } catch (e) {
      setReplayMode("UNKNOWN");
      setPlayerMsg(e instanceof Error ? e.message : "Failed to query replay mode");
    } finally {
      setPlayerBusy(false);
    }
  };

  const queryStatus = async () => {
    setPlayerBusy(true);
    try {
      const r = await fetch(`${API_BASE}/scenario/status`);
      const data = await r.json() as { state: PlaybackState; current_scenario: string | null; replay_mode?: ReplayMode };
      setPlaybackState(data.state);
      if (data.current_scenario) setSelectedScenario(data.current_scenario);
      if (data.replay_mode) setReplayMode(data.replay_mode);
    } catch {
      /* silent */
    } finally {
      setPlayerBusy(false);
    }
  };

  const decodeScenario = async (decodeLoaded: boolean, forceRedownload = false, localPath: string | null = null) => {
    setInspectorBusy(true);
    setInspectorError(null);
    try {
      const endpoint = decodeLoaded ? "/scenario/inspector/decode-loaded" : "/scenario/inspector/decode-selected";
      const payload = {
        remote_path: decodeLoaded || localPath ? null : selectedScenario,
        local_path: localPath,
        force_redownload: forceRedownload,
        transfer_config: buildTransferConfigForInspector(),
      };
      const r = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json() as ScenarioDecodeResult;
      setInspectorResult(data);
      if (!data.ok) {
        setInspectorError(data.errors?.join(" | ") || "Decode failed");
      }
      if (data.objects?.length > 0) {
        setSelectedInspectorObjectId(data.objects[0].object_id);
      }
    } catch (e) {
      setInspectorError(e instanceof Error ? e.message : "Decode failed");
    } finally {
      setInspectorBusy(false);
    }
  };

  useEffect(() => {
    if (!selectedScenario || !session.connected) {
      return;
    }
    void decodeScenario(false);
    // Decode details for the currently selected scenario so live controls can show key stats.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedScenario, session.connected]);

  const clearScenarioCache = async () => {
    setInspectorBusy(true);
    setInspectorError(null);
    try {
      const r = await fetch(`${API_BASE}/scenario/inspector/clear-cache`, { method: "POST" });
      const data = await r.json() as { ok: boolean; removed_files: number; error?: string };
      if (!data.ok) {
        setInspectorError(data.error ?? "Failed to clear cache");
      }
    } catch (e) {
      setInspectorError(e instanceof Error ? e.message : "Failed to clear cache");
    } finally {
      setInspectorBusy(false);
    }
  };

  useEffect(() => {
    if (playbackState === "playing") {
      if (playbackStartAt == null) {
        setPlaybackStartAt(Date.now());
      }
    } else {
      setPlaybackStartAt(null);
      setEstimatedPlaybackSec(null);
    }
  }, [playbackState, playbackStartAt]);

  useEffect(() => {
    if (playbackState !== "playing" || playbackStartAt == null || !inspectorResult?.duration) {
      return;
    }
    const id = setInterval(() => {
      const elapsed = (Date.now() - playbackStartAt) / 1000;
      const duration = inspectorResult.duration ?? 0;
      if (duration > 0) {
        setEstimatedPlaybackSec(Math.min(elapsed, duration));
      } else {
        setEstimatedPlaybackSec(elapsed);
      }
    }, 500);
    return () => clearInterval(id);
  }, [playbackState, playbackStartAt, inspectorResult?.duration]);

  // -------------------------------------------------------------------------
  // SCPI console
  // -------------------------------------------------------------------------

  const runScpiCommand = async () => {
    const cleanedCommand = scpiCommand.trim();
    if (!cleanedCommand) {
      setScpiError("Command is empty");
      return;
    }
    setScpiRunning(true);
    setScpiError(null);
    try {
      const r = await fetch(`${API_BASE}/scpi/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cleanedCommand, timeout_ms: scpiTimeoutMs }),
      });
      if (!r.ok) {
        const p = await r.json() as { detail?: string };
        throw new Error(p.detail ?? "Command failed");
      }
      const data: CommandResult = await r.json() as CommandResult;
      setScpiResult(data);
      setScpiCommand(cleanedCommand);
      setScpiHistory((current) => [cleanedCommand, ...current.filter((entry) => entry !== cleanedCommand)].slice(0, 12));
      await refreshLog();
    } catch (e) {
      setScpiError(e instanceof Error ? e.message : "Command failed");
    } finally {
      setScpiRunning(false);
    }
  };

  // -------------------------------------------------------------------------
  // Log
  // -------------------------------------------------------------------------

  const refreshLog = async () => {
    try {
      const r = await fetch(`${API_BASE}/scenario/log`);
      if (r.ok) {
        const data = await r.json() as { log_entries: CommandLogEntry[] };
        setCommandLog(data.log_entries.slice(-60).reverse());
      }
    } catch {
      /* silent */
    }
  };

  const clearLog = async () => {
    try {
      await fetch(`${API_BASE}/scenario/log/clear`, { method: "POST" });
      setCommandLog([]);
    } catch {
      /* silent */
    }
  };

  // -------------------------------------------------------------------------
  // HCOPy actions
  // -------------------------------------------------------------------------

  const hcopyPost = async (endpoint: string, body: object): Promise<Record<string, unknown>> => {
    const r = await fetch(`${API_BASE}/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.json() as Promise<Record<string, unknown>>;
  };

  const hcopyGet = async (endpoint: string): Promise<Record<string, unknown>> => {
    const r = await fetch(`${API_BASE}/${endpoint}`);
    return r.json() as Promise<Record<string, unknown>>;
  };

  const applyHcopySettings = async () => {
    setHcopyBusy(true);
    setHcopyMsg(null);
    setHcopyMsgErr(false);
    try {
      await hcopyPost("hcopy/format", { format: hcopyFormat });
      await hcopyPost("hcopy/region", { region: hcopyRegion });
      await hcopyPost("hcopy/auto-naming", { enabled: hcopyAutoNaming });
      if (!hcopyAutoNaming && hcopyManualFilename.trim()) {
        await hcopyPost("hcopy/filename", { path: hcopyManualFilename });
      }
      if (hcopyAutoNaming) {
        await hcopyPost("hcopy/auto-directory", { directory: hcopyAutoDir });
        await hcopyPost("hcopy/prefix-enabled", { enabled: hcopyPrefixEnabled });
        if (hcopyPrefixEnabled && hcopyPrefix.trim()) {
          await hcopyPost("hcopy/prefix", { prefix: hcopyPrefix });
        }
        await hcopyPost("hcopy/date-components", {
          year: hcopyYearEnabled,
          month: hcopyMonthEnabled,
          day: hcopyDayEnabled,
        });
      }
      setHcopyMsg("Settings applied.");
    } catch (e) {
      setHcopyMsgErr(true);
      setHcopyMsg(e instanceof Error ? e.message : "Failed to apply settings");
    } finally {
      setHcopyBusy(false);
    }
  };

  const executeHcopy = async () => {
    setHcopyBusy(true);
    setHcopyMsg(null);
    setHcopyMsgErr(false);
    try {
      const result = await hcopyPost("hcopy/execute", {});
      if (result.ok) {
        setHcopyAutoFilename((result.generated_filename as string | null) ?? null);
        setHcopyAutoFullPath((result.generated_path as string | null) ?? null);
        setHcopyMsg((result.message as string) ?? "Hardcopy saved on instrument.");
        // Refresh auto number
        const numResult = await hcopyGet("hcopy/auto-number");
        if (numResult.number !== null && numResult.number !== undefined) {
          setHcopyAutoNumber(numResult.number as number);
        }
      } else {
        setHcopyMsgErr(true);
        setHcopyMsg((result.error as string) ?? "Execute failed");
      }
    } catch (e) {
      setHcopyMsgErr(true);
      setHcopyMsg(e instanceof Error ? e.message : "Execute failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  const captureHcopyData = async () => {
    setHcopyBusy(true);
    setHcopyMsg(null);
    setHcopyMsgErr(false);
    try {
      const result = await hcopyPost("hcopy/capture-data", { timeout_ms: 12000 });
      if (result.ok) {
        setHcopyLastCapture((result.file_path as string) ?? null);
        setHcopyMsg((result.message as string) ?? "Captured.");
      } else {
        setHcopyMsgErr(true);
        setHcopyMsg((result.error as string) ?? "Capture failed");
      }
    } catch (e) {
      setHcopyMsgErr(true);
      setHcopyMsg(e instanceof Error ? e.message : "Capture failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  const clearHcopyDirectory = async () => {
    const confirmed = window.confirm(
      `This will delete ALL .png/.bmp/.jpg/.xpm files in:\n\n${hcopyAutoDir}\n\nThis action cannot be undone. Continue?`
    );
    if (!confirmed) return;
    setHcopyBusy(true);
    setHcopyMsg(null);
    setHcopyMsgErr(false);
    try {
      const result = await hcopyPost("hcopy/auto-directory/clear", {});
      if (result.ok) {
        setHcopyMsg("Auto directory cleared.");
      } else {
        setHcopyMsgErr(true);
        setHcopyMsg((result.error as string) ?? "Clear failed");
      }
    } catch (e) {
      setHcopyMsgErr(true);
      setHcopyMsg(e instanceof Error ? e.message : "Clear failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  const refreshHcopyAutoInfo = async () => {
    setHcopyBusy(true);
    try {
      const [numR, fileR, pathR] = await Promise.all([
        hcopyGet("hcopy/auto-number"),
        hcopyGet("hcopy/auto-filename"),
        hcopyGet("hcopy/auto-path"),
      ]);
      if (numR.number !== null && numR.number !== undefined) setHcopyAutoNumber(numR.number as number);
      if (fileR.filename) setHcopyAutoFilename(fileR.filename as string);
      if (pathR.path) setHcopyAutoFullPath(pathR.path as string);
    } catch {
      /* silent */
    } finally {
      setHcopyBusy(false);
    }
  };

  const openHcopyLastCapture = async () => {
    if (!hcopyLastCapture) return;
    try {
      await hcopyPost("hardcopy/open-file", { file_path: hcopyLastCapture });
    } catch {
      /* silent */
    }
  };

  const refreshHcopyPresets = async () => {
    try {
      const result = await hcopyGet("hcopy/dialog-presets");
      const presets = (result.presets as HcopyDialogPreset[] | undefined) ?? [];
      setHcopyPresets(presets);
      if (!hcopySelectedPresetName && presets.length > 0) {
        setHcopySelectedPresetName(presets[0].name);
      }
    } catch {
      /* silent */
    }
  };

  const scanHcopyDialogs = async () => {
    setHcopyBusy(true);
    setHcopyDialogMsg(null);
    try {
      const result = await hcopyGet("hcopy/dialogs/open");
      if (!result.ok) {
        setHcopyDialogMsg((result.error as string) ?? "Dialog scan failed");
        return;
      }

      const dialogs = (result.dialogs as HcopyDialogEntry[] | undefined) ?? [];
      setHcopyDialogs(dialogs);
      if (dialogs.length > 0) {
        setHcopySelectedDialogId(dialogs[0].raw_id);
        setHcopyDialogMsg(`Found ${dialogs.length} open dialog(s).`);
      } else {
        setHcopyDialogMsg("No open dialogs detected.");
      }
    } catch (e) {
      setHcopyDialogMsg(e instanceof Error ? e.message : "Dialog scan failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  const openHcopyDialog = async (dialogId: string) => {
    setHcopyBusy(true);
    setHcopyDialogMsg(null);
    try {
      const result = await hcopyPost("hcopy/dialogs/open", {
        dialog_id: dialogId,
        delay_ms: hcopyScreenSwitchDelayMs,
        verify: hcopyVerifyDialogOpened,
      });
      if (result.ok) {
        setHcopyDialogMsg(`Opened dialog ${dialogId}`);
        const dialogs = (result.dialogs as HcopyDialogEntry[] | undefined) ?? [];
        if (dialogs.length > 0) {
          setHcopyDialogs(dialogs);
        }
      } else {
        setHcopyDialogMsg(`Open failed for ${dialogId}: ${(result.error as string) ?? "Unknown error"}`);
      }
    } catch (e) {
      setHcopyDialogMsg(e instanceof Error ? e.message : "Open dialog failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  const closeHcopyDialog = async (dialogId: string) => {
    setHcopyBusy(true);
    setHcopyDialogMsg(null);
    try {
      const result = await hcopyPost("hcopy/dialogs/close", { dialog_id: dialogId });
      if (result.ok) {
        setHcopyDialogMsg(`Closed dialog ${dialogId}`);
      } else {
        setHcopyDialogMsg(`Close failed for ${dialogId}: ${(result.error as string) ?? "Unknown error"}`);
      }
    } catch (e) {
      setHcopyDialogMsg(e instanceof Error ? e.message : "Close dialog failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  const closeAllHcopyDialogs = async () => {
    const confirmed = window.confirm("Close all open dialogs?");
    if (!confirmed) return;

    setHcopyBusy(true);
    setHcopyDialogMsg(null);
    try {
      const result = await hcopyPost("hcopy/dialogs/close-all", { confirm: true });
      if (result.ok) {
        setHcopyDialogs([]);
        setHcopyDialogMsg("Closed all dialogs.");
      } else {
        setHcopyDialogMsg((result.error as string) ?? "Close all dialogs failed");
      }
    } catch (e) {
      setHcopyDialogMsg(e instanceof Error ? e.message : "Close all dialogs failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  const saveHcopyDialogPreset = async (dialogId: string) => {
    const name = hcopyNewPresetName.trim() || window.prompt("Preset name", "")?.trim() || "";
    if (!name) {
      setHcopyDialogMsg("Preset name is required.");
      return;
    }

    setHcopyBusy(true);
    setHcopyDialogMsg(null);
    try {
      const result = await hcopyPost("hcopy/dialog-presets", {
        name,
        dialog_id: dialogId,
        region: hcopyRegion,
      });
      if (result.ok) {
        setHcopyNewPresetName("");
        setHcopySelectedPresetName(name);
        setHcopyDialogMsg(`Saved preset ${name}.`);
        await refreshHcopyPresets();
      } else {
        setHcopyDialogMsg((result.error as string) ?? "Save preset failed");
      }
    } catch (e) {
      setHcopyDialogMsg(e instanceof Error ? e.message : "Save preset failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  const resolveHcopyTargetDialogId = (): string | undefined => {
    if (hcopyTargetType === "manual") {
      return hcopyManualDialogId.trim() || undefined;
    }
    if (hcopyTargetType === "current_active_dialog") {
      return hcopySelectedDialogId || undefined;
    }
    return undefined;
  };

  const captureSelectedHcopyScreen = async (dialogIdOverride?: string) => {
    setHcopyBusy(true);
    setHcopyMsg(null);
    setHcopyMsgErr(false);
    setHcopyDialogMsg(null);
    try {
      const result = await hcopyPost("hcopy/capture-selected", {
        target_type: hcopyTargetType,
        dialog_id: dialogIdOverride || resolveHcopyTargetDialogId(),
        preset_name: hcopyTargetType === "preset" ? hcopySelectedPresetName : undefined,
        mode: hcopyCaptureMode,
        region: hcopyRegion,
        screen_switch_delay_ms: hcopyScreenSwitchDelayMs,
        verify_dialog_opened: hcopyVerifyDialogOpened,
        close_dialog_after_capture: hcopyCloseDialogAfterCapture,
        format: hcopyFormat,
        auto_naming: hcopyAutoNaming,
        manual_filename: hcopyAutoNaming ? undefined : hcopyManualFilename,
        auto_directory: hcopyAutoNaming ? hcopyAutoDir : undefined,
        local_dir: "./screenshots",
        local_filename: hcopyPrefixEnabled && hcopyPrefix.trim() ? hcopyPrefix.trim() : "hardcopy_capture",
      });

      const workflowLog = (result.log as HcopyWorkflowLogEntry[] | undefined) ?? [];
      setHcopyWorkflowLog(workflowLog);

      if (result.ok) {
        if (result.file_path) {
          setHcopyLastCapture(result.file_path as string);
        }
        setHcopyMsg((result.message as string) ?? "Capture completed.");
      } else {
        setHcopyMsgErr(true);
        setHcopyMsg((result.error as string) ?? "Capture selected screen failed");
      }
    } catch (e) {
      setHcopyMsgErr(true);
      setHcopyMsg(e instanceof Error ? e.message : "Capture selected screen failed");
    } finally {
      setHcopyBusy(false);
    }
  };

  useEffect(() => {
    void refreshHcopyPresets();
  }, []);

  useEffect(() => {
    if (session.connected) {
      void refreshHcopyPresets();
    }
  }, [session.connected]);

  useEffect(() => {
    if (!hcopyQuickOpen) {
      return;
    }
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        setHcopyQuickOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hcopyQuickOpen]);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------

  const hasSelection = Boolean(selectedScenario);
  const selectedOpt = CONNECTION_OPTIONS.find((o) => o.value === protocol)!;
  const selectedInspectorObject = inspectorResult?.objects?.find((o) => o.object_id === selectedInspectorObjectId) ?? null;
  const liveStatsObject = selectedInspectorObject ?? inspectorResult?.objects?.[0] ?? null;
  const liveStartM = liveStatsObject?.min_distance ?? null;
  const liveStopM = liveStatsObject?.max_distance ?? null;
  const liveSpeedMs = liveStatsObject?.average_speed ?? liveStatsObject?.initial_speed ?? null;
  const liveRcsM2 =
    liveStatsObject?.rcs_summary?.average
    ?? liveStatsObject?.rcs_summary?.max
    ?? liveStatsObject?.rcs_summary?.min
    ?? null;

  const formatMetricWithUnit = (value: number | null | undefined, unit: string, digits = 2): string => {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return "—";
    }
    return `${value.toFixed(digits)} ${unit}`;
  };

  // =========================================================================
  // Render
  // =========================================================================

  return (
    <div className="ucp-shell">
      {/* ================================================================
          TOP BAR
          ================================================================ */}
      <div className="ucp-topbar">
        <span className="ucp-topbar-title">AREG800A Control</span>
        <div className="ucp-topbar-sep" />

        {/* Connection form */}
        <div className="ucp-conn-form">
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
            >
              {CONNECTION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value} disabled={!o.supported}>
                  {o.label}{o.supported ? "" : " ✗"}
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
            />
          </label>
          <label>
            Port
            <input
              value={port}
              onChange={(e) => setPort(e.target.value)}
              inputMode="numeric"
              style={{ width: 60 }}
            />
          </label>
        </div>

        <button
          className="ucp-btn"
          onClick={session.connected ? disconnectDevice : connectDevice}
          disabled={connecting}
        >
          {connecting ? "Connecting…" : session.connected ? "Disconnect" : "Connect"}
        </button>

        <div className="ucp-conn-indicator">
          <span className={`ucp-dot ${session.connected ? "connected" : "disconnected"}`} />
          <span>{session.connected ? `${session.host}:${session.port}` : "Not connected"}</span>
          {session.connected && (
            <span style={{ color: "var(--text-dim)", fontSize: 12 }}>({session.transport})</span>
          )}
        </div>

        <div className="ucp-topbar-sep" />

        {/* Playback state badge */}
        <div
          className="ucp-state-badge"
          style={{ background: stateColor(playbackState) }}
        >
          {stateLabel(playbackState)}
        </div>

        <div className="ucp-topbar-right">
          <button
            className="ucp-btn secondary ucp-icon-btn"
            onClick={() => setHcopyQuickOpen(true)}
            disabled={!session.connected}
            title="Open hardcopy quick actions"
            aria-label="Open hardcopy quick actions"
          >
            📸
          </button>

          {connError && (
            <span style={{ color: "var(--accent-red)", fontSize: 12 }}>
              {connError}
            </span>
          )}
        </div>
      </div>

      {hcopyQuickOpen && (
        <div className="ucp-modal-backdrop" onClick={() => setHcopyQuickOpen(false)}>
          <div className="ucp-modal ucp-modal-hcopy" onClick={(e) => e.stopPropagation()}>
            <div className="ucp-modal-header">
              <div className="ucp-modal-title">Hardcopy Quick Access</div>
              <button className="ucp-btn secondary" onClick={() => setHcopyQuickOpen(false)}>Close</button>
            </div>

            <div className="ucp-modal-body">
              <div className="ucp-hcopy-row" style={{ alignItems: "end" }}>
                <label className="ucp-hcopy-label" style={{ minWidth: 140 }}>
                  Format
                  <select className="ucp-cmd-input" value={hcopyFormat} onChange={(e) => setHcopyFormat(e.target.value)}>
                    {"PNG,BMP,JPG,XPM".split(",").map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                </label>
                <label className="ucp-hcopy-label" style={{ minWidth: 150 }}>
                  Region
                  <select className="ucp-cmd-input" value={hcopyRegion} onChange={(e) => setHcopyRegion(e.target.value)}>
                    <option value="ALL">ALL</option>
                    <option value="DIALog">DIALog</option>
                  </select>
                </label>
                <label className="ucp-hcopy-label" style={{ minWidth: 170 }}>
                  Capture mode
                  <select
                    className="ucp-cmd-input"
                    value={hcopyCaptureMode}
                    onChange={(e) => setHcopyCaptureMode(e.target.value as HcopyCaptureMode)}
                  >
                    <option value="execute">Save to instrument</option>
                    <option value="data">Capture to PC</option>
                  </select>
                </label>
                <button className="ucp-btn secondary" onClick={applyHcopySettings} disabled={hcopyBusy || !session.connected}>
                  Apply
                </button>
              </div>

              <div className="ucp-hcopy-actions">
                <button className="ucp-btn" onClick={executeHcopy} disabled={hcopyBusy || !session.connected}>
                  {hcopyBusy ? "Working…" : "Execute (→ Instrument)"}
                </button>
                <button className="ucp-btn success" onClick={() => captureSelectedHcopyScreen()} disabled={hcopyBusy || !session.connected}>
                  {hcopyBusy ? "Working…" : "Capture Selected Screen"}
                </button>
                <button className="ucp-btn" onClick={captureHcopyData} disabled={hcopyBusy || !session.connected}>
                  {hcopyBusy ? "Working…" : "Capture (→ PC)"}
                </button>
              </div>

              {hcopyMsg && (
                <div className={`ucp-msg ${hcopyMsgErr ? "error" : "success"}`}>{hcopyMsg}</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ================================================================
          MAIN CONTENT
          ================================================================ */}
      <div className="ucp-main">

        {/* ============================================================
            Live Scenario Control – transport buttons (top, always visible)
            ============================================================ */}
        <Section icon="🎮" title="Live Scenario Control">
          <div className="ucp-player-inset">
            {/* Track display */}
            <div className="ucp-track-display" style={{ marginBottom: 10 }}>
              <span className="ucp-track-icon">🎬</span>
              <div className="ucp-track-info">
                <div className="ucp-track-name">
                  {selectedScenario
                    ? selectedScenario.split("/").pop() ?? selectedScenario
                    : "No scenario selected"}
                </div>
                {selectedScenario && (
                  <div className="ucp-track-meta">{selectedScenario}</div>
                )}
              </div>
              <div
                className="ucp-state-badge"
                style={{ background: stateColor(playbackState) }}
              >
                {stateLabel(playbackState)}
              </div>
            </div>

            <div className="ucp-live-control-grid">
              <div className="ucp-live-control-pane">
                <div className="ucp-player-controls">
                  <div className="ucp-player-controls-row ucp-player-controls-row--mode">
                    <label className="ucp-replay-select">
                      <span>Replay</span>
                      <select
                        value={replayMode === "UNKNOWN" ? "SINGle" : replayMode}
                        onChange={(e) => setReplayMode(e.target.value as ReplayMode)}
                        disabled={!session.connected || playerBusy}
                      >
                        <option value="SINGle">Single</option>
                        <option value="LOOP">Loop</option>
                      </select>
                    </label>
                    <button
                      className="ucp-ctrl-btn secondary ucp-ctrl-btn--compact"
                      onClick={() => setReplayModeOnDevice(replayMode)}
                      disabled={!session.connected || playerBusy || replayMode === "UNKNOWN"}
                      title="Apply replay mode to instrument"
                    >
                      Apply Mode
                    </button>
                    <button
                      className="ucp-ctrl-btn secondary ucp-ctrl-btn--compact"
                      onClick={queryReplayMode}
                      disabled={!session.connected || playerBusy}
                      title="Query replay mode from instrument"
                    >
                      Read Mode
                    </button>
                    <button
                      className="ucp-ctrl-btn secondary ucp-ctrl-btn--compact"
                      onClick={queryStatus}
                      disabled={playerBusy}
                      title="Query current scenario status"
                    >
                      Refresh Status
                    </button>
                  </div>

                  <div className="ucp-player-controls-row ucp-player-controls-row--actions">
                    <button
                      className="ucp-ctrl-btn"
                      onClick={loadScenario}
                      disabled={!hasSelection || playerBusy}
                      title={session.connected ? "Load scenario onto instrument" : "Load scenario into offline preview"}
                    >
                      ⏏ Load
                    </button>
                    <button
                      className="ucp-ctrl-btn play"
                      onClick={() => playerAction("Play", "/scenario/play")}
                      disabled={!hasSelection || playerBusy}
                      title={session.connected ? "Start playback" : "Start offline preview playback"}
                    >
                      ▶ Play
                    </button>
                    <button
                      className="ucp-ctrl-btn"
                      onClick={() => playerAction("Pause", "/scenario/pause")}
                      disabled={playbackState !== "playing" || playerBusy}
                      title={session.connected ? "Pause playback" : "Pause offline preview playback"}
                    >
                      ⏸ Pause
                    </button>
                    <button
                      className="ucp-ctrl-btn stop"
                      onClick={stopScenario}
                      title={session.connected ? "Stop playback immediately" : "Stop offline preview playback"}
                    >
                      ⏹ Stop
                    </button>
                    <button
                      className="ucp-ctrl-btn"
                      onClick={() => playerAction("Restart", "/scenario/restart")}
                      disabled={!hasSelection || playerBusy}
                      title={session.connected ? "Restart playback" : "Restart offline preview playback"}
                    >
                      🔄 Restart
                    </button>
                  </div>
                </div>

                {playerMsg && (
                  <div className="ucp-msg error" style={{ marginTop: 8 }}>{playerMsg}</div>
                )}
              </div>

              <div className="ucp-live-details-pane">
                <div className="ucp-live-details-title">Scenario Details</div>
                <div className="ucp-live-stats-grid">
                  <div className="ucp-live-stat">
                    <span className="label">Start</span>
                    <span className="value">{formatMetricWithUnit(liveStartM, "m", 2)}</span>
                  </div>
                  <div className="ucp-live-stat">
                    <span className="label">Stop</span>
                    <span className="value">{formatMetricWithUnit(liveStopM, "m", 2)}</span>
                  </div>
                  <div className="ucp-live-stat">
                    <span className="label">Speed</span>
                    <span className="value">{formatMetricWithUnit(liveSpeedMs, "m/s", 2)}</span>
                  </div>
                  <div className="ucp-live-stat">
                    <span className="label">RCS</span>
                    <span className="value">{formatMetricWithUnit(liveRcsM2, "m²", 2)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Section>

        {/* External Storage Browser is placed at the absolute bottom */}

        {/* ============================================================
            Two-column layout: [Log] | [Instrument Storage Browser]
            ============================================================ */}
        <div className="ucp-player-log-grid">
          {/* ---- LEFT: Command Log ---- */}
          <div className="ucp-log-col">
            <div className="ucp-log-panel" style={storagePanelHeight ? { height: `${storagePanelHeight}px` } : undefined}>
              <div className="ucp-log-panel-header">
                <span>📋 Command Log</span>
                <div style={{ display: "flex", gap: 6 }}>
                  <button className="ucp-btn secondary" style={{ padding: "2px 10px", fontSize: 12 }} onClick={refreshLog}>Refresh</button>
                  <button className="ucp-btn secondary danger" style={{ padding: "2px 10px", fontSize: 12 }} onClick={clearLog}>Clear</button>
                </div>
              </div>
              <div className="ucp-log-list ucp-log-list--fill">
                {commandLog.length === 0 ? (
                  <div className="ucp-empty-state">No commands logged yet.</div>
                ) : (
                  [...commandLog].reverse().map((entry, i) => (
                    <div key={i} className={`ucp-log-entry ${entry.ok ? "ok" : "error"}`}>
                      <span className="ucp-log-ts">{entry.timestamp}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="ucp-log-cmd">{entry.command}</div>
                        {entry.response && (
                          <div className="ucp-log-response">→ {entry.response}</div>
                        )}
                        {entry.error && (
                          <div className="ucp-log-error">✗ {entry.error}</div>
                        )}
                      </div>
                      <span className={`ucp-log-type ${entry.command_type}`}>
                        {entry.command_type}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>{/* end ucp-log-col */}

          {/* ---- RIGHT: Instrument Storage Browser ---- */}
          <div className="ucp-sim-player-col" ref={storagePanelRef}>
            <Section icon="📁" title="Instrument Storage Browser">
              <div className="ucp-storage-panel-body">
              {/* Directory + scan */}
              <div className="ucp-row" style={{ marginBottom: 10 }}>
                <div className="ucp-field" style={{ flex: 1 }}>
                  <label>Device directory</label>
                  <input
                    value={deviceDir}
                    onChange={(e) => setDeviceDir(e.target.value)}
                    placeholder="Type device path (default /var/user)"
                    disabled={!session.connected}
                  />
                </div>
                <button
                  className="ucp-btn"
                  onClick={() => scanDeviceFiles()}
                  disabled={!session.connected || scanning}
                  style={{ alignSelf: "flex-end" }}
                >
                  {scanning ? "Scanning…" : "Refresh Files"}
                </button>
              </div>

              {scanError && <div className="ucp-msg error">{scanError}</div>}
              {scanMsg && !scanError && <div className="ucp-msg success">{scanMsg}</div>}
              {selectedScanDirectory && (
                <div className="ucp-auto-indicator" style={{ marginBottom: 10 }}>
                  Auto-selected scan directory: {selectedScanDirectory}
                </div>
              )}

              {/* Available files dropdown */}
              <div className="ucp-field" style={{ marginBottom: 12 }}>
                <label>Scenario Library (.osi/.sm)</label>
                {deviceFiles.length === 0 ? (
                  <div className="ucp-empty-state">
                    {session.connected
                      ? 'No .osi/.sm files found on the device. Click "Refresh Files" to scan.'
                      : "Connect to the device to scan for available .osi/.sm files."}
                  </div>
                ) : (
                  <select
                    className="ucp-file-dropdown"
                    value={selectedScenario ?? ""}
                    onChange={(e) => {
                      setSelectedScenario(e.target.value || null);
                      setPlaybackState("not_loaded");
                      setPlayerMsg(null);
                    }}
                  >
                    <option value="">— Select a scenario —</option>
                    {deviceFiles.map((f) => (
                      <option key={f.path} value={f.path}>
                        {f.name}{f.size_bytes != null ? ` (${formatBytes(f.size_bytes)})` : ""}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Upload area */}
              <details style={{ marginTop: 4 }}>
                <summary
                  style={{
                    cursor: "pointer",
                    color: "var(--text-muted)",
                    fontSize: 13,
                    userSelect: "none",
                    marginBottom: 8,
                  }}
                >
                  ⬆ Upload Scenario File (.osi/.sm) to device
                </summary>
                <div style={{ marginTop: 10 }}>
                  <div className="ucp-upload-area">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".osi,.sm"
                      onChange={handleFileSelect}
                      id="ucp-file-input"
                    />
                    <label className="ucp-upload-label" htmlFor="ucp-file-input">
                      📂 Choose .osi/.sm file
                    </label>
                    <span className="ucp-selected-file">
                      {localFile ? localFile.name : "No file chosen"}
                    </span>
                  </div>

                  <div className="ucp-row" style={{ marginTop: 8 }}>
                    <div className="ucp-remote-field" style={{ flex: 1 }}>
                      <label>Destination on device</label>
                      <div className="ucp-empty-state" style={{ marginTop: 4 }}>
                        {localFile
                          ? `${deviceDir.replace(/\/$/, "")}/${localFile.name}`
                          : "Choose a local .osi/.sm file to generate destination path"}
                      </div>
                    </div>
                    <button
                      className="ucp-btn"
                      onClick={uploadFile}
                      disabled={!localFile || !session.connected || uploading}
                    >
                      {uploading ? "Uploading…" : "Upload"}
                    </button>
                  </div>

                  {uploading && (
                    <div className="ucp-progress-bar">
                      <div className="ucp-progress-fill" style={{ width: `${uploadProgress}%` }} />
                    </div>
                  )}

                  {uploadMsg && (
                    <div className={`ucp-msg ${uploadMsg.ok ? "success" : "error"}`} style={{ marginTop: 8 }}>
                      {uploadMsg.text}
                    </div>
                  )}
                  {selectedUploadDirectory && (
                    <div className="ucp-auto-indicator" style={{ marginTop: 8 }}>
                      Auto-selected upload directory: {selectedUploadDirectory}
                    </div>
                  )}
                </div>
              </details>
              </div>
            </Section>
          </div>{/* end ucp-sim-player-col */}

        </div>{/* end ucp-player-log-grid */}

        {/* ============================================================
            Simulation Overview – below log + file explorer
            ============================================================ */}
        <Section icon="📊" title="Simulation Overview & Scenario Details" defaultOpen={false}>
          <SimulationOverview />
        </Section>

        {/* ============================================================
          SECTION 4 – Scenario Generator (simple + speed sweep)
            ============================================================ */}
        <Section icon="🎬" title="Scenario Generator" defaultOpen={false}>
          <div className="ucp-generator-shell">
            <div className="ucp-generator-header">
              <div>
                <div className="ucp-generator-title">Generator Mode</div>
                <div className="ucp-generator-subtitle">
                  Use one workflow at a time: quick single-scenario creation or structured speed sweep generation.
                </div>
              </div>

              <div className="ucp-generator-toggle" role="tablist" aria-label="Scenario generator mode">
                <button
                  type="button"
                  role="tab"
                  aria-selected={generatorMode === "simple"}
                  className={`ucp-generator-tab ${generatorMode === "simple" ? "active" : ""}`}
                  onClick={() => setGeneratorMode("simple")}
                >
                  ⚡ Simple
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={generatorMode === "speed_sweep"}
                  className={`ucp-generator-tab ${generatorMode === "speed_sweep" ? "active" : ""}`}
                  onClick={() => setGeneratorMode("speed_sweep")}
                >
                  🧪 Speed Sweep
                </button>
              </div>
            </div>

            <div className="ucp-generator-meta">
              {generatorMode === "simple"
                ? "Simple mode: create one scenario file quickly with template-driven parameters."
                : "Speed sweep mode: build step cases across a speed range for repeatable validation runs."}
            </div>

            <div className="ucp-generator-stack" style={{ marginTop: 10 }}>
              <div className="ucp-generator-block">
                <div className="ucp-generator-block-title">
                  {generatorMode === "simple" ? "Simple Scenario Generator" : "Speed Sweep Generator"}
                </div>
                <div className="ucp-generator-embed">
                  {generatorMode === "simple" ? (
                    <ScenarioGenerator />
                  ) : (
                    <ScenarioSweepPanel connected={session.connected} mode="speed-sweep" />
                  )}
                </div>
              </div>
            </div>
          </div>
        </Section>

        {/* ============================================================
          SECTION 5 – Hardcopy / Screenshot
            ============================================================ */}
        <Section icon="📸" title="Hardcopy / Screenshot" defaultOpen={false}>
          <div className="ucp-hcopy-panel">
            {/* ---- Format & Region ---- */}
            <div className="ucp-hcopy-row">
              <label className="ucp-hcopy-label">
                Image Format
                <select
                  className="ucp-cmd-input"
                  value={hcopyFormat}
                  onChange={(e) => setHcopyFormat(e.target.value)}
                >
                  {["PNG", "BMP", "JPG", "XPM"].map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </label>
              <label className="ucp-hcopy-label">
                Region
                <select
                  className="ucp-cmd-input"
                  value={hcopyRegion}
                  onChange={(e) => setHcopyRegion(e.target.value)}
                >
                  <option value="ALL">ALL (full screen)</option>
                  <option value="DIALog">DIALog (active dialog)</option>
                </select>
              </label>
              <label className="ucp-hcopy-label">
                Target selector
                <select
                  className="ucp-cmd-input"
                  value={hcopyTargetType}
                  onChange={(e) => setHcopyTargetType(e.target.value as HcopyTargetType)}
                >
                  <option value="current_screen">Current screen</option>
                  <option value="current_active_dialog">Current active dialog</option>
                  <option value="preset">Saved dialog preset</option>
                  <option value="manual">Manually entered dialog ID</option>
                </select>
              </label>
            </div>

            <div className="ucp-hcopy-sub">
              <div className="ucp-hcopy-row" style={{ alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <button
                  className="ucp-btn secondary"
                  onClick={scanHcopyDialogs}
                  disabled={hcopyBusy || !session.connected}
                >
                  Scan open dialogs
                </button>
                <button
                  className="ucp-btn secondary danger"
                  onClick={closeAllHcopyDialogs}
                  disabled={hcopyBusy || !session.connected}
                >
                  Close All Dialogs…
                </button>
                <label className="ucp-hcopy-label" style={{ minWidth: 140 }}>
                  Output mode
                  <select
                    className="ucp-cmd-input"
                    value={hcopyCaptureMode}
                    onChange={(e) => setHcopyCaptureMode(e.target.value as HcopyCaptureMode)}
                  >
                    <option value="execute">Save to instrument (:HCOPy:EXECute)</option>
                    <option value="data">Capture to PC (:HCOPy:DATA?)</option>
                  </select>
                </label>
                <label className="ucp-hcopy-label" style={{ minWidth: 120 }}>
                  Screen switch delay (ms)
                  <input
                    className="ucp-cmd-input"
                    type="number"
                    min={0}
                    step={50}
                    value={hcopyScreenSwitchDelayMs}
                    onChange={(e) => setHcopyScreenSwitchDelayMs(Math.max(0, Number(e.target.value) || 0))}
                  />
                </label>
              </div>

              <div className="ucp-hcopy-row" style={{ alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <label className="ucp-hcopy-check-label">
                  <input
                    type="checkbox"
                    checked={hcopyVerifyDialogOpened}
                    onChange={(e) => setHcopyVerifyDialogOpened(e.target.checked)}
                  />
                  Verify dialog opened before hardcopy
                </label>
                <label className="ucp-hcopy-check-label">
                  <input
                    type="checkbox"
                    checked={hcopyCloseDialogAfterCapture}
                    onChange={(e) => setHcopyCloseDialogAfterCapture(e.target.checked)}
                  />
                  Close dialog after hardcopy
                </label>
              </div>

              {hcopyTargetType === "preset" && (
                <div className="ucp-hcopy-row" style={{ alignItems: "end" }}>
                  <label className="ucp-hcopy-label" style={{ flex: 1 }}>
                    Preset
                    <select
                      className="ucp-cmd-input"
                      value={hcopySelectedPresetName}
                      onChange={(e) => setHcopySelectedPresetName(e.target.value)}
                    >
                      <option value="">Select preset…</option>
                      {hcopyPresets.map((preset) => (
                        <option key={preset.name} value={preset.name}>{preset.name} ({preset.dialog_id})</option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="ucp-btn secondary"
                    onClick={refreshHcopyPresets}
                    disabled={hcopyBusy || !session.connected}
                  >
                    Refresh Presets
                  </button>
                </div>
              )}

              {hcopyTargetType === "manual" && (
                <label className="ucp-hcopy-label" style={{ flex: 1 }}>
                  Manual Dialog ID
                  <input
                    className="ucp-cmd-input"
                    value={hcopyManualDialogId}
                    onChange={(e) => setHcopyManualDialogId(e.target.value)}
                    placeholder='Dialog ID from :DISPlay:DIALog:ID?'
                  />
                </label>
              )}

              <div className="ucp-hcopy-row" style={{ alignItems: "end" }}>
                <label className="ucp-hcopy-label" style={{ flex: 1 }}>
                  New preset name
                  <input
                    className="ucp-cmd-input"
                    value={hcopyNewPresetName}
                    onChange={(e) => setHcopyNewPresetName(e.target.value)}
                    placeholder="e.g. Scenario screen"
                  />
                </label>
                <button
                  className="ucp-btn secondary"
                  onClick={() => saveHcopyDialogPreset(hcopySelectedDialogId)}
                  disabled={!hcopySelectedDialogId || hcopyBusy || !session.connected}
                >
                  Save Selected As Preset
                </button>
              </div>

              {hcopyDialogMsg && <div className="ucp-msg info">{hcopyDialogMsg}</div>}

              <div className="ucp-hcopy-dialog-table-wrap">
                <table className="ucp-hcopy-dialog-table">
                  <thead>
                    <tr>
                      <th>Raw dialog ID</th>
                      <th>Dialog name</th>
                      <th>Qualifier</th>
                      <th>Instance / Tab</th>
                      <th>User label</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hcopyDialogs.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="ucp-empty-state">No open dialogs detected.</td>
                      </tr>
                    ) : hcopyDialogs.map((dialog) => (
                      <tr
                        key={dialog.raw_id}
                        className={hcopySelectedDialogId === dialog.raw_id ? "ucp-hcopy-dialog-selected" : ""}
                        onClick={() => setHcopySelectedDialogId(dialog.raw_id)}
                      >
                        <td>{dialog.raw_id}</td>
                        <td>{dialog.dialog_name}</td>
                        <td>{dialog.qualifier ?? "-"}</td>
                        <td>{dialog.instance_data ?? dialog.tab_data ?? "-"}</td>
                        <td>{dialog.user_label}</td>
                        <td>
                          <div className="ucp-hcopy-dialog-actions-inline">
                            <button className="ucp-btn secondary" onClick={(e) => { e.stopPropagation(); void openHcopyDialog(dialog.raw_id); }} disabled={hcopyBusy || !session.connected}>Open</button>
                            <button className="ucp-btn secondary" onClick={(e) => { e.stopPropagation(); void closeHcopyDialog(dialog.raw_id); }} disabled={hcopyBusy || !session.connected}>Close</button>
                            <button className="ucp-btn secondary" onClick={(e) => { e.stopPropagation(); void saveHcopyDialogPreset(dialog.raw_id); }} disabled={hcopyBusy || !session.connected}>Save preset</button>
                            <button
                              className="ucp-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                setHcopyTargetType("manual");
                                setHcopyManualDialogId(dialog.raw_id);
                                void captureSelectedHcopyScreen(dialog.raw_id);
                              }}
                              disabled={hcopyBusy || !session.connected}
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

            {/* ---- Auto naming toggle ---- */}
            <div className="ucp-hcopy-row" style={{ alignItems: "center", gap: 12 }}>
              <label className="ucp-hcopy-check-label">
                <input
                  type="checkbox"
                  checked={hcopyAutoNaming}
                  onChange={(e) => setHcopyAutoNaming(e.target.checked)}
                />
                Automatic Naming
              </label>
            </div>

            {/* ---- Auto naming options ---- */}
            {hcopyAutoNaming ? (
              <div className="ucp-hcopy-sub">
                <label className="ucp-hcopy-label" style={{ flex: 1 }}>
                  Auto Directory (on instrument)
                  <input
                    className="ucp-cmd-input"
                    value={hcopyAutoDir}
                    onChange={(e) => setHcopyAutoDir(e.target.value)}
                    placeholder="/var/user/HCopy"
                  />
                </label>

                <div className="ucp-hcopy-row" style={{ alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <label className="ucp-hcopy-check-label">
                    <input
                      type="checkbox"
                      checked={hcopyPrefixEnabled}
                      onChange={(e) => setHcopyPrefixEnabled(e.target.checked)}
                    />
                    Prefix
                  </label>
                  {hcopyPrefixEnabled && (
                    <input
                      className="ucp-cmd-input"
                      style={{ flex: 1, minWidth: 140 }}
                      value={hcopyPrefix}
                      onChange={(e) => setHcopyPrefix(e.target.value)}
                      placeholder="e.g. hardcopy"
                    />
                  )}
                </div>

                <div className="ucp-hcopy-row" style={{ alignItems: "center", gap: 16 }}>
                  <span style={{ fontSize: "0.85rem", color: "var(--color-muted, #888)" }}>Date components:</span>
                  <label className="ucp-hcopy-check-label">
                    <input type="checkbox" checked={hcopyYearEnabled} onChange={(e) => setHcopyYearEnabled(e.target.checked)} />
                    Year
                  </label>
                  <label className="ucp-hcopy-check-label">
                    <input type="checkbox" checked={hcopyMonthEnabled} onChange={(e) => setHcopyMonthEnabled(e.target.checked)} />
                    Month
                  </label>
                  <label className="ucp-hcopy-check-label">
                    <input type="checkbox" checked={hcopyDayEnabled} onChange={(e) => setHcopyDayEnabled(e.target.checked)} />
                    Day
                  </label>
                </div>

                {/* Auto naming info */}
                <div className="ucp-hcopy-info-row">
                  <div className="ucp-hcopy-info-item">
                    <span className="ucp-hcopy-info-label">Auto number:</span>
                    <span>{hcopyAutoNumber !== null ? String(hcopyAutoNumber) : "—"}</span>
                  </div>
                  <div className="ucp-hcopy-info-item">
                    <span className="ucp-hcopy-info-label">Filename:</span>
                    <span>{hcopyAutoFilename ?? "—"}</span>
                  </div>
                  <div className="ucp-hcopy-info-item">
                    <span className="ucp-hcopy-info-label">Full path:</span>
                    <span>{hcopyAutoFullPath ?? "—"}</span>
                  </div>
                </div>

                <div className="ucp-hcopy-row" style={{ gap: 8, flexWrap: "wrap" }}>
                  <button
                    className="ucp-btn secondary"
                    onClick={refreshHcopyAutoInfo}
                    disabled={hcopyBusy || !session.connected}
                  >
                    Refresh Auto Info
                  </button>
                  <button
                    className="ucp-btn secondary danger"
                    onClick={clearHcopyDirectory}
                    disabled={hcopyBusy || !session.connected}
                    title="Delete all image files from the auto-naming directory on the instrument"
                  >
                    Clear Auto Directory…
                  </button>
                </div>
              </div>
            ) : (
              <div className="ucp-hcopy-sub">
                <label className="ucp-hcopy-label" style={{ flex: 1 }}>
                  Manual Filename (full path on instrument)
                  <input
                    className="ucp-cmd-input"
                    value={hcopyManualFilename}
                    onChange={(e) => setHcopyManualFilename(e.target.value)}
                    placeholder="/var/user/myshot.png"
                  />
                </label>
              </div>
            )}

            {/* ---- Action buttons ---- */}
            <div className="ucp-hcopy-actions">
              <button
                className="ucp-btn secondary"
                onClick={applyHcopySettings}
                disabled={hcopyBusy || !session.connected}
                title="Send format, region and naming settings to instrument"
              >
                Apply Settings
              </button>
              <button
                className="ucp-btn"
                onClick={executeHcopy}
                disabled={hcopyBusy || !session.connected}
                title=":HCOPy:EXECute — save screenshot to instrument file system"
              >
                {hcopyBusy ? "Working…" : "Execute (→ Instrument)"}
              </button>
              <button
                className="ucp-btn success"
                onClick={() => captureSelectedHcopyScreen()}
                disabled={hcopyBusy || !session.connected}
                title="Switch selected screen/dialog and then capture"
              >
                {hcopyBusy ? "Working…" : "Capture Selected Screen"}
              </button>
              <button
                className="ucp-btn"
                onClick={captureHcopyData}
                disabled={hcopyBusy || !session.connected}
                title=":HCOPy:DATA? — transfer image directly to PC"
              >
                {hcopyBusy ? "Working…" : "Capture (→ PC)"}
              </button>
            </div>

            {/* ---- Feedback ---- */}
            {hcopyMsg && (
              <div className={`ucp-msg ${hcopyMsgErr ? "error" : "success"}`}>{hcopyMsg}</div>
            )}
            {hcopyLastCapture && (
              <div className="ucp-hcopy-row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: "0.85rem" }}>
                  Last capture: <code style={{ wordBreak: "break-all" }}>{hcopyLastCapture}</code>
                </span>
                <button
                  className="ucp-btn secondary"
                  style={{ flexShrink: 0 }}
                  onClick={openHcopyLastCapture}
                >
                  Open Folder
                </button>
              </div>
            )}

            {hcopyWorkflowLog.length > 0 && (
              <div className="ucp-hcopy-workflow-log">
                <div className="ucp-hcopy-workflow-log-title">Screen-switch workflow log</div>
                <div className="ucp-log-list" style={{ maxHeight: 200 }}>
                  {hcopyWorkflowLog.map((entry, idx) => (
                    <div key={`${entry.command}-${idx}`} className={`ucp-log-entry ${entry.ok ? "ok" : "error"}`}>
                      <span className="ucp-log-ts">{entry.timestamp ?? new Date().toISOString()}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="ucp-log-cmd">{entry.command}</div>
                        {entry.message && <div className="ucp-log-response">{entry.message}</div>}
                        {entry.error && <div className="ucp-log-error">✗ {entry.error}</div>}
                      </div>
                      <span className="ucp-log-type write">{entry.command_type ?? "action"}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Section>

        {/* ============================================================
          SECTION 7 – Manual SCPI Console
            ============================================================ */}
        <Section icon="⌨" title="Manual SCPI Console" defaultOpen={false}>
          <div className="ucp-console-grid">
            <CommandBuilder command={scpiCommand} onCommandChange={setScpiCommand} />
            <div className="ucp-row" style={{ gap: 12, alignItems: "end", flexWrap: "wrap" }}>
              <label style={{ minWidth: 160 }}>
                Timeout (ms)
                <input
                  className="ucp-cmd-input"
                  type="number"
                  min={100}
                  step={100}
                  value={scpiTimeoutMs}
                  onChange={(e) => setScpiTimeoutMs(Math.max(100, Number(e.target.value) || 3000))}
                />
              </label>
              <label style={{ minWidth: 260, flex: 1 }}>
                Recent commands
                <select
                  className="ucp-cmd-input"
                  value=""
                  onChange={(e) => {
                    if (e.target.value) {
                      setScpiCommand(e.target.value);
                    }
                  }}
                >
                  <option value="">Select recent command…</option>
                  {scpiHistory.map((entry) => (
                    <option key={entry} value={entry}>{entry}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="ucp-cmd-row">
              <input
                className="ucp-cmd-input"
                value={scpiCommand}
                onChange={(e) => setScpiCommand(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void runScpiCommand(); }}
                placeholder="Enter SCPI command…"
              />
              <button
                className="ucp-btn"
                onClick={runScpiCommand}
                disabled={scpiRunning || !session.connected}
              >
                {scpiRunning ? "Sending…" : "Send"}
              </button>
            </div>
            {scpiError && <div className="ucp-msg error">{scpiError}</div>}
            {scpiResult && (
              <pre className="ucp-output">
                {JSON.stringify(scpiResult, null, 2)}
              </pre>
            )}
          </div>
        </Section>

        {/* ============================================================
            External Storage Browser – absolute bottom
            ============================================================ */}
        <Section icon="⇅" title="External Storage Browser" defaultOpen={false}>
          <div className="ucp-row" style={{ marginBottom: 10 }}>
            <div className="ucp-field" style={{ minWidth: 180 }}>
              <label>Protocol</label>
              <select value={transferProtocol} onChange={(e) => setTransferProtocol(e.target.value as TransferProtocol)}>
                <option value="ftp">FTP</option>
                <option value="smb">SMB/Samba (mapped folder)</option>
                <option value="mapped_folder">Local mapped folder</option>
                <option value="manual_usb">Manual USB workflow</option>
              </select>
            </div>
            <div className="ucp-field" style={{ minWidth: 180 }}>
              <label>Instrument IP / host</label>
              <input value={transferHost} onChange={(e) => setTransferHost(e.target.value)} placeholder="192.168.1.50" />
            </div>
            <div className="ucp-field" style={{ minWidth: 140 }}>
              <label>Username</label>
              <input value={transferUser} onChange={(e) => setTransferUser(e.target.value)} />
            </div>
            <div className="ucp-field" style={{ minWidth: 140 }}>
              <label>Password</label>
              <input type="password" value={transferPassword} onChange={(e) => setTransferPassword(e.target.value)} />
            </div>
          </div>

          <div className="ucp-row" style={{ marginBottom: 10 }}>
            <div className="ucp-field" style={{ flex: 1 }}>
              <label>Remote directory</label>
              <input value={transferRemoteDir} onChange={(e) => setTransferRemoteDir(e.target.value)} placeholder="/var/user/" />
            </div>
            <div className="ucp-field" style={{ flex: 1 }}>
              <label>Mapped folder root (SMB/mapped mode)</label>
              <input value={transferMappedRoot} onChange={(e) => setTransferMappedRoot(e.target.value)} placeholder="W:\\ or \\host\\user" />
            </div>
          </div>

          <div className="ucp-row" style={{ marginBottom: 10 }}>
            <button className="ucp-btn secondary" onClick={testTransferConnection} disabled={transferBusy}>Test connection</button>
            <button className="ucp-btn secondary" onClick={runTransferPreflight} disabled={transferBusy}>Run checklist</button>
            <button className="ucp-btn" onClick={() => refreshTransferFiles(false)} disabled={transferBusy}>Refresh remote files</button>
            <button className="ucp-btn" onClick={() => refreshTransferFiles(true)} disabled={transferBusy}>Refresh OSI dropdown</button>
            <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-dim)" }}>Status: {transferStatus}</div>
          </div>

          {transferUser === "instrument" && transferPassword === "instrument" && (
            <div className="ucp-msg info" style={{ marginBottom: 10 }}>
              The AREG factory default FTP/Samba credentials are in use (instrument/instrument). The manual recommends changing this password before connecting the instrument to a network.
            </div>
          )}

          <div className="ucp-row" style={{ marginBottom: 10 }}>
            <div className="ucp-field" style={{ minWidth: 150 }}>
              <label>File filter</label>
              <select value={transferFilter} onChange={(e) => setTransferFilter(e.target.value as FileFilterType)}>
                <option value="all">All files</option>
                <option value="osi">.osi</option>
                <option value="scpi">.scpi</option>
                <option value="txt">.txt</option>
                <option value="csv">.csv</option>
                <option value="custom">custom</option>
              </select>
            </div>
            {transferFilter === "custom" && (
              <div className="ucp-field" style={{ minWidth: 140 }}>
                <label>Custom extension</label>
                <input value={transferCustomFilter} onChange={(e) => setTransferCustomFilter(e.target.value)} placeholder=".bin" />
              </div>
            )}
            <div className="ucp-field" style={{ minWidth: 180 }}>
              <label>Create remote folder</label>
              <input value={transferNewFolder} onChange={(e) => setTransferNewFolder(e.target.value)} placeholder="/var/user/new_dir" />
            </div>
            <button className="ucp-btn secondary" onClick={createTransferDirectory} disabled={transferBusy}>Create folder</button>
          </div>

          <div className="ucp-row" style={{ marginBottom: 10 }}>
            <div className="ucp-upload-area" style={{ flex: 1 }}>
              <input id="transfer-upload-file" type="file" onChange={(e) => setTransferLocalFile(e.target.files?.[0] ?? null)} />
              <label className="ucp-upload-label" htmlFor="transfer-upload-file">Choose local file</label>
              <span className="ucp-selected-file">{transferLocalFile ? transferLocalFile.name : "No local file selected"}</span>
            </div>
            <button className="ucp-btn" onClick={uploadTransferFile} disabled={transferBusy || !transferLocalFile}>Upload</button>
          </div>

          <div className="ucp-row" style={{ marginBottom: 10 }}>
            <div className="ucp-field" style={{ flex: 1 }}>
              <label>Download local directory</label>
              <input value={transferDownloadDir} onChange={(e) => setTransferDownloadDir(e.target.value)} placeholder="C:/temp" />
            </div>
            <div className="ucp-field" style={{ flex: 1 }}>
              <label>Scenario workspace directory</label>
              <input value={transferWorkspaceDir} onChange={(e) => setTransferWorkspaceDir(e.target.value)} placeholder="./scenarios" />
            </div>
            <button className="ucp-btn" onClick={downloadTransferFile} disabled={transferBusy || !transferSelectedPath}>Download</button>
            <button className="ucp-btn" onClick={importScenarioToWorkspace} disabled={transferBusy || !transferSelectedPath || !transferSelectedPath.toLowerCase().endsWith(".osi")}>Import To Workspace</button>
            <div className="ucp-field" style={{ minWidth: 160 }}>
              <label>Rename selected to</label>
              <input value={transferRenameTo} onChange={(e) => setTransferRenameTo(e.target.value)} placeholder="new_name.osi" />
            </div>
            <button className="ucp-btn secondary" onClick={renameTransferFile} disabled={transferBusy || !transferSelectedPath}>Rename</button>
            <button className="ucp-btn secondary danger" onClick={deleteTransferFile} disabled={transferBusy || !transferSelectedPath}>Delete</button>
          </div>

          <div className="ucp-log-list" style={{ marginBottom: 10 }}>
            {transferFiles.length === 0 ? (
              <div className="ucp-empty-state">No files listed. Run connection test and refresh.</div>
            ) : (
              transferFiles.map((f) => (
                <div
                  key={f.remote_path}
                  className={`ucp-log-entry ${transferSelectedPath === f.remote_path ? "ok" : ""}`}
                  onClick={() => setTransferSelectedPath(f.remote_path)}
                  style={{ cursor: "pointer" }}
                >
                  <span className="ucp-log-ts">{f.modified_time ?? "-"}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="ucp-log-cmd">{f.name}</div>
                    <div className="ucp-log-response">{f.remote_path}</div>
                  </div>
                  <span className="ucp-log-type write">{f.is_directory ? "dir" : (f.size ?? 0) + " B"}</span>
                </div>
              ))
            )}
          </div>

          {transferError && <div className="ucp-msg error" style={{ marginBottom: 8 }}>{transferError}</div>}
          {transferWarnings.length > 0 && (
            <div className="ucp-msg info" style={{ marginBottom: 8 }}>{transferWarnings.join(" | ")}</div>
          )}
          {transferLikelyCauses.length > 0 && (
            <div className="ucp-msg info" style={{ marginBottom: 8 }}>
              Likely causes: {transferLikelyCauses.join(" | ")}
            </div>
          )}

          {transferChecklist.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Pre-flight checklist</div>
              {transferChecklist.map((item, i) => (
                <div key={i} className="ucp-empty-state">[{item.status.toUpperCase()}] {item.name}</div>
              ))}
            </div>
          )}

          <details>
            <summary style={{ cursor: "pointer", color: "var(--text-muted)", fontSize: 13 }}>AREG file transfer setup help</summary>
            <div className="ucp-empty-state" style={{ marginTop: 8 }}>
              <div style={{ fontWeight: 600 }}>FTP setup</div>
              {transferHelp.ftp.map((line, i) => <div key={`ftp-${i}`}>{i + 1}. {line}</div>)}
              <div style={{ fontWeight: 600, marginTop: 8 }}>SMB setup</div>
              {transferHelp.smb.map((line, i) => <div key={`smb-${i}`}>{i + 1}. {line}</div>)}
              <div style={{ fontWeight: 600, marginTop: 8 }}>USB setup</div>
              {transferHelp.usb.map((line, i) => <div key={`usb-${i}`}>{i + 1}. {line}</div>)}
            </div>
          </details>

          {transferProtocol === "manual_usb" && (
            <div className="ucp-msg info" style={{ marginTop: 8 }}>
              Manual USB workflow: enable USB storage and Volatile Mode on AREG, copy files via instrument File Manager from /usb/ to /var/user/, then refresh OSI list.
            </div>
          )}
        </Section>

      </div>
    </div>
  );
}
