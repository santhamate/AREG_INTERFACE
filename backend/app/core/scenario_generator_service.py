"""Main scenario generator service for AREG800A.

This module orchestrates scenario generation, including:
- Template selection and parameterization
- OSI message generation
- File writing with validation
- Preview and metadata tracking
- Generation and transfer logging

This service is the primary interface for generating .osi scenario files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import struct
from typing import Any

from backend.app.core.file_transfer import FileTransferService
from backend.app.core.osi_utils import check_osi_availability, write_osi_file
from backend.app.core.scenario_templates import (
    AzimuthSweepParams,
    AzimuthSweepTemplate,
    ConstantObjectParams,
    ConstantObjectTemplate,
    MultiObjectParams,
    MultiObjectTemplate,
    RangeSweepParams,
    RangeSweepTemplate,
    ScenarioPreview,
)


@dataclass
class GenerationLog:
    """Log entry for scenario generation."""
    timestamp: str
    template_type: str
    parameters: dict[str, Any]
    output_filename: str
    message_count: int
    bytes_written: int
    duration_s: float
    success: bool
    error: str | None = None


@dataclass
class TransferLog:
    """Log entry for file transfer to AREG."""
    timestamp: str
    local_path: str
    remote_path: str
    transfer_method: str
    bytes_transferred: int
    success: bool
    error: str | None = None


@dataclass
class ScenarioGeneratorState:
    """State tracking for scenario generator."""
    osi_available: bool
    osi_error: str | None
    generation_logs: list[GenerationLog] = field(default_factory=list)
    transfer_logs: list[TransferLog] = field(default_factory=list)
    last_generated_file: Path | None = None
    last_preview: ScenarioPreview | None = None


class ScenarioGeneratorService:
    """Main service for AREG scenario generation."""
    
    def __init__(self):
        """Initialize scenario generator service."""
        osi_available, osi_error = check_osi_availability()
        self.state = ScenarioGeneratorState(
            osi_available=osi_available,
            osi_error=osi_error,
        )
        self.transfer_service = FileTransferService()
    
    def get_status(self) -> dict[str, object]:
        """Get current status of scenario generator.
        
        Returns:
            {
                "osi_available": bool,
                "osi_error": str | None,
                "last_generated_file": str | None,
                "last_preview": dict | None,
            }
        """
        return {
            "osi_available": self.state.osi_available,
            "osi_error": self.state.osi_error,
            "last_generated_file": str(self.state.last_generated_file) if self.state.last_generated_file else None,
            "last_preview": (
                {
                    "duration_s": self.state.last_preview.duration_s,
                    "message_count": self.state.last_preview.message_count,
                    "object_count": self.state.last_preview.object_count,
                    "min_range_m": self.state.last_preview.min_range_m,
                    "max_range_m": self.state.last_preview.max_range_m,
                    "min_azimuth_deg": self.state.last_preview.min_azimuth_deg,
                    "max_azimuth_deg": self.state.last_preview.max_azimuth_deg,
                    "min_velocity_mps": self.state.last_preview.min_velocity_mps,
                    "max_velocity_mps": self.state.last_preview.max_velocity_mps,
                    "min_rcs_dbsm": self.state.last_preview.min_rcs_dbsm,
                    "max_rcs_dbsm": self.state.last_preview.max_rcs_dbsm,
                    "estimated_file_size_bytes": self.state.last_preview.estimated_file_size_bytes,
                    "warnings": self.state.last_preview.warnings,
                }
                if self.state.last_preview
                else None
            ),
        }
    
    def generate_range_sweep(
        self,
        output_dir: str | Path = "./scenarios",
        output_filename: str | None = None,
        sensor_id: int = 1,
        update_interval_s: float = 0.1,
        start_range_m: float = 120.0,
        stop_range_m: float = 20.0,
        radial_velocity_mps: float = -10.0,
        rcs_dbsm: float = 10.0,
        azimuth_deg: float = 0.0,
        elevation_deg: float = 0.0,
        scenario_name: str = "range_sweep",
    ) -> dict[str, object]:
        """Generate a range sweep scenario.
        
        Args:
            output_dir: Directory to save .osi file
            output_filename: Custom filename (auto-generated if None)
            sensor_id: Radar sensor ID
            update_interval_s: Interval between messages (must be >= 0.01 s)
            start_range_m: Starting range in meters
            stop_range_m: Target/stop range in meters
            radial_velocity_mps: Radial velocity (negative = toward radar)
            rcs_dbsm: Radar cross section in dBsm
            azimuth_deg: Azimuth in degrees
            elevation_deg: Elevation in degrees
            scenario_name: Friendly name for scenario
        
        Returns:
            {
                "ok": bool,
                "file_path": str | None,
                "message_count": int,
                "duration_s": float,
                "preview": dict,
                "error": str | None,
            }
        """
        if not self.state.osi_available:
            return {
                "ok": False,
                "file_path": None,
                "message_count": 0,
                "duration_s": 0.0,
                "preview": None,
                "error": self.state.osi_error,
            }
        
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename if not provided
            if not output_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{scenario_name}_{timestamp}.osi"
            elif not output_filename.lower().endswith(".osi"):
                output_filename += ".osi"
            
            output_path = output_dir / output_filename
            
            # Create parameters
            params = RangeSweepParams(
                sensor_id=sensor_id,
                update_interval_s=update_interval_s,
                start_range_m=start_range_m,
                stop_range_m=stop_range_m,
                radial_velocity_mps=radial_velocity_mps,
                rcs_dbsm=rcs_dbsm,
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
            )
            
            # Generate scenario
            messages, preview = RangeSweepTemplate.generate(params)
            
            if len(messages) == 0:
                error_msg = "Generated scenario contains no messages"
                self._log_generation(
                    template_type="range_sweep",
                    parameters=params.__dict__,
                    output_filename=str(output_path),
                    message_count=0,
                    bytes_written=0,
                    duration_s=0.0,
                    success=False,
                    error=error_msg,
                )
                return {
                    "ok": False,
                    "file_path": None,
                    "message_count": 0,
                    "duration_s": 0.0,
                    "preview": None,
                    "error": error_msg,
                }
            
            # Write file
            result = write_osi_file(messages, str(output_path))
            
            if not result["ok"]:
                self._log_generation(
                    template_type="range_sweep",
                    parameters=params.__dict__,
                    output_filename=str(output_path),
                    message_count=0,
                    bytes_written=0,
                    duration_s=preview.duration_s,
                    success=False,
                    error=result["error"],
                )
                return {
                    "ok": False,
                    "file_path": None,
                    "message_count": len(messages),
                    "duration_s": preview.duration_s,
                    "preview": None,
                    "error": result["error"],
                }
            
            # Log success
            self.state.last_generated_file = output_path
            self.state.last_preview = preview
            self._log_generation(
                template_type="range_sweep",
                parameters=params.__dict__,
                output_filename=str(output_path),
                message_count=len(messages),
                bytes_written=result["bytes_written"],
                duration_s=preview.duration_s,
                success=True,
            )
            
            return {
                "ok": True,
                "file_path": str(output_path),
                "message_count": len(messages),
                "duration_s": preview.duration_s,
                "preview": self._preview_to_dict(preview),
                "error": None,
            }
        
        except Exception as ex:
            error_msg = str(ex)
            self._log_generation(
                template_type="range_sweep",
                parameters={},
                output_filename="",
                message_count=0,
                bytes_written=0,
                duration_s=0.0,
                success=False,
                error=error_msg,
            )
            return {
                "ok": False,
                "file_path": None,
                "message_count": 0,
                "duration_s": 0.0,
                "preview": None,
                "error": error_msg,
            }
    
    def generate_constant_object(
        self,
        output_dir: str | Path = "./scenarios",
        output_filename: str | None = None,
        sensor_id: int = 1,
        duration_s: float = 10.0,
        update_interval_s: float = 0.1,
        range_m: float = 100.0,
        radial_velocity_mps: float = 0.0,
        rcs_dbsm: float = 10.0,
        azimuth_deg: float = 0.0,
        elevation_deg: float = 0.0,
        scenario_name: str = "constant_object",
    ) -> dict[str, object]:
        """Generate a constant object scenario."""
        if not self.state.osi_available:
            return {
                "ok": False,
                "file_path": None,
                "message_count": 0,
                "duration_s": 0.0,
                "preview": None,
                "error": self.state.osi_error,
            }
        
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if not output_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{scenario_name}_{timestamp}.osi"
            elif not output_filename.lower().endswith(".osi"):
                output_filename += ".osi"
            
            output_path = output_dir / output_filename
            
            params = ConstantObjectParams(
                sensor_id=sensor_id,
                duration_s=duration_s,
                update_interval_s=update_interval_s,
                range_m=range_m,
                radial_velocity_mps=radial_velocity_mps,
                rcs_dbsm=rcs_dbsm,
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
            )
            
            messages, preview = ConstantObjectTemplate.generate(params)
            
            if len(messages) == 0:
                error_msg = "Generated scenario contains no messages"
                self._log_generation(
                    template_type="constant_object",
                    parameters=params.__dict__,
                    output_filename=str(output_path),
                    message_count=0,
                    bytes_written=0,
                    duration_s=0.0,
                    success=False,
                    error=error_msg,
                )
                return {
                    "ok": False,
                    "file_path": None,
                    "message_count": 0,
                    "duration_s": 0.0,
                    "preview": None,
                    "error": error_msg,
                }
            
            result = write_osi_file(messages, str(output_path))
            
            if not result["ok"]:
                self._log_generation(
                    template_type="constant_object",
                    parameters=params.__dict__,
                    output_filename=str(output_path),
                    message_count=0,
                    bytes_written=0,
                    duration_s=preview.duration_s,
                    success=False,
                    error=result["error"],
                )
                return {
                    "ok": False,
                    "file_path": None,
                    "message_count": len(messages),
                    "duration_s": preview.duration_s,
                    "preview": None,
                    "error": result["error"],
                }
            
            self.state.last_generated_file = output_path
            self.state.last_preview = preview
            self._log_generation(
                template_type="constant_object",
                parameters=params.__dict__,
                output_filename=str(output_path),
                message_count=len(messages),
                bytes_written=result["bytes_written"],
                duration_s=preview.duration_s,
                success=True,
            )
            
            return {
                "ok": True,
                "file_path": str(output_path),
                "message_count": len(messages),
                "duration_s": preview.duration_s,
                "preview": self._preview_to_dict(preview),
                "error": None,
            }
        
        except Exception as ex:
            error_msg = str(ex)
            self._log_generation(
                template_type="constant_object",
                parameters={},
                output_filename="",
                message_count=0,
                bytes_written=0,
                duration_s=0.0,
                success=False,
                error=error_msg,
            )
            return {
                "ok": False,
                "file_path": None,
                "message_count": 0,
                "duration_s": 0.0,
                "preview": None,
                "error": error_msg,
            }
    
    def generate_multi_object(
        self,
        output_dir: str | Path = "./scenarios",
        output_filename: str | None = None,
        sensor_id: int = 1,
        update_interval_s: float = 0.1,
        duration_s: float = 10.0,
        objects: list[dict] | None = None,
        scenario_name: str = "multi_object",
    ) -> dict[str, object]:
        """Generate a multi-object scenario.
        
        Args:
            objects: List of dicts with keys:
                - name: object identifier
                - enabled: bool (default True)
                - start_range_m: float
                - stop_range_m: float
                - radial_velocity_mps: float
                - rcs_dbsm: float
                - azimuth_deg: float
                - elevation_deg: float
        """
        if not self.state.osi_available:
            return {
                "ok": False,
                "file_path": None,
                "message_count": 0,
                "duration_s": 0.0,
                "preview": None,
                "error": self.state.osi_error,
            }
        
        if objects is None:
            objects = []
        
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if not output_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{scenario_name}_{timestamp}.osi"
            elif not output_filename.lower().endswith(".osi"):
                output_filename += ".osi"
            
            output_path = output_dir / output_filename
            
            params = MultiObjectParams(
                sensor_id=sensor_id,
                update_interval_s=update_interval_s,
                duration_s=duration_s,
                objects=objects,
            )
            
            messages, preview = MultiObjectTemplate.generate(params)
            
            if len(messages) == 0:
                error_msg = "Generated scenario contains no messages"
                self._log_generation(
                    template_type="multi_object",
                    parameters={"object_count": len(objects), "duration_s": duration_s},
                    output_filename=str(output_path),
                    message_count=0,
                    bytes_written=0,
                    duration_s=0.0,
                    success=False,
                    error=error_msg,
                )
                return {
                    "ok": False,
                    "file_path": None,
                    "message_count": 0,
                    "duration_s": 0.0,
                    "preview": None,
                    "error": error_msg,
                }
            
            result = write_osi_file(messages, str(output_path))
            
            if not result["ok"]:
                self._log_generation(
                    template_type="multi_object",
                    parameters={"object_count": len(objects), "duration_s": duration_s},
                    output_filename=str(output_path),
                    message_count=0,
                    bytes_written=0,
                    duration_s=preview.duration_s,
                    success=False,
                    error=result["error"],
                )
                return {
                    "ok": False,
                    "file_path": None,
                    "message_count": len(messages),
                    "duration_s": preview.duration_s,
                    "preview": None,
                    "error": result["error"],
                }
            
            self.state.last_generated_file = output_path
            self.state.last_preview = preview
            self._log_generation(
                template_type="multi_object",
                parameters={"object_count": len(objects), "duration_s": duration_s},
                output_filename=str(output_path),
                message_count=len(messages),
                bytes_written=result["bytes_written"],
                duration_s=preview.duration_s,
                success=True,
            )
            
            return {
                "ok": True,
                "file_path": str(output_path),
                "message_count": len(messages),
                "duration_s": preview.duration_s,
                "preview": self._preview_to_dict(preview),
                "error": None,
            }
        
        except Exception as ex:
            error_msg = str(ex)
            self._log_generation(
                template_type="multi_object",
                parameters={},
                output_filename="",
                message_count=0,
                bytes_written=0,
                duration_s=0.0,
                success=False,
                error=error_msg,
            )
            return {
                "ok": False,
                "file_path": None,
                "message_count": 0,
                "duration_s": 0.0,
                "preview": None,
                "error": error_msg,
            }
    
    def generate_azimuth_sweep(
        self,
        output_dir: str | Path = "./scenarios",
        output_filename: str | None = None,
        sensor_id: int = 1,
        update_interval_s: float = 0.1,
        duration_s: float = 10.0,
        range_m: float = 100.0,
        start_azimuth_deg: float = -180.0,
        stop_azimuth_deg: float = 180.0,
        radial_velocity_mps: float = 0.0,
        rcs_dbsm: float = 10.0,
        elevation_deg: float = 0.0,
        scenario_name: str = "azimuth_sweep",
    ) -> dict[str, object]:
        """Generate an azimuth sweep scenario."""
        if not self.state.osi_available:
            return {
                "ok": False,
                "file_path": None,
                "message_count": 0,
                "duration_s": 0.0,
                "preview": None,
                "error": self.state.osi_error,
            }
        
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if not output_filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{scenario_name}_{timestamp}.osi"
            elif not output_filename.lower().endswith(".osi"):
                output_filename += ".osi"
            
            output_path = output_dir / output_filename
            
            params = AzimuthSweepParams(
                sensor_id=sensor_id,
                update_interval_s=update_interval_s,
                duration_s=duration_s,
                range_m=range_m,
                start_azimuth_deg=start_azimuth_deg,
                stop_azimuth_deg=stop_azimuth_deg,
                radial_velocity_mps=radial_velocity_mps,
                rcs_dbsm=rcs_dbsm,
                elevation_deg=elevation_deg,
            )
            
            messages, preview = AzimuthSweepTemplate.generate(params)
            
            if len(messages) == 0:
                error_msg = "Generated scenario contains no messages"
                self._log_generation(
                    template_type="azimuth_sweep",
                    parameters=params.__dict__,
                    output_filename=str(output_path),
                    message_count=0,
                    bytes_written=0,
                    duration_s=0.0,
                    success=False,
                    error=error_msg,
                )
                return {
                    "ok": False,
                    "file_path": None,
                    "message_count": 0,
                    "duration_s": 0.0,
                    "preview": None,
                    "error": error_msg,
                }
            
            result = write_osi_file(messages, str(output_path))
            
            if not result["ok"]:
                self._log_generation(
                    template_type="azimuth_sweep",
                    parameters=params.__dict__,
                    output_filename=str(output_path),
                    message_count=0,
                    bytes_written=0,
                    duration_s=preview.duration_s,
                    success=False,
                    error=result["error"],
                )
                return {
                    "ok": False,
                    "file_path": None,
                    "message_count": len(messages),
                    "duration_s": preview.duration_s,
                    "preview": None,
                    "error": result["error"],
                }
            
            self.state.last_generated_file = output_path
            self.state.last_preview = preview
            self._log_generation(
                template_type="azimuth_sweep",
                parameters=params.__dict__,
                output_filename=str(output_path),
                message_count=len(messages),
                bytes_written=result["bytes_written"],
                duration_s=preview.duration_s,
                success=True,
            )
            
            return {
                "ok": True,
                "file_path": str(output_path),
                "message_count": len(messages),
                "duration_s": preview.duration_s,
                "preview": self._preview_to_dict(preview),
                "error": None,
            }
        
        except Exception as ex:
            error_msg = str(ex)
            self._log_generation(
                template_type="azimuth_sweep",
                parameters={},
                output_filename="",
                message_count=0,
                bytes_written=0,
                duration_s=0.0,
                success=False,
                error=error_msg,
            )
            return {
                "ok": False,
                "file_path": None,
                "message_count": 0,
                "duration_s": 0.0,
                "preview": None,
                "error": error_msg,
            }
    
    def get_generation_logs(self, limit: int = 50) -> list[dict[str, object]]:
        """Get generation logs (most recent first)."""
        logs = self.state.generation_logs[-limit:]
        logs.reverse()
        return [
            {
                "timestamp": log.timestamp,
                "template_type": log.template_type,
                "output_filename": log.output_filename,
                "message_count": log.message_count,
                "bytes_written": log.bytes_written,
                "duration_s": log.duration_s,
                "success": log.success,
                "error": log.error,
            }
            for log in logs
        ]

    def validate_osi_file(self, file_path: str | Path | None = None) -> dict[str, object]:
        """Validate a length-prefixed .osi file and count contained messages."""
        path: Path | None
        if file_path is None:
            path = self.state.last_generated_file
        else:
            path = Path(file_path)

        if path is None:
            return {
                "ok": False,
                "file_path": None,
                "exists": False,
                "size_bytes": 0,
                "message_count": 0,
                "error": "No file path provided and no previously generated scenario found.",
            }

        if not path.exists():
            return {
                "ok": False,
                "file_path": str(path),
                "exists": False,
                "size_bytes": 0,
                "message_count": 0,
                "error": f"File does not exist: {path}",
            }

        if not path.is_file():
            return {
                "ok": False,
                "file_path": str(path),
                "exists": True,
                "size_bytes": 0,
                "message_count": 0,
                "error": f"Path is not a file: {path}",
            }

        data = path.read_bytes()
        size_bytes = len(data)
        offset = 0
        message_count = 0

        while offset < size_bytes:
            if size_bytes - offset < 4:
                return {
                    "ok": False,
                    "file_path": str(path),
                    "exists": True,
                    "size_bytes": size_bytes,
                    "message_count": message_count,
                    "error": "Invalid .osi framing: incomplete 4-byte length prefix.",
                }

            msg_len = struct.unpack_from("<L", data, offset)[0]
            offset += 4

            if msg_len < 0:
                return {
                    "ok": False,
                    "file_path": str(path),
                    "exists": True,
                    "size_bytes": size_bytes,
                    "message_count": message_count,
                    "error": "Invalid .osi framing: negative message length.",
                }

            if offset + msg_len > size_bytes:
                return {
                    "ok": False,
                    "file_path": str(path),
                    "exists": True,
                    "size_bytes": size_bytes,
                    "message_count": message_count,
                    "error": "Invalid .osi framing: message length exceeds file size.",
                }

            offset += msg_len
            message_count += 1

        return {
            "ok": True,
            "file_path": str(path),
            "exists": True,
            "size_bytes": size_bytes,
            "message_count": message_count,
            "error": None,
        }

    def transfer_file(
        self,
        local_path: str | Path | None,
        remote_path: str | Path,
        transfer_method: str = "local_copy",
    ) -> dict[str, object]:
        """Transfer a generated scenario file using a registered transfer adapter."""
        src_path: Path | None
        if local_path is None:
            src_path = self.state.last_generated_file
        else:
            src_path = Path(local_path)

        if src_path is None:
            error_msg = "No local file path provided and no previously generated scenario found."
            self._log_transfer("", str(remote_path), transfer_method, 0, False, error_msg)
            return {
                "ok": False,
                "local_path": None,
                "remote_path": str(remote_path),
                "transfer_method": transfer_method,
                "bytes_transferred": 0,
                "error": error_msg,
            }

        dst_path = Path(remote_path)
        result = self.transfer_service.transfer(src_path, dst_path, method=transfer_method)

        self._log_transfer(
            local_path=result.local_path,
            remote_path=result.remote_path,
            transfer_method=result.method,
            bytes_transferred=result.bytes_transferred,
            success=result.ok,
            error=result.error,
        )

        return {
            "ok": result.ok,
            "local_path": result.local_path,
            "remote_path": result.remote_path,
            "transfer_method": result.method,
            "bytes_transferred": result.bytes_transferred,
            "error": result.error,
        }

    def get_transfer_logs(self, limit: int = 50) -> list[dict[str, object]]:
        """Get transfer logs (most recent first)."""
        logs = self.state.transfer_logs[-limit:]
        logs.reverse()
        return [
            {
                "timestamp": log.timestamp,
                "local_path": log.local_path,
                "remote_path": log.remote_path,
                "transfer_method": log.transfer_method,
                "bytes_transferred": log.bytes_transferred,
                "success": log.success,
                "error": log.error,
            }
            for log in logs
        ]
    
    def _log_generation(
        self,
        template_type: str,
        parameters: dict[str, Any],
        output_filename: str,
        message_count: int,
        bytes_written: int,
        duration_s: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Log a generation event."""
        log = GenerationLog(
            timestamp=datetime.now().isoformat(),
            template_type=template_type,
            parameters=parameters,
            output_filename=output_filename,
            message_count=message_count,
            bytes_written=bytes_written,
            duration_s=duration_s,
            success=success,
            error=error,
        )
        self.state.generation_logs.append(log)

    def _log_transfer(
        self,
        local_path: str,
        remote_path: str,
        transfer_method: str,
        bytes_transferred: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Log a transfer event."""
        log = TransferLog(
            timestamp=datetime.now().isoformat(),
            local_path=local_path,
            remote_path=remote_path,
            transfer_method=transfer_method,
            bytes_transferred=bytes_transferred,
            success=success,
            error=error,
        )
        self.state.transfer_logs.append(log)
    
    def _preview_to_dict(self, preview: ScenarioPreview) -> dict[str, object]:
        """Convert preview to dict for serialization."""
        return {
            "duration_s": preview.duration_s,
            "message_count": preview.message_count,
            "object_count": preview.object_count,
            "min_range_m": preview.min_range_m,
            "max_range_m": preview.max_range_m,
            "min_azimuth_deg": preview.min_azimuth_deg,
            "max_azimuth_deg": preview.max_azimuth_deg,
            "min_velocity_mps": preview.min_velocity_mps,
            "max_velocity_mps": preview.max_velocity_mps,
            "min_rcs_dbsm": preview.min_rcs_dbsm,
            "max_rcs_dbsm": preview.max_rcs_dbsm,
            "estimated_file_size_bytes": preview.estimated_file_size_bytes,
            "warnings": preview.warnings,
        }
