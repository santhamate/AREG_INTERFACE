export type SweepRunnerState =
  | "IDLE"
  | "GENERATING"
  | "UPLOADING"
  | "READY"
  | "LOADING_SCENARIO"
  | "RUNNING"
  | "WAITING_FOR_COMPLETION"
  | "WAITING_BETWEEN_REPEATS"
  | "WAITING_BETWEEN_SCENARIOS"
  | "PAUSED"
  | "COMPLETED"
  | "FAILED"
  | "STOPPED_BY_USER";

export interface SweepStateTransition {
  at: string;
  from: SweepRunnerState;
  to: SweepRunnerState;
  reason: string;
}

export class ScenarioSweepRunner {
  private _state: SweepRunnerState = "IDLE";
  private _transitions: SweepStateTransition[] = [];

  get state(): SweepRunnerState {
    return this._state;
  }

  get transitions(): SweepStateTransition[] {
    return this._transitions;
  }

  transition(next: SweepRunnerState, reason: string): void {
    const from = this._state;
    this._state = next;
    this._transitions.push({
      at: new Date().toISOString(),
      from,
      to: next,
      reason,
    });
  }
}
