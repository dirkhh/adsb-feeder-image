"""
Test the configurable paths system.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the paths module - import module, not individual constants
# so we can see updates when set_adsb_base_dir() is called
import utils.paths
from utils.paths import get_adsb_base_dir, set_adsb_base_dir


class TestPathConfiguration:
    """Test the configurable paths system."""

    def test_default_paths(self):
        """Test that default paths use /opt/adsb"""
        # Reset to default
        os.environ.pop('ADSB_BASE_DIR', None)
        
        # Import fresh to get defaults
        import importlib
        import utils.paths
        importlib.reload(utils.paths)
        
        assert utils.paths.ADSB_BASE_DIR == Path("/opt/adsb")
        assert utils.paths.ADSB_CONFIG_DIR == Path("/opt/adsb/config")
        assert utils.paths.ENV_FILE == Path("/opt/adsb/config/.env")

    def test_environment_variable_configuration(self):
        """Test that paths can be configured via environment variable"""
        test_dir = "/tmp/adsb-test"
        
        with patch.dict(os.environ, {'ADSB_BASE_DIR': test_dir}):
            # Import fresh to pick up environment variable
            import importlib
            import utils.paths
            importlib.reload(utils.paths)
            
            assert utils.paths.ADSB_BASE_DIR == Path(test_dir)
            assert utils.paths.ADSB_CONFIG_DIR == Path(f"{test_dir}/config")
            assert utils.paths.ENV_FILE == Path(f"{test_dir}/config/.env")

    def test_set_adsb_base_dir_function(self):
        """Test the set_adsb_base_dir function"""
        test_dir = "/tmp/adsb-test-dynamic"

        # Set the base directory
        set_adsb_base_dir(test_dir)

        assert get_adsb_base_dir() == Path(test_dir)
        assert utils.paths.ADSB_BASE_DIR == Path(test_dir)
        assert utils.paths.ADSB_CONFIG_DIR == Path(f"{test_dir}/config")

    def test_path_consistency_after_change(self):
        """Test that all paths are consistent after changing base directory"""
        original_base = get_adsb_base_dir()

        try:
            test_dir = "/tmp/adsb-test-consistency"
            set_adsb_base_dir(test_dir)

            # All paths should be relative to the new base
            assert utils.paths.ADSB_BASE_DIR == Path(test_dir)
            assert utils.paths.ADSB_CONFIG_DIR == Path(f"{test_dir}/config")
            assert utils.paths.ENV_FILE == Path(f"{test_dir}/config/.env")
            assert utils.paths.VERBOSE_FILE == Path(f"{test_dir}/config/verbose")

        finally:
            # Restore original
            set_adsb_base_dir(str(original_base))

    def test_temporary_directory_usage(self):
        """Test using temporary directory for testing"""
        with tempfile.TemporaryDirectory(prefix='adsb-test-') as temp_dir:
            set_adsb_base_dir(temp_dir)

            assert utils.paths.ADSB_BASE_DIR == Path(temp_dir)
            assert utils.paths.ADSB_CONFIG_DIR == Path(f"{temp_dir}/config")

            # Verify paths are accessible
            assert str(utils.paths.ADSB_BASE_DIR).startswith(temp_dir)

    def test_backward_compatibility(self):
        """Test that the path system maintains backward compatibility"""
        # Test that the old constant names still work
        from utils.config import CONF_DIR, ENV_FILE_PATH

        # These should now use the configurable paths
        assert CONF_DIR == str(utils.paths.ADSB_CONFIG_DIR)
        assert ENV_FILE_PATH == str(utils.paths.ENV_FILE)


class TestPathIntegration:
    """Test integration with existing modules."""

    def test_config_module_integration(self):
        """Test that config module uses the new path system"""
        test_dir = "/tmp/adsb-test-config"

        with patch.dict(os.environ, {'ADSB_BASE_DIR': test_dir}):
            # Import fresh modules - reload paths first, then config
            import importlib
            import utils.paths
            import utils.config
            importlib.reload(utils.paths)
            importlib.reload(utils.config)

            assert utils.config.CONF_DIR == f"{test_dir}/config"
            assert utils.config.ENV_FILE_PATH == f"{test_dir}/config/.env"

    def test_data_module_integration(self):
        """Test that data module uses the new path system"""
        test_dir = "/tmp/adsb-test-data"

        with patch.dict(os.environ, {'ADSB_BASE_DIR': test_dir}):
            # Import fresh modules - reload paths first, then data
            import importlib
            import utils.paths
            import utils.data
            importlib.reload(utils.paths)
            importlib.reload(utils.data)

            # Create config directory structure for Data instance
            Path(test_dir).mkdir(exist_ok=True)
            Path(f"{test_dir}/config").mkdir(exist_ok=True)

            # Create a Data instance to test
            data = utils.data.Data()
            assert data.data_path == Path(test_dir)
            assert data.config_path == Path(f"{test_dir}/config")
