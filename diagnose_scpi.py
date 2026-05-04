"""
SCPI Connection Diagnostics Tool

Helps troubleshoot SCPI connection issues with AREG800A.
Usage: python diagnose_scpi.py
"""

import asyncio
import socket
from pathlib import Path


async def test_hislip_connection(host: str = "127.0.0.1", port: int = 4880) -> dict:
    """Test HiSLIP (TCP) connection to device."""
    print(f"\n🔍 Testing HiSLIP connection to {host}:{port}...")
    
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5.0
        )
        writer.close()
        await writer.wait_closed()
        print(f"✅ HiSLIP connection successful: {host}:{port} is reachable")
        return {"ok": True, "message": "HiSLIP connection successful"}
    except asyncio.TimeoutError:
        print(f"❌ Connection timeout: {host}:{port} is not responding (5s timeout)")
        return {"ok": False, "message": f"Connection timeout to {host}:{port}"}
    except ConnectionRefusedError:
        print(f"❌ Connection refused: {host}:{port} - Device not listening or wrong port")
        return {"ok": False, "message": f"Connection refused to {host}:{port}"}
    except OSError as e:
        print(f"❌ Network error: {e}")
        return {"ok": False, "message": f"Network error: {e}"}


async def test_socket_connection(host: str = "127.0.0.1", port: int = 5025) -> dict:
    """Test raw Socket connection to device."""
    print(f"\n🔍 Testing Socket connection to {host}:{port}...")
    
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5.0
        )
        writer.close()
        await writer.wait_closed()
        print(f"✅ Socket connection successful: {host}:{port} is reachable")
        return {"ok": True, "message": "Socket connection successful"}
    except asyncio.TimeoutError:
        print(f"❌ Connection timeout: {host}:{port} is not responding (5s timeout)")
        return {"ok": False, "message": f"Connection timeout to {host}:{port}"}
    except ConnectionRefusedError:
        print(f"❌ Connection refused: {host}:{port} - Device not listening or wrong port")
        return {"ok": False, "message": f"Connection refused to {host}:{port}"}
    except OSError as e:
        print(f"❌ Network error: {e}")
        return {"ok": False, "message": f"Network error: {e}"}


def check_localhost():
    """Check if localhost (127.0.0.1) is reachable."""
    print("\n🔍 Checking localhost (127.0.0.1)...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", 1))
        sock.close()
        
        if result == 0:
            print("✅ Localhost is reachable")
            return True
        else:
            print("⚠️ Localhost (127.0.0.1) test inconclusive")
            return True  # Not necessarily a problem
    except Exception as e:
        print(f"⚠️ Could not check localhost: {e}")
        return True


async def main():
    print("=" * 60)
    print("SCPI CONNECTION DIAGNOSTICS")
    print("=" * 60)
    
    # Check backend is running
    print("\n📋 Configuration:")
    print(f"  Default HiSLIP host: 127.0.0.1")
    print(f"  Default HiSLIP port: 4880")
    print(f"  Default Socket host: 127.0.0.1")
    print(f"  Default Socket port: 5025")
    print(f"  Command timeout: 3000 ms")
    
    # Check localhost
    check_localhost()
    
    # Test HiSLIP
    hislip = await test_hislip_connection("127.0.0.1", 4880)
    
    # Test Socket
    socket_result = await test_socket_connection("127.0.0.1", 5025)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 DIAGNOSIS SUMMARY:")
    print("=" * 60)
    
    if not hislip["ok"] and not socket_result["ok"]:
        print("\n❌ CRITICAL: Neither HiSLIP nor Socket connection is available")
        print("\n🔧 TROUBLESHOOTING STEPS:")
        print("1. Verify AREG800A device is powered on and running")
        print("2. Verify device network connectivity:")
        print("   - Device IP address (default: 127.0.0.1 for simulator)")
        print("   - Device HiSLIP port (default: 4880)")
        print("3. Try connecting via different host/port:")
        print("   - Edit host/port in UI before clicking Connect")
        print("4. Check firewall/network settings:")
        print("   - Firewall may be blocking ports 4880 (HiSLIP) or 5025 (Socket)")
        print("5. Try ping the device first:")
        print("   - Windows: ping <device_ip>")
        print("   - Linux/Mac: ping <device_ip>")
        print("6. Check if device is running AREG simulator (if using simulator)")
    elif hislip["ok"]:
        print("\n✅ HiSLIP connection is available")
        print("   Use protocol: 'hislip'")
        print("   Host: 127.0.0.1")
        print("   Port: 4880")
    elif socket_result["ok"]:
        print("\n✅ Socket connection is available")
        print("   Use protocol: 'socket'")
        print("   Host: 127.0.0.1")
        print("   Port: 5025")
    
    print("\n💡 NEXT STEPS:")
    print("1. Open the application at http://127.0.0.1:5173")
    print("2. Enter the correct host and port in the Connection section")
    print("3. Select the appropriate protocol (HiSLIP or Socket)")
    print("4. Click 'Connect' button")
    print("5. If still failing, check:")
    print("   - Device IP address (ask device administrator)")
    print("   - Device port configuration (check device manual)")
    print("   - Network connectivity (ping device)")
    print("   - Firewall rules (check if ports are blocked)")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
