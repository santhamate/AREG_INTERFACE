import { useMemo, useRef, useState } from "react";
import "./ScenarioSweepPanel.css";
import {
  defaultScenarioSweepConfig,
  type ScenarioSweepConfig,
  type SweepExecutionMode,
  type SpeedUnit,
  type DirectionMode,
  type SweepReplayMode,
  type ToleranceMode,
  validateScenarioSweepConfig,
} from "../sweep/ScenarioSweepConfig";
import {
  buildSpeedSweepCases,
  speedToMps,
  mpsToUnit,
  type SpeedStepCase,
} from "../sweep/ScenarioSweepGenerator";
import {
  ScenarioSweepResultStore,
  type SweepResultRow,
} from "../sweep/ScenarioSweepResultStore";
import { ScenarioSweepRunner, type SweepRunnerState } from "../sweep/ScenarioSweepRunner";
import { SpeedComparator } from "../sweep/SpeedComparator";

const API_BASE = "http://127.0.0.1:8000/api";
const PREPARED_SWEEP_STORAGE_KEY = "areg.preparedSpeedSweep";
const AREG_POSITION_MIN_MS = 0;
const AREG_POSITION_MAX_MS = 12000;
const SWEEP_POLL_INTERVAL_MS = 700;

type StatusTag = "not_started" | "running" | "completed" | "warning" | "failed";

interface SweepPanelProps {
  connected: boolean;
  mode?: "full" | "speed-sweep";
}

interface RadarComparisonConfig {
  enabled: boolean;
  ip: string;
  port: number;
  packetFormat: "hex_raw";
  expectedSpeed: number | null;
  measuredSpeed: number | null;
  speedError: number | null;
  toleranceMode: ToleranceMode;
}

const resultStore = new ScenarioSweepResultStore();

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function toCsv(rows: SweepResultRow[]): string {
  const headers = [
    "index", "speed", "speed_unit", "repeat", "scenario_file", "scenario_path",
    "status", "areg_load_status", "playback_status", "progress", "current_position",
    "start_timestamp", "end_timestamp", "measured_radar_speed", "pass_fail", "error", "notes",
  ];
  const lines = rows.map((row) => [
    row.index,
    row.speed,
    row.speedUnit,
    row.repeatIndex,
    row.filename,
    row.aregPath,
    row.status,
    row.aregLoadStatus ?? "",
    row.playbackStatus ?? "",
    row.progress ?? "",
    row.currentPosition ?? "",
    row.startTimestamp ?? "",
    row.endTimestamp ?? "",
    row.measuredRadarSpeed ?? "",
    row.passFail,
    row.error ?? "",
    row.notes,
  ].map((v) => `"${String(v).replace(/"/g, "\"\"")}"`).join(","));

  return `${headers.join(",")}\n${lines.join("\n")}`;
}

function downloadTextFile(filename: string, text: string, type: string): void {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function formatStateTag(status: SweepResultRow["status"]): StatusTag {
  if (status === "failed") return "failed";
  if (status === "playing" || status === "loaded") return "running";
  if (status === "completed") return "completed";
  if (status === "uploaded" || status === "generated") return "warning";
  return "not_started";
}

function speedValueToKmh(value: number, unit: SpeedUnit): number {
  return mpsToUnit(speedToMps(value, unit), "kmh");
}

function persistPreparedSweep(cases: SpeedStepCase[], unit: SpeedUnit): void {
  const payload = {
    timestamp: new Date().toISOString(),
    count: cases.length,
    scenarios: cases.map((c, i) => ({
      index: i + 1,
      filename: c.filename,
      aregPath: c.aregPath,
      targetKmh: speedValueToKmh(c.expectedDisplaySpeed, unit),
    })),
  };
  localStorage.setItem(PREPARED_SWEEP_STORAGE_KEY, JSON.stringify(payload));
}

export default function ScenarioSweepPanel({ connected, mode = "full" }: SweepPanelProps) {
  const speedSweepOnly = mode === "speed-sweep";
  const [config, setConfig] = useState<ScenarioSweepConfig>(defaultScenarioSweepConfig());
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [rows, setRows] = useState<SweepResultRow[]>([]);
  const [speedCases, setSpeedCases] = useState<SpeedStepCase[]>([]);
  const [runner] = useState(() => new ScenarioSweepRunner());
  const [runnerState, setRunnerState] = useState<SweepRunnerState>(runner.state);
  const [messages, setMessages] = useState<string[]>([]);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [selectedRowIds, setSelectedRowIds] = useState<Record<string, boolean>>({});
  const [fromIndex, setFromIndex] = useState(1);
  const [busy, setBusy] = useState(false);
  const [currentSweepSpeedLabel, setCurrentSweepSpeedLabel] = useState<string>("-");
  const [currentRowId, setCurrentRowId] = useState<string | null>(null);
  const [radarConfig, setRadarConfig] = useState<RadarComparisonConfig>({
    enabled: false,
    ip: "127.0.0.1",
    port: 5000,
    packetFormat: "hex_raw",
    expectedSpeed: null,
    measuredSpeed: null,
    speedError: null,
    toleranceMode: "fixed_kmh",
  });

  const controlRef = useRef({
    stopRequested: false,
    pauseRequested: false,
    skipRequested: false,
    retryRequested: false,
  });

  const rowIndexRef = useRef(-1);
  const scenarioDurationByFilenameRef = useRef<Record<string, number>>({});
  const comparator = useMemo(() => new SpeedComparator(), []);
  const distanceSpanM = Math.abs(config.endPositionM - config.startPositionM);

  const getScenarioDurationMsForFilename = (filename: string): number => {
    const known = scenarioDurationByFilenameRef.current[filename];
    if (Number.isFinite(known) && (known as number) > 0) {
      return known as number;
    }
    return Math.max(1000, config.commandTimeoutMs);
  };

  const transition = (next: SweepRunnerState, reason: string) => {
    runner.transition(next, reason);
    setRunnerState(next);
    setMessages((prev) => [`${new Date().toISOString()} ${reason}`, ...prev].slice(0, 500));
  };

  const updateRows = (next: SweepResultRow[]) => {
    resultStore.setRows(next);
    setRows(next);
  };

  const patchRow = (rowId: string, patch: Partial<SweepResultRow>) => {
    resultStore.updateRow(rowId, patch);
    setRows([...resultStore.getRows()]);
  };

  const scpiSend = async (command: string, timeoutMs = config.commandTimeoutMs) => {
    const r = await fetch(`${API_BASE}/scpi/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, timeout_ms: timeoutMs }),
    });
    if (!r.ok) throw new Error(`SCPI failed (${r.status})`);
    return r.json();
  };

  const applyDynamicScenarioMode = async () => {
    await scpiSend("SOURce1:AREGenerator:OSETup:MODE DYNamic");
    await scpiSend("SOURce1:AREGenerator:OSETup:SOURce SCENario");
    await scpiSend("SOURce1:AREGenerator:OSETup:APPLy");
  };

  const generatePreviewRows = (cases: SpeedStepCase[]): SweepResultRow[] => {
    let index = 1;
    const next: SweepResultRow[] = [];
    for (const c of cases) {
      for (let rep = 1; rep <= config.repeatsPerSpeed; rep += 1) {
        next.push({
          rowId: `${c.filename}-${rep}`,
          index,
          speed: c.expectedDisplaySpeed,
          speedUnit: config.speedUnit,
          repeatIndex: rep,
          filename: c.filename,
          aregPath: c.aregPath,
          status: "not_generated",
          aregLoadStatus: null,
          playbackStatus: null,
          progress: null,
          currentPosition: null,
          startTimestamp: null,
          endTimestamp: null,
          measuredRadarSpeed: null,
          passFail: "pending",
          notes: "",
          error: null,
          progressSamples: [],
          actualPositionSamples: [],
        });
        index += 1;
      }
    }
    return next;
  };

  const validateAndBuild = (): { ok: boolean; cases: SpeedStepCase[] } => {
    const errs = validateScenarioSweepConfig(config);
    const cases = buildSpeedSweepCases(
      config.startSpeed,
      config.stopSpeed,
      config.stepSize,
      config.speedUnit,
      config.directionMode,
      config.filenamePrefix,
      config.targetAregFolder,
    );

    if (cases.length === 0) {
      errs.push("Generated speed list is empty. Check start/stop/step configuration.");
    }
    if (cases.some((c) => Math.abs(c.signedSpeedMps) < 1e-9)) {
      errs.push("Zero speed is not supported when start/end positions are used to derive scenario duration.");
    }
    if (!connected && config.executionMode !== "generate_only") {
      errs.push("AREG must be connected for upload/run modes.");
    }

    setValidationErrors(errs);
    return { ok: errs.length === 0, cases };
  };

  const prepareSweep = async () => {
    const { ok, cases } = validateAndBuild();
    if (!ok) return;

    setBusy(true);
    setMessages([]);
    setSpeedCases(cases);
    scenarioDurationByFilenameRef.current = {};
    const previewRows = generatePreviewRows(cases);
    updateRows(previewRows);

    try {
      transition("GENERATING", "State IDLE -> GENERATING");

      const localPathByFilename: Record<string, string> = {};
      for (const c of cases) {
        const genResp = await fetch(`${API_BASE}/generator/range-sweep`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            output_dir: "./scenarios",
            output_filename: c.filename,
            sensor_id: 1,
            update_interval_s: config.updateIntervalMs / 1000,
            start_range_m: config.startPositionM,
            stop_range_m: config.endPositionM,
            radial_velocity_mps: c.signedSpeedMps,
            rcs_dbsm: 10,
            azimuth_deg: 0,
            elevation_deg: 0,
            scenario_name: c.filename.replace(/\.osi$/i, ""),
          }),
        });
        const genData = await genResp.json();
        if (!genResp.ok || !genData.ok || !genData.file_path) {
          throw new Error(`Generation failed for ${c.filename}: ${genData.error ?? genResp.statusText}`);
        }
        localPathByFilename[c.filename] = String(genData.file_path);
        if (typeof genData.duration_s === "number" && genData.duration_s > 0) {
          scenarioDurationByFilenameRef.current[c.filename] = Math.max(1, Math.round(genData.duration_s * 1000));
        }
        const next = resultStore.getRows().map((row) => (
          row.filename === c.filename ? { ...row, status: "generated" as const } : row
        ));
        updateRows(next);
      }

      if (config.executionMode !== "generate_only") {
        transition("UPLOADING", "State GENERATING -> UPLOADING");
        for (const c of cases) {
          const uploadResp = await fetch(`${API_BASE}/device/files/upload`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              local_path: localPathByFilename[c.filename],
              remote_path: c.aregPath,
              preferred_directory: config.targetAregFolder,
            }),
          });
          const uploadData = await uploadResp.json();
          if (!uploadResp.ok || !uploadData.ok) {
            throw new Error(`Upload failed for ${c.filename}: ${uploadData.error ?? uploadResp.statusText}`);
          }

          const next = resultStore.getRows().map((row) => (
            row.filename === c.filename ? { ...row, status: "uploaded" as const } : row
          ));
          updateRows(next);
        }

        await applyDynamicScenarioMode();

        await fetch(`${API_BASE}/scenario/scan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ force_refresh: true }),
        });
      }

      transition("READY", "State preparation complete -> READY");

      // Make prepared sweep available to validation page without rescanning device scenarios.
      persistPreparedSweep(cases, config.speedUnit);

      if (config.executionMode === "generate_upload_run") {
        void startSweep({ selectedOnly: false, fromRow: 1 });
      }
    } catch (e) {
      transition("FAILED", "State -> FAILED during prepare");
      setMessages((prev) => [`Prepare error: ${e instanceof Error ? e.message : "Unknown error"}`, ...prev]);
    } finally {
      setBusy(false);
    }
  };

  const pollPlayback = async (row: SweepResultRow, rowStopPositionMs: number): Promise<{ ok: boolean; error?: string }> => {
    const startMs = Date.now();
    const timeoutMs = Math.max(rowStopPositionMs + config.commandTimeoutMs, config.commandTimeoutMs + 1000);
    const progressSamples = [...row.progressSamples];
    const positionSamples = [...row.actualPositionSamples];

    while (Date.now() - startMs < timeoutMs) {
      if (controlRef.current.stopRequested) {
        return { ok: false, error: "Stopped by user" };
      }
      if (controlRef.current.skipRequested) {
        controlRef.current.skipRequested = false;
        await fetch(`${API_BASE}/scenario/stop`, { method: "POST" });
        return { ok: false, error: "Skipped by user" };
      }

      while (controlRef.current.pauseRequested) {
        transition("PAUSED", "Runner paused by user");
        await sleep(150);
        if (controlRef.current.stopRequested) {
          return { ok: false, error: "Stopped by user" };
        }
      }

      const [statusResp, positionResp] = await Promise.all([
        fetch(`${API_BASE}/scenario/status`),
        fetch(`${API_BASE}/scenario/position/actual`),
      ]);

      const statusData = await statusResp.json();
      const positionData = await positionResp.json();

      const nowIso = new Date().toISOString();
      const progress = row.progress;
      const position = typeof positionData.position === "number" ? positionData.position : null;
      const playbackState = String(statusData.state ?? "unknown");

      progressSamples.push({ t: Date.now(), value: progress });
      positionSamples.push({ t: Date.now(), value: position });

      patchRow(row.rowId, {
        status: "playing",
        playbackStatus: playbackState,
        progress,
        currentPosition: position,
        progressSamples,
        actualPositionSamples: positionSamples,
        notes: `Last poll ${nowIso}`,
      });

      const completionByStatus = ["stopped", "loaded", "paused", "not_loaded"].includes(playbackState);
      const completionByPosition = typeof position === "number" && position >= rowStopPositionMs;

      if (completionByStatus || completionByPosition) {
        return { ok: true };
      }

      await sleep(SWEEP_POLL_INTERVAL_MS);
    }

    return { ok: false, error: "Scenario playback timeout" };
  };

  const getExecutionRows = (selectedOnly: boolean, fromRow: number): SweepResultRow[] => {
    const sorted = [...resultStore.getRows()].sort((a, b) => a.index - b.index);
    const fromFiltered = sorted.filter((r) => r.index >= fromRow);
    if (!selectedOnly) return fromFiltered;
    return fromFiltered.filter((r) => selectedRowIds[r.rowId]);
  };

  const startSweep = async (opts?: { selectedOnly: boolean; fromRow: number }) => {
    const selectedOnly = opts?.selectedOnly ?? false;
    const fromRow = opts?.fromRow ?? 1;

    if (!connected) {
      setValidationErrors(["AREG must be connected to run sweep."]);
      return;
    }

    const executionRows = getExecutionRows(selectedOnly, fromRow);
    if (executionRows.length === 0) {
      setValidationErrors(["No rows selected for execution."]);
      return;
    }

    setBusy(true);
    controlRef.current.stopRequested = false;
    controlRef.current.pauseRequested = false;

    try {
      transition("RUNNING", "State READY -> RUNNING");

      let previousFilename: string | null = null;
      for (let i = 0; i < executionRows.length; i += 1) {
        const row = executionRows[i];
        rowIndexRef.current = i;
        setCurrentRowId(row.rowId);
        setCurrentSweepSpeedLabel(`${row.speed.toFixed(2)} ${row.speedUnit}`);

        if (controlRef.current.stopRequested) {
          transition("STOPPED_BY_USER", "State RUNNING -> STOPPED_BY_USER");
          await fetch(`${API_BASE}/scenario/stop`, { method: "POST" });
          break;
        }

        transition("LOADING_SCENARIO", `Loading ${row.filename}`);
        const rowDurationMs = getScenarioDurationMsForFilename(row.filename);
        const rowStopPositionMs = Math.min(AREG_POSITION_MAX_MS, Math.max(AREG_POSITION_MIN_MS, rowDurationMs));
        if (rowStopPositionMs !== rowDurationMs) {
          setMessages((prev) => [
            `${new Date().toISOString()} Stop position clamped to ${rowStopPositionMs} ms (requested ${rowDurationMs} ms)`,
            ...prev,
          ].slice(0, 500));
        }
        if (row.filename !== previousFilename) {
          const loadResp = await fetch(`${API_BASE}/scenario/load`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scenario_name: row.aregPath, replay_mode: config.replayMode }),
          });
          const loadData = await loadResp.json();
          if (!loadResp.ok || !loadData.ok) {
            patchRow(row.rowId, { status: "failed", error: loadData.message ?? "Load failed" });
            transition("FAILED", `Failed loading ${row.filename}`);
            continue;
          }

          await fetch(`${API_BASE}/scenario/replay-mode`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: config.replayMode as SweepReplayMode }),
          });
          await fetch(`${API_BASE}/scenario/position/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ value: AREG_POSITION_MIN_MS }),
          });
          await fetch(`${API_BASE}/scenario/position/stop`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ value: rowStopPositionMs }),
          });
        }

        patchRow(row.rowId, {
          status: "loaded",
          aregLoadStatus: "loaded",
          startTimestamp: new Date().toISOString(),
          error: null,
        });

        await fetch(`${API_BASE}/scenario/reset`, { method: "POST" });

        transition("WAITING_FOR_COMPLETION", `Running row ${row.index}`);
        const playResp = await fetch(`${API_BASE}/scenario/play`, { method: "POST" });
        const playData = await playResp.json();
        if (!playResp.ok || !playData.ok) {
          patchRow(row.rowId, {
            status: "failed",
            error: playData.message ?? "Play failed",
            endTimestamp: new Date().toISOString(),
          });
          continue;
        }

        const result = await pollPlayback(row, rowStopPositionMs);
        if (!result.ok) {
          patchRow(row.rowId, {
            status: "failed",
            error: result.error ?? "Unknown playback error",
            endTimestamp: new Date().toISOString(),
            passFail: "fail",
          });

          if (controlRef.current.retryRequested) {
            controlRef.current.retryRequested = false;
            i -= 1;
            continue;
          }
        } else {
          patchRow(row.rowId, {
            status: "completed",
            endTimestamp: new Date().toISOString(),
            passFail: "pending",
            playbackStatus: "completed",
          });

          if (config.delayBeforeRadarReadMs > 0) {
            await sleep(config.delayBeforeRadarReadMs);
          }

          const expectedKmh = speedValueToKmh(row.speed, config.speedUnit);

          if (typeof row.measuredRadarSpeed === "number") {
            const cmp = comparator.compare(expectedKmh, row.measuredRadarSpeed, {
              toleranceMode: config.toleranceMode,
              fixedToleranceKmh: config.passFailTolerance,
              percentageTolerance: config.passFailTolerance,
            });
            patchRow(row.rowId, {
              passFail: cmp.passed ? "pass" : "fail",
              notes: `Speed error ${cmp.error.toFixed(2)} km/h (tol ${cmp.toleranceApplied.toFixed(2)})`,
            });
          }
        }

        const next = executionRows[i + 1];
        const sameScenarioNext = next?.filename === row.filename;
        previousFilename = row.filename;

        if (sameScenarioNext && config.delayBetweenRepeatsMs > 0) {
          transition("WAITING_BETWEEN_REPEATS", `Delay ${config.delayBetweenRepeatsMs} ms`);
          await sleep(config.delayBetweenRepeatsMs);
        } else if (!sameScenarioNext && config.delayBetweenScenariosMs > 0) {
          transition("WAITING_BETWEEN_SCENARIOS", `Delay ${config.delayBetweenScenariosMs} ms`);
          await sleep(config.delayBetweenScenariosMs);
        }
      }

      if (!controlRef.current.stopRequested) {
        transition("COMPLETED", "Sweep finished");
      }
      setCurrentRowId(null);
      setCurrentSweepSpeedLabel("-");
    } catch (e) {
      transition("FAILED", "Unhandled runner error");
      setMessages((prev) => [`Runner error: ${e instanceof Error ? e.message : "Unknown"}`, ...prev]);
    } finally {
      setBusy(false);
    }
  };

  const pauseSweep = () => {
    controlRef.current.pauseRequested = true;
    transition("PAUSED", "Pause requested by user");
  };

  const resumeSweep = () => {
    controlRef.current.pauseRequested = false;
    transition("RUNNING", "Resume requested by user");
  };

  const stopSweep = async () => {
    controlRef.current.stopRequested = true;
    controlRef.current.pauseRequested = false;
    await fetch(`${API_BASE}/scenario/stop`, { method: "POST" });
    transition("STOPPED_BY_USER", "Stop requested by user");
  };

  const resetSweep = async () => {
    controlRef.current.stopRequested = true;
    controlRef.current.pauseRequested = false;
    controlRef.current.skipRequested = false;
    controlRef.current.retryRequested = false;
    await fetch(`${API_BASE}/scenario/reset`, { method: "POST" });
    transition("IDLE", "Reset requested by user");
  };

  const skipCurrent = async () => {
    controlRef.current.skipRequested = true;
    await fetch(`${API_BASE}/scenario/stop`, { method: "POST" });
  };

  const retryCurrent = () => {
    controlRef.current.retryRequested = true;
  };

  const summary = useMemo(() => {
    const totalRepeats = rows.length;
    const completedRepeats = rows.filter((r) => r.status === "completed").length;
    const failedRepeats = rows.filter((r) => r.status === "failed").length;

    const bySpeed = new Map<string, SweepResultRow[]>();
    for (const row of rows) {
      const key = `${row.speed}_${row.speedUnit}`;
      const list = bySpeed.get(key) ?? [];
      list.push(row);
      bySpeed.set(key, list);
    }

    const unstable = Array.from(bySpeed.entries())
      .filter(([, group]) => group.some((g) => g.status === "failed" || g.passFail === "warning"))
      .map(([speed]) => speed);

    const measured = rows
      .filter((r) => typeof r.measuredRadarSpeed === "number")
      .map((r) => ({
        expected: r.speed,
        measured: r.measuredRadarSpeed as number,
        err: (r.measuredRadarSpeed as number) - r.speed,
      }));

    const avgAbsErr = measured.length > 0
      ? measured.reduce((sum, m) => sum + Math.abs(m.err), 0) / measured.length
      : null;

    const best = measured.length > 0
      ? measured.reduce((a, b) => Math.abs(a.err) < Math.abs(b.err) ? a : b)
      : null;

    const worst = measured.length > 0
      ? measured.reduce((a, b) => Math.abs(a.err) > Math.abs(b.err) ? a : b)
      : null;

    const failedSpeeds = Array.from(new Set(rows.filter((r) => r.status === "failed").map((r) => `${r.speed} ${r.speedUnit}`)));

    return {
      totalScenarios: speedCases.length,
      totalRepeats,
      completedRepeats,
      failedRepeats,
      unstable,
      best,
      worst,
      avgAbsErr,
      failedSpeeds,
    };
  }, [rows, speedCases.length]);

  const exportJson = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      config,
      speed_cases: speedCases,
      transitions: runner.transitions,
      rows,
      radar: radarConfig,
    };
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    downloadTextFile(`areg_speed_sweep_results_${ts}.json`, JSON.stringify(payload, null, 2), "application/json");
  };

  const exportCsv = () => {
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    downloadTextFile(`areg_speed_sweep_results_${ts}.csv`, toCsv(rows), "text/csv");
  };

  const toggleSelectRow = (rowId: string) => {
    setSelectedRowIds((prev) => ({ ...prev, [rowId]: !prev[rowId] }));
  };

  const setConfigNum = (key: keyof ScenarioSweepConfig, value: number) => {
    setConfig((prev) => ({ ...prev, [key]: Number.isFinite(value) ? value : 0 }));
  };

  const applyQuickPreset = (preset: "urban" | "highway" | "extended") => {
    if (preset === "urban") {
      setConfig((p) => ({
        ...p,
        startSpeed: 5,
        stopSpeed: 60,
        stepSize: 5,
        speedUnit: "kmh",
        startPositionM: 120,
        endPositionM: 20,
        repeatsPerSpeed: 1,
        executionMode: "generate_upload_run",
      }));
      return;
    }
    if (preset === "highway") {
      setConfig((p) => ({
        ...p,
        startSpeed: 20,
        stopSpeed: 160,
        stepSize: 10,
        speedUnit: "kmh",
        startPositionM: 160,
        endPositionM: 20,
        repeatsPerSpeed: 1,
        executionMode: "generate_upload_run",
      }));
      return;
    }
    setConfig((p) => ({
      ...p,
      startSpeed: 10,
      stopSpeed: 220,
      stepSize: 10,
      speedUnit: "kmh",
      startPositionM: 240,
      endPositionM: 20,
      repeatsPerSpeed: 1,
      executionMode: "generate_upload_run",
    }));
  };

  const prepareAndRun = async () => {
    await prepareSweep();
    if (controlRef.current.stopRequested) return;
    if (config.executionMode === "generate_upload_run") return;
    await startSweep({ selectedOnly: false, fromRow: Math.max(1, fromIndex) });
  };

  return (
    <div className="sweep-root">
      <div className="sweep-toolbar">
        <div className="sweep-state">
          {speedSweepOnly ? "Speed Sweep" : "Automated Scenario Sweep"} State: <strong>{runnerState}</strong>
        </div>
        <div className="sweep-state">Current simulated speed: <strong>{currentSweepSpeedLabel}</strong></div>
        <div className="sweep-actions">
          <button className="ucp-btn" onClick={prepareSweep} disabled={busy}>Prepare Sweep</button>
          {!speedSweepOnly && <button className="ucp-btn" onClick={() => startSweep({ selectedOnly: false, fromRow: fromIndex })} disabled={busy}>Start Sweep</button>}
          {speedSweepOnly && <button className="ucp-btn" onClick={() => void prepareAndRun()} disabled={busy}>Prepare + Run</button>}
          {!speedSweepOnly && (
            <button className="ucp-btn secondary" onClick={() => startSweep({ selectedOnly: true, fromRow: fromIndex })} disabled={busy}>Run Selected Rows</button>
          )}
          {!speedSweepOnly && <button className="ucp-btn secondary" onClick={pauseSweep}>Pause</button>}
          {!speedSweepOnly && <button className="ucp-btn secondary" onClick={resumeSweep}>Resume</button>}
          <button className="ucp-btn secondary danger" onClick={() => void stopSweep()}>Stop</button>
          <button className="ucp-btn secondary" onClick={() => void resetSweep()}>Reset</button>
          {!speedSweepOnly && <button className="ucp-btn secondary" onClick={() => void skipCurrent()}>Skip Current</button>}
          {!speedSweepOnly && <button className="ucp-btn secondary" onClick={retryCurrent}>Retry Current</button>}
        </div>
      </div>

      {speedSweepOnly && (
        <div className="sweep-quick-panel">
          <div className="sweep-quick-title">Quick Setup</div>
          <div className="sweep-actions">
            <button className="ucp-btn secondary" onClick={() => applyQuickPreset("urban")}>Urban</button>
            <button className="ucp-btn secondary" onClick={() => applyQuickPreset("highway")}>Highway</button>
            <button className="ucp-btn secondary" onClick={() => applyQuickPreset("extended")}>Extended</button>
          </div>
          <div className="sweep-grid-simple">
            <label className="ucp-field">
              <span>Start speed</span>
              <input type="number" value={config.startSpeed} onChange={(e) => setConfigNum("startSpeed", Number(e.target.value))} />
            </label>
            <label className="ucp-field">
              <span>Stop speed</span>
              <input type="number" value={config.stopSpeed} onChange={(e) => setConfigNum("stopSpeed", Number(e.target.value))} />
            </label>
            <label className="ucp-field">
              <span>Step size</span>
              <input type="number" value={config.stepSize} onChange={(e) => setConfigNum("stepSize", Number(e.target.value))} />
            </label>
            <label className="ucp-field">
              <span>Unit</span>
              <select value={config.speedUnit} onChange={(e) => setConfig((p) => ({ ...p, speedUnit: e.target.value as SpeedUnit }))}>
                <option value="kmh">km/h</option>
                <option value="ms">m/s</option>
                <option value="mph">mph</option>
              </select>
            </label>
            <label className="ucp-field">
              <span>Start position (m)</span>
              <input type="number" min={0} value={config.startPositionM} onChange={(e) => setConfigNum("startPositionM", Number(e.target.value))} />
            </label>
            <label className="ucp-field">
              <span>Stop position (m)</span>
              <input type="number" min={0} value={config.endPositionM} onChange={(e) => setConfigNum("endPositionM", Number(e.target.value))} />
            </label>
            <label className="ucp-field">
              <span>Execution</span>
              <select value={config.executionMode} onChange={(e) => setConfig((p) => ({ ...p, executionMode: e.target.value as SweepExecutionMode }))}>
                <option value="generate_only">Generate only</option>
                <option value="generate_upload">Generate + upload</option>
                <option value="generate_upload_run">Generate + upload + run</option>
              </select>
            </label>
            <label className="ucp-field">
              <span>Repeats</span>
              <input type="number" min={1} value={config.repeatsPerSpeed} onChange={(e) => setConfigNum("repeatsPerSpeed", Number(e.target.value))} />
            </label>
          </div>
          <button className="ucp-btn secondary" onClick={() => setShowAdvanced((v) => !v)}>
            {showAdvanced ? "Hide Advanced" : "Show Advanced"}
          </button>
        </div>
      )}

      {(!speedSweepOnly || showAdvanced) && (
      <div className="sweep-grid-2">
        <label className="ucp-field">
          <span>Start speed</span>
          <input type="number" value={config.startSpeed} onChange={(e) => setConfigNum("startSpeed", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>Stop speed</span>
          <input type="number" value={config.stopSpeed} onChange={(e) => setConfigNum("stopSpeed", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>Step size</span>
          <input type="number" value={config.stepSize} onChange={(e) => setConfigNum("stepSize", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>Speed unit</span>
          <select value={config.speedUnit} onChange={(e) => setConfig((p) => ({ ...p, speedUnit: e.target.value as SpeedUnit }))}>
            <option value="kmh">km/h</option>
            <option value="ms">m/s</option>
            <option value="mph">mph</option>
          </select>
        </label>
        <label className="ucp-field">
          <span>Direction/sign</span>
          <select value={config.directionMode} onChange={(e) => setConfig((p) => ({ ...p, directionMode: e.target.value as DirectionMode }))}>
            <option value="approaching">approaching radar</option>
            <option value="away">moving away from radar</option>
            <option value="signed">signed speed mode</option>
          </select>
        </label>
        <label className="ucp-field">
          <span>Update interval (ms)</span>
          <input type="number" min={1} value={config.updateIntervalMs} onChange={(e) => setConfigNum("updateIntervalMs", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>Start position (m)</span>
          <input type="number" min={0} value={config.startPositionM} onChange={(e) => setConfigNum("startPositionM", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>End position (m)</span>
          <input type="number" min={0} value={config.endPositionM} onChange={(e) => setConfigNum("endPositionM", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>Distance span (m)</span>
          <input type="number" value={distanceSpanM} disabled />
        </label>
        <label className="ucp-field">
          <span>Repeats per step</span>
          <input type="number" min={1} value={config.repeatsPerSpeed} onChange={(e) => setConfigNum("repeatsPerSpeed", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>Delay between repeats (ms)</span>
          <input type="number" min={0} value={config.delayBetweenRepeatsMs} onChange={(e) => setConfigNum("delayBetweenRepeatsMs", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>Delay between scenarios (ms)</span>
          <input type="number" min={0} value={config.delayBetweenScenariosMs} onChange={(e) => setConfigNum("delayBetweenScenariosMs", Number(e.target.value))} />
        </label>
        {!speedSweepOnly && (
          <label className="ucp-field">
            <span>Delay before radar read (ms)</span>
            <input type="number" min={0} value={config.delayBeforeRadarReadMs} onChange={(e) => setConfigNum("delayBeforeRadarReadMs", Number(e.target.value))} />
          </label>
        )}
        <label className="ucp-field">
          <span>Replay mode</span>
          <select value={config.replayMode} onChange={(e) => setConfig((p) => ({ ...p, replayMode: e.target.value as SweepReplayMode }))}>
            <option value="SINGle">Single</option>
            <option value="LOOP">Loop</option>
          </select>
        </label>
        <label className="ucp-field">
          <span>Target folder on AREG</span>
          <input value={config.targetAregFolder} onChange={(e) => setConfig((p) => ({ ...p, targetAregFolder: e.target.value }))} />
        </label>
        <label className="ucp-field">
          <span>Filename prefix</span>
          <input value={config.filenamePrefix} onChange={(e) => setConfig((p) => ({ ...p, filenamePrefix: e.target.value }))} />
        </label>
        <label className="ucp-field">
          <span>Overwrite generated files</span>
          <select value={config.overwriteExisting ? "yes" : "no"} onChange={(e) => setConfig((p) => ({ ...p, overwriteExisting: e.target.value === "yes" }))}>
            <option value="yes">yes</option>
            <option value="no">no</option>
          </select>
        </label>
        <label className="ucp-field">
          <span>Execution mode</span>
          <select value={config.executionMode} onChange={(e) => setConfig((p) => ({ ...p, executionMode: e.target.value as SweepExecutionMode }))}>
            <option value="generate_only">Generate only</option>
            <option value="generate_upload">Generate and upload</option>
            <option value="generate_upload_run">Generate upload and run</option>
          </select>
        </label>
        {!speedSweepOnly && (
          <label className="ucp-field">
            <span>Pass/fail tolerance</span>
            <input type="number" value={config.passFailTolerance} onChange={(e) => setConfigNum("passFailTolerance", Number(e.target.value))} />
          </label>
        )}
        {!speedSweepOnly && (
          <label className="ucp-field">
            <span>Tolerance mode</span>
            <select value={config.toleranceMode} onChange={(e) => setConfig((p) => ({ ...p, toleranceMode: e.target.value as ToleranceMode }))}>
              <option value="fixed_kmh">fixed km/h</option>
              <option value="percentage">percentage</option>
              <option value="custom_rule">custom rule</option>
            </select>
          </label>
        )}
        <label className="ucp-field">
          <span>Command timeout (ms)</span>
          <input type="number" min={100} value={config.commandTimeoutMs} onChange={(e) => setConfigNum("commandTimeoutMs", Number(e.target.value))} />
        </label>
        <label className="ucp-field">
          <span>Run from sequence index</span>
          <input type="number" min={1} value={fromIndex} onChange={(e) => setFromIndex(Math.max(1, Number(e.target.value) || 1))} />
        </label>
      </div>
      )}

      {validationErrors.length > 0 && (
        <div className="ucp-msg error">
          {validationErrors.map((e) => <div key={e}>{e}</div>)}
        </div>
      )}

      <div className="sweep-section-title">Speed List Preview / Result Table</div>
      <div className="sweep-table-wrap">
        <table className="sweep-table">
          <thead>
            <tr>
              {!speedSweepOnly && <th>Run</th>}
              <th>#</th>
              <th>Speed</th>
              <th>Repeat</th>
              <th>Status</th>
              {!speedSweepOnly && <th>Scenario File</th>}
              {!speedSweepOnly && <th>AREG Path</th>}
              {!speedSweepOnly && <th>AREG Load</th>}
              {!speedSweepOnly && <th>Playback</th>}
              {!speedSweepOnly && <th>Progress</th>}
              {!speedSweepOnly && <th>Position</th>}
              {!speedSweepOnly && <th>Measured Radar</th>}
              {!speedSweepOnly && <th>Pass/Fail</th>}
              {!speedSweepOnly && <th>Error</th>}
              {!speedSweepOnly && <th>Notes</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.rowId} className={`sweep-row-${formatStateTag(row.status)} ${currentRowId === row.rowId ? "sweep-row-current" : ""}`}>
                {!speedSweepOnly && (
                  <td>
                    <input type="checkbox" checked={!!selectedRowIds[row.rowId]} onChange={() => toggleSelectRow(row.rowId)} />
                  </td>
                )}
                <td>{row.index}</td>
                <td>{row.speed.toFixed(2)} {row.speedUnit}</td>
                <td>{row.repeatIndex}</td>
                <td>{row.status}</td>
                {!speedSweepOnly && <td>{row.filename}</td>}
                {!speedSweepOnly && <td>{row.aregPath}</td>}
                {!speedSweepOnly && <td>{row.aregLoadStatus ?? "-"}</td>}
                {!speedSweepOnly && <td>{row.playbackStatus ?? "-"}</td>}
                {!speedSweepOnly && <td>{row.progress ?? "-"}</td>}
                {!speedSweepOnly && <td>{row.currentPosition ?? "-"}</td>}
                {!speedSweepOnly && <td>{row.measuredRadarSpeed ?? "-"}</td>}
                {!speedSweepOnly && <td>{row.passFail}</td>}
                {!speedSweepOnly && <td>{row.error ?? "-"}</td>}
                {!speedSweepOnly && <td>{row.notes || "-"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!speedSweepOnly && (
      <>
      <div className="sweep-section-title">Radar Result Comparison</div>
      <div className="sweep-grid-2">
        <label className="ucp-field">
          <span>Radar TCP enabled</span>
          <select value={radarConfig.enabled ? "yes" : "no"} onChange={(e) => setRadarConfig((p) => ({ ...p, enabled: e.target.value === "yes" }))}>
            <option value="no">no</option>
            <option value="yes">yes</option>
          </select>
        </label>
        <label className="ucp-field">
          <span>Radar IP</span>
          <input value={radarConfig.ip} onChange={(e) => setRadarConfig((p) => ({ ...p, ip: e.target.value }))} />
        </label>
        <label className="ucp-field">
          <span>Radar TCP port</span>
          <input type="number" value={radarConfig.port} onChange={(e) => setRadarConfig((p) => ({ ...p, port: Number(e.target.value) || 0 }))} />
        </label>
        <label className="ucp-field">
          <span>Packet format</span>
          <select value={radarConfig.packetFormat} onChange={(e) => setRadarConfig((p) => ({ ...p, packetFormat: e.target.value as "hex_raw" }))}>
            <option value="hex_raw">hex/raw</option>
          </select>
        </label>
        <div className="ucp-empty-state sweep-placeholder">
          Radar decoder is intentionally not implemented yet. Placeholder architecture is ready (RadarTcpClient, RadarPacketDecoder, RadarMeasurementCollector, SpeedComparator).
        </div>
      </div>
      </>
      )}

      <div className="sweep-section-title">Summary</div>
      <div className="sweep-summary-grid">
        <div>Total scenarios: <strong>{summary.totalScenarios}</strong></div>
        <div>Total repeats: <strong>{summary.totalRepeats}</strong></div>
        <div>Completed repeats: <strong>{summary.completedRepeats}</strong></div>
        <div>Failed repeats: <strong>{summary.failedRepeats}</strong></div>
        <div>Unstable speed points: <strong>{summary.unstable.length}</strong></div>
        {!speedSweepOnly && <div>Average abs error: <strong>{summary.avgAbsErr != null ? `${summary.avgAbsErr.toFixed(3)} km/h` : "n/a"}</strong></div>}
        {!speedSweepOnly && <div>Best error: <strong>{summary.best ? summary.best.err.toFixed(3) : "n/a"}</strong></div>}
        {!speedSweepOnly && <div>Worst error: <strong>{summary.worst ? summary.worst.err.toFixed(3) : "n/a"}</strong></div>}
      </div>

      {summary.failedSpeeds.length > 0 && (
        <div className="ucp-msg info">Failed speeds: {summary.failedSpeeds.join(", ")}</div>
      )}

      {!speedSweepOnly && (
        <div className="sweep-actions" style={{ marginTop: 10 }}>
          <button className="ucp-btn secondary" onClick={exportCsv}>Export CSV</button>
          <button className="ucp-btn secondary" onClick={exportJson}>Export JSON</button>
        </div>
      )}

      <div className="sweep-section-title">State Transition Log</div>
      <div className="sweep-log-box">
        {messages.length === 0 ? "No state transitions yet." : messages.map((m) => <div key={m}>{m}</div>)}
      </div>
    </div>
  );
}
