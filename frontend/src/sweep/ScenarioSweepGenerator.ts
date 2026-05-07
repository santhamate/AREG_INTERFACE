import type { DirectionMode, SpeedUnit } from "./ScenarioSweepConfig";

export interface SpeedStepCase {
  speedInput: number;
  speedUnit: SpeedUnit;
  signedSpeedMps: number;
  expectedDisplaySpeed: number;
  filename: string;
  aregPath: string;
}

export function speedToMps(value: number, unit: SpeedUnit): number {
  if (unit === "kmh") return value / 3.6;
  if (unit === "mph") return value * 0.44704;
  return value;
}

export function mpsToUnit(value: number, unit: SpeedUnit): number {
  if (unit === "kmh") return value * 3.6;
  if (unit === "mph") return value / 0.44704;
  return value;
}

export function unitToken(unit: SpeedUnit): string {
  if (unit === "kmh") return "kmh";
  if (unit === "mph") return "mph";
  return "ms";
}

export function buildSignedSpeedMps(speedInput: number, unit: SpeedUnit, mode: DirectionMode): number {
  const absMps = Math.abs(speedToMps(speedInput, unit));
  if (mode === "approaching") return -absMps;
  if (mode === "away") return absMps;
  return speedToMps(speedInput, unit);
}

function filenameSignedToken(speedInput: number): string {
  const sign = speedInput >= 0 ? "p" : "n";
  const padded = Math.abs(Math.round(speedInput)).toString().padStart(3, "0");
  return `${sign}${padded}`;
}

export function makeScenarioFilename(prefix: string, speedInput: number, unit: SpeedUnit): string {
  return `${prefix}_${filenameSignedToken(speedInput)}_${unitToken(unit)}.osi`;
}

export function normalizeAregFolder(path: string): string {
  const trimmed = path.trim() || "/var/user/";
  return trimmed.endsWith("/") ? trimmed : `${trimmed}/`;
}

export function buildSpeedSweepCases(
  startSpeed: number,
  stopSpeed: number,
  stepSize: number,
  speedUnit: SpeedUnit,
  directionMode: DirectionMode,
  filenamePrefix: string,
  targetFolder: string,
): SpeedStepCase[] {
  const cases: SpeedStepCase[] = [];
  if (!Number.isFinite(stepSize) || stepSize === 0) return cases;

  const step = Math.abs(stepSize);
  const ascending = stopSpeed >= startSpeed;
  const delta = ascending ? step : -step;
  const folder = normalizeAregFolder(targetFolder);

  let current = startSpeed;
  const maxIterations = 20000;
  for (let i = 0; i < maxIterations; i += 1) {
    const beyond = ascending ? current > stopSpeed + 1e-9 : current < stopSpeed - 1e-9;
    if (beyond) break;

    const filename = makeScenarioFilename(filenamePrefix, current, speedUnit);
    const signedSpeedMps = buildSignedSpeedMps(current, speedUnit, directionMode);
    const expectedDisplaySpeed = mpsToUnit(signedSpeedMps, speedUnit);

    cases.push({
      speedInput: current,
      speedUnit,
      signedSpeedMps,
      expectedDisplaySpeed,
      filename,
      aregPath: `${folder}${filename}`,
    });

    current += delta;
  }

  return cases;
}
