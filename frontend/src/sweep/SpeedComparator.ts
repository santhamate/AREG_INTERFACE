import type { ToleranceMode } from "./ScenarioSweepConfig";

export interface CompareOptions {
  toleranceMode: ToleranceMode;
  fixedToleranceKmh: number;
  percentageTolerance: number;
}

export interface CompareResult {
  expected: number;
  measured: number;
  error: number;
  passed: boolean;
  toleranceApplied: number;
}

export class SpeedComparator {
  compare(expectedKmh: number, measuredKmh: number, options: CompareOptions): CompareResult {
    const error = measuredKmh - expectedKmh;

    let tolerance = options.fixedToleranceKmh;
    if (options.toleranceMode === "percentage") {
      tolerance = Math.abs(expectedKmh) * (options.percentageTolerance / 100);
    }
    if (options.toleranceMode === "custom_rule") {
      tolerance = Math.abs(expectedKmh) < 100 ? 3 : Math.abs(expectedKmh) * 0.03;
    }

    return {
      expected: expectedKmh,
      measured: measuredKmh,
      error,
      passed: Math.abs(error) <= tolerance,
      toleranceApplied: tolerance,
    };
  }
}
