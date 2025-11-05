#!/bin/bash
# Deployment script for GitHub Reporter Service

set -e

SERVICE_NAME="github-reporter"
INSTALL_DIR="/opt/adsb-boot-test/github-reporter"
CONFIG_DIR="/etc/adsb-boot-test"
SERVICE_FILE="/etc/systemd/system/github-reporter.service"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Installing GitHub Reporter Service to $INSTALL_DIR..."

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
    uv pip install -r "$SOURCE_DIR/requirements-reporter.txt" --python ./venv/bin/python
else
    echo "   Using pip (uv not available - consider installing it for faster deploys)..."
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r "$SOURCE_DIR/requirements-reporter.txt"
fi

# Create configuration directory
echo "📁 Creating configuration directory..."
mkdir -p "$CONFIG_DIR"

# Copy service files
echo "📋 Copying service files..."
cp "$SOURCE_DIR/github_reporter.py" "$INSTALL_DIR/"
cp "$SOURCE_DIR/../automated-boot-testing/metrics.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/github_reporter.py"

# Create environment file template if it doesn't exist
if [[ ! -f "$CONFIG_DIR/reporter.env" ]]; then
    echo "⚙️ Creating environment configuration template..."
    cat > "$CONFIG_DIR/reporter.env" << 'EOF'
# GitHub Reporter Configuration
# IMPORTANT: Set these values before starting the service

# GitHub Personal Access Token (fine-grained)
# Required permissions: Contents (R/W), Pull Requests (R/W), Metadata (R)
# Generate at: https://github.com/settings/tokens?type=beta
GITHUB_TOKEN=your_github_token_here

# Repository in format "owner/repo"
GITHUB_REPO=dirkhh/adsb-feeder-image

# Path to metrics database
METRICS_DB_PATH=/var/lib/adsb-boot-test/metrics.db

# Poll interval in seconds (default: 60)
POLL_INTERVAL_SECONDS=60

# Health endpoint port (default: 9457)
HEALTH_PORT=9457
EOF
    chmod 600 "$CONFIG_DIR/reporter.env"
    echo "✅ Configuration template created at $CONFIG_DIR/reporter.env"
    echo "   ⚠️  IMPORTANT: Edit this file and set your GITHUB_TOKEN!"
else
    echo "✅ Configuration file already exists at $CONFIG_DIR/reporter.env"
fi

# Install systemd service
echo "🔧 Installing systemd service..."
cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=GitHub Test Results Reporter Service
Documentation=https://github.com/dirkhh/adsb-feeder-image
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/adsb-boot-test/github-reporter

# Load environment from config file
EnvironmentFile=/etc/adsb-boot-test/reporter.env

# Python virtual environment and script
ExecStart=/opt/adsb-boot-test/github-reporter/venv/bin/python3 /opt/adsb-boot-test/github-reporter/github_reporter.py

# Restart configuration
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/adsb-boot-test

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=github-reporter

[Install]
WantedBy=multi-user.target
EOF

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
echo "   Config:        $CONFIG_DIR/reporter.env"
echo "   Metrics DB:    /var/lib/adsb-boot-test/metrics.db"
echo ""
echo "⚠️  IMPORTANT NEXT STEPS:"
echo ""
echo "1. Configure GitHub token:"
echo "   sudo nano $CONFIG_DIR/reporter.env"
echo "   Set GITHUB_TOKEN to your GitHub personal access token"
echo "   Set GITHUB_REPO if different from dirkhh/adsb-feeder-image"
echo ""
echo "2. Generate GitHub token (if you haven't already):"
echo "   Visit: https://github.com/settings/tokens?type=beta"
echo "   Repository: Select your repository"
echo "   Permissions: Contents (R/W), Pull Requests (R/W), Metadata (R)"
echo ""
echo "3. Start the service:"
echo "   sudo systemctl start $SERVICE_NAME"
echo ""
echo "4. Check service status:"
echo "   sudo systemctl status $SERVICE_NAME"
echo ""
echo "5. View logs:"
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "6. Check health endpoint:"
echo "   curl http://localhost:9457/health"
echo ""
echo "7. Test with a release:"
echo "   Create a new release on GitHub and watch the logs"
echo "   The reporter will poll for unreported tests every 60 seconds"
echo ""
