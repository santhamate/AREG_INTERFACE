"""
TCV907 Radar API Models - Pydantic models for radar API requests and responses
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class RadarConnectionRequest(BaseModel):
    """Request to connect or configure radar"""
    ip: str = Field(default="192.168.4.1", description="Radar IP address")
    port: int = Field(default=20000, description="Radar UDP port")


class RadarConnectionResponse(BaseModel):
    """Response for connection operations"""
    ok: bool
    connected: bool
    state: str
    radar_ip: str
    radar_port: int
    message: Optional[str] = None
    error: Optional[str] = None


class RadarStatisticsResponse(BaseModel):
    """Radar connection and data statistics"""
    connected: bool
    state: str
    radar_ip: str
    radar_port: int
    packets_received: int
    bytes_received: int
    speeds_parsed: int
    parse_errors: int
    uptime_seconds: float
    packet_rate_per_second: float
    speed_history_count: int
    last_error: Optional[str] = None


class SpeedMeasurementModel(BaseModel):
    """Single speed measurement"""
    speed_kmh: float = Field(description="Speed in km/h")
    timestamp: str = Field(description="ISO format timestamp")
    packet_number: int = Field(description="Sequential packet number")
    raw_data_hex: str = Field(description="Raw packet data as hex string")


class SpeedHistoryResponse(BaseModel):
    """Response containing speed history"""
    ok: bool
    count: int
    measurements: list[SpeedMeasurementModel]
    limit: Optional[int] = None


class RadarStatusResponse(BaseModel):
    """Overall radar system status"""
    ok: bool
    connected: bool
    state: str
    last_speed: Optional[SpeedMeasurementModel] = None
    statistics: RadarStatisticsResponse
    last_error: Optional[str] = None
