export type SweepRowStatus =
  | "not_generated"
  | "generated"
  | "uploaded"
  | "loaded"
  | "playing"
  | "completed"
  | "failed";

export interface SweepProgressSample {
  t: number;
  value: number | null;
}

export interface SweepPositionSample {
  t: number;
  value: number | null;
}

export interface SweepResultRow {
  rowId: string;
  index: number;
  speed: number;
  speedUnit: string;
  repeatIndex: number;
  filename: string;
  aregPath: string;
  status: SweepRowStatus;
  aregLoadStatus: string | null;
  playbackStatus: string | null;
  progress: number | null;
  currentPosition: number | null;
  startTimestamp: string | null;
  endTimestamp: string | null;
  measuredRadarSpeed: number | null;
  passFail: "pass" | "fail" | "warning" | "pending";
  notes: string;
  error: string | null;
  progressSamples: SweepProgressSample[];
  actualPositionSamples: SweepPositionSample[];
}

export class ScenarioSweepResultStore {
  private rows: SweepResultRow[] = [];

  setRows(rows: SweepResultRow[]): void {
    this.rows = rows;
  }

  getRows(): SweepResultRow[] {
    return this.rows;
  }

  updateRow(rowId: string, patch: Partial<SweepResultRow>): void {
    this.rows = this.rows.map((row) => (row.rowId === rowId ? { ...row, ...patch } : row));
  }
}
