"""Scenario generation templates for AREG800A radar echo simulator.

This module implements reusable scenario templates:
- Range sweep: Single object moving toward/away from radar
- Constant object: Stationary or constant-velocity object
- Multi-object sweep: Multiple objects with independent parameters
- Azimuth sweep: Single object rotating around radar
- (Optional) Constant echo power: Advanced template using RCS compensation

Each template validates input parameters, generates OSI messages, and provides
preview information for the user interface.

References:
- R&S AREG800A Application Note: Scenario Generation Using Python (1GP152)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.core.osi_utils import (
    RadarDetectionData,
    add_timestamp_interval,
    degrees_to_radians,
    generate_osi_msg,
    validate_detection_params,
)


@dataclass
class ScenarioPreview:
    """Preview/metadata for a generated scenario."""
    duration_s: float
    message_count: int
    object_count: int
    min_range_m: float
    max_range_m: float
    min_azimuth_deg: float
    max_azimuth_deg: float
    min_velocity_mps: float
    max_velocity_mps: float
    min_rcs_dbsm: float
    max_rcs_dbsm: float
    estimated_file_size_bytes: int
    warnings: list[str]


@dataclass
class RangeSweepParams:
    """Parameters for range sweep scenario."""
    sensor_id: int = 1
    update_interval_s: float = 0.1
    start_range_m: float = 120.0
    stop_range_m: float = 20.0
    radial_velocity_mps: float = -10.0
    rcs_dbsm: float = 10.0
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0


@dataclass
class ConstantObjectParams:
    """Parameters for constant object scenario."""
    sensor_id: int = 1
    duration_s: float = 10.0
    update_interval_s: float = 0.1
    range_m: float = 100.0
    radial_velocity_mps: float = 0.0
    rcs_dbsm: float = 10.0
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0


@dataclass
class MultiObjectParams:
    """Parameters for multi-object scenario."""
    sensor_id: int = 1
    update_interval_s: float = 0.1
    duration_s: float = 10.0
    objects: list[dict] = None  # List of {name, enabled, start_range, stop_range, velocity, rcs, azimuth, elevation}
    
    def __post_init__(self):
        if self.objects is None:
            self.objects = []


@dataclass
class AzimuthSweepParams:
    """Parameters for azimuth sweep scenario."""
    sensor_id: int = 1
    update_interval_s: float = 0.1
    duration_s: float = 10.0
    range_m: float = 100.0
    start_azimuth_deg: float = -180.0
    stop_azimuth_deg: float = 180.0
    radial_velocity_mps: float = 0.0
    rcs_dbsm: float = 10.0
    elevation_deg: float = 0.0


class RangeSweepTemplate:
    """Generate a range sweep scenario (single object moving toward/away from radar).
    
    The object starts at start_range_m and moves toward stop_range_m at a constant
    radial velocity. One OSI message is generated per update_interval_s.
    """
    
    @staticmethod
    def validate_params(params: RangeSweepParams) -> tuple[bool, list[str]]:
        """Validate range sweep parameters.
        
        Returns:
            Tuple of (valid: bool, warnings: list[str])
        """
        warnings = []
        
        if params.update_interval_s < 0.01:
            return False, ["Update interval must be >= 0.01 s (10 ms)"]
        
        if params.start_range_m <= 0:
            warnings.append("Start range should be positive")
        
        if params.stop_range_m < 0:
            warnings.append("Stop range should be non-negative")
        
        # Warn if range/velocity direction mismatch
        moving_towards = params.radial_velocity_mps < 0
        moving_away = params.radial_velocity_mps > 0
        range_decreasing = params.start_range_m > params.stop_range_m
        
        if range_decreasing and moving_away:
            warnings.append("Range decreases but velocity is positive (away). Consider negative velocity.")
        elif not range_decreasing and moving_towards:
            warnings.append("Range increases but velocity is negative (toward). Consider positive velocity.")
        
        # Validate detection parameters
        valid, error = validate_detection_params(
            distance_m=params.start_range_m,
            azimuth_deg=params.azimuth_deg,
            elevation_deg=params.elevation_deg,
            radial_velocity_mps=params.radial_velocity_mps,
            rcs_dbsm=params.rcs_dbsm,
        )
        if not valid:
            return False, [error]
        
        return True, warnings
    
    @staticmethod
    def generate(params: RangeSweepParams) -> tuple[list[bytes], ScenarioPreview]:
        """Generate range sweep OSI messages.
        
        Returns:
            Tuple of (messages: list[bytes], preview: ScenarioPreview)
        """
        valid, warnings = RangeSweepTemplate.validate_params(params)
        if not valid:
            raise ValueError(f"Invalid parameters: {warnings[0]}")
        
        messages: list[bytes] = []
        timestamp_sec = 0
        timestamp_nanos = 0
        current_range = params.start_range_m
        range_step = params.radial_velocity_mps * params.update_interval_s
        
        # Generate messages while object is in range
        message_count = 0
        while (range_step > 0 and current_range <= params.stop_range_m) or \
              (range_step < 0 and current_range >= params.stop_range_m) or \
              (range_step == 0):
            # Create detection
            detection = RadarDetectionData(
                distance_m=current_range,
                azimuth_rad=degrees_to_radians(params.azimuth_deg),
                elevation_rad=degrees_to_radians(params.elevation_deg),
                radial_velocity_mps=params.radial_velocity_mps,
                rcs_dbsm=params.rcs_dbsm,
            )
            
            # Generate message
            msg = generate_osi_msg(
                sensor_id=params.sensor_id,
                timestamp_sec=timestamp_sec,
                timestamp_nanos=timestamp_nanos,
                detections=[detection],
            )
            messages.append(msg)
            message_count += 1
            
            # Move to next update
            current_range += range_step
            timestamp_sec, timestamp_nanos = add_timestamp_interval(
                timestamp_sec, timestamp_nanos, params.update_interval_s
            )
            
            # Safety: prevent infinite loop
            if message_count > 100000:
                warnings.append("Scenario truncated to 100,000 messages (safety limit)")
                break
        
        duration_s = (timestamp_sec) + (timestamp_nanos / 1_000_000_000)
        
        preview = ScenarioPreview(
            duration_s=duration_s,
            message_count=len(messages),
            object_count=1,
            min_range_m=min(params.start_range_m, params.stop_range_m),
            max_range_m=max(params.start_range_m, params.stop_range_m),
            min_azimuth_deg=params.azimuth_deg,
            max_azimuth_deg=params.azimuth_deg,
            min_velocity_mps=params.radial_velocity_mps,
            max_velocity_mps=params.radial_velocity_mps,
            min_rcs_dbsm=params.rcs_dbsm,
            max_rcs_dbsm=params.rcs_dbsm,
            estimated_file_size_bytes=sum(len(m) for m in messages) + len(messages) * 4,
            warnings=warnings,
        )
        
        return messages, preview


class ConstantObjectTemplate:
    """Generate a constant object scenario (object with static or constant-velocity parameters).
    
    The object remains at a fixed range (with optional constant radial velocity),
    azimuth, and RCS for the specified duration.
    """
    
    @staticmethod
    def validate_params(params: ConstantObjectParams) -> tuple[bool, list[str]]:
        """Validate constant object parameters."""
        warnings = []
        
        if params.update_interval_s < 0.01:
            return False, ["Update interval must be >= 0.01 s (10 ms)"]
        
        if params.duration_s < params.update_interval_s:
            warnings.append("Duration is less than one update interval")
        
        if params.duration_s <= 0:
            return False, ["Duration must be positive"]
        
        valid, error = validate_detection_params(
            distance_m=params.range_m,
            azimuth_deg=params.azimuth_deg,
            elevation_deg=params.elevation_deg,
            radial_velocity_mps=params.radial_velocity_mps,
            rcs_dbsm=params.rcs_dbsm,
        )
        if not valid:
            return False, [error]
        
        return True, warnings
    
    @staticmethod
    def generate(params: ConstantObjectParams) -> tuple[list[bytes], ScenarioPreview]:
        """Generate constant object OSI messages."""
        valid, warnings = ConstantObjectTemplate.validate_params(params)
        if not valid:
            raise ValueError(f"Invalid parameters: {warnings[0]}")
        
        messages: list[bytes] = []
        timestamp_sec = 0
        timestamp_nanos = 0
        current_range = params.range_m
        
        # Generate messages for the specified duration
        while (timestamp_sec) + (timestamp_nanos / 1_000_000_000) < params.duration_s:
            detection = RadarDetectionData(
                distance_m=current_range,
                azimuth_rad=degrees_to_radians(params.azimuth_deg),
                elevation_rad=degrees_to_radians(params.elevation_deg),
                radial_velocity_mps=params.radial_velocity_mps,
                rcs_dbsm=params.rcs_dbsm,
            )
            
            msg = generate_osi_msg(
                sensor_id=params.sensor_id,
                timestamp_sec=timestamp_sec,
                timestamp_nanos=timestamp_nanos,
                detections=[detection],
            )
            messages.append(msg)
            
            # Update range if there's radial velocity
            current_range += params.radial_velocity_mps * params.update_interval_s
            
            timestamp_sec, timestamp_nanos = add_timestamp_interval(
                timestamp_sec, timestamp_nanos, params.update_interval_s
            )
        
        duration_s = (timestamp_sec) + (timestamp_nanos / 1_000_000_000)
        
        preview = ScenarioPreview(
            duration_s=duration_s,
            message_count=len(messages),
            object_count=1,
            min_range_m=min(params.range_m, params.range_m + params.radial_velocity_mps * duration_s),
            max_range_m=max(params.range_m, params.range_m + params.radial_velocity_mps * duration_s),
            min_azimuth_deg=params.azimuth_deg,
            max_azimuth_deg=params.azimuth_deg,
            min_velocity_mps=params.radial_velocity_mps,
            max_velocity_mps=params.radial_velocity_mps,
            min_rcs_dbsm=params.rcs_dbsm,
            max_rcs_dbsm=params.rcs_dbsm,
            estimated_file_size_bytes=sum(len(m) for m in messages) + len(messages) * 4,
            warnings=warnings,
        )
        
        return messages, preview


class MultiObjectTemplate:
    """Generate a multi-object scenario with independent parameters per object.
    
    Each object can have independent range sweep, velocity, azimuth, and RCS.
    Multiple objects are included in each OSI message at the same timestamp.
    """
    
    @staticmethod
    def validate_params(params: MultiObjectParams) -> tuple[bool, list[str]]:
        """Validate multi-object parameters."""
        warnings = []
        
        if params.update_interval_s < 0.01:
            return False, ["Update interval must be >= 0.01 s (10 ms)"]
        
        enabled_objects = [obj for obj in params.objects if obj.get("enabled", True)]
        if len(enabled_objects) == 0:
            return False, ["At least one object must be enabled"]
        
        if len(enabled_objects) > 8:
            warnings.append("More than 8 objects configured. AREG supports max 8 objects per frontend.")
        
        if len(enabled_objects) > 4:
            warnings.append("More than 4 objects may exceed QAT mode limit (4 objects).")
        
        return True, warnings
    
    @staticmethod
    def generate(params: MultiObjectParams) -> tuple[list[bytes], ScenarioPreview]:
        """Generate multi-object OSI messages."""
        valid, warnings = MultiObjectTemplate.validate_params(params)
        if not valid:
            raise ValueError(f"Invalid parameters: {warnings[0]}")
        
        messages: list[bytes] = []
        timestamp_sec = 0
        timestamp_nanos = 0
        
        # Track object states
        object_states = {}
        for obj in params.objects:
            if obj.get("enabled", True):
                object_states[obj["name"]] = {
                    "current_range": obj.get("start_range_m", 100.0),
                    "range_step": obj.get("radial_velocity_mps", 0.0) * params.update_interval_s,
                }
        
        # Generate messages for duration
        while (timestamp_sec) + (timestamp_nanos / 1_000_000_000) < params.duration_s:
            detections: list[RadarDetectionData] = []
            
            for obj in params.objects:
                if not obj.get("enabled", True):
                    continue
                
                obj_name = obj["name"]
                state = object_states[obj_name]
                current_range = state["current_range"]
                
                detection = RadarDetectionData(
                    distance_m=current_range,
                    azimuth_rad=degrees_to_radians(obj.get("azimuth_deg", 0.0)),
                    elevation_rad=degrees_to_radians(obj.get("elevation_deg", 0.0)),
                    radial_velocity_mps=obj.get("radial_velocity_mps", 0.0),
                    rcs_dbsm=obj.get("rcs_dbsm", 10.0),
                )
                detections.append(detection)
                
                # Update range
                state["current_range"] += state["range_step"]
            
            # Generate message with all detections
            if detections:
                msg = generate_osi_msg(
                    sensor_id=params.sensor_id,
                    timestamp_sec=timestamp_sec,
                    timestamp_nanos=timestamp_nanos,
                    detections=detections,
                )
                messages.append(msg)
            
            timestamp_sec, timestamp_nanos = add_timestamp_interval(
                timestamp_sec, timestamp_nanos, params.update_interval_s
            )
        
        duration_s = (timestamp_sec) + (timestamp_nanos / 1_000_000_000)
        
        # Calculate min/max ranges across all objects
        all_ranges = []
        for obj in params.objects:
            if obj.get("enabled", True):
                all_ranges.append(obj.get("start_range_m", 100.0))
                all_ranges.append(obj.get("stop_range_m", obj.get("start_range_m", 100.0)))
        
        preview = ScenarioPreview(
            duration_s=duration_s,
            message_count=len(messages),
            object_count=len([obj for obj in params.objects if obj.get("enabled", True)]),
            min_range_m=min(all_ranges) if all_ranges else 0.0,
            max_range_m=max(all_ranges) if all_ranges else 0.0,
            min_azimuth_deg=-180.0,  # Simplified
            max_azimuth_deg=180.0,
            min_velocity_mps=-100.0,  # Simplified
            max_velocity_mps=100.0,
            min_rcs_dbsm=0.0,  # Simplified
            max_rcs_dbsm=50.0,
            estimated_file_size_bytes=sum(len(m) for m in messages) + len(messages) * 4,
            warnings=warnings,
        )
        
        return messages, preview


class AzimuthSweepTemplate:
    """Generate an azimuth sweep scenario (object rotating around radar).
    
    The object rotates from start_azimuth_deg to stop_azimuth_deg while maintaining
    constant range and RCS.
    """
    
    @staticmethod
    def validate_params(params: AzimuthSweepParams) -> tuple[bool, list[str]]:
        """Validate azimuth sweep parameters."""
        warnings = []
        
        if params.update_interval_s < 0.01:
            return False, ["Update interval must be >= 0.01 s (10 ms)"]
        
        if params.duration_s <= 0:
            return False, ["Duration must be positive"]
        
        if abs(params.start_azimuth_deg - params.stop_azimuth_deg) < 0.01:
            warnings.append("Start and stop azimuth are nearly identical")
        
        return True, warnings
    
    @staticmethod
    def generate(params: AzimuthSweepParams) -> tuple[list[bytes], ScenarioPreview]:
        """Generate azimuth sweep OSI messages."""
        valid, warnings = AzimuthSweepTemplate.validate_params(params)
        if not valid:
            raise ValueError(f"Invalid parameters: {warnings[0]}")
        
        messages: list[bytes] = []
        timestamp_sec = 0
        timestamp_nanos = 0
        
        # Calculate azimuth step
        num_steps = int(params.duration_s / params.update_interval_s)
        if num_steps == 0:
            num_steps = 1
        
        azimuth_range = params.stop_azimuth_deg - params.start_azimuth_deg
        azimuth_step = azimuth_range / num_steps if num_steps > 1 else 0
        
        for i in range(num_steps):
            current_azimuth = params.start_azimuth_deg + (i * azimuth_step)
            
            detection = RadarDetectionData(
                distance_m=params.range_m,
                azimuth_rad=degrees_to_radians(current_azimuth),
                elevation_rad=degrees_to_radians(params.elevation_deg),
                radial_velocity_mps=params.radial_velocity_mps,
                rcs_dbsm=params.rcs_dbsm,
            )
            
            msg = generate_osi_msg(
                sensor_id=params.sensor_id,
                timestamp_sec=timestamp_sec,
                timestamp_nanos=timestamp_nanos,
                detections=[detection],
            )
            messages.append(msg)
            
            timestamp_sec, timestamp_nanos = add_timestamp_interval(
                timestamp_sec, timestamp_nanos, params.update_interval_s
            )
        
        duration_s = (timestamp_sec) + (timestamp_nanos / 1_000_000_000)
        
        preview = ScenarioPreview(
            duration_s=duration_s,
            message_count=len(messages),
            object_count=1,
            min_range_m=params.range_m,
            max_range_m=params.range_m,
            min_azimuth_deg=min(params.start_azimuth_deg, params.stop_azimuth_deg),
            max_azimuth_deg=max(params.start_azimuth_deg, params.stop_azimuth_deg),
            min_velocity_mps=params.radial_velocity_mps,
            max_velocity_mps=params.radial_velocity_mps,
            min_rcs_dbsm=params.rcs_dbsm,
            max_rcs_dbsm=params.rcs_dbsm,
            estimated_file_size_bytes=sum(len(m) for m in messages) + len(messages) * 4,
            warnings=warnings,
        )
        
        return messages, preview
