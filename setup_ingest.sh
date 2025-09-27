#!/bin/bash
# Setup script for ingest_mirror.py
# This script automatically detects the correct paths and sets up environment variables

# Get the current user and directory
CURRENT_USER=$(whoami)
CURRENT_DIR=$(pwd)

# Find the logs directory
if [ -d "logs" ]; then
    LOG_ROOT="$CURRENT_DIR/logs"
elif [ -d "../logs" ]; then
    LOG_ROOT="$CURRENT_DIR/../logs"
elif [ -d "/home/$CURRENT_USER/Desktop/aicam/logs" ]; then
    LOG_ROOT="/home/$CURRENT_USER/Desktop/aicam/logs"
elif [ -d "/home/$CURRENT_USER/aicam/logs" ]; then
    LOG_ROOT="/home/$CURRENT_USER/aicam/logs"
else
    echo "Error: Could not find logs directory"
    echo "Please ensure you're in the aicam directory or set LOG_ROOT manually"
    exit 1
fi

echo "Detected logs directory: $LOG_ROOT"

# Set environment variables
export INGEST_URL="https://etrikedashboard.com"
export INGEST_KEY="super-long-random-string-12345"
export PI_ID="PI005"
export LOG_ROOT="$LOG_ROOT"
export INGEST_INTERVAL=5
export MIRROR_VERBOSE=1

echo "Environment variables set:"
echo "  INGEST_URL: $INGEST_URL"
echo "  PI_ID: $PI_ID"
echo "  LOG_ROOT: $LOG_ROOT"
echo "  INGEST_INTERVAL: $INGEST_INTERVAL"
echo "  MIRROR_VERBOSE: $MIRROR_VERBOSE"
echo ""
echo "Now you can run: python3 ingest_mirror.py"
