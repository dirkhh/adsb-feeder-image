"""
Test to verify that the adsb_test_env fixture sets up the environment correctly
"""
import os
from pathlib import Path
import pytest


def test_adsb_test_env_creates_directory_structure(adsb_test_env):
    """Verify that the fixture creates the proper directory structure"""
    # Check that the base directory exists
    assert adsb_test_env.exists()
    assert adsb_test_env.is_dir()

    # Check that ADSB_BASE_DIR environment variable is set correctly
    assert os.environ.get('ADSB_BASE_DIR') == str(adsb_test_env)

    # Check that config directory exists
    config_dir = adsb_test_env / "config"
    assert config_dir.exists()
    assert config_dir.is_dir()

    # Check that rb directory exists
    rb_dir = adsb_test_env / "rb"
    assert rb_dir.exists()
    assert rb_dir.is_dir()

    # Check that scripts directory exists
    scripts_dir = adsb_test_env / "scripts"
    assert scripts_dir.exists()
    assert scripts_dir.is_dir()


def test_adsb_test_env_has_required_files(adsb_test_env):
    """Verify that the fixture creates all required files"""
    # Check docker.image.versions file
    docker_versions = adsb_test_env / "docker.image.versions"
    assert docker_versions.exists()
    assert docker_versions.is_file()

    # Check adsb.im.version file
    version_file = adsb_test_env / "adsb.im.version"
    assert version_file.exists()
    assert version_file.is_file()
    version = version_file.read_text().strip()
    assert len(version) > 0
    print(f"Version: {version}")

    # Check feeder-image.name file
    feeder_image_name = adsb_test_env / "feeder-image.name"
    assert feeder_image_name.exists()
    assert feeder_image_name.is_file()

    # Check .env file in config directory
    env_file = adsb_test_env / "config" / ".env"
    assert env_file.exists()
    assert env_file.is_file()

    # Verify .env contains version information
    env_content = env_file.read_text()
    assert "_ADSBIM_BASE_VERSION" in env_content
    assert "_ADSBIM_CONTAINER_VERSION" in env_content

    # Check config.json file
    config_json = adsb_test_env / "config" / "config.json"
    assert config_json.exists()
    assert config_json.is_file()


def test_adsb_test_env_can_import_modules(adsb_test_env):
    """Verify that Python modules can be imported with the test environment"""
    # This test verifies that the paths module works with the configured environment
    try:
        from utils import paths

        # Verify that the paths module uses the test environment
        assert str(paths.ADSB_BASE_DIR) == str(adsb_test_env)

        # Verify that path constants are correct
        assert str(paths.ADSB_CONFIG_DIR) == str(adsb_test_env / "config")
        assert str(paths.DOCKER_IMAGE_VERSIONS_FILE) == str(adsb_test_env / "docker.image.versions")
        assert str(paths.VERSION_FILE) == str(adsb_test_env / "adsb.im.version")

        print(f"ADSB_BASE_DIR: {paths.ADSB_BASE_DIR}")
        print(f"ADSB_CONFIG_DIR: {paths.ADSB_CONFIG_DIR}")

    except ImportError as e:
        pytest.skip(f"Could not import utils.paths: {e}")


def test_adsb_test_env_data_module_works(adsb_test_env):
    """Verify that the Data module can be imported and instantiated"""
    try:
        from utils.data import Data

        # This should work without errors now that we have a proper environment
        data = Data()

        # Verify that the data object has expected attributes
        assert hasattr(data, 'data_path')
        assert hasattr(data, 'config_path')
        assert hasattr(data, 'env_file_path')

        print(f"data.data_path: {data.data_path}")
        print(f"data.config_path: {data.config_path}")

    except ImportError as e:
        pytest.skip(f"Could not import utils.data: {e}")


def test_adsb_test_env_cleanup(adsb_test_env):
    """Verify that the fixture cleans up properly"""
    # Store the temp directory path
    temp_path = adsb_test_env

    # The directory should exist during the test
    assert temp_path.exists()

    # After the test completes, the fixture's finally block will clean up
    # We can't test the cleanup in the same test, but we verify it exists now
    # The fixture will automatically clean up in its finally block
