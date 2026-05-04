"""OSI (ASAM Open Simulation Interface) utilities for scenario generation.

This module provides wrappers and helpers for working with OSI SensorData messages
for the AREG800A radar echo generator. It handles the protobuf serialization,
message framing, and timestamp generation required by the AREG.

References:
- R&S AREG800A Application Note: Scenario Generation Using Python (1GP152)
- OSI Version 3.5.0+ (https://github.com/esmini/osi)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

# Try to import OSI3 protobuf bindings
try:
    from osi3.osi_sensordata_pb2 import SensorData
    OSI3_AVAILABLE = True
except ImportError:
    OSI3_AVAILABLE = False
    SensorData = None


@dataclass
class RadarDetectionData:
    """Single radar detection/object to be added to an OSI message."""
    distance_m: float          # Position distance in meters (range)
    azimuth_rad: float         # Position azimuth in radians
    elevation_rad: float       # Position elevation in radians (default 0.0)
    radial_velocity_mps: float # Radial velocity in m/s (positive = moving away)
    rcs_dbsm: float           # Radar cross section in dBsm (dBm²)


class OsiRadarSensor:
    """Wrapper for OSI SensorData message containing radar detections.
    
    This class simplifies creation of OSI radar messages by providing a high-level
    interface to the protobuf SensorData structure.
    """
    
    def __init__(self, sensor_id: int = 1, timestamp_sec: int = 0, timestamp_nanos: int = 0):
        """Initialize OSI sensor with timestamp.
        
        Args:
            sensor_id: Unique identifier for the radar sensor (default 1)
            timestamp_sec: Timestamp seconds (OSI format)
            timestamp_nanos: Timestamp nanoseconds (OSI format)
        
        Raises:
            RuntimeError: If OSI3 package is not installed
        """
        if not OSI3_AVAILABLE:
            raise RuntimeError(
                "OSI3 Python bindings are not installed. "
                "Scenario generation requires the osi3 Python package (minimum version 3.5.0). "
                "Install with: pip install osi3"
            )
        
        self.sensordata = SensorData()
        self.sensordata.sensor_id.value = sensor_id
        self.sensordata.timestamp.seconds = timestamp_sec
        self.sensordata.timestamp.nanos = timestamp_nanos
        
        # Get or create the radar_sensor within feature_data
        self.radar_sensor = self.sensordata.feature_data.radar_sensor.add()
    
    def add_detection(
        self,
        distance: float,
        azimuth: float,
        radial_velocity: float,
        rcs: float,
        elevation: float = 0.0,
    ) -> None:
        """Add a single radar detection to this SensorData message.
        
        Args:
            distance: Detection distance in meters
            azimuth: Detection azimuth in radians
            radial_velocity: Radial velocity in m/s (positive = away from sensor)
            rcs: Radar cross section in dBsm
            elevation: Detection elevation in radians (default 0.0)
        """
        detection = self.radar_sensor.detection.add()
        detection.position.distance = distance
        detection.position.azimuth = azimuth
        detection.position.elevation = elevation
        detection.radial_velocity = radial_velocity
        detection.rcs = rcs
    
    def serialize_to_byte_msg(self) -> bytes:
        """Serialize the SensorData message to protobuf bytes.
        
        Returns:
            Serialized protobuf message (raw bytes, no length prefix)
        """
        return self.sensordata.SerializeToString()


def generate_osi_msg(
    sensor_id: int,
    timestamp_sec: int,
    timestamp_nanos: int,
    detections: list[RadarDetectionData],
) -> bytes:
    """Generate a single OSI SensorData message with multiple detections.
    
    This function creates one SensorData message containing all provided detections
    at a specific timestamp. The message is serialized to protobuf bytes.
    
    Args:
        sensor_id: Radar sensor ID
        timestamp_sec: Message timestamp (seconds)
        timestamp_nanos: Message timestamp (nanoseconds)
        detections: List of RadarDetectionData objects
    
    Returns:
        Serialized SensorData message (bytes, without length prefix)
    
    Raises:
        RuntimeError: If OSI3 is not available
    """
    sensor = OsiRadarSensor(sensor_id, timestamp_sec, timestamp_nanos)
    for det in detections:
        sensor.add_detection(
            distance=det.distance_m,
            azimuth=det.azimuth_rad,
            elevation=det.elevation_rad,
            radial_velocity=det.radial_velocity_mps,
            rcs=det.rcs_dbsm,
        )
    return sensor.serialize_to_byte_msg()


def write_osi_file(messages: list[bytes], output_path: str | Path) -> dict[str, object]:
    """Write serialized OSI messages to a .osi file with length prefixes.
    
    Each message is prefixed with a little-endian 32-bit length field per IEEE 488.2.
    This format is expected by the AREG800A scenario player.
    
    Args:
        messages: List of serialized SensorData messages (bytes)
        output_path: Path where .osi file will be written
    
    Returns:
        Dict with result metadata:
        {
            "ok": bool,
            "file_path": str,
            "message_count": int,
            "bytes_written": int,
            "error": str | None
        }
    
    Raises:
        ValueError: If output_path doesn't end with .osi
        IOError: If file cannot be written
    """
    output_path = Path(output_path)
    
    if output_path.suffix.lower() != ".osi":
        raise ValueError(f"Output file must end with .osi, got: {output_path.name}")
    
    try:
        total_bytes = 0
        with open(output_path, "wb") as f:
            for msg in messages:
                # Write 32-bit little-endian length prefix
                length_prefix = struct.pack("<L", len(msg))
                f.write(length_prefix)
                f.write(msg)
                total_bytes += len(length_prefix) + len(msg)
        
        return {
            "ok": True,
            "file_path": str(output_path),
            "message_count": len(messages),
            "bytes_written": total_bytes,
            "error": None,
        }
    except (IOError, OSError) as ex:
        return {
            "ok": False,
            "file_path": str(output_path),
            "message_count": len(messages),
            "bytes_written": 0,
            "error": str(ex),
        }


def add_timestamp_interval(
    timestamp_sec: int, timestamp_nanos: int, interval_s: float
) -> tuple[int, int]:
    """Add a time interval to an OSI timestamp, handling carry-over correctly.
    
    This function avoids floating-point accumulation errors by working in nanoseconds.
    
    Args:
        timestamp_sec: Current timestamp seconds
        timestamp_nanos: Current timestamp nanoseconds
        interval_s: Interval to add (seconds as float)
    
    Returns:
        Tuple of (new_seconds, new_nanos) with carry-over handled
    
    Example:
        >>> add_timestamp_interval(0, 0, 0.1)
        (0, 100000000)  # 0 sec + 100 ms
        >>> add_timestamp_interval(0, 900000000, 0.2)
        (1, 100000000)  # Carry-over from nanos to seconds
    """
    # Convert interval to nanoseconds, rounding carefully
    interval_ns = int(round(interval_s * 1_000_000_000))
    
    # Add to current nanos
    timestamp_nanos += interval_ns
    
    # Handle carry to seconds
    timestamp_sec += timestamp_nanos // 1_000_000_000
    timestamp_nanos = timestamp_nanos % 1_000_000_000
    
    return timestamp_sec, timestamp_nanos


def degrees_to_radians(degrees: float) -> float:
    """Convert degrees to radians.
    
    Args:
        degrees: Angle in degrees
    
    Returns:
        Angle in radians
    """
    import math
    return degrees * (math.pi / 180.0)


def validate_detection_params(
    distance_m: float,
    azimuth_deg: float,
    elevation_deg: float,
    radial_velocity_mps: float,
    rcs_dbsm: float,
) -> tuple[bool, str | None]:
    """Validate radar detection parameters.
    
    Args:
        distance_m: Distance in meters
        azimuth_deg: Azimuth in degrees
        elevation_deg: Elevation in degrees
        radial_velocity_mps: Radial velocity in m/s
        rcs_dbsm: RCS in dBsm
    
    Returns:
        Tuple of (valid: bool, error_message: str | None)
    """
    if distance_m < 0:
        return False, "Distance must be non-negative"
    
    if not (-180 <= azimuth_deg <= 360):
        return False, "Azimuth must be between -180 and 360 degrees"
    
    if not (-90 <= elevation_deg <= 90):
        return False, "Elevation must be between -90 and 90 degrees"
    
    if not (-1000 <= rcs_dbsm <= 100):  # Reasonable physical range
        return False, "RCS must be between -1000 and 100 dBsm"
    
    if not (-500 <= radial_velocity_mps <= 500):  # Reasonable for automotive radar
        return False, "Radial velocity must be between -500 and 500 m/s"
    
    return True, None


def check_osi_availability() -> tuple[bool, str | None]:
    """Check if OSI3 package is available.
    
    Returns:
        Tuple of (available: bool, error_message: str | None)
    """
    if not OSI3_AVAILABLE:
        return False, (
            "OSI3 Python bindings are not installed. "
            "Scenario generation requires the osi3 Python package (minimum version 3.5.0). "
            "Install with: pip install osi3"
        )
    return True, None
