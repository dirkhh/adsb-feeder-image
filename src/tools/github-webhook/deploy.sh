#!/bin/bash
# Deployment script for GitHub Webhook Service

set -e

SERVICE_NAME="github-webhook"
INSTALL_DIR="/opt/github-webhook"
SERVICE_USER="www-data"
SERVICE_GROUP="www-data"

echo "Deploying GitHub Webhook Service..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

# Create installation directory
echo "Creating installation directory..."
mkdir -p $INSTALL_DIR

# Copy files
echo "Copying service files..."
cp webhook_service.py $INSTALL_DIR/
cp requirements.txt $INSTALL_DIR/

# Set ownership
echo "Setting file ownership..."
chown -R $SERVICE_USER:$SERVICE_GROUP $INSTALL_DIR

# Create Python virtual environment
echo "Creating Python virtual environment..."
pushd $INSTALL_DIR
sudo -u $SERVICE_USER python3 -m venv venv
sudo -u $SERVICE_USER $INSTALL_DIR/venv/bin/pip install --upgrade pip
sudo -u $SERVICE_USER $INSTALL_DIR/venv/bin/pip install -r requirements.txt
popd
# Install systemd service
echo "Installing systemd service..."
cp github-webhook.service /etc/systemd/system/
systemctl daemon-reload

# Enable service
echo "Enabling service..."
systemctl enable $SERVICE_NAME

echo "Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Create secrets file: sudo cp secrets.env.example /etc/github-webhook/secrets.env"
echo "2. Edit /etc/github-webhook/secrets.env and set your secrets"
echo "3. Set permissions: sudo chmod 600 /etc/github-webhook/secrets.env"
echo "4. Configure Apache2 to proxy /cicd-webhook to 127.0.0.1:9111"
echo "5. Start the service: systemctl start github-webhook"
echo "6. Check status: systemctl status github-webhook"
echo "7. View logs: journalctl -u github-webhook -f"
