#!/bin/bash

set -e

# Configuration
SERVICE_NAME="adsb-boot-test"
INSTALL_DIR="/opt/adsb-boot-test"
CONFIG_DIR="/etc/adsb-boot-test"
SERVICE_FILE="/etc/systemd/system/adsb-boot-test.service"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Installing ADS-B Boot Test Service to $INSTALL_DIR..."

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
if command -v uv &> /dev/null; then
    echo "   Using uv (fast installer)..."
    uv pip install -r "$SOURCE_DIR/requirements.txt" --python ./venv/bin/python
else
    echo "   Using pip (uv not available - consider installing it for faster deploys)..."
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r "$SOURCE_DIR/requirements.txt"
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
cp "$SOURCE_DIR/adsb-boot-test-service.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/test-feeder-image.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/test-vm-image.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/run-selenium-as-testuser.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/setup-tftp-iscsi.sh" "$INSTALL_DIR/"
cp "$SOURCE_DIR/metrics.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/boot-test-metrics-cli.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/serial_console_reader.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/power-toggle-kasa.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/power-toggle-unifi.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/generate-api-key.py" "$INSTALL_DIR/"

cp -r "$SOURCE_DIR/selenium_framework" "$INSTALL_DIR/"
cp -r "$SOURCE_DIR/boot_test_lib" "$INSTALL_DIR/"
cp -r "$SOURCE_DIR/hardware_backends" "$INSTALL_DIR/"

chmod +x "$INSTALL_DIR"/*.py
chmod +x "$INSTALL_DIR"/*.sh

# Create required directories
echo "📁 Creating required directories..."
mkdir -p "$INSTALL_DIR/test-images"
mkdir -p "$INSTALL_DIR/serial-logs"
mkdir -p "$INSTALL_DIR/setup-logs"
mkdir -p /var/lib/adsb-boot-test
chmod 755 /var/lib/adsb-boot-test

# Install systemd service
echo "🔧 Installing systemd service..."
cp "$SOURCE_DIR/adsb-boot-test.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "🎉 Installation complete!"
