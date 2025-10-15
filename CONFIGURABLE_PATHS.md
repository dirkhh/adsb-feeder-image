# Configurable Paths for ADS-B Setup Application

This document explains how to use the configurable paths system in the ADS-B setup application, which allows you to override the default `/opt/adsb` base directory for testing, development, or different deployment scenarios.

## Overview

The ADS-B setup application traditionally uses hardcoded paths under `/opt/adsb`. The new configurable paths system allows you to:

- Override the base directory via environment variable
- Use different paths for testing
- Deploy to different directory structures
- Maintain backward compatibility

## Quick Start

### For Testing

```bash
# Set environment variable before running tests
export ADSB_BASE_DIR="/tmp/adsb-test"
python -m pytest tests/

# Or use inline
ADSB_BASE_DIR="/tmp/adsb-test" python -m pytest tests/
```

### For Development

```bash
# Use a local development directory
export ADSB_BASE_DIR="/home/user/adsb-dev"
python app.py
```

### For Production

```bash
# Use default /opt/adsb (no environment variable needed)
python app.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADSB_BASE_DIR` | `/opt/adsb` | Base directory for all ADS-B files |
| `SKYSTATS_DB_DATA_PATH` | `${ADSB_BASE_DIR}/skystats-db` | Skystats database path |

## Path Structure

When you set `ADSB_BASE_DIR`, the following directory structure is expected:

```
${ADSB_BASE_DIR}/
├── config/                    # Configuration files
│   ├── .env                   # Environment variables
│   ├── config.json            # JSON configuration
│   ├── verbose                # Verbosity level
│   ├── ultrafeeder/           # Ultrafeeder config
│   ├── nanofeeder/            # Nanofeeder config
│   └── restore/               # Backup restore directory
├── data/                      # Data files
├── scripts/                   # Executable scripts
├── logs/                      # Log files
├── extras/                    # Extra configuration files
├── rb/                        # Fake files for testing
│   └── thermal_zone0/
├── state/                     # Application state files
├── adsb.im.version            # Version file
├── adsb.im.secure_image       # Security flag
└── docker-compose-adsb        # Docker compose script
```

## Programming Interface

### Using Paths in Code

```python
from utils.paths import ADSB_BASE_DIR, ADSB_CONFIG_DIR, ENV_FILE

# Use the configurable paths
config_file = ADSB_CONFIG_DIR / "config.json"
env_file = ENV_FILE
base_dir = ADSB_BASE_DIR

# Paths automatically adapt to ADSB_BASE_DIR setting
```

### Setting Paths Programmatically

```python
from utils.paths import set_adsb_base_dir, get_adsb_base_dir

# Change the base directory at runtime
set_adsb_base_dir("/tmp/my-adsb-setup")

# Get current base directory
current_base = get_adsb_base_dir()
```

### Backward Compatibility

The old hardcoded constants still work:

```python
# These still work and now use configurable paths
from utils.config import CONF_DIR, ENV_FILE_PATH
from utils.data import Data

data = Data()
print(data.data_path)  # Uses ADSB_BASE_DIR
```

## Testing

### Unit Tests

The test suite automatically uses temporary directories:

```python
# In conftest.py - automatically set up
import os
import tempfile

test_base_dir = os.environ.get('ADSB_BASE_DIR', tempfile.mkdtemp(prefix='adsb-test-'))
os.environ['ADSB_BASE_DIR'] = test_base_dir
```

### Manual Testing

```python
import tempfile
from utils.paths import set_adsb_base_dir

with tempfile.TemporaryDirectory(prefix='adsb-test-') as temp_dir:
    set_adsb_base_dir(temp_dir)
    
    # Your test code here
    from utils.config import CONF_DIR
    assert CONF_DIR == f"{temp_dir}/config"
```

## Migration Guide

### For Existing Code

1. **Replace hardcoded paths**:
   ```python
   # Old
   config_file = "/opt/adsb/config/config.json"
   
   # New
   from utils.paths import CONFIG_JSON_FILE
   config_file = CONFIG_JSON_FILE
   ```

2. **Update imports**:
   ```python
   # Add to imports
   from utils.paths import ADSB_CONFIG_DIR, ENV_FILE
   ```

3. **Use pathlib consistently**:
   ```python
   # Old
   os.path.join("/opt/adsb", "config", "file.txt")
   
   # New
   ADSB_CONFIG_DIR / "file.txt"
   ```

### For New Code

Always use the configurable paths:

```python
from utils.paths import (
    ADSB_BASE_DIR, ADSB_CONFIG_DIR, ADSB_DATA_DIR,
    ENV_FILE, CONFIG_JSON_FILE, VERBOSE_FILE
)

# Use these instead of hardcoded paths
config_dir = ADSB_CONFIG_DIR
env_file = ENV_FILE
```

## Docker and Containerization

### Docker Environment

```dockerfile
# In Dockerfile
ENV ADSB_BASE_DIR=/app/adsb

# Or override at runtime
docker run -e ADSB_BASE_DIR=/custom/path adsb-app
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  adsb-setup:
    environment:
      - ADSB_BASE_DIR=/opt/adsb
    volumes:
      - /host/adsb:/opt/adsb
```

## Troubleshooting

### Common Issues

1. **Import Errors**:
   ```python
   # If paths module is not available, use fallbacks
   try:
       from utils.paths import ADSB_CONFIG_DIR
   except ImportError:
       ADSB_CONFIG_DIR = Path("/opt/adsb/config")
   ```

2. **Permission Issues**:
   ```bash
   # Ensure directory is writable
   mkdir -p /tmp/adsb-test/config
   chmod 755 /tmp/adsb-test
   ```

3. **Path Not Found**:
   ```python
   # Check if base directory exists
   from utils.paths import ADSB_BASE_DIR
   if not ADSB_BASE_DIR.exists():
       ADSB_BASE_DIR.mkdir(parents=True, exist_ok=True)
   ```

### Debug Mode

Enable debug logging to see path usage:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from utils.paths import get_adsb_base_dir
print(f"Using ADS-B base directory: {get_adsb_base_dir()}")
```

## Best Practices

1. **Set environment variable early**: Set `ADSB_BASE_DIR` before importing any application modules
2. **Use pathlib**: Always use `Path` objects instead of string concatenation
3. **Test with different paths**: Test your code with various base directories
4. **Document path requirements**: Document which directories need to exist
5. **Handle missing paths gracefully**: Check if paths exist before using them

## Examples

### Complete Test Setup

```python
import os
import tempfile
from utils.paths import set_adsb_base_dir

def test_with_temp_directory():
    with tempfile.TemporaryDirectory(prefix='adsb-test-') as temp_dir:
        # Set up test environment
        set_adsb_base_dir(temp_dir)
        
        # Create necessary directories
        (Path(temp_dir) / "config").mkdir(parents=True)
        (Path(temp_dir) / "data").mkdir(parents=True)
        
        # Run your tests
        from utils.config import CONF_DIR
        assert CONF_DIR == f"{temp_dir}/config"
```

### Production Deployment

```bash
#!/bin/bash
# deploy.sh

# Set production directory
export ADSB_BASE_DIR="/opt/adsb"

# Ensure directories exist
mkdir -p /opt/adsb/{config,data,scripts,logs,extras,state}

# Start application
python app.py
```

This configurable paths system provides flexibility while maintaining backward compatibility and making testing much easier!
