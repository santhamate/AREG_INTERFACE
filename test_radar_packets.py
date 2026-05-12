#!/usr/bin/env python3
"""
Test program to receive and display raw UDP packets from TCV907 radar device.

Usage:
    python test_radar_packets.py [--host 192.168.4.1] [--port 20000] [--timeout 5]

This program listens for UDP packets from the radar and displays them in hex format.
"""

import socket
import sys
import argparse
from datetime import datetime
from pathlib import Path


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Receive and display raw UDP packets from TCV907 radar device"
    )
    parser.add_argument(
        "--host",
        default="192.168.4.1",
        help="Radar device IP address (default: 192.168.4.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=20000,
        help="Radar UDP port (default: 20000)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Socket timeout in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--mode",
        choices=["listen", "connect"],
        default="listen",
        help="Receive mode: 'listen' = bind to port and receive broadcasts (default), 'connect' = connect to device",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Number of packets to receive (0 = unlimited, default: 0)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional: save packets to CSV file (default: None)",
    )
    return parser.parse_args()


def format_packet(packet_num, data, source_ip):
    """Format packet data for display"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_data = data.hex().upper()
    byte_count = len(data)
    
    # Show individual bytes
    bytes_list = " ".join(f"{b:02X}" for b in data)
    
    # Decode full measurement for 24-byte speed packets.
    from tcv907_radar_client import TCV907RadarClient
    full = None
    if byte_count == 24:
        full = TCV907RadarClient.parse_full_measurement(data)

    output = f"\n{'='*80}\n"
    output += f"Packet #{packet_num:4d} | {timestamp} | From {source_ip}\n"
    output += f"{'='*80}\n"
    output += f"Length:  {byte_count} bytes\n"
    output += f"Hex:     {hex_data}\n"
    output += f"Bytes:   {bytes_list}\n"

    if full:
        target_id, speed_kmh, h_distance, v_distance = full
        output += f"Target:  {target_id}\n"
        output += f"Speed:   {speed_kmh:8.2f} km/h\n"
        output += f"H-dist:  {h_distance:8.2f} m\n"
        output += f"V-dist:  {v_distance:8.2f} m\n"
    elif byte_count != 24:
        output += "Info:    non-speed packet (ignored for speed decode)\n"
    
    # Show additional info for longer packets
    if byte_count > 2:
        remaining = data[2:].hex().upper()
        output += f"Extra:   {remaining}\n"
    
    return output


def main():
    """Main test receiver"""
    args = parse_args()
    
    print(f"\n📡 TCV907 Radar Packet Receiver")
    print(f"{'='*80}")
    
    if args.mode == "listen":
        print(f"MODE: LISTEN (binding to port {args.port})")
        print(f"This will receive broadcast packets from the radar")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(args.timeout)
        
        try:
            sock.bind(("0.0.0.0", args.port))
            print(f"✅ Listening on 0.0.0.0:{args.port}")
        except PermissionError:
            print(f"❌ Permission denied. Try running as Administrator.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error binding to port: {e}")
            sys.exit(1)
    else:
        print(f"MODE: CONNECT (connecting to {args.host}:{args.port})")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(args.timeout)
        
        try:
            sock.connect((args.host, args.port))
            print(f"✅ Connected to {args.host}:{args.port}")
        except Exception as e:
            print(f"❌ Error connecting: {e}")
            sys.exit(1)
    
    print(f"Socket timeout: {args.timeout}s")
    if args.count > 0:
        print(f"Will receive {args.count} packets and exit")
    else:
        print(f"Waiting for packets (Ctrl+C to stop)...")
    print(f"{'='*80}\n")
    
    packet_num = 0
    packets_data = []
    
    try:
        while True:
            try:
                if args.mode == "listen":
                    data, addr = sock.recvfrom(4096)
                    source_ip = addr[0]
                    source_port = addr[1]
                else:
                    data = sock.recv(4096)
                    source_ip = args.host
                    source_port = args.port
                
                packet_num += 1
                output = format_packet(packet_num, data, source_ip)
                print(output)
                
                if args.output:
                    from tcv907_radar_client import TCV907RadarClient
                    full = TCV907RadarClient.parse_full_measurement(data) if len(data) == 24 else None
                    packets_data.append({
                        'packet_num': packet_num,
                        'timestamp': datetime.now().isoformat(),
                        'source_ip': source_ip,
                        'source_port': source_port,
                        'length': len(data),
                        'hex': data.hex().upper(),
                        'target_id': full[0] if full else None,
                        'speed_kmh': full[1] if full else None,
                        'h_distance': full[2] if full else None,
                        'v_distance': full[3] if full else None,
                    })
                
                if args.count > 0 and packet_num >= args.count:
                    print(f"\n✅ Received {packet_num} packets. Exiting.")
                    break
                    
            except socket.timeout:
                if packet_num == 0:
                    print(f"⏱️  No packets received after {args.timeout}s...")
                    if args.mode == "listen":
                        print(f"   Make sure radar is sending to port {args.port}")
                    else:
                        print(f"   Radar may be broadcasting. Try: python test_radar_packets.py --mode listen")
                    sys.exit(1)
                continue
                
    except KeyboardInterrupt:
        print(f"\n\n⏹️  Interrupted by user")
        
    finally:
        sock.close()
    
    print(f"\n{'='*80}")
    print(f"Summary: Received {packet_num} packets")
    print(f"{'='*80}\n")
    
    if args.output and packets_data:
        try:
            import csv
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            fieldnames = ['packet_num', 'timestamp', 'source_ip', 'source_port', 'length', 'hex', 'target_id', 'speed_kmh', 'h_distance', 'v_distance']
            with open(output_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=',')
                writer.writeheader()
                writer.writerows(packets_data)
            
            print(f"✅ Packets exported to: {output_path}\n")
        except Exception as e:
            print(f"❌ Error writing to CSV: {e}\n")


if __name__ == "__main__":
    main()
