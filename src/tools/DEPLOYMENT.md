# Remote Deployment Guide

This guide explains how to deploy the github-webhook and adsb-test-service to remote servers from your development machine.

## Overview

The `remote-deploy-test-services.sh` script automates deployment to remote servers by:
1. Copying service files to remote staging directory
2. Running the existing deployment script on the remote server (`deploy.sh` for github-webhook, `install-service.sh` for adsb-test-service)
3. Restarting the service
4. Verifying the service is running
5. Cleaning up temporary files

## Prerequisites

### 1. SSH Key Authentication

You must have SSH key-based authentication configured for the remote servers. Password authentication is not supported by this script.

**Setup SSH keys:**

```bash
# Generate SSH key if you don't have one (with passphrase for security)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy your public key to the remote server
ssh-copy-id root@your-server.com

# Test the connection (should not prompt for password)
ssh root@your-server.com
```

### 2. Using ssh-agent for Passphrase-Protected Keys

If your SSH keys have passphrases (recommended for security), use `ssh-agent` to avoid re-entering the passphrase for each connection:

**Quick start:**

```bash
# Start ssh-agent and add your key in one command
eval "$(ssh-agent -s)" && ssh-add

# Then run deployment
./remote-deploy-test-services.sh
```

**Detailed setup:**

```bash
# 1. Start ssh-agent (if not already running)
eval "$(ssh-agent -s)"
# Output: Agent pid 12345

# 2. Add your SSH key (will prompt for passphrase once)
ssh-add ~/.ssh/id_ed25519
# Enter passphrase for ~/.ssh/id_ed25519: ****

# 3. Verify keys are loaded
ssh-add -l
# Output: 256 SHA256:... your_email@example.com (ED25519)

# 4. Now run deployment (no more passphrase prompts!)
./remote-deploy-test-services.sh
```

**The deployment script will check ssh-agent status and provide helpful error messages if keys aren't loaded.**

**Persistent ssh-agent (optional):**

To avoid starting ssh-agent every time, add to your `~/.bashrc` or `~/.zshrc`:

```bash
# Start ssh-agent if not running
if [ -z "$SSH_AUTH_SOCK" ]; then
    eval "$(ssh-agent -s)" > /dev/null
fi

# Auto-add keys on first use
ssh-add -l &>/dev/null || ssh-add
```

Or use a keychain tool:
- **Linux**: `keychain` package
- **macOS**: Built-in Keychain (add `UseKeychain yes` to `~/.ssh/config`)
- **Windows**: Use Windows SSH Agent service

### 3. Remote Server Requirements

- Root or sudo access on remote servers
- SSH server running and accessible
- Python 3.9+ installed
- systemd for service management

### 4. Local Setup

```bash
# Navigate to the tools directory
cd src/tools

# Copy the example .env file
cp .env.example .env

# Edit .env with your server hostnames
nano .env
```

## Configuration

Edit the `.env` file with your deployment targets:

```bash
# GitHub Webhook Service (public-facing server)
WEBHOOK_HOST=root@webhook.example.com

# Boot Test Service (private server with test hardware)
BOOT_TEST_HOST=root@boottest.example.com
```

**Format options:**
- `root@hostname` - Explicit user
- `admin@192.168.1.10` - Non-root user (must have sudo)
- `hostname.com` - Defaults to `root@hostname.com`
- Leave blank to skip deployment of that service

**Security Notes:**
- Root SSH access is required for service installation
- Consider using a dedicated deployment user with sudo privileges
- Use SSH key restrictions if concerned about security
- Both services can be deployed to the same host if needed

## Usage

### Deploy Both Services

```bash
./remote-deploy-test-services.sh
# or explicitly
./remote-deploy-test-services.sh all
```

### Deploy Individual Services

```bash
# Deploy only github-webhook
./remote-deploy-test-services.sh webhook

# Deploy only adsb-test-service
./remote-deploy-test-services.sh boot-test
```

## What Gets Deployed

### GitHub Webhook Service
- `webhook_service.py` - Main FastAPI service
- `requirements.txt` - Python dependencies
- `github-webhook.service` - Systemd unit file
- `deploy.sh` - Installation script
- `secrets.env.example` - Secret template
- Configuration and utility scripts

**Installed to:** `/opt/github-webhook`

### Boot Test Service
- `adsb-test-service.py` - Main Flask service
- `test-feeder-image.py` - Test execution script
- `requirements.txt` - Python dependencies
- `adsb-test-service.service` - Systemd unit file
- `install-service.sh` - Installation script
- Configuration and utility scripts

**Installed to:** `/opt/automated-boot-testing`

## Deployment Process

The script follows this sequence for each service:

1. **Connection Test** - Verifies SSH access to remote server
2. **Stage Files** - Creates `/tmp/adsb-deploy-<timestamp>` and copies files
3. **Run Deploy Script** - Executes the service's `deploy.sh` on remote
4. **Restart Service** - Runs `systemctl restart <service-name>`
5. **Health Check** - Verifies service started successfully
6. **Cleanup** - Removes staging directory
7. **Status Report** - Shows final deployment status

## Troubleshooting

### SSH Connection Failed

```
✗ Cannot connect to root@hostname via SSH
⚠ Ensure SSH key authentication is configured
```

**Solution:**
```bash
# Test SSH connection manually
ssh root@hostname

# If it prompts for password, copy your SSH key
ssh-copy-id root@hostname
```

### ssh-agent Not Running

```
✗ ssh-agent is not running
ℹ Start ssh-agent and add your keys:
  eval "$(ssh-agent -s)"
  ssh-add ~/.ssh/id_ed25519
```

**Solution:**
```bash
# Quick fix - start agent, add keys, and deploy in one command
eval "$(ssh-agent -s)" && ssh-add && ./remote-deploy-test-services.sh

# Or do it step by step:
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
./remote-deploy-test-services.sh
```

### No SSH Keys Loaded

```
✗ No SSH keys are loaded in ssh-agent
ℹ Add your SSH key(s):
  ssh-add ~/.ssh/id_ed25519
```

**Solution:**
```bash
# Add your key (will prompt for passphrase once)
ssh-add ~/.ssh/id_ed25519

# If you have multiple keys, add them all
ssh-add ~/.ssh/id_rsa
ssh-add ~/.ssh/id_ed25519_deploy

# Verify keys are loaded
ssh-add -l
```

**Common issues:**
- **Wrong key path**: Check `ls -la ~/.ssh/` to find your key files
- **Passphrase prompt**: This is normal - enter it once and ssh-agent remembers
- **Permission denied**: Ensure key file permissions are correct (`chmod 600 ~/.ssh/id_ed25519`)

### Service Failed to Start

If the service fails to start, the script will display the last 20 log entries:

```bash
# Manually check logs on remote server
ssh root@hostname
journalctl -u github-webhook -f
# or
journalctl -u adsb-test-service -f
```

### Deploy Script Failed

If the deployment script fails on the remote server, SSH to the server and run it manually to see detailed errors:

```bash
ssh root@hostname

# For github-webhook
cd /tmp/adsb-deploy-*/github-webhook
bash -x deploy.sh

# For adsb-test-service
cd /tmp/adsb-deploy-*/automated-boot-testing
bash -x install-service.sh
```

### Permission Denied

If you see permission errors, ensure:
1. The remote user has sudo/root privileges
2. `/opt/` directory exists and is writable by root
3. systemd service files can be written to `/etc/systemd/system/`

## Security Considerations

### SSH Key Security

- Use strong SSH key encryption (ed25519 recommended)
- Protect your private key with a passphrase
- Use `ssh-agent` to avoid repeatedly entering passphrase
- Consider SSH key restrictions for deployment-only access

### Alternative: Non-Root Deployment

Instead of SSH-ing as root, you can use a deployment user:

1. Create deployment user on remote:
```bash
adduser deploy
usermod -aG sudo deploy
```

2. Configure passwordless sudo for deployment tasks:
```bash
# /etc/sudoers.d/deploy
deploy ALL=(ALL) NOPASSWD: /bin/systemctl restart github-webhook
deploy ALL=(ALL) NOPASSWD: /bin/systemctl restart adsb-test-service
deploy ALL=(ALL) NOPASSWD: /bin/cp * /opt/*
```

3. Update .env:
```bash
WEBHOOK_HOST=deploy@webhook.example.com
```

### SSH Key Restrictions

Limit what the deployment key can do by adding to `~/.ssh/authorized_keys` on remote:

```
command="/usr/local/bin/deploy-only.sh",no-port-forwarding,no-X11-forwarding ssh-ed25519 AAAA...
```

## Workflow Examples

### Development Workflow

```bash
# 1. Make changes to service code locally
nano automated-boot-testing/adsb-test-service.py

# 2. Test locally if possible
cd automated-boot-testing
python adsb-test-service.py --config test-config.json

# 3. Deploy to remote server
cd ..
./remote-deploy-test-services.sh boot-test

# 4. Check remote logs
ssh root@boottest.example.com "journalctl -u adsb-test-service -f"
```

### CI/CD Integration

The script can be integrated into CI/CD pipelines:

```yaml
# GitHub Actions example
- name: Deploy to Production
  env:
    WEBHOOK_HOST: ${{ secrets.WEBHOOK_HOST }}
    BOOT_TEST_HOST: ${{ secrets.BOOT_TEST_HOST }}
  run: |
    cd src/tools
    ./remote-deploy-test-services.sh all
```

## Testing Deployment

After deployment, verify services are working:

```bash
# Test github-webhook health
curl https://webhook.example.com/health

# Test adsb-test-service health (requires API key)
curl -H "X-API-Key: $API_KEY" http://boottest.example.com:9456/health

# Check service status on remote
ssh root@webhook.example.com "systemctl status github-webhook"
ssh root@boottest.example.com "systemctl status adsb-test-service"
```

## Files

- `remote-deploy-test-services.sh` - Main deployment script
- `.env` - Deployment configuration (git-ignored)
- `.env.example` - Configuration template
- `DEPLOYMENT.md` - This documentation

## Related Documentation

- [github-webhook/README.md](github-webhook/README.md) - Webhook service details
- [automated-boot-testing/README.md](automated-boot-testing/README.md) - Boot test service details
