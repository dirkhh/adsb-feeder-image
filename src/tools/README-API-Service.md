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
sudo ./src/tools/install-service.sh
```

This will:
1. Install Python dependencies (Flask, requests)
2. Create `/etc/adsb-test-service/config.json`
3. Install systemd service
4. Enable the service

## Configuration

Edit `/etc/adsb-test-service/config.json`:

```json
{
  "rpi_ip": "192.168.77.190",
  "kasa_ip": "192.168.22.147",
  "timeout_minutes": 10,
  "host": "0.0.0.0",
  "port": 9456,
  "log_level": "INFO"
}
```

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
./src/tools/test-api.py

# Test with custom URL
./src/tools/test-api.py http://192.168.1.100:8080
```

## Security

The service runs with systemd security features:
- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict`
- `ProtectHome=true`
- Limited write access to specific paths

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
ls -la src/tools/test-feeder-image.py

# Test manually
sudo .venv/bin/python src/tools/test-feeder-image.py --help
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

```
src/tools/
├── adsb-test-service.py          # Main service
├── adsb-test-service.service     # Systemd service file
├── config.json.example          # Configuration template
├── install-service.sh           # Installation script
├── test-api.py                  # API testing script
└── test-feeder-image.py         # Core test script
```

## Requirements

- Python 3.11+
- Flask
- requests
- selenium
- kasa (python-kasa)
- Virtual environment with all test dependencies
