#!/bin/bash
# Setup script for Raspberry Pi data sync

echo "🔧 Setting up E-Trike data sync on Raspberry Pi"

# Install required Python packages
echo "📦 Installing Python packages..."
pip3 install requests

# Create systemd service for auto-start
echo "⚙️  Creating systemd service..."

# Get current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create service file
sudo tee /etc/systemd/system/etrike-sync.service > /dev/null <<EOF
[Unit]
Description=E-Trike Data Sync Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/sync_data.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
echo "🚀 Enabling sync service..."
sudo systemctl daemon-reload
sudo systemctl enable etrike-sync.service

echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Edit sync_data.py and update SERVER_URL to your Google server"
echo "2. Start the sync service: sudo systemctl start etrike-sync"
echo "3. Check status: sudo systemctl status etrike-sync"
echo "4. View logs: sudo journalctl -u etrike-sync -f"
