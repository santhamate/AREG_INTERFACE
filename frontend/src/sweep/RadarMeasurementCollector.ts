import type { DecodedRadarMeasurement } from "./RadarPacketDecoder";

export class RadarMeasurementCollector {
  private values: number[] = [];

  push(measurement: DecodedRadarMeasurement): void {
    if (typeof measurement.speed === "number" && Number.isFinite(measurement.speed)) {
      this.values.push(measurement.speed);
    }
  }

  latest(): number | null {
    if (this.values.length === 0) return null;
    return this.values[this.values.length - 1];
  }
}
