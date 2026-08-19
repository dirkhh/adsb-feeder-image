"""
Tests for utils.data module
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from utils.data import Data
from utils.environment import Env
from utils.config import write_values_to_config_json


def reset_data_singleton():
    """Reset the Data singleton and reload paths module for testing"""
    import importlib
    import utils.paths
    import utils.config

    # Reload paths and config modules to pick up new ADSB_BASE_DIR from environment
    importlib.reload(utils.paths)
    importlib.reload(utils.config)

    # Use the new reset_for_testing method
    Data.reset_for_testing()


class TestDataClass:
    """Test the Data class"""

    def test_data_singleton(self):
        """Test that Data is a singleton"""
        data1 = Data()
        data2 = Data()
        assert data1 is data2

    def test_reset_for_testing(self, adsb_test_env):
        """Test that reset_for_testing properly resets the singleton"""
        # Create first instance
        data1 = Data()
        data1.previous_version = "1.0.0"
        data1._env_by_tags_dict[("test",)] = "test_value"

        # Verify it's a singleton
        data2 = Data()
        assert data1 is data2
        assert data2.previous_version == "1.0.0"

        # Reset the singleton
        Data.reset_for_testing()

        # Create new instance - should be a different object
        data3 = Data()
        assert data3 is not data1
        assert data3.previous_version == ""
        assert data3._env_by_tags_dict == {}

    def test_reset_for_testing_requires_test_env(self, monkeypatch):
        """Test that reset_for_testing raises error outside test environment"""
        # Remove ADSB_TEST_ENV to simulate production
        monkeypatch.delenv("ADSB_TEST_ENV", raising=False)

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="can only be called in test environment"):
            Data.reset_for_testing()

    def test_data_paths(self):
        """Test that Data has correct paths"""
        import os
        data = Data()
        expected_base = Path(os.environ.get('ADSB_BASE_DIR', '/opt/adsb'))
        assert data.data_path == expected_base
        assert data.config_path == expected_base / "config"
        assert data.env_file_path == expected_base / "config" / ".env"
        assert data.version_file == expected_base / "adsb.im.version"
        assert data.secure_image_path == expected_base / "adsb.im.secure_image"

    def test_data_initial_values(self):
        """Test initial values of Data instance"""
        data = Data()
        assert data.is_feeder_image is True
        assert data._env_by_tags_dict == {}
        assert data.ultrafeeder == []
        assert data.previous_version == ""

    def test_proxy_routes(self):
        """Test proxy routes configuration"""
        data = Data()
        routes = data.proxy_routes

        # Check that routes is a list of lists
        assert isinstance(routes, list)
        assert len(routes) > 0

        # Check structure of first route
        first_route = routes[0]
        assert isinstance(first_route, list)
        assert len(first_route) == 3  # endpoint, port, url_path

    def test_env_values_property(self, adsb_test_env):
        """Test env_values property with real Env instances"""
        reset_data_singleton()

        # Write test data to config file
        write_values_to_config_json({"TEST_VAR": "test_value"}, reason="test")

        # Create real Env instance (which registers itself with Data._env)
        test_env = Env("TEST_VAR", tags=["test"])

        data = Data()
        data._env.add(test_env)  # Add to Data's env set
        env_values = data.env_values

        # Check that our test value exists (config will have many default values too)
        assert "TEST_VAR" in env_values
        assert env_values["TEST_VAR"] == "test_value"

    def test_env_values_caching(self, adsb_test_env):
        """Test that env_values returns consistent values"""
        reset_data_singleton()

        # Write test data to config file
        write_values_to_config_json({"TEST_VAR": "test_value"}, reason="test")

        # Create real Env instance
        test_env = Env("TEST_VAR", tags=["test"])

        data = Data()
        data._env.add(test_env)

        # First call
        env_values1 = data.env_values
        # Second call
        env_values2 = data.env_values

        # Should return consistent values (not necessarily same object, but same content)
        assert env_values1 == env_values2
        assert env_values1["TEST_VAR"] == env_values2["TEST_VAR"]

    def test_env_by_tags(self, adsb_test_env):
        """Test env_by_tags method with real Env instances"""
        reset_data_singleton()

        # Write test data to config file FIRST (before creating Env instances)
        write_values_to_config_json({
            "TEST_FEEDER_NAME": "test_feeder",
            "TEST_FEEDER_LAT": "40.7128",
            "TEST_FEEDER_LON": "-74.0060"
        }, reason="test")

        # Create real Env instances with tags, like the real app does
        # These will read their values from the config we just wrote
        test_name_env = Env("TEST_FEEDER_NAME", tags=["test_name"])
        test_lat_env = Env("TEST_FEEDER_LAT", tags=["test_lat", "location"])
        test_lon_env = Env("TEST_FEEDER_LON", tags=["test_lon", "location"])

        # Get Data instance and add our test Env instances to it
        data = Data()
        data._env.add(test_name_env)
        data._env.add(test_lat_env)
        data._env.add(test_lon_env)

        # Test finding environment variable by single tag
        env = data.env_by_tags(["test_name"])
        assert env is not None
        assert env.name == "TEST_FEEDER_NAME"
        assert env.value == "test_feeder"

        # Test finding environment variable by multiple tags (both tags must match)
        env = data.env_by_tags(["test_lat", "location"])
        assert env is not None
        assert env.name == "TEST_FEEDER_LAT"
        assert env.value == "40.7128"

    def test_env_by_tags_not_found(self, adsb_test_env):
        """Test env_by_tags when variable not found"""
        reset_data_singleton()

        # Write test data to config file
        write_values_to_config_json({"TEST_VAR": "test_value"}, reason="test")

        # Create a real Env instance but with different tags
        test_env = Env("TEST_VAR", tags=["different_tag"])

        data = Data()
        data._env.add(test_env)

        # Search for a tag that doesn't exist - should raise Exception
        with pytest.raises(Exception, match="No Env for tags"):
            data.env_by_tags(["nonexistent_tag"])

    def test_is_enabled(self, adsb_test_env):
        """Test is_enabled method with real Env instances"""
        reset_data_singleton()

        # Write test data to config file
        write_values_to_config_json({
            "ENABLE_SERVICE": True,
            "DISABLE_SERVICE": False,
            "NO_SERVICE": "some_value"
        }, reason="test")

        # Create real Env instances with is_enabled tag (like app does)
        enabled_env = Env("ENABLE_SERVICE", default=False, tags=["enabled_service", "is_enabled"])
        disabled_env = Env("DISABLE_SERVICE", default=False, tags=["disabled_service", "is_enabled"])
        no_service_env = Env("NO_SERVICE", tags=["no_service"])  # No is_enabled tag

        data = Data()
        data._env.add(enabled_env)
        data._env.add(disabled_env)
        data._env.add(no_service_env)

        # is_enabled looks for tag + "is_enabled"
        assert data.is_enabled("enabled_service") is True
        assert data.is_enabled("disabled_service") is False

        # Calling is_enabled on tag without is_enabled tag should raise exception
        with pytest.raises(Exception, match="No Env for tags"):
            data.is_enabled("no_service")  # No is_enabled tag

        # Calling is_enabled on nonexistent tag should raise exception
        with pytest.raises(Exception, match="No Env for tags"):
            data.is_enabled("nonexistent")

    def test_list_is_enabled(self, adsb_test_env):
        """Test list_is_enabled method with real list Env instances"""
        reset_data_singleton()

        # Write test data to config file - use boolean/truthy values
        write_values_to_config_json({
            "ENABLED_LIST": [True, False, True, "true", "1", "on"]
        }, reason="test")

        # Create real Env instance with list default and is_enabled tag
        enabled_env = Env("ENABLED_LIST", default=[False], tags=["enabled_list", "is_enabled"])

        data = Data()
        data._env.add(enabled_env)

        # Test list_is_enabled with boolean values
        assert data.list_is_enabled("enabled_list", 0) is True   # True boolean
        assert data.list_is_enabled("enabled_list", 1) is False  # False boolean
        assert data.list_is_enabled("enabled_list", 2) is True   # True boolean
        assert data.list_is_enabled("enabled_list", 3) is True   # "true" string
        assert data.list_is_enabled("enabled_list", 4) is True   # "1" string
        assert data.list_is_enabled("enabled_list", 5) is True   # "on" string

    def test_list_is_enabled_nonexistent(self, adsb_test_env):
        """Test list_is_enabled with nonexistent variable raises exception"""
        reset_data_singleton()

        # Write empty config
        write_values_to_config_json({}, reason="test")

        data = Data()
        # Don't add any Env instances

        # Should raise exception for nonexistent tags
        with pytest.raises(Exception, match="No Env for tags"):
            data.list_is_enabled("nonexistent", idx=0)

    def test_list_get(self, adsb_test_env):
        """Test list_get method on Env instance"""
        reset_data_singleton()

        # Write test data to config file
        write_values_to_config_json({
            "SERVICE_LIST": ["service1", "service2", "service3"]
        }, reason="test")

        # Create real Env instance with list default
        service_env = Env("SERVICE_LIST", default=[""], tags=["service_list"])

        data = Data()
        data._env.add(service_env)

        # Get the Env and test list_get on it
        env = data.env_by_tags(["service_list"])
        assert env.list_get(0) == "service1"
        assert env.list_get(1) == "service2"
        assert env.list_get(2) == "service3"

    def test_list_get_out_of_bounds(self, adsb_test_env):
        """Test list_get with out of bounds index on Env"""
        reset_data_singleton()

        # Write test data to config file
        write_values_to_config_json({
            "SERVICE_LIST": ["service1", "service2"]
        }, reason="test")

        # Create real Env instance with list default
        service_env = Env("SERVICE_LIST", default=[""], tags=["service_list"])

        data = Data()
        data._env.add(service_env)

        # Get the Env and test out of bounds - should pad with default value
        env = data.env_by_tags(["service_list"])
        assert env.list_get(5) == ""
        assert env.list_get(-1) == ""

    def test_list_get_nonexistent(self, adsb_test_env):
        """Test that getting nonexistent Env raises exception"""
        reset_data_singleton()

        # Write empty config
        write_values_to_config_json({}, reason="test")

        data = Data()
        # Don't add any Env instances

        # Should raise exception for nonexistent tag
        with pytest.raises(Exception, match="No Env for tags"):
            data.env_by_tags(["nonexistent"])

    @patch('pathlib.Path.exists')
    def test_is_feeder_image_detection(self, mock_exists):
        """Test is_feeder_image detection"""
        # Test when OS flag file exists
        def exists_side_effect(path):
            if str(path) == "/opt/adsb/os.adsb.feeder.image":
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        data = Data()
        assert data.is_feeder_image is True

    @patch('pathlib.Path.exists')
    def test_is_feeder_image_detection_false(self, mock_exists):
        """Test is_feeder_image detection when flag file doesn't exist"""
        # Test when OS flag file doesn't exist
        def exists_side_effect(path):
            if str(path) == "/opt/adsb/os.adsb.feeder.image":
                return False
            return False

        mock_exists.side_effect = exists_side_effect

        data = Data()
        # Should still be True due to heuristic check
        assert data.is_feeder_image is True

    def test_ultrafeeder_property(self):
        """Test ultrafeeder property"""
        data = Data()

        # Initially empty
        assert data.ultrafeeder == []

        # Can be modified
        data.ultrafeeder = ["feeder1", "feeder2"]
        assert data.ultrafeeder == ["feeder1", "feeder2"]

    def test_previous_version_property(self):
        """Test previous_version property"""
        data = Data()

        # Initially empty
        assert data.previous_version == ""

        # Can be modified
        data.previous_version = "1.0.0"
        assert data.previous_version == "1.0.0"

    def test_env_values_integration(self, adsb_test_env):
        """Test integration of env_values with other methods using real Env instances"""
        reset_data_singleton()

        # Write test data to config file
        write_values_to_config_json({
            "TEST_FEEDER_NAME": "test_feeder",
            "TEST_FEEDER_LAT": "40.7128",
            "TEST_FEEDER_LON": "-74.0060",
            "TEST_ENABLE_SERVICE": True,
            "TEST_SERVICE_LIST": ["service1", "service2", "service3"]
        }, reason="test")

        # Create real Env instances
        name_env = Env("TEST_FEEDER_NAME", tags=["test_name"])
        lat_env = Env("TEST_FEEDER_LAT", tags=["test_lat"])
        lon_env = Env("TEST_FEEDER_LON", tags=["test_lon"])
        enabled_env = Env("TEST_ENABLE_SERVICE", default=False, tags=["test_service", "is_enabled"])
        list_env = Env("TEST_SERVICE_LIST", default=[""], tags=["test_list"])  # No is_enabled tag for string list

        data = Data()
        data._env.add(name_env)
        data._env.add(lat_env)
        data._env.add(lon_env)
        data._env.add(enabled_env)
        data._env.add(list_env)

        # Test that all methods work with real Env instances
        env_values = data.env_values
        assert "TEST_FEEDER_NAME" in env_values
        assert env_values["TEST_FEEDER_NAME"] == "test_feeder"

        # Test env_by_tags
        env = data.env_by_tags(["test_name"])
        assert env.value == "test_feeder"

        # Test is_enabled
        assert data.is_enabled("test_service") is True

        # Test list methods on Env
        list_env_instance = data.env_by_tags(["test_list"])
        assert list_env_instance.list_get(0) == "service1"
        assert list_env_instance.list_get(1) == "service2"
        assert list_env_instance.list_get(2) == "service3"

    def test_proxy_routes_content(self, adsb_test_env):
        """Test specific content of proxy routes"""
        reset_data_singleton()

        data = Data()
        routes = data.proxy_routes

        # Check for specific expected routes
        route_dict = {route[0]: route for route in routes}

        # Test some expected routes
        assert "/map/" in route_dict
        assert "/tar1090/" in route_dict
        assert "/graphs1090/" in route_dict
        assert "/fr24/" in route_dict
        assert "/logs/" in route_dict

        # Check route structure: [endpoint, port, url_path]
        map_route = route_dict["/map/"]
        assert map_route[0] == "/map/"
        assert isinstance(map_route[1], (int, str))  # port can be int or string
        assert map_route[2] == "/"  # url_path
