#!/usr/bin/env python3
"""
GPS Data Sender for E-Trike Dashboard
This script reads GPS data from VK-162 USB GPS receiver and sends it to the dashboard.
"""

import serial
import pynmea2
import time
import requests
import json
import sys
from datetime import datetime
import pytz

class GPSSender:
    def __init__(self, pi_id, dashboard_url="https://etrikedashboard.com"):
        self.pi_id = pi_id
        self.dashboard_url = dashboard_url
        self.serial_port = None
        self.last_position = None
        
    def connect_gps(self, port="/dev/ttyUSB0", baudrate=9600):
        """Connect to VK-162 GPS receiver"""
        try:
            self.serial_port = serial.Serial(port, baudrate, timeout=1)
            print(f"✅ Connected to GPS receiver on {port}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to GPS receiver: {e}")
            return False
    
    def read_gps_data(self):
        """Read GPS data from serial port"""
        if not self.serial_port:
            return None
            
        try:
            line = self.serial_port.readline().decode('ascii', errors='ignore')
            if line.startswith('$GPRMC'):
                msg = pynmea2.parse(line)
                if msg.latitude and msg.longitude:
                    return {
                        'pi_id': self.pi_id,
                        'latitude': float(msg.latitude),
                        'longitude': float(msg.longitude),
                        'speed': float(msg.spd_over_grnd) if msg.spd_over_grnd else 0,
                        'heading': float(msg.true_course) if msg.true_course else 0,
                        'timestamp': int(datetime.now(pytz.timezone('Europe/Madrid')).timestamp())
                    }
        except Exception as e:
            print(f"Error reading GPS data: {e}")
        
        return None
    
    def send_to_dashboard(self, gps_data):
        """Send GPS data to dashboard"""
        try:
            response = requests.post(
                f"{self.dashboard_url}/gps-data",
                json=gps_data,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✅ GPS data sent: {gps_data['latitude']:.6f}, {gps_data['longitude']:.6f}")
                return True
            else:
                print(f"❌ Failed to send GPS data: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending GPS data: {e}")
            return False
    
    def run(self, update_interval=5):
        """Main loop to continuously read and send GPS data"""
        print(f"🚀 Starting GPS data sender for Pi {self.pi_id}")
        print(f"📡 Dashboard URL: {self.dashboard_url}")
        print(f"⏱️  Update interval: {update_interval} seconds")
        print("Press Ctrl+C to stop")
        
        while True:
            try:
                gps_data = self.read_gps_data()
                
                if gps_data:
                    # Only send if position has changed significantly
                    if self.should_send_position(gps_data):
                        self.send_to_dashboard(gps_data)
                        self.last_position = gps_data
                    else:
                        print("📍 Position unchanged, skipping send")
                else:
                    print("⏳ Waiting for GPS signal...")
                
                time.sleep(update_interval)
                
            except KeyboardInterrupt:
                print("\n🛑 Stopping GPS data sender...")
                break
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
                time.sleep(update_interval)
    
    def should_send_position(self, current_data):
        """Check if position has changed enough to warrant sending"""
        if not self.last_position:
            return True
        
        # Calculate distance between last and current position
        lat1, lon1 = self.last_position['latitude'], self.last_position['longitude']
        lat2, lon2 = current_data['latitude'], current_data['longitude']
        
        # Simple distance calculation (not perfectly accurate but good enough)
        lat_diff = abs(lat2 - lat1)
        lon_diff = abs(lon2 - lon1)
        distance = ((lat_diff ** 2) + (lon_diff ** 2)) ** 0.5
        
        # Send if moved more than ~10 meters (roughly 0.0001 degrees)
        return distance > 0.0001

def main():
    if len(sys.argv) < 2:
        print("Usage: python gps_sender.py <pi_id> [dashboard_url] [serial_port]")
        print("Example: python gps_sender.py pi001 http://192.168.1.100:5001 /dev/ttyUSB0")
        sys.exit(1)
    
    pi_id = sys.argv[1]
    dashboard_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:5001"
    serial_port = sys.argv[3] if len(sys.argv) > 3 else "/dev/ttyUSB0"
    
    sender = GPSSender(pi_id, dashboard_url)
    
    if sender.connect_gps(serial_port):
        sender.run()
    else:
        print("❌ Failed to connect to GPS receiver. Exiting.")
        sys.exit(1)

if __name__ == "__main__":
    main()
