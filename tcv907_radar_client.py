#!/usr/bin/env python3
"""
TCV907 Radar TCP/UDP Communication Client
Standalone module for receiving speed data from TCV907 radar devices

This module provides a clean interface to:
- Connect to TCV907 radar via UDP
- Parse 5-byte speed packets
- Stream real-time speed measurements
- Handle connection management

Version: 1.0.0
Author: Sántha Máté
License: MIT

Usage:
    from tcv907_radar_client import TCV907RadarClient
    
    client = TCV907RadarClient(
        radar_ip="192.168.4.1",
        radar_port=2000,
        on_speed_callback=handle_speed_data
    )
    
    client.connect()
    # ... use the client ...
    client.disconnect()
"""

import socket
import threading
import time
import re
from datetime import datetime
from typing import Optional, Callable, List, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RadarConnectionState(Enum):
    """Enumeration for radar connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class SpeedMeasurement:
    """Container for a single speed measurement"""
    speed_kmh: float
    timestamp: datetime
    packet_number: int
    raw_data: bytes
    target_id: Optional[int] = None          # Car/target number (byte 5 of frame)
    h_distance: Optional[float] = None       # Horizontal distance (m)
    v_distance: Optional[float] = None       # Vertical distance (m)

    def __repr__(self) -> str:
        extra = ""
        if self.target_id is not None:
            extra = f", target={self.target_id}, h={self.h_distance:.1f}m, v={self.v_distance:.1f}m"
        return f"SpeedMeasurement(speed={self.speed_kmh:.2f} km/h{extra}, time={self.timestamp.strftime('%H:%M:%S.%f')[:-3]})"


class TCV907RadarClient:
    """
    Client for receiving speed data from TCV907 radar device via UDP
    
    The TCV907 radar transmits short UDP packets containing speed data.
    Packet structure:
    - Byte 0: Header/Status
    - Bytes 1-2: Speed value (little-endian unsigned short)
                 Actual speed (km/h) = raw_value / 100.0
    - Remaining byte(s): trailer/checksum/firmware-specific footer
    
    Example speeds:
    - 0x03F7 (1015 raw) = 10.15 km/h
    - 0x07EF (2031 raw) = 20.31 km/h
    - 0x0FA0 (4000 raw) = 40.00 km/h
    """
    
    # UDP packet structure constants
    SPEED_PACKET_SIZE = 24  # Only 24-byte packets are valid speed payloads
    MIN_PACKET_SIZE = 2
    SPEED_SCALE = 100.0    # Divide raw value by 100 to get km/h
    
    # Socket configuration
    DEFAULT_RADAR_IP = "192.168.4.1"
    DEFAULT_RADAR_PORT = 20000
    SOCKET_TIMEOUT = 1.0  # 1 second timeout on socket receive
    RECEIVE_BUFFER_SIZE = 65536  # 64KB buffer for burst packets
    
    def __init__(
        self,
        radar_ip: str = DEFAULT_RADAR_IP,
        radar_port: int = DEFAULT_RADAR_PORT,
        on_speed_callback: Optional[Callable[[SpeedMeasurement], None]] = None,
        on_connection_changed: Optional[Callable[[RadarConnectionState], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize TCV907 Radar Client
        
        Args:
            radar_ip: IP address of the radar (default: 192.168.4.1)
            radar_port: UDP port for radar communication (default: 20000)
            on_speed_callback: Callback function called when speed data is received
            on_connection_changed: Callback for connection state changes
            on_error: Callback for error messages
        """
        self.radar_ip = radar_ip
        self.radar_port = radar_port
        
        self.udp_socket: Optional[socket.socket] = None
        self.is_connected = False
        self.connection_state = RadarConnectionState.DISCONNECTED
        
        # Reading thread management
        self.read_thread: Optional[threading.Thread] = None
        self.stop_reading = False
        
        # Statistics
        self.packets_received = 0
        self.bytes_received = 0
        self.speeds_parsed = 0
        self.parse_errors = 0
        self.start_time: Optional[datetime] = None
        
        # Speed data storage (optional)
        self.speed_history: List[SpeedMeasurement] = []
        self.max_history = 1000  # Keep last 1000 measurements
        
        # Callbacks
        self.on_speed_callback = on_speed_callback
        self.on_connection_changed = on_connection_changed
        self.on_error = on_error
        
        # Thread safety
        self._lock = threading.Lock()
    
    def connect(self) -> bool:
        """Connect to the radar and start receiving data
        
        Note: The radar broadcasts UDP packets to our PC. We LISTEN on the port,
        not connect to the radar. The radar_ip parameter is used for filtering.
        """
        try:
            # Setup UDP socket in LISTEN mode (not connect mode)
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.settimeout(self.SOCKET_TIMEOUT)
            
            # Bind to the port to receive broadcast packets from the radar
            # Bind to all interfaces (0.0.0.0) to receive from any source
            self.udp_socket.bind(("0.0.0.0", self.radar_port))
            
            logger.info(f"UDP socket listening on 0.0.0.0:{self.radar_port}")
            self.is_connected = True
            self._set_connection_state(RadarConnectionState.CONNECTED)

            # Start background reading thread
            self.stop_reading = False
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()

            return True
        except Exception as e:
            error_msg = f"Failed to listen on port {self.radar_port}: {str(e)}"
            logger.error(error_msg)
            self._call_error_callback(error_msg)
            self._set_connection_state(RadarConnectionState.ERROR)
            self.is_connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the radar and stop receiving data"""
        try:
            self.stop_reading = True
            self.is_connected = False
            
            if self.udp_socket:
                self.udp_socket.close()
                self.udp_socket = None
            
            # Wait for read thread to finish (with timeout)
            if self.read_thread and self.read_thread.is_alive():
                self.read_thread.join(timeout=2.0)
            
            self._set_connection_state(RadarConnectionState.DISCONNECTED)
            logger.info("UDP connection closed")
            
        except Exception as e:
            error_msg = f"Error disconnecting from radar: {str(e)}"
            logger.error(error_msg)
            self._call_error_callback(error_msg)
    
    def _read_loop(self) -> None:
        """Main reading loop - runs in background thread"""
        logger.info("Starting UDP read loop")
        
        while not self.stop_reading and self.is_connected:
            try:
                if self.udp_socket:
                    # Receive UDP packet (atomic operation)
                    data, addr = self.udp_socket.recvfrom(4096)
                    
                    # Verify data is from expected radar IP
                    if data and addr[0] == self.radar_ip:
                        with self._lock:
                            self.packets_received += 1
                            self.bytes_received += len(data)
                        
                        # Process only 24-byte packets (speed data payload).
                        if len(data) == self.SPEED_PACKET_SIZE:
                            self._process_speed_packet(data)
                        else:
                            logger.debug(f"Ignoring non-speed packet ({len(data)} bytes), expected {self.SPEED_PACKET_SIZE} bytes")
                
            except socket.timeout:
                # Normal timeout - continue loop
                continue
                
            except Exception as e:
                if self.is_connected:
                    error_msg = f"UDP read error: {str(e)}"
                    logger.error(error_msg)
                    self._call_error_callback(error_msg)
                break
            
            # Small delay to prevent CPU spinning
            time.sleep(0.001)
        
        logger.info("UDP read loop stopped")
    
    def _process_speed_packet(self, data: bytes) -> None:
        """
        Process a received speed packet
        
        Args:
            data: 5-byte packet data
        """
        try:
            speed_kmh = self.parse_speed_packet(data)
            
            if speed_kmh is not None:
                with self._lock:
                    self.speeds_parsed += 1
                    packet_num = self.speeds_parsed
                
                # Create measurement object
                # Extract full measurement fields if available
                full = TCV907RadarClient.parse_full_measurement(data)
                measurement = SpeedMeasurement(
                    speed_kmh=speed_kmh,
                    timestamp=datetime.now(),
                    packet_number=packet_num,
                    raw_data=data,
                    target_id=full[0] if full else None,
                    h_distance=full[2] if full else None,
                    v_distance=full[3] if full else None,
                )
                
                # Store in history
                with self._lock:
                    self.speed_history.append(measurement)
                    if len(self.speed_history) > self.max_history:
                        self.speed_history.pop(0)
                
                # Call user callback
                if self.on_speed_callback:
                    try:
                        self.on_speed_callback(measurement)
                    except Exception as e:
                        logger.error(f"Error in speed callback: {e}")
                
                logger.debug(f"Parsed speed: {speed_kmh:.2f} km/h")
            else:
                with self._lock:
                    self.parse_errors += 1
                logger.warning(f"Failed to parse speed from packet: {data.hex()}")
                
        except Exception as e:
            logger.error(f"Error processing speed packet: {e}")
    
    @staticmethod
    def parse_full_measurement(data: bytes):
        """
        Parse a 24-byte TCV907 speed frame into all 4 fields.

        Frame layout:
          [0-1]  FF FB   sync header
          [2]    14      payload length (20)
          [3]    30      frame type ('0')
          [4]    01      target count
          [5]    CE      target ID  (e.g. 0xCE = 206)
          [6-22] ASCII   "021.4-00.3-060.3\x00"  (speed - h_dist - v_dist)
          [23]          checksum

        The three ASCII fields separated by '-' are:
          Field 0: v_distance   (vertical range, sweeping, e.g. 021.4 m)
          Field 1: h_distance   (horizontal distance, signed, e.g. -00.3 m)
          Field 2: speed_kmh    (speed, negative = approaching, e.g. -060.3 km/h)

        Returns:
            (target_id, speed_kmh, h_distance, v_distance) or None on failure
        """
        try:
            if len(data) != 24:
                return None
            # Byte 5 is the target/car ID
            target_id = data[5]
            # ASCII payload starts at byte 6; strip null terminator and trailing garbage
            ascii_raw = data[6:23].decode("ascii", errors="ignore").rstrip("\x00").strip()
            # Split on '-' keeping the sign on subsequent tokens
            # ascii_raw example: "021.4-00.3-060.3"
            # Split yields: ['021.4', '00.3', '060.3'] - re-attach '-' to tokens 1+
            parts = ascii_raw.split("-")
            if len(parts) < 3:
                logger.warning(f"Unexpected ASCII payload '{ascii_raw}' in {data.hex()}")
                return None
            v_distance  = float(parts[0])                    # e.g. 21.4 m  (range)
            h_distance  = -float(parts[1])                   # e.g. -0.3 m
            speed_kmh   = -float(parts[2].split()[0])        # e.g. -60.3 km/h (neg = approaching)
            logger.debug(
                f"Parsed frame: target={target_id} speed={speed_kmh:.2f} "
                f"h={h_distance:.2f} v={v_distance:.2f} from {data.hex()}"
            )
            return (target_id, speed_kmh, h_distance, v_distance)
        except Exception as e:
            logger.error(f"Error in parse_full_measurement: {e}")
            return None

    @staticmethod
    def parse_speed_packet(data: bytes) -> Optional[float]:
        """
        Parse a TCV907 speed packet and return measured speed in km/h.

        For 24-byte frames the ASCII payload layout is:
          "<v_dist>-<h_dist>-<speed>\x00"
        The LAST field (after the second '-') is the speed.
        E.g. "021.4-00.3-060.3" -> speed = -60.3 km/h (approaching)

        Legacy fallback: bytes 0-1 signed little-endian / 100.
        """
        try:
            if len(data) < 2:
                logger.warning(f"Packet too short for speed decode: {data.hex()}")
                return None

            if len(data) == TCV907RadarClient.SPEED_PACKET_SIZE:
                result = TCV907RadarClient.parse_full_measurement(data)
                if result is not None:
                    _, speed_kmh, _, _ = result
                    return speed_kmh

            # Legacy fallback parser.
            speed_raw = int.from_bytes(data[0:2], "little", signed=True)
            speed_kmh = speed_raw / TCV907RadarClient.SPEED_SCALE
            logger.debug(f"Decoded legacy speed: raw={speed_raw} ({speed_kmh:.2f} km/h) from {data.hex()}")
            return speed_kmh
        except Exception as e:
            logger.error(f"Error parsing speed packet: {e}")
            return None
    
    def get_statistics(self) -> dict:
        """
        Get connection and reception statistics
        
        Returns:
            Dictionary containing statistics
        """
        with self._lock:
            uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
            packet_rate = self.packets_received / uptime if uptime > 0 else 0
            
            return {
                'connected': self.is_connected,
                'state': self.connection_state.value,
                'radar_ip': self.radar_ip,
                'radar_port': self.radar_port,
                'packets_received': self.packets_received,
                'bytes_received': self.bytes_received,
                'speeds_parsed': self.speeds_parsed,
                'parse_errors': self.parse_errors,
                'uptime_seconds': uptime,
                'packet_rate_per_second': packet_rate,
                'speed_history_count': len(self.speed_history),
            }
    
    def get_last_speed(self) -> Optional[SpeedMeasurement]:
        """Get the last received speed measurement"""
        with self._lock:
            if self.speed_history:
                return self.speed_history[-1]
        return None
    
    def get_speed_history(self, limit: Optional[int] = None) -> List[SpeedMeasurement]:
        """
        Get speed measurement history
        
        Args:
            limit: Maximum number of measurements to return (None = all)
            
        Returns:
            List of SpeedMeasurement objects
        """
        with self._lock:
            if limit:
                return self.speed_history[-limit:].copy()
            return self.speed_history.copy()
    
    def clear_history(self) -> None:
        """Clear speed history"""
        with self._lock:
            self.speed_history.clear()
    
    def _set_connection_state(self, state: RadarConnectionState) -> None:
        """Set connection state and call callback"""
        self.connection_state = state
        if self.on_connection_changed:
            try:
                self.on_connection_changed(state)
            except Exception as e:
                logger.error(f"Error in connection state callback: {e}")
    
    def _call_error_callback(self, error_msg: str) -> None:
        """Call error callback"""
        if self.on_error:
            try:
                self.on_error(error_msg)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")


# Example usage
if __name__ == "__main__":
    """Demo of TCV907RadarClient"""
    
    def on_speed_data(measurement: SpeedMeasurement):
        print(f"  ✓ {measurement}")
    
    def on_connection_changed(state: RadarConnectionState):
        print(f"Connection state: {state.value}")
    
    def on_error(error_msg: str):
        print(f"ERROR: {error_msg}")
    
    # Create client
    client = TCV907RadarClient(
        radar_ip="192.168.4.1",
        radar_port=20000,
        on_speed_callback=on_speed_data,
        on_connection_changed=on_connection_changed,
        on_error=on_error
    )
    
    # Connect and run for 30 seconds
    if client.connect():
        print("Connected to radar, receiving data...")
        try:
            time.sleep(30)
        except KeyboardInterrupt:
            print("Interrupted by user")
        finally:
            client.disconnect()
            stats = client.get_statistics()
            print(f"\nStatistics: {stats}")
    else:
        print("Failed to connect to radar")
