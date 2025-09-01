# AI Camera - E-Trike Passenger Detection & Data Sync

Complete AI camera system for passenger detection and data synchronization.

## Features
- Real-time passenger detection using YOLO
- Data synchronization to cloud
- Web dashboard for monitoring
- Automatic deployment scripts

## Quick Setup
```bash
git clone https://github.com/yourusername/aicam.git
cd aicam
./setup_pi.sh
source .venv/bin/activate
python main.py
```

## Manual Setup
```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
pip uninstall numpy scipy -y
```

## Usage
- **AI Detection**: `python main.py`
- **Data Sync**: `python sync_data.py`
- **Dashboard**: `python dashboard.py`
- **Deploy**: `./deploy_pi.sh`

## Files
- `main.py` - Main AI detection system
- `sync_data.py` - Data synchronization
- `dashboard.py` - Web dashboard
- `config.json` - Configuration
- `setup_pi.sh` - Setup script
- `deploy_pi.sh` - Deployment script
