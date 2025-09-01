#!/bin/bash

# Pi Deployment Script for E-Trike Passenger Counting System
# This script helps deploy the updated Pi configuration and code

echo "🚀 E-Trike Pi Deployment Script"
echo "================================"

# Check if we're on a Pi or local machine
if [[ "$(uname -m)" == "arm"* ]]; then
    echo "✅ Running on Raspberry Pi"
    PI_MODE=true
else
    echo "💻 Running on local machine"
    PI_MODE=false
fi

echo ""
echo "📋 Current Configuration:"
echo "   Pi ID: PI001"
echo "   City: manila"
echo "   TODA: bltmpc"
echo "   E-Trike: 00001"
echo "   Location: Main Terminal"
echo ""

if [ "$PI_MODE" = true ]; then
    echo "🔧 Pi Setup Mode:"
    echo "1. Installing dependencies..."
    pip3 install -r requirements.txt
    
    echo "2. Testing configuration..."
    python3 -c "
import json
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    print('✅ Config loaded successfully')
    print(f'   Pi ID: {config.get(\"pi_id\", \"Not set\")}')
    print(f'   City: {config.get(\"city\", \"Not set\")}')
    print(f'   TODA: {config.get(\"toda_id\", \"Not set\")}')
    print(f'   E-Trike: {config.get(\"etrike_id\", \"Not set\")}')
except Exception as e:
    print(f'❌ Config error: {e}')
"
    
    echo ""
    echo "3. Testing main script..."
    python3 -m py_compile main.py
    if [ $? -eq 0 ]; then
        echo "✅ Main script compiles successfully"
    else
        echo "❌ Main script has errors"
    fi
    
    echo ""
    echo "🎯 Next Steps:"
    echo "1. Mount the Pi in your e-trike vehicle"
    echo "2. Connect power and camera"
    echo "3. Run: python3 main.py"
    echo "4. Test passenger detection"
    echo "5. Check logs in the 'logs' folder"
    
else
    echo "💻 Local Development Mode:"
    echo "1. Copy these files to your Pi:"
    echo "   - ai-cam/ folder"
    echo "   - requirements.txt"
    echo ""
    echo "2. On the Pi, run:"
    echo "   chmod +x deploy_pi.sh"
    echo "   ./deploy_pi.sh"
    echo ""
    echo "3. Or manually:"
    echo "   cd ai-cam"
    echo "   pip3 install -r requirements.txt"
    echo "   python3 main.py"
fi

echo ""
echo "📱 Dashboard Integration:"
echo "1. Register Pi in dashboard: http://your-dashboard/pi-registration"
echo "2. Use Pi ID: PI001"
echo "3. Apply filters to see Pi-specific data"
echo ""
echo "🔍 Troubleshooting:"
echo "- Check logs/ folder for passenger data"
echo "- Verify camera connection"
echo "- Ensure config.json is readable"
echo "- Check Pi network connectivity"
