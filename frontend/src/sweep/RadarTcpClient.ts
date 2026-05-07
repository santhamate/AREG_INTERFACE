export interface RadarTcpConfig {
  enabled: boolean;
  ip: string;
  port: number;
  packetFormat: "hex_raw";
}

export class RadarTcpClient {
  async connect(_config: RadarTcpConfig): Promise<void> {
    // TODO: Implement real TCP client integration through backend service.
    throw new Error("RadarTcpClient is not implemented yet.");
  }

  async disconnect(): Promise<void> {
    // TODO: Implement real TCP client integration through backend service.
  }
}
