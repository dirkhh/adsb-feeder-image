#!/bin/bash

set -e

# Configuration
SERVICE_NAME="adsb-test-service"
INSTALL_DIR="/opt/adsb-test-service"
CONFIG_DIR="/etc/adsb-test-service"
SERVICE_FILE="/etc/systemd/system/adsb-test-service.service"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SOURCE_DIR")")")"

echo "🚀 Installing ADS-B Test Service to $INSTALL_DIR..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

# Create installation directory
echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Create dedicated virtual environment
echo "🐍 Creating virtual environment..."
if [[ -d "venv" ]]; then
    echo "   Virtual environment already exists, updating..."
else
    python3 -m venv venv
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
./venv/bin/pip install --upgrade pip
if [[ -f "$SOURCE_DIR/requirements.txt" ]]; then
    echo "   Using requirements.txt file..."
    ./venv/bin/pip install -r "$SOURCE_DIR/requirements.txt"
else
    echo "   Installing individual packages..."
    ./venv/bin/pip install flask requests selenium webdriver-manager beautifulsoup4 python-kasa
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

# Copy service files
echo "📋 Copying service files..."
cp "$SOURCE_DIR/adsb-test-service.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/test-feeder-image.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/run-selenium-test.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/setup-tftp-iscsi.sh" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR"/*.py
chmod +x "$INSTALL_DIR"/*.sh

# Create test images directory
echo "📁 Creating test images directory..."
mkdir -p "$INSTALL_DIR/test-images"

# Install systemd service
echo "🔧 Installing systemd service..."
cp "$SOURCE_DIR/adsb-test-service.service" "$SERVICE_FILE"

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
echo "📁 Installation structure:"
echo "   Service files: $INSTALL_DIR/"
echo "   Virtual env:   $INSTALL_DIR/venv/"
echo "   Test images:   $INSTALL_DIR/test-images/"
echo "   Config:        $CONFIG_DIR/config.json"
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
echo "7. Manual service management:"
echo "   sudo systemctl stop $SERVICE_NAME"
echo "   sudo systemctl restart $SERVICE_NAME"
echo "   sudo systemctl disable $SERVICE_NAME"
echo ""
