# Automated Boot Testing

This directory contains tools for automated testing of ADS-B feeder images, including a web service API for triggering tests remotely.

## Quick Start

### Development Setup
```bash
# Set up development environment
./src/tools/automated-boot-testing/setup-dev.sh

# Run the service manually
.venv/bin/python src/tools/automated-boot-testing/adsb-boot-test-service.py --help
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

- **`adsb-boot-test-service.py`** - Main web service API
- **`test-feeder-image.py`** - Core test script for image validation
- **`install-service.sh`** - Production installation script
- **`setup-dev.sh`** - Development environment setup
- **`setup-tftp-iscsi.sh`** - TFTP/iSCSI boot environment setup
- **`pyproject.toml`** - Python dependencies (managed with uv)
- **`config.json.example`** - Configuration template
- **`test-api.py`** - API testing utility
- **`README-BootTestingService.md`** - Detailed documentation

## Hardware Configuration

### Power Toggle Options

The boot testing system supports two power toggle methods:

#### Kasa Smart Plug

For basic power cycling using TP-Link Kasa smart plugs.

**Configuration:**
Add to `/etc/adsb-boot-test/config.json`:
```json
{
  "power_toggle_script": "/opt/adsb-boot-test/power-toggle-kasa.py",
  "kasa_ip": "192.168.1.100"
}
```

#### UniFi PoE Switch

Controls PoE power via direct SSH commands to the switch (much faster than Controller API).

**Requirements:**
- UniFi switch with PoE capability
- SSH access enabled on the switch
- SSH keypair without passphrase

**Setup:**

1. Generate SSH keypair (if you don't have one):
```bash
ssh-keygen -t ed25519 -f /etc/adsb-boot-test/unifi_key -N ""
```

2. Copy public key to the switch:
```bash
ssh-copy-id -i /etc/adsb-boot-test/unifi_key.pub admin@192.168.1.10
```

3. Test SSH access:
```bash
ssh -i /etc/adsb-boot-test/unifi_key admin@192.168.1.10 "swctrl poe show id 16"
```

You should see output showing the port's PoE status.

**Configuration:**

Add to `/etc/adsb-boot-test/config.json`:
```json
{
  "power_toggle_script": "/opt/adsb-boot-test/power-toggle-unifi.py",
  "unifi_ssh_address": "192.168.1.10",
  "unifi_ssh_username": "admin",
  "unifi_ssh_keypath": "/etc/adsb-boot-test/unifi_key",
  "unifi_port_number": 16
}
```

**Test:**
```bash
/opt/adsb-boot-test/power-toggle-unifi.py off
/opt/adsb-boot-test/power-toggle-unifi.py on
```

You should see output indicating the port power state change and verification.

## Documentation

See `README-BootTestingService.md` for comprehensive documentation including:
- Installation instructions
- Configuration options
- API usage examples
- Troubleshooting guides
