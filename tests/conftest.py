"""
Pytest configuration and fixtures for adsb-setup tests
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# IMPORTANT: Set ADSB_BASE_DIR at module import time, before any application code is imported.
# This ensures that when test files import application modules, the paths.py module reads
# this environment variable instead of defaulting to /opt/adsb
if 'ADSB_BASE_DIR' not in os.environ:
    # Create a temporary directory that will be used for the test session
    # This gets set once when conftest.py is loaded
    _TEST_ADSB_BASE_DIR = tempfile.mkdtemp(prefix="adsb_test_session_")
    os.environ['ADSB_BASE_DIR'] = _TEST_ADSB_BASE_DIR

# Add the adsb-setup directory to the Python path
adsb_setup_path = Path(__file__).parent.parent / "src" / "modules" / "adsb-feeder" / "filesystem" / "root" / "opt" / "adsb" / "adsb-setup"
if adsb_setup_path.exists():
    sys.path.insert(0, str(adsb_setup_path))
else:
    # Fallback: try to find the adsb-setup directory
    current_dir = Path(__file__).parent
    possible_paths = [
        current_dir.parent / "adsb-setup",
        current_dir.parent.parent / "adsb-setup",
        Path("/opt/adsb/adsb-setup")
    ]
    for path in possible_paths:
        if path.exists():
            sys.path.insert(0, str(path))
            break

# Mock system paths and files that the app expects to exist
@pytest.fixture
def mock_system_paths():
    """Mock system paths and files that the app expects to exist"""
    # Create a more targeted mocking approach
    original_exists = None
    original_os_exists = None
    original_read_text = None

    try:
        # Mock at the module level where these functions are used
        with patch('pathlib.Path.exists') as mock_exists, \
             patch('os.path.exists') as mock_os_exists, \
             patch('pathlib.Path.read_text') as mock_read_text:

            # Mock common system files
            def exists_side_effect(path):
                system_files = [
                    "/etc/machine-id",
                    "/opt/adsb/config/verbose",
                    "/opt/adsb/config/.env",
                    "/opt/adsb/config/config.json",
                    "/opt/adsb/adsb.im.version",
                    "/opt/adsb/adsb.im.secure_image",
                    "/opt/adsb/os.adsb.feeder.image",
                    "/boot/dietpi",
                    "/etc/rpi-issue"
                ]
                path_str = str(path)
                if path_str in system_files:
                    return True
                # For other paths, use the original behavior
                return False

            def read_text_side_effect(path):
                path_str = str(path)
                if path_str == "/etc/machine-id":
                    return "test-machine-id-12345"
                elif path_str == "/opt/adsb/config/verbose":
                    return "4"
                elif path_str == "/opt/adsb/adsb.im.version":
                    return "1.0.0"
                # For other paths, return empty string
                return ""

            # Only apply the side effect for specific paths
            def selective_exists(path):
                path_str = str(path)
                if any(sys_file in path_str for sys_file in ["/etc/machine-id", "/opt/adsb", "/boot/dietpi", "/etc/rpi-issue"]):
                    return exists_side_effect(path)
                # For other paths, don't interfere
                return True  # Let the real pathlib handle it

            def selective_read_text(path):
                path_str = str(path)
                if any(sys_file in path_str for sys_file in ["/etc/machine-id", "/opt/adsb"]):
                    return read_text_side_effect(path)
                # For other paths, return empty string
                return ""

            mock_exists.side_effect = selective_exists
            mock_os_exists.side_effect = selective_exists
            mock_read_text.side_effect = selective_read_text

            yield

    except Exception:
        # If mocking fails, just continue without it
        yield

@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory for testing"""
    temp_dir = tempfile.mkdtemp()
    config_dir = Path(temp_dir) / "config"
    config_dir.mkdir()

    # Create mock config files
    env_file = config_dir / ".env"
    env_file.write_text("TEST_VAR=test_value\n")

    json_file = config_dir / "config.json"
    json_file.write_text('{"test": "value"}')

    version_file = config_dir / "adsb.im.version"
    version_file.write_text("1.0.0")

    yield config_dir

    shutil.rmtree(temp_dir)

@pytest.fixture
def mock_flask_app():
    """Mock Flask app for testing"""
    with patch('flask.Flask') as mock_flask:
        app = MagicMock()
        mock_flask.return_value = app
        app.secret_key = "test-secret-key"
        app.config = {}
        yield app

@pytest.fixture
def mock_requests():
    """Mock requests library for HTTP calls"""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post:

        # Default successful responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.text = "OK"

        mock_get.return_value = mock_response
        mock_post.return_value = mock_response

        yield {
            'get': mock_get,
            'post': mock_post,
            'response': mock_response
        }

@pytest.fixture
def mock_subprocess():
    """Mock subprocess calls"""
    with patch('subprocess.run') as mock_run, \
         patch('subprocess.Popen') as mock_popen:

        # Default successful subprocess results
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""

        mock_run.return_value = mock_result
        mock_popen.return_value = MagicMock()

        yield {
            'run': mock_run,
            'popen': mock_popen,
            'result': mock_result
        }

@pytest.fixture
def mock_file_operations():
    """Mock file operations"""
    with patch('builtins.open') as mock_open, \
         patch('shutil.move') as mock_move, \
         patch('shutil.copyfile') as mock_copy:

        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        mock_file.read.return_value = "file content"
        mock_file.write = MagicMock()

        yield {
            'open': mock_open,
            'move': mock_move,
            'copy': mock_copy,
            'file': mock_file
        }

# Environment variables for testing
@pytest.fixture
def test_env_vars():
    """Set up test environment variables"""
    env_vars = {
        'TEST_VAR': 'test_value',
        'FEEDER_NAME': 'test_feeder',
        'FEEDER_LAT': '40.7128',
        'FEEDER_LON': '-74.0060',
        'FEEDER_ALT': '10'
    }

    with patch.dict(os.environ, env_vars):
        yield env_vars

@pytest.fixture(scope="function")
def adsb_test_env():
    """
    Create a complete ADS-B test environment with proper directory structure
    and initialized configuration files.

    This fixture:
    1. Creates a temp directory structure mirroring /opt/adsb
    2. Copies necessary files from src/modules/adsb-feeder/filesystem/root/opt/adsb
    3. Generates version file
    4. Initializes .env and config.json files
    5. Sets ADSB_BASE_DIR environment variable

    Returns:
        Path: The base directory path (equivalent to /opt/adsb in production)
    """
    import subprocess
    import json

    # Create temporary directory structure
    temp_base = Path(tempfile.mkdtemp(prefix="adsb_test_"))

    # Find source directory
    source_root = Path(__file__).parent.parent / "src" / "modules" / "adsb-feeder" / "filesystem" / "root" / "opt" / "adsb"

    if not source_root.exists():
        # Cleanup and raise error if source not found
        shutil.rmtree(temp_base, ignore_errors=True)
        pytest.skip(f"Source directory not found: {source_root}")

    try:
        # Create directory structure
        config_dir = temp_base / "config"
        config_dir.mkdir(parents=True)

        rb_dir = temp_base / "rb"
        rb_dir.mkdir(parents=True)

        scripts_dir = temp_base / "scripts"
        scripts_dir.mkdir(parents=True)

        # Copy essential files from source
        # 1. Copy docker.image.versions
        docker_versions_src = source_root / "docker.image.versions"
        if docker_versions_src.exists():
            shutil.copy2(docker_versions_src, temp_base / "docker.image.versions")

        # 2. Copy yml template files to config directory
        for yml_file in source_root.glob("*.yml"):
            shutil.copy2(yml_file, config_dir / yml_file.name)

        # Also check config subdirectory for yml files
        source_config = source_root / "config"
        if source_config.exists():
            for yml_file in source_config.glob("*.yml"):
                shutil.copy2(yml_file, config_dir / yml_file.name)

        # 3. Copy create-json-from-env.sh script
        create_json_script = source_root / "create-json-from-env.sh"
        if create_json_script.exists():
            shutil.copy2(create_json_script, temp_base / "create-json-from-env.sh")
            os.chmod(temp_base / "create-json-from-env.sh", 0o755)

        # 4. Copy docker-compose scripts
        for script_name in ["docker-compose-adsb", "docker-compose-start"]:
            script_src = source_root / script_name
            if script_src.exists():
                shutil.copy2(script_src, temp_base / script_name)
                os.chmod(temp_base / script_name, 0o755)

        # 5. Generate adsb.im.version file
        version_file = temp_base / "adsb.im.version"
        tools_get_version = Path(__file__).parent.parent / "tools" / "get_version.sh"

        if tools_get_version.exists():
            try:
                result = subprocess.run(
                    ["bash", str(tools_get_version)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                version = result.stdout.strip() if result.returncode == 0 else "0.0.0-test"
            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                version = "0.0.0-test"
        else:
            version = "0.0.0-test"

        version_file.write_text(version)

        # 6. Create feeder-image.name file
        feeder_image_name = temp_base / "feeder-image.name"
        feeder_image_name.write_text("ADS-B Feeder Test Image")

        # 7. Create machine-id file (needed by util.py)
        machine_id_file = Path("/etc/machine-id")
        if not machine_id_file.exists():
            # Create a mock machine-id in the temp directory
            mock_machine_id = temp_base / "machine-id"
            mock_machine_id.write_text("test-machine-id-1234567890abcdef")

        # 8. Initialize .env file from docker.image.versions
        env_file = config_dir / ".env"
        if not env_file.exists():
            docker_versions = temp_base / "docker.image.versions"
            if docker_versions.exists():
                # Copy docker.image.versions to .env
                shutil.copy2(docker_versions, env_file)

                # Append version information
                with open(env_file, "a") as f:
                    f.write(f"\n_ADSBIM_BASE_VERSION={version}\n")
                    f.write(f"_ADSBIM_CONTAINER_VERSION={version}\n")

        # 9. Create config.json from .env
        config_json = config_dir / "config.json"
        if not config_json.exists():
            # If create-json-from-env.sh exists, try to run it
            create_script = temp_base / "create-json-from-env.sh"
            if create_script.exists() and env_file.exists():
                try:
                    # Run the script with proper environment
                    env = os.environ.copy()
                    env['ADSB_BASE_DIR'] = str(temp_base)
                    subprocess.run(
                        ["bash", str(create_script)],
                        cwd=str(temp_base),
                        env=env,
                        capture_output=True,
                        timeout=10
                    )
                except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                    pass

            # If config.json still doesn't exist, create a minimal one
            if not config_json.exists():
                minimal_config = {
                    "_ADSBIM_BASE_VERSION": version,
                    "_ADSBIM_CONTAINER_VERSION": version,
                    "FEEDER_LAT": "",
                    "FEEDER_LONG": "",
                    "FEEDER_ALT_M": "",
                    "FEEDER_TZ": "",
                    "MLAT_SITE_NAME": "test-site"
                }
                config_json.write_text(json.dumps(minimal_config, indent=2))

        # 10. Set ADSB_BASE_DIR environment variable
        old_adsb_base_dir = os.environ.get('ADSB_BASE_DIR')
        os.environ['ADSB_BASE_DIR'] = str(temp_base)

        # Yield the base directory path
        yield temp_base

    finally:
        # Cleanup: restore old environment variable and remove temp directory
        if old_adsb_base_dir is not None:
            os.environ['ADSB_BASE_DIR'] = old_adsb_base_dir
        elif 'ADSB_BASE_DIR' in os.environ:
            del os.environ['ADSB_BASE_DIR']

        shutil.rmtree(temp_base, ignore_errors=True)
