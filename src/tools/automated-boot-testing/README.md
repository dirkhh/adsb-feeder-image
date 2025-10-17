# Automated Boot Testing

This directory contains tools for automated testing of ADS-B feeder images, including a web service API for triggering tests remotely.

## Quick Start

### Development Setup
```bash
# Set up development environment
./src/tools/automated-boot-testing/setup-dev.sh

# Run the service manually
.venv/bin/python src/tools/automated-boot-testing/adsb-test-service.py --help
```

### Production Installation
```bash
# Install as systemd service
sudo ./src/tools/automated-boot-testing/install-service.sh
```

### TFTP/iSCSI Boot Setup
```bash
# Prepare an image for network boot
sudo ./src/tools/automated-boot-testing/setup-tftp-iscsi.sh /path/to/image.img
```

## Files

- **`adsb-test-service.py`** - Main web service API
- **`test-feeder-image.py`** - Core test script for image validation
- **`install-service.sh`** - Production installation script
- **`setup-dev.sh`** - Development environment setup
- **`setup-tftp-iscsi.sh`** - TFTP/iSCSI boot environment setup
- **`requirements.txt`** - Python dependencies
- **`config.json.example`** - Configuration template
- **`test-api.py`** - API testing utility
- **`README-API-Service.md`** - Detailed documentation

## Debugging Tools

- **`analyze-js-behavior.py`** - JavaScript behavior analysis
- **`debug-js-transitions.py`** - Page transition debugging

## Documentation

See `README-API-Service.md` for comprehensive documentation including:
- Installation instructions
- Configuration options
- API usage examples
- Troubleshooting guides
