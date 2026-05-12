"""
TCV907 Radar Service - Backend service for radar connection and speed data management

Wraps the TCV907RadarClient to provide high-level radar operations
with FastAPI-compatible data structures and async/sync bridge.
"""

import sys
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from dataclasses import asdict
from datetime import datetime

# Add project root to path to import radar client
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tcv907_radar_client import TCV907RadarClient, SpeedMeasurement, RadarConnectionState

logger = logging.getLogger(__name__)


class TCV907RadarService:
    """Service for managing TCV907 radar connection and speed data"""
    
    _instance: Optional['TCV907RadarService'] = None
    
    def __new__(cls):
        """Implement singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize radar service"""
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.client: Optional[TCV907RadarClient] = None
        self.radar_ip = "192.168.4.1"
        self.radar_port = 20000
        self.connection_callbacks: List[Callable[[str], None]] = []
        self.speed_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.error_callbacks: List[Callable[[str], None]] = []
        self.last_error: Optional[str] = None
        logger.info("TCV907RadarService initialized")
    
    def set_radar_config(self, ip: str, port: int) -> None:
        """Set radar IP and port configuration"""
        self.radar_ip = ip
        self.radar_port = port
        logger.info(f"Radar config updated: {ip}:{port}")
    
    def _on_speed_data(self, measurement: SpeedMeasurement) -> None:
        """Internal callback for speed data"""
        try:
            # Convert measurement to JSON-serializable dict
            data = {
                'speed_kmh': measurement.speed_kmh,
                'timestamp': measurement.timestamp.isoformat(),
                'packet_number': measurement.packet_number,
                'raw_data_hex': measurement.raw_data.hex()
            }
            
            # Notify all subscribers
            for callback in self.speed_callbacks:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Error in speed callback: {e}")
        except Exception as e:
            logger.error(f"Error processing speed data: {e}")
    
    def _on_connection_changed(self, state: RadarConnectionState) -> None:
        """Internal callback for connection state changes"""
        try:
            state_str = state.value
            logger.info(f"Radar connection state changed: {state_str}")
            
            # Notify all subscribers
            for callback in self.connection_callbacks:
                try:
                    callback(state_str)
                except Exception as e:
                    logger.error(f"Error in connection callback: {e}")
        except Exception as e:
            logger.error(f"Error in connection state handler: {e}")
    
    def _on_error(self, error_msg: str) -> None:
        """Internal callback for errors"""
        try:
            self.last_error = error_msg
            logger.error(f"Radar error: {error_msg}")
            
            # Notify all subscribers
            for callback in self.error_callbacks:
                try:
                    callback(error_msg)
                except Exception as e:
                    logger.error(f"Error in error callback: {e}")
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
    
    def connect(self) -> bool:
        """Connect to the radar device"""
        try:
            if self.client and self.client.is_connected:
                logger.warning("Already connected to radar")
                return True
            
            # Create new client with callbacks
            self.client = TCV907RadarClient(
                radar_ip=self.radar_ip,
                radar_port=self.radar_port,
                on_speed_callback=self._on_speed_data,
                on_connection_changed=self._on_connection_changed,
                on_error=self._on_error
            )
            
            # Connect
            success = self.client.connect()
            if success:
                logger.info(f"Successfully connected to radar at {self.radar_ip}:{self.radar_port}")
            else:
                logger.error("Failed to connect to radar")
            
            return success
            
        except Exception as e:
            error_msg = f"Failed to connect to radar: {str(e)}"
            logger.error(error_msg)
            self.last_error = error_msg
            return False
    
    def disconnect(self) -> bool:
        """Disconnect from the radar device"""
        try:
            if self.client:
                self.client.disconnect()
                self.client = None
                logger.info("Disconnected from radar")
                return True
            return False
        except Exception as e:
            error_msg = f"Error disconnecting from radar: {str(e)}"
            logger.error(error_msg)
            self.last_error = error_msg
            return False
    
    def is_connected(self) -> bool:
        """Check if radar is connected"""
        return self.client is not None and self.client.is_connected
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get radar connection and data statistics"""
        if not self.client:
            return {
                'connected': False,
                'state': 'disconnected',
                'radar_ip': self.radar_ip,
                'radar_port': self.radar_port,
                'packets_received': 0,
                'bytes_received': 0,
                'speeds_parsed': 0,
                'parse_errors': 0,
                'uptime_seconds': 0,
                'packet_rate_per_second': 0,
                'speed_history_count': 0,
                'last_error': self.last_error
            }
        
        stats = self.client.get_statistics()
        stats['last_error'] = self.last_error
        return stats
    
    def get_last_speed(self) -> Optional[Dict[str, Any]]:
        """Get the last received speed measurement"""
        if not self.client:
            return None
        
        measurement = self.client.get_last_speed()
        if measurement:
            return {
                'speed_kmh': measurement.speed_kmh,
                'timestamp': measurement.timestamp.isoformat(),
                'packet_number': measurement.packet_number,
                'raw_data_hex': measurement.raw_data.hex()
            }
        return None
    
    def get_speed_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get speed measurement history"""
        if not self.client:
            return []
        
        measurements = self.client.get_speed_history(limit=limit)
        return [
            {
                'speed_kmh': m.speed_kmh,
                'timestamp': m.timestamp.isoformat(),
                'packet_number': m.packet_number,
                'raw_data_hex': m.raw_data.hex()
            }
            for m in measurements
        ]
    
    def clear_history(self) -> None:
        """Clear speed measurement history"""
        if self.client:
            self.client.clear_history()
            logger.info("Speed history cleared")
    
    def subscribe_connection_state(self, callback: Callable[[str], None]) -> None:
        """Subscribe to connection state changes"""
        self.connection_callbacks.append(callback)
    
    def subscribe_speed_data(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to speed data updates"""
        self.speed_callbacks.append(callback)
    
    def subscribe_errors(self, callback: Callable[[str], None]) -> None:
        """Subscribe to error messages"""
        self.error_callbacks.append(callback)
    
    def unsubscribe_connection_state(self, callback: Callable[[str], None]) -> None:
        """Unsubscribe from connection state changes"""
        if callback in self.connection_callbacks:
            self.connection_callbacks.remove(callback)
    
    def unsubscribe_speed_data(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Unsubscribe from speed data updates"""
        if callback in self.speed_callbacks:
            self.speed_callbacks.remove(callback)
    
    def unsubscribe_errors(self, callback: Callable[[str], None]) -> None:
        """Unsubscribe from error messages"""
        if callback in self.error_callbacks:
            self.error_callbacks.remove(callback)


# Singleton instance
_radar_service: Optional[TCV907RadarService] = None


def get_radar_service() -> TCV907RadarService:
    """Get or create the radar service singleton"""
    global _radar_service
    if _radar_service is None:
        _radar_service = TCV907RadarService()
    return _radar_service
