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
cp "$SOURCE_DIR/run_selenium_test.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/run-selenium-as-testuser.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/setup-tftp-iscsi.sh" "$INSTALL_DIR/"
cp "$SOURCE_DIR/metrics.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/boot-test-metrics-cli.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/serial_console_reader.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/power-toggle-kasa.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/power-toggle-unifi.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/generate-api-key.py" "$INSTALL_DIR/"

# Copy selenium_framework directory
echo "📋 Copying selenium framework..."
cp -r "$SOURCE_DIR/selenium_framework" "$INSTALL_DIR/"

# Copy boot_test_lib directory
echo "📋 Copying boot test library..."
cp -r "$SOURCE_DIR/boot_test_lib" "$INSTALL_DIR/"

# Copy hardware_backends directory
echo "📋 Copying hardware backends..."
cp -r "$SOURCE_DIR/hardware_backends" "$INSTALL_DIR/"

chmod +x "$INSTALL_DIR"/*.py
chmod +x "$INSTALL_DIR"/*.sh

# Create test images directory
echo "📁 Creating test images directory..."
mkdir -p "$INSTALL_DIR/test-images"

# Create serial logs directory
echo "📁 Creating serial logs directory..."
mkdir -p "$INSTALL_DIR/serial-logs"

# Create metrics database directory
echo "📁 Creating metrics database directory..."
mkdir -p /var/lib/adsb-boot-test
chmod 755 /var/lib/adsb-boot-test

# Install systemd service
echo "🔧 Installing systemd service..."
cp "$SOURCE_DIR/adsb-boot-test.service" "$SERVICE_FILE"

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
echo "   Metrics DB:    /var/lib/adsb-boot-test/metrics.db"
echo ""
echo "Next steps:"
echo "1. Edit the configuration file:"
echo "   sudo nano $CONFIG_DIR/config.json"
echo ""
echo "2. Set your IP addresses (rpi_ip) and power toggle script (power_toggle_script)"
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
echo "7. View metrics:"
echo "   sudo $INSTALL_DIR/boot-test-metrics-cli.py"
echo "   sudo $INSTALL_DIR/boot-test-metrics-cli.py --stats 7"
echo "   sudo $INSTALL_DIR/boot-test-metrics-cli.py --failures"
echo ""
echo "8. Manual service management:"
echo "   sudo systemctl stop $SERVICE_NAME"
echo "   sudo systemctl restart $SERVICE_NAME"
echo "   sudo systemctl disable $SERVICE_NAME"
echo ""
