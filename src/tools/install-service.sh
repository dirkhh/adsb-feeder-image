#!/bin/bash
"""
Installation script for the ADS-B Test Service

This script:
1. Installs required Python dependencies
2. Creates configuration directory and files
3. Installs systemd service
4. Sets up logging
5. Enables and starts the service
"""

set -e

# Configuration
SERVICE_NAME="adsb-test-service"
CONFIG_DIR="/etc/adsb-test-service"
SERVICE_FILE="/etc/systemd/system/adsb-test-service.service"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SOURCE_DIR")")"

echo "🚀 Installing ADS-B Test Service..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
cd "$PROJECT_ROOT"
if [[ -f ".venv/bin/pip" ]]; then
    .venv/bin/pip install flask requests
else
    echo "❌ Virtual environment not found. Please run the project setup first."
    exit 1
fi

# Create configuration directory
echo "📁 Creating configuration directory..."
mkdir -p "$CONFIG_DIR"

# Create configuration file if it doesn't exist
if [[ ! -f "$CONFIG_DIR/config.json" ]]; then
    echo "⚙️ Creating configuration file..."
    cp "$SOURCE_DIR/config.json.example" "$CONFIG_DIR/config.json"
    echo "✅ Configuration created at $CONFIG_DIR/config.json"
    echo "   Please edit this file to set your IP addresses!"
else
    echo "✅ Configuration file already exists"
fi

# Install systemd service
echo "🔧 Installing systemd service..."
cp "$SOURCE_DIR/adsb-test-service.service" "$SERVICE_FILE"

# Update service file paths
sed -i "s|/home/hohndel/src/adsb-feeder-image|$PROJECT_ROOT|g" "$SERVICE_FILE"

# Setup logging (systemd will handle log collection)
echo "📝 Setting up logging..."
echo "   Logs will be available via: journalctl -u $SERVICE_NAME"

# Reload systemd
echo "🔄 Reloading systemd..."
systemctl daemon-reload

# Enable service
echo "✅ Enabling service..."
systemctl enable "$SERVICE_NAME"

echo ""
echo "🎉 Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit the configuration file:"
echo "   sudo nano $CONFIG_DIR/config.json"
echo ""
echo "2. Set your IP addresses (rpi_ip and kasa_ip)"
echo ""
echo "3. Start the service:"
echo "   sudo systemctl start $SERVICE_NAME"
echo ""
echo "4. Check service status:"
echo "   sudo systemctl status $SERVICE_NAME"
echo ""
echo "5. View logs:"
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo "   sudo journalctl -u $SERVICE_NAME --since '1 hour ago'"
echo ""
echo "6. Test the API:"
echo "   curl -X POST http://localhost:9456/api/trigger-boot-test \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"url\": \"https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6-beta.6/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz\"}'"
echo ""
