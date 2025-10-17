# GitHub Webhook Service

A Python-based webhook service that listens for GitHub release notifications and filters binaries based on naming patterns to determine which ones qualify for additional tests.

## Overview

This service monitors GitHub releases and specifically looks for binaries with the following criteria:
- Must contain 'raspberrypi64' in the filename
- Must have a pattern like `pi-2-3-4-<version>` or `pi-2-3-4-5-<version>` (containing '4')
- Ignores `pi-5-<version>` patterns (doesn't contain '4')

When qualifying binaries are found, the service prints their download URLs to stdout for further processing.

## Features

- ✅ GitHub webhook signature verification for security
- ✅ Filters release binaries based on naming patterns
- ✅ Systemd service integration for Ubuntu deployment
- ✅ Apache2 proxy configuration support
- ✅ Comprehensive logging and health checks
- ✅ Parallel processing support with Gunicorn

## Quick Start

### 1. Deploy the Service

```bash
# Clone and deploy
git clone <your-repo>
cd github-webhook
sudo ./deploy.sh
```

### 2. Configure Secrets

Create and configure the secrets file:

```bash
# Copy the example secrets file
sudo mkdir -p /etc/github-webhook
sudo cp secrets.env.example /etc/github-webhook/secrets.env

# Edit with your actual secrets
sudo nano /etc/github-webhook/secrets.env

# Set secure permissions
sudo chmod 600 /etc/github-webhook/secrets.env
```

**Required secrets:**
- `GITHUB_WEBHOOK_SECRET`: GitHub webhook secret for signature verification
- `BOOT_TEST_API_URL`: URL of boot test API (use Tailscale IP: `http://100.x.x.x:9456/api/trigger-boot-test`)
- `BOOT_TEST_API_KEY`: API key from `generate-api-key.py`

**Generate secure secrets:**
```bash
# Generate webhook secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate API key (from automated-boot-testing directory)
cd ../automated-boot-testing
python3 generate-api-key.py webhook-service
```

### 3. Configure Apache2

Add this to your Apache2 virtual host configuration:

```apache
# Proxy webhook requests to the service
ProxyPreserveHost On
ProxyPass /cicd-webhook/binary-test http://127.0.0.1:9111/cicd-webhook/binary-test
ProxyPassReverse /cicd-webhook/binary-test http://127.0.0.1:9111/cicd-webhook/binary-test

# Optional: Add authentication/rate limiting
<Location "/cicd-webhook/binary-test">
    # Add your security headers here
    Header always set X-Content-Type-Options nosniff
    Header always set X-Frame-Options DENY
</Location>
```

Reload Apache2:
```bash
sudo systemctl reload apache2
```

### 4. Start the Service

```bash
sudo systemctl start github-webhook
sudo systemctl status github-webhook
```

## GitHub Webhook Configuration

### 1. Create a Webhook in GitHub

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Webhooks**
3. Click **Add webhook**

### 2. Configure Webhook Settings

- **Payload URL**: `https://yourdomain.com/cicd-webhook/binary-test`
- **Content type**: `application/json`
- **Secret**: Generate a strong random secret (save this for the service configuration)
- **Which events**: Select "Let me select individual events"
  - ✅ Check "Releases" (this sends `release` events)
- **Active**: ✅ Check this box

### 3. Test the Webhook

After creating the webhook, GitHub will send a test payload. Check your service logs:

```bash
sudo journalctl -u github-webhook -f
```

You should see the webhook being processed successfully.

## Service Management

### Start/Stop/Restart
```bash
sudo systemctl start github-webhook
sudo systemctl stop github-webhook
sudo systemctl restart github-webhook
```

### View Logs
```bash
# Follow logs in real-time
sudo journalctl -u github-webhook -f

# View recent logs
sudo journalctl -u github-webhook --since "1 hour ago"
```

### Check Status
```bash
sudo systemctl status github-webhook
```

## Configuration

### Environment Variables

The service can be configured using environment variables:

- `GITHUB_WEBHOOK_SECRET`: GitHub webhook secret for signature verification (required)
- `BOOT_TEST_API_KEY`: API key for boot test API authentication (required)
- `BOOT_TEST_API_URL`: URL of the boot test API (default: `http://localhost:9456/api/trigger-boot-test`)
- `HOST`: Service host (default: 127.0.0.1)
- `PORT`: Service port (default: 9111)
- `BOOT_TEST_TIMEOUT`: Timeout in seconds for boot test API calls (default: 30)

### Binary Filtering Logic

The service filters binaries using the following logic:

1. **Must contain 'raspberrypi64'**: Binary name must include this substring
2. **Must match pi-* pattern**: Must have pattern like `pi-2-3-4-<version>`
3. **Must contain '4'**: The numbers part must include '4'

**Examples:**
- ✅ `myapp-raspberrypi64-pi-2-3-4-v1.0.0.tar.gz` (contains '4')
- ✅ `myapp-raspberrypi64-pi-2-3-4-5-v1.0.0.tar.gz` (contains '4')
- ❌ `myapp-raspberrypi64-pi-5-v1.0.0.tar.gz` (doesn't contain '4')
- ❌ `myapp-arm64-pi-2-3-4-v1.0.0.tar.gz` (no 'raspberrypi64')

## API Endpoints

- `POST /cicd-webhook/binary-test`: Main webhook endpoint for GitHub
- `GET /health`: Health check endpoint
- `GET /`: Service information
- `GET /docs`: Interactive API documentation (FastAPI auto-generated)

## Security

### Network Security Model

This service is designed to work with the **ADS-B Boot Test API** which should be deployed on a private, encrypted network:

#### ✅ Recommended: Tailscale/VPN Deployment
- **Configure API URL with Tailscale IP**: `http://100.x.x.x:9456/api/trigger-boot-test`
- Tailscale provides WireGuard encryption between webhook service and boot test API
- API keys transmitted securely over encrypted tunnel
- No public internet exposure of boot test API

#### ⚠️  Warning: HTTP Communication
- Boot test API uses HTTP (not HTTPS) by design
- **MUST** use Tailscale/VPN for encrypted transport
- Never expose boot test API to public internet without HTTPS/TLS

### Security Features

- ✅ **Webhook signature verification** using HMAC-SHA256 (constant-time comparison)
- ✅ **API key authentication** for boot test API calls (X-API-Key header)
- ✅ **URL validation** - only HTTPS GitHub release URLs accepted
- ✅ **Secrets management** - environment file with restrictive permissions (600)
- ✅ **Systemd security hardening** - NoNewPrivileges, PrivateTmp, ProtectSystem=strict
- ✅ **Runs as unprivileged user** (www-data) with minimal privileges
- ✅ **Input validation** and structured error handling

### Secret Management

**Critical: Never commit secrets to version control!**

1. **Webhook secret**: Store in `/etc/github-webhook/secrets.env` (mode 600)
2. **API key**: Generate with `generate-api-key.py`, store in secrets.env
3. **Rotate secrets** if compromised
4. **Use strong entropy**: Generated secrets should be ≥256 bits

### Security Checklist

Before deploying to production:
- [ ] Webhook secret is configured and unique
- [ ] Boot test API key is configured
- [ ] Boot test API URL uses Tailscale/VPN (100.x.x.x)
- [ ] secrets.env has permissions 600 and is owned by root
- [ ] Service is behind Apache2/nginx with HTTPS
- [ ] Firewall rules restrict access appropriately
- [ ] Dependencies are up to date (aiohttp ≥3.9.3)

## Troubleshooting

### Service Won't Start
```bash
# Check service status
sudo systemctl status github-webhook

# Check for configuration errors
sudo journalctl -u github-webhook --no-pager
```

### Webhook Not Receiving Events
1. Verify the webhook URL is correct in GitHub
2. Check Apache2 proxy configuration
3. Ensure the service is running and accessible
4. Check firewall settings

### Signature Verification Failing
1. Verify `GITHUB_WEBHOOK_SECRET` is set correctly
2. Ensure the secret in GitHub matches the service configuration
3. Check for any URL encoding issues

## Development

### Local Testing
```bash
# Setup virtual environment and install dependencies
./setup_venv.sh

# Activate virtual environment
source venv/bin/activate

# Set environment variable
export GITHUB_WEBHOOK_SECRET="your_secret_here"

# Run locally
python webhook_service.py
```

### Testing Webhook Locally
Use ngrok or similar tool to expose your local service:
```bash
ngrok http 9111
# Use the ngrok URL in your GitHub webhook configuration
```

## Files

- `webhook_service.py`: Main webhook service application (FastAPI)
- `requirements.txt`: Python dependencies
- `github-webhook.service`: Systemd service file
- `deploy.sh`: Deployment script
- `setup_venv.sh`: Local development environment setup
- `test_filter.py`: Test script for binary filtering logic
- `README.md`: This documentation
