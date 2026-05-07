export type SpeedUnit = "kmh" | "ms" | "mph";
export type DirectionMode = "approaching" | "away" | "signed";
export type SweepReplayMode = "SINGle" | "LOOP";
export type SweepExecutionMode = "generate_only" | "generate_upload" | "generate_upload_run";
export type ToleranceMode = "fixed_kmh" | "percentage" | "custom_rule";

export interface ScenarioSweepConfig {
  startSpeed: number;
  stopSpeed: number;
  stepSize: number;
  speedUnit: SpeedUnit;
  directionMode: DirectionMode;
  repeatsPerSpeed: number;
  updateIntervalMs: number;
  startPositionM: number;
  endPositionM: number;
  replayMode: SweepReplayMode;
  targetAregFolder: string;
  delayBetweenRepeatsMs: number;
  delayBetweenScenariosMs: number;
  delayBeforeRadarReadMs: number;
  passFailTolerance: number;
  toleranceMode: ToleranceMode;
  filenamePrefix: string;
  overwriteExisting: boolean;
  executionMode: SweepExecutionMode;
  commandTimeoutMs: number;
}

export function defaultScenarioSweepConfig(): ScenarioSweepConfig {
  return {
    startSpeed: 10,
    stopSpeed: 100,
    stepSize: 10,
    speedUnit: "kmh",
    directionMode: "approaching",
    repeatsPerSpeed: 3,
    updateIntervalMs: 100,
    startPositionM: 50,
    endPositionM: 0,
    replayMode: "SINGle",
    targetAregFolder: "/var/user/",
    delayBetweenRepeatsMs: 250,
    delayBetweenScenariosMs: 300,
    delayBeforeRadarReadMs: 0,
    passFailTolerance: 3,
    toleranceMode: "fixed_kmh",
    filenamePrefix: "speed_sweep",
    overwriteExisting: true,
    executionMode: "generate_upload_run",
    commandTimeoutMs: 3000,
  };
}

export function validateScenarioSweepConfig(config: ScenarioSweepConfig): string[] {
  const errors: string[] = [];

  if (!Number.isFinite(config.startSpeed) || !Number.isFinite(config.stopSpeed)) {
    errors.push("Start and stop speed must be valid numbers.");
  }
  if (!Number.isFinite(config.stepSize) || config.stepSize === 0) {
    errors.push("Step size must be a non-zero number.");
  }
  if (!Number.isFinite(config.updateIntervalMs) || config.updateIntervalMs <= 0) {
    errors.push("Update interval must be greater than zero.");
  }
  if (!Number.isFinite(config.startPositionM) || config.startPositionM < 0) {
    errors.push("Start position must be greater than or equal to zero meters.");
  }
  if (!Number.isFinite(config.endPositionM) || config.endPositionM < 0) {
    errors.push("End position must be greater than or equal to zero meters.");
  }
  if (config.endPositionM === config.startPositionM) {
    errors.push("Start and end positions must be different.");
  }
  if (!Number.isFinite(config.repeatsPerSpeed) || config.repeatsPerSpeed < 1) {
    errors.push("Repeats per speed must be at least 1.");
  }
  if (!config.targetAregFolder.trim()) {
    errors.push("Target folder on AREG is required.");
  }
  if (!config.filenamePrefix.trim()) {
    errors.push("Scenario filename prefix is required.");
  }
  if (!Number.isFinite(config.commandTimeoutMs) || config.commandTimeoutMs < 100) {
    errors.push("Command timeout must be at least 100 ms.");
  }

  return errors;
}
