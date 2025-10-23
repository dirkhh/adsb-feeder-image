# ADS-B Test Service

A systemd service that provides a web API for triggering automated feeder image tests.

## Features

- **RESTful API**: POST to `/api/trigger-boot-test` to trigger tests
- **GitHub URL Validation**: Only accepts release artifacts from `dirkhh/adsb-feeder-image`
- **Queue System**: Processes tests sequentially with duplicate prevention (1 hour window)
- **Configurable**: IP addresses and timeouts via JSON config file
- **Timeout Protection**: Each test has a 10-minute timeout to prevent hanging
- **Systemd Integration**: Proper logging to stdout/stderr for journald
- **Comprehensive Logging**: Detailed logs for debugging and monitoring

## Installation

```bash
# Run the installation script as root
sudo ./src/tools/automated-boot-testing/install-service.sh
```

This will:
1. Create `/opt/adsb-test-service/` with dedicated virtual environment
2. Install Python dependencies from `requirements.txt`
3. Copy service files to `/opt/adsb-test-service/`
4. Create `/etc/adsb-test-service/config.json`
5. Install and enable systemd service

## Configuration

Edit `/etc/adsb-test-service/config.json`:

```json
{
  "rpi_ip": "192.168.77.190",
  "kasa_ip": "192.168.22.147",
  "timeout_minutes": 10,
  "host": "0.0.0.0",
  "port": 9456,
  "log_level": "INFO",
  "ssh_key": "/etc/adsb-test-service/ssh_key"
}
```

### SSH Key Configuration

The `ssh_key` parameter is **required** for automated testing:

- **Purpose**: Enables passwordless SSH access to test images for verification and debugging
- **Value**: Path to the private SSH key file (e.g., `/etc/adsb-test-service/ssh_key`)
- **Public key requirement**: The public key (`.pub` extension) must exist alongside the private key
- **Validation**: On service startup, the private and public keys are validated to ensure they match using fingerprint comparison
- **Installation**: The public key is automatically copied to `/root/.ssh/authorized_keys` in the test image during boot preparation

**Example setup:**
```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -f /etc/adsb-test-service/ssh_key -N ""

# Set proper permissions
chmod 600 /etc/adsb-test-service/ssh_key
chmod 644 /etc/adsb-test-service/ssh_key.pub
```

**Security notes:**
- The private key should only be readable by the service user
- The service validates that the private and public keys match before running tests
- If keys don't match or don't exist, the service will fail to start with a clear error message

## Usage

### Start the Service

```bash
sudo systemctl start adsb-test-service
sudo systemctl status adsb-test-service
```

### View Logs

```bash
# Follow logs in real-time
sudo journalctl -u adsb-test-service -f

# View logs from last hour
sudo journalctl -u adsb-test-service --since '1 hour ago'

# View recent logs
sudo journalctl -u adsb-test-service -n 100
```

### API Endpoints

#### 1. Trigger Test
```bash
curl -X POST http://localhost:9456/api/trigger-boot-test \
     -H 'Content-Type: application/json' \
     -d '{"url": "https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6-beta.6/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz"}'
```

**Response:**
```json
{
  "status": "queued",
  "message": "Test queued successfully",
  "queue_size": 1,
  "test_id": "test_1642345678_abc123"
}
```

#### 2. Check Status
```bash
curl http://localhost:9456/api/status
```

**Response:**
```json
{
  "status": "running",
  "queue_size": 0,
  "processing": false,
  "config": {
    "rpi_ip": "192.168.77.190",
    "kasa_ip": "192.168.22.147",
    "timeout_minutes": 10
  }
}
```

#### 3. Health Check
```bash
curl http://localhost:9456/health
```

**Response:**
```json
{"status": "healthy"}
```

## How It Works

1. **Request Validation**: Validates GitHub release URLs from the correct repository
2. **Duplicate Prevention**: Ignores duplicate URLs submitted within 1 hour
3. **Queue Processing**: Processes tests sequentially to avoid conflicts
4. **Test Execution**: Runs `test-feeder-image.py` with the provided URL
5. **Timeout Protection**: Each test is limited to 10 minutes maximum
6. **Result Logging**: Logs success/failure with detailed information

## Queue Behavior

- Tests are processed **sequentially** (one at a time)
- **Duplicate prevention**: Same URL ignored if submitted within 1 hour
- **Timeout protection**: Each test limited to 10 minutes
- **Queue status**: Available via `/api/status` endpoint

## Logging

The service logs to stdout/stderr, which systemd captures in the journal:

- **INFO**: Normal operations, test results
- **ERROR**: Test failures, service errors
- **Test IDs**: Each test gets a unique ID for tracking

Example log entries:
```
2025-01-16 11:15:23,456 - root - INFO - Test request from 192.168.1.100: {'status': 'queued', 'queue_size': 1}
2025-01-16 11:15:24,123 - root - INFO - Starting test test_1642345678_abc123 for URL: https://github.com/...
2025-01-16 11:25:30,789 - root - INFO - ✅ Test test_1642345678_abc123 PASSED
```

## Testing

Use the included test script:

```bash
# Test API endpoints
./src/tools/automated-boot-testing/test-api.py

# Test with custom URL
./src/tools/automated-boot-testing/test-api.py http://192.168.1.100:9456
```

## Security

### Network Security Model

This service is designed for use on **private, encrypted networks** (Tailscale, WireGuard, or VPN):

#### ✅ Recommended: Tailscale/VPN Deployment
- **Bind to Tailscale IP** (`100.x.x.x`) or localhost (`127.0.0.1`)
- Tailscale provides WireGuard encryption between nodes
- API keys transmitted securely over encrypted tunnel
- No public internet exposure

Example configuration:
```json
{
  "host": "100.64.1.2",  // Your Tailscale IP
  "port": 9456
}
```

#### ⚠️ Warning: Public Network Deployment
If binding to `0.0.0.0` (all interfaces):
- API keys transmitted in **plaintext** over HTTP
- Vulnerable to network sniffing
- Must use HTTPS/TLS or restrict with firewall rules

**For production use on public networks:**
1. Deploy behind nginx with TLS termination, or
2. Use SSH tunneling: `ssh -L 9456:localhost:9456 user@host`, or
3. Add firewall rules to restrict access

### Authentication Security

- API key authentication using timing-safe comparison
- Keys stored in `/etc/adsb-test-service/config.json` (readable by service only)
- Generate secure keys with: `python3 generate-api-key.py`

**Important:**
- Never use example keys from `config.json.example`
- Rotate keys if compromised
- Keep config file permissions restrictive: `chmod 600 /etc/adsb-test-service/config.json`

### Systemd Hardening

The service runs with systemd security features:
- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolated /tmp directory
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=true` - No access to user home directories
- Limited write access to `/opt/adsb-test-service/` only

## Troubleshooting

### Service Won't Start
```bash
# Check service status
sudo systemctl status adsb-test-service

# Check logs for errors
sudo journalctl -u adsb-test-service -n 50
```

### Tests Failing
```bash
# Check if test script exists and is executable
ls -la src/tools/automated-boot-testing/test-feeder-image.py

# Test manually
sudo .venv/bin/python src/tools/automated-boot-testing/test-feeder-image.py --help
```

### API Not Responding
```bash
# Check if service is listening
sudo netstat -tlnp | grep 9456

# Test local connection
curl http://localhost:9456/health
```

## Integration

This service can be integrated with:
- **GitHub Actions**: Trigger tests on new releases
- **Webhooks**: Monitor for new releases and auto-test
- **CI/CD Pipelines**: Automated testing of feeder images
- **Monitoring**: Health checks and status monitoring

## File Structure

### Development Files (in project)
```
src/tools/automated-boot-testing/
├── adsb-test-service.py          # Main service (source)
├── adsb-test-service.service     # Systemd service file
├── config.json.example          # Configuration template
├── install-service.sh           # Production installation script
├── setup-dev.sh                 # Development setup script
├── setup-tftp-iscsi.sh          # TFTP/iSCSI boot setup
├── requirements.txt             # Python dependencies
├── test-api.py                  # API testing script
├── test-feeder-image.py         # Core test script (source)
├── analyze-js-behavior.py       # JavaScript analysis tool
└── debug-js-transitions.py      # Transition debugging tool
```

### Production Installation (after install)
```
/opt/adsb-test-service/
├── adsb-test-service.py         # Main service (installed)
├── test-feeder-image.py         # Core test script (installed)
├── setup-tftp-iscsi.sh         # TFTP/iSCSI setup script (installed)
├── venv/                        # Dedicated virtual environment
│   └── bin/python              # Service Python interpreter
└── test-images/                 # Cached test images

/etc/adsb-test-service/
└── config.json                 # Service configuration

/etc/systemd/system/
└── adsb-test-service.service   # Systemd service file
```

## Updating the Service

To update the service with new code:

```bash
# Stop the service
sudo systemctl stop adsb-test-service

# Run the install script again (it will update files)
sudo ./src/tools/automated-boot-testing/install-service.sh

# Start the service
sudo systemctl start adsb-test-service
```

The installation script is idempotent - it can be run multiple times safely.

## Requirements

### System Requirements
- Python 3.11+
- Firefox browser (for Selenium WebDriver)
- SSH client tools (for remote system management)
- Network utilities (ping, etc.)

### Python Dependencies
All Python dependencies are listed in `requirements.txt` and automatically installed:
- Flask (web framework)
- requests (HTTP client)
- selenium (browser automation)
- webdriver-manager (WebDriver management)
- beautifulsoup4 (HTML parsing)
- python-kasa (smart switch control)

### Installation
Dependencies are automatically installed in the dedicated virtual environment at `/opt/adsb-test-service/venv/`

### Development Setup
For development, use the setup script:

```bash
# Set up development environment
./src/tools/automated-boot-testing/setup-dev.sh
```

Or install manually:

```bash
# In your development environment
pip install -r src/tools/automated-boot-testing/requirements.txt
```
