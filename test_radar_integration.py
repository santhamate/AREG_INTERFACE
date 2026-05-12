#!/usr/bin/env python3
"""
Test script for TCV907 Radar Client and Backend Service Integration

This script tests the radar client functionality and the backend service wrapper.
"""

import sys
import asyncio
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(project_root))

from tcv907_radar_client import TCV907RadarClient, SpeedMeasurement, RadarConnectionState
from backend.app.core.tcv907_radar_service import get_radar_service


def test_radar_client():
    """Test the low-level TCV907RadarClient"""
    print("=" * 70)
    print("Testing TCV907RadarClient (Low-Level)")
    print("=" * 70)
    
    # Collect speed data
    speeds = []
    
    def on_speed_data(measurement: SpeedMeasurement):
        speeds.append(measurement)
        print(f"✓ Received: {measurement}")
    
    def on_connection_changed(state: RadarConnectionState):
        print(f"  Connection: {state.value}")
    
    def on_error(error_msg: str):
        print(f"  ERROR: {error_msg}")
    
    # Create client
    client = TCV907RadarClient(
        radar_ip="192.168.4.1",
        radar_port=20000,
        on_speed_callback=on_speed_data,
        on_connection_changed=on_connection_changed,
        on_error=on_error
    )
    
    # Connect
    print("\n1. Connecting to radar...")
    if client.connect():
        print("✓ Connected!")
        
        # Listen for 5 seconds
        print("\n2. Listening for speed data (5 seconds)...")
        time.sleep(5)
        
        # Get statistics
        print("\n3. Getting statistics...")
        stats = client.get_statistics()
        print(f"   Packets received: {stats['packets_received']}")
        print(f"   Speeds parsed: {stats['speeds_parsed']}")
        print(f"   Parse errors: {stats['parse_errors']}")
        print(f"   Packet rate: {stats['packet_rate_per_second']:.1f} pps")
        
        # Get last speed
        print("\n4. Getting last speed...")
        last = client.get_last_speed()
        if last:
            print(f"   Last speed: {last.speed_kmh:.2f} km/h")
        else:
            print("   No speed data received")
        
        # Disconnect
        print("\n5. Disconnecting...")
        client.disconnect()
        print("✓ Disconnected!")
    else:
        print("✗ Failed to connect")


def test_radar_service():
    """Test the backend TCV907RadarService wrapper"""
    print("\n" + "=" * 70)
    print("Testing TCV907RadarService (Backend Service)")
    print("=" * 70)
    
    service = get_radar_service()
    
    # Configure
    print("\n1. Configuring service...")
    service.set_radar_config("192.168.4.1", 20000)
    print("✓ Service configured")
    
    # Check statistics
    print("\n2. Getting initial statistics...")
    stats = service.get_statistics()
    print(f"   State: {stats['state']}")
    print(f"   Connected: {stats['connected']}")
    
    # Connect
    print("\n3. Connecting through service...")
    if service.connect():
        print("✓ Connected through service!")
        
        # Listen for 5 seconds
        print("\n4. Listening for speed data (5 seconds)...")
        time.sleep(5)
        
        # Get status
        print("\n5. Getting service status...")
        status = service.get_statistics()
        print(f"   Packets: {status['packets_received']}")
        print(f"   Speeds parsed: {status['speeds_parsed']}")
        print(f"   Errors: {status['parse_errors']}")
        
        # Get last speed
        print("\n6. Getting last speed from service...")
        last_speed = service.get_last_speed()
        if last_speed:
            print(f"   Speed: {last_speed['speed_kmh']:.2f} km/h")
            print(f"   Time: {last_speed['timestamp']}")
        else:
            print("   No speed data yet")
        
        # Get history
        print("\n7. Getting speed history...")
        history = service.get_speed_history(limit=5)
        print(f"   History count: {len(history)}")
        for i, m in enumerate(history):
            print(f"     {i+1}. {m['speed_kmh']:.2f} km/h @ {m['timestamp']}")
        
        # Disconnect
        print("\n8. Disconnecting through service...")
        service.disconnect()
        print("✓ Disconnected!")
    else:
        error = status.get('last_error', 'Unknown error')
        print(f"✗ Failed to connect: {error}")


async def test_api_endpoints():
    """Test the FastAPI endpoints (simulated)"""
    print("\n" + "=" * 70)
    print("Testing API Endpoints (Simulated)")
    print("=" * 70)
    
    try:
        import httpx
        
        base_url = "http://localhost:8000/api"
        
        print("\n1. Testing /tcv907/status endpoint...")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/tcv907/status", timeout=5)
            if response.status_code == 200:
                print("✓ Status endpoint working")
                data = response.json()
                print(f"   Connected: {data.get('connected', False)}")
            else:
                print(f"✗ Status endpoint failed: {response.status_code}")
        
        print("\n2. Testing /tcv907/connect endpoint...")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/tcv907/connect",
                json={"ip": "192.168.4.1", "port": 20000},
                timeout=5
            )
            if response.status_code == 200:
                print("✓ Connect endpoint working")
                data = response.json()
                print(f"   OK: {data.get('ok', False)}")
            else:
                print(f"✗ Connect endpoint failed: {response.status_code}")
        
    except ImportError:
        print("\n⚠ httpx not installed - skipping API endpoint tests")
    except Exception as e:
        print(f"\n⚠ Could not test API endpoints: {e}")


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "TCV907 Radar Integration Tests" + " " * 23 + "║")
    print("╚" + "=" * 68 + "╝")
    
    try:
        # Test low-level client
        test_radar_client()
        
        # Test service wrapper
        test_radar_service()
        
        # Test API endpoints (requires running backend)
        # asyncio.run(test_api_endpoints())
        
    except KeyboardInterrupt:
        print("\n\n⏹ Tests interrupted by user")
    except Exception as e:
        print(f"\n\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
