#!/usr/bin/env python3
"""
Data sync script for Raspberry Pi to send data to Google server
Run this on the Raspberry Pi to sync logs and historical data
"""

import os
import json
import requests
import time
import zipfile
import tempfile
from datetime import datetime

# Configuration
SERVER_URL = "https://etrikedashboard.com:5001"  # Direct IP access with HTTPS
API_KEY = None  # Optional: for authentication
SYNC_INTERVAL = 5    # 5 seconds
LOG_DIR = "logs"
HISTORICAL_FILE = "historical_summary.json"

def create_data_package():
    """Create a zip file with all log data and historical summary"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with tempfile.NamedTemporaryFile(suffix=f"_data_{timestamp}.zip", delete=False) as temp_zip:
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            
            # Add all log files
            if os.path.exists(LOG_DIR):
                for root, dirs, files in os.walk(LOG_DIR):
                    for file in files:
                        if file.endswith('.json'):
                            file_path = os.path.join(root, file)
                            # Maintain directory structure in zip
                            arcname = os.path.relpath(file_path, '.')
                            zipf.write(file_path, arcname)
            
            # Add historical summary
            if os.path.exists(HISTORICAL_FILE):
                zipf.write(HISTORICAL_FILE)
        
        return temp_zip.name

def upload_data_package(zip_path):
    """Upload the data package to the server"""
    try:
        with open(zip_path, 'rb') as f:
            files = {'data_package': f}
            headers = {}
            
            if API_KEY:
                headers['Authorization'] = f'Bearer {API_KEY}'
            
            # Add debug info and longer timeout
            print(f"🔍 Attempting upload to: {SERVER_URL}/upload-data")
            response = requests.post(
                f"{SERVER_URL}/upload-data",
                files=files,
                headers=headers,
                timeout=60,
                verify=True  # Enable SSL verification for security
            )
            print(f"📡 Response status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"✅ Data uploaded successfully at {datetime.now()}")
                return True
            else:
                print(f"❌ Upload failed: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Upload error: {e}")
        return False
    finally:
        # Clean up temp file
        if os.path.exists(zip_path):
            os.remove(zip_path)

def sync_data():
    """Main sync function"""
    print(f"🔄 Starting data sync at {datetime.now()}")
    
    # Create data package
    zip_path = create_data_package()
    print(f"📦 Created data package: {zip_path}")
    
    # Upload to server
    success = upload_data_package(zip_path)
    
    return success

def main():
    """Run continuous sync"""
    print("🚀 Starting E-Trike data sync service")
    print(f"📍 Server: {SERVER_URL}")
    print(f"⏱️  Sync interval: {SYNC_INTERVAL} seconds")
    
    while True:
        try:
            sync_data()
        except Exception as e:
            print(f"❌ Sync error: {e}")
        
        print(f"⏳ Waiting {SYNC_INTERVAL} seconds until next sync...")
        time.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    main()
