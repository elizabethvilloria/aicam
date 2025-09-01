#!/bin/bash
echo "? Setting up AI Camera System on Raspberry Pi..."

# Install system dependencies
sudo apt update
sudo apt install -y python3-venv python3-picamera2 libcamera-apps libcap-dev

# Create virtual environment with system access
python3 -m venv .venv --system-site-packages
source .venv/bin/activate

# Install packages
pip install -r requirements.txt

# Remove conflicting packages (use system versions)
pip uninstall numpy scipy -y

echo "? Setup complete!"
echo "Run: source .venv/bin/activate && python main.py"
echo "For sync: source .venv/bin/activate && python sync_data.py"
