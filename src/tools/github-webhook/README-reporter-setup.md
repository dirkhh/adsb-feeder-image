# GitHub Reporter Service Setup

## Prerequisites

1. Python 3.8+ with venv
2. GitHub Personal Access Token with permissions:
   - Pull requests: Read and Write
   - Contents: Read and Write
   - Metadata: Read

## Installation

### 1. Create GitHub Token

Visit https://github.com/settings/tokens?type=beta and create a fine-grained token:
- Repository access: Select your repository
- Permissions: Pull requests (R/W), Contents (R/W), Metadata (R)
- Expiration: Set to maximum (note expiration date for renewal)

### 2. Install Service

```bash
# Create service directory
sudo mkdir -p /opt/adsb-boot-test/github-webhook
cd /opt/adsb-boot-test/github-webhook

# Copy reporter files
sudo cp /path/to/src/tools/github-webhook/github_reporter.py .
sudo cp /path/to/src/tools/github-webhook/requirements-reporter.txt .

# Create virtual environment and install dependencies
python3 -m venv venv
venv/bin/pip install -r requirements-reporter.txt

# Copy and configure systemd service
sudo cp github-reporter.service.example /etc/systemd/system/github-reporter.service
sudo nano /etc/systemd/system/github-reporter.service
# Edit: Set GITHUB_TOKEN and GITHUB_REPO

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable github-reporter
sudo systemctl start github-reporter

# Check status
sudo systemctl status github-reporter
sudo journalctl -u github-reporter -f
```

### 3. Verify Operation

```bash
# Check health endpoint
curl http://localhost:9457/health

# Should return:
# {"status":"healthy","github_token_valid":true,...}
```

## Monitoring

### Check Logs
```bash
sudo journalctl -u github-reporter -f
```

### Health Endpoint
```bash
curl http://localhost:9457/health
```

### Token Expiration

Fine-grained tokens expire. Monitor logs for warnings:
- "⚠️  Token expires in X days" - renew soon
- "✗ GitHub token validation failed" - token expired, generate new one

To update token:
```bash
sudo systemctl stop github-reporter
sudo nano /etc/systemd/system/github-reporter.service  # Update GITHUB_TOKEN
sudo systemctl daemon-reload
sudo systemctl start github-reporter
```

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u github-reporter -n 50

# Common issues:
# - Invalid GITHUB_TOKEN: Generate new token
# - GITHUB_REPO not set: Set to "owner/repo"
# - Metrics DB not found: Normal if no tests run yet
```

### No results posting
```bash
# Check metrics DB
sqlite3 /var/lib/adsb-boot-test/metrics.db "SELECT * FROM test_runs WHERE github_event_type IS NOT NULL"

# Verify GitHub permissions
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
```
