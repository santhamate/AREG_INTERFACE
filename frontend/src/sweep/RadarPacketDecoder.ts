export interface DecodedRadarMeasurement {
  speed: number | null;
  raw: string;
}

export class RadarPacketDecoder {
  decode(_payload: string): DecodedRadarMeasurement {
    // TODO: Implement decoder once radar packet format is defined.
    return { speed: null, raw: _payload };
  }
}
