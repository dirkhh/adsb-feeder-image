# ADS-B Test Service

A systemd service that provides a web API for triggering automated feeder image tests.

## Features

- **RESTful API**: POST to `/api/trigger-boot-test` to trigger tests
- **GitHub URL Validation**: Only accepts release artifacts from `dirkhh/adsb-feeder-image`
- **Queue System**: Processes tests sequentially with duplicate detection (1 hour window)
- **Duplicate Detection**: Prevents redundant tests for same URL + release_id within 1 hour
- **Configurable**: IP addresses and timeouts via JSON config file
- **Timeout Protection**: Each test has a 10-minute timeout to prevent hanging
- **Systemd Integration**: Proper logging to stdout/stderr for journald
- **Comprehensive Logging**: Detailed logs for debugging and monitoring
- **Metrics Tracking**: SQLite-based metrics tracking with CLI query tool

## Installation

```bash
# Run the installation script as root
sudo ./src/tools/automated-boot-testing/install-service.sh
```

This will:
1. Create `/opt/adsb-boot-test/` with dedicated virtual environment
2. Install Python dependencies from `pyproject.toml` (using uv)
3. Copy service files to `/opt/adsb-boot-test/`
4. Create `/etc/adsb-boot-test/config.json`
5. Install and enable systemd service

## Configuration

Edit `/etc/adsb-boot-test/config.json`:

```json
{
  "rpi_ip": "192.168.77.190",
  "kasa_ip": "192.168.22.147",
  "timeout_minutes": 10,
  "host": "0.0.0.0",
  "port": 9456,
  "log_level": "INFO",
  "ssh_key": "/etc/adsb-boot-test/ssh_key"
}
```

### SSH Key Configuration

The `ssh_key` parameter is **required** for automated testing:

- **Purpose**: Enables passwordless SSH access to test images for verification and debugging
- **Value**: Path to the private SSH key file (e.g., `/etc/adsb-boot-test/ssh_key`)
- **Public key requirement**: The public key (`.pub` extension) must exist alongside the private key
- **Validation**: On service startup, the private and public keys are validated to ensure they match using fingerprint comparison
- **Installation**: The public key is automatically copied to `/root/.ssh/authorized_keys` in the test image during boot preparation

**Example setup:**
```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -f /etc/adsb-boot-test/ssh_key -N ""

# Set proper permissions
chmod 600 /etc/adsb-boot-test/ssh_key
chmod 644 /etc/adsb-boot-test/ssh_key.pub
```

**Security notes:**
- The private key should only be readable by the service user
- The service validates that the private and public keys match before running tests
- If keys don't match or don't exist, the service will fail to start with a clear error message

## Usage

### Start the Service

```bash
sudo systemctl start adsb-boot-test
sudo systemctl status adsb-boot-test
```

### View Logs

```bash
# Follow logs in real-time
sudo journalctl -u adsb-boot-test -f

# View logs from last hour
sudo journalctl -u adsb-boot-test --since '1 hour ago'

# View recent logs
sudo journalctl -u adsb-boot-test -n 100
```

### API Endpoints

#### 1. Trigger Test
```bash
curl -X POST http://localhost:9456/api/trigger-boot-test \
     -H 'Content-Type: application/json' \
     -d '{"url": "https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6-beta.6/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz"}'
```

**Response (test queued):**
```json
{
  "status": "queued",
  "message": "Test queued successfully",
  "queue_size": 1,
  "test_id": "test_1642345678_abc123"
}
```

**Response (duplicate ignored):**
```json
{
  "status": "ignored",
  "message": "Duplicate test from 15 minutes ago",
  "previous_test_id": "test_1642345000_xyz789"
}
```

The API automatically detects and rejects duplicate test submissions for the same URL + GitHub release ID combination within a 1-hour window. See "Duplicate Detection" section below for details.

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
2. **Duplicate Detection**: Checks for duplicate URL + release_id combinations within 1 hour
3. **Queue Processing**: Processes tests sequentially to avoid conflicts
4. **Test Execution**: Runs `test-feeder-image.py` with the provided URL
5. **Timeout Protection**: Each test is limited to 10 minutes maximum
6. **Result Logging**: Logs success/failure with detailed information

## Duplicate Detection

The service automatically detects and prevents duplicate test submissions to avoid wasting resources on redundant tests.

### How It Works

- **Detection Criteria**: Same URL + GitHub release_id combination
- **Time Window**: 1 hour (hardcoded)
- **Response**: HTTP 200 with `status: "ignored"` (not an error)
- **Bypass**: Tests without `release_id` skip duplicate check (manual tests always allowed)

### When Duplicates Occur

Duplicates can happen due to:
- GitHub webhook retries (network issues, service restarts)
- Multiple workflow runs for same release
- Manual re-submissions of the same release

### API Behavior

**First request (queued):**
```bash
curl -X POST http://localhost:9456/api/trigger-boot-test \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://github.com/.../test.img.xz",
    "github_context": {
      "release_id": 12345,
      "commit_sha": "abc123"
    }
  }'
```

Response: `{"status": "queued", "test_id": "test_123"}`

**Second request within 1 hour (ignored):**
```bash
# Same URL and release_id
curl -X POST http://localhost:9456/api/trigger-boot-test \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://github.com/.../test.img.xz",
    "github_context": {
      "release_id": 12345,
      "commit_sha": "abc123"
    }
  }'
```

Response: `{"status": "ignored", "message": "Duplicate test from 15 minutes ago", "previous_test_id": "test_123"}`

### Storage

Duplicate detection uses the same SQLite database as test metrics:
- Database: `/opt/adsb/boot-test-metrics.db`
- Table: `test_runs`
- Query: Finds matching `image_url` + `github_release_id` within time window

### Logging

Duplicate detection is logged for monitoring:
```
INFO: Duplicate test ignored: URL=https://github.com/.../test.img.xz, release_id=12345, previous test_id=123, 15 minutes ago
```

### Error Handling

The duplicate check includes fail-safe error handling:
- If database query fails, test is **allowed to proceed**
- Error is logged as WARNING
- This prevents database issues from blocking legitimate tests

## Queue Behavior

- Tests are processed **sequentially** (one at a time)
- **Duplicate detection**: Same URL + release_id ignored if submitted within 1 hour
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
- Keys stored in `/etc/adsb-boot-test/config.json` (readable by service only)
- Generate secure keys with: `python3 generate-api-key.py`

**Important:**
- Never use example keys from `config.json.example`
- Rotate keys if compromised
- Keep config file permissions restrictive: `chmod 600 /etc/adsb-boot-test/config.json`

### Systemd Hardening

The service runs with systemd security features:
- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolated /tmp directory
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=true` - No access to user home directories
- Limited write access to `/opt/adsb-boot-test/` only

## Troubleshooting

### Service Won't Start
```bash
# Check service status
sudo systemctl status adsb-boot-test

# Check logs for errors
sudo journalctl -u adsb-boot-test -n 50
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

## Test Metrics

The service includes SQLite-based metrics tracking to monitor test results over time.

### Viewing Metrics

```bash
# Show recent test results (default view)
sudo /opt/adsb-boot-test/boot-test-metrics-cli.py

# Show last 20 tests
sudo /opt/adsb-boot-test/boot-test-metrics-cli.py --recent 20

# Show statistics for last 7 days
sudo /opt/adsb-boot-test/boot-test-metrics-cli.py --stats 7

# Show only failures
sudo /opt/adsb-boot-test/boot-test-metrics-cli.py --failures

# Filter by version
sudo /opt/adsb-boot-test/boot-test-metrics-cli.py --version "v3.0.6-beta.8"

# Show details for specific test
sudo /opt/adsb-boot-test/boot-test-metrics-cli.py --details 42
```

### Metrics Database

- **Location**: `/var/lib/adsb-boot-test/metrics.db`
- **Format**: SQLite database
- **Auto-created** on first test run
- **Tracks**: Image URL, version, test stages, duration, pass/fail, error details

### Direct Database Queries

```bash
# Open database
sqlite3 /var/lib/adsb-boot-test/metrics.db

# View recent tests
SELECT image_version, status, duration_seconds, started_at
FROM test_runs
ORDER BY started_at DESC
LIMIT 10;

# Get pass rate by version
SELECT
  image_version,
  COUNT(*) as total,
  SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed
FROM test_runs
GROUP BY image_version;
```

### Integration Guide

See [METRICS_INTEGRATION.md](METRICS_INTEGRATION.md) for detailed integration instructions.

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
├── adsb-boot-test-service.py          # Main service (source)
├── adsb-boot-test.service     # Systemd service file
├── config.json.example          # Configuration template
├── install-service.sh           # Production installation script
├── setup-dev.sh                 # Development setup script
├── setup-tftp-iscsi.sh          # TFTP/iSCSI boot setup
├── test-api.py                  # API testing script
├── test-feeder-image.py         # Core test script (source)
├── run-selenium-test.py         # Selenium test runner (non-root)
├── metrics.py                   # Metrics tracking module (NEW)
├── boot-test-metrics-cli.py     # Metrics CLI query tool (NEW)
├── METRICS_INTEGRATION.md       # Metrics integration guide (NEW)
```

### Production Installation (after install)
```
/opt/adsb-boot-test/
├── adsb-boot-test-service.py         # Main service (installed)
├── test-feeder-image.py         # Core test script (installed)
├── setup-tftp-iscsi.sh         # TFTP/iSCSI setup script (installed)
├── venv/                        # Dedicated virtual environment
│   └── bin/python              # Service Python interpreter
└── test-images/                 # Cached test images

/etc/adsb-boot-test/
└── config.json                 # Service configuration

/etc/systemd/system/
└── adsb-boot-test.service   # Systemd service file
```

## Updating the Service

To update the service with new code:

```bash
# Stop the service
sudo systemctl stop adsb-boot-test

# Run the install script again (it will update files)
sudo ./src/tools/automated-boot-testing/install-service.sh

# Start the service
sudo systemctl start adsb-boot-test
```

The installation script is idempotent - it can be run multiple times safely.

## Requirements

### System Requirements
- Python 3.11+
- Firefox browser (for Selenium WebDriver)
- SSH client tools (for remote system management)
- Network utilities (ping, etc.)

### Python Dependencies
All Python dependencies are listed in `pyproject.toml` and automatically installed using `uv`:
- Flask (web framework)
- requests (HTTP client)
- selenium (browser automation)
- webdriver-manager (WebDriver management)
- beautifulsoup4 (HTML parsing)
- python-kasa (smart switch control)

### Installation
Dependencies are automatically installed using `uv` in the dedicated virtual environment at `/opt/adsb-boot-test/venv/`

### Development Setup
For development, use the setup script:

```bash
# Set up development environment
./src/tools/automated-boot-testing/setup-dev.sh
```

Or install manually using uv:

```bash
# In your development environment
uv pip install -e .
```
