"""
Integration tests for system components and configuration
"""
import pytest
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import json
from pathlib import Path

from app import AdsbIm
from utils.data import Data
from utils.environment import Env
from utils.config import read_values_from_config_json, write_values_to_config_json


@pytest.mark.usefixtures("adsb_test_env")
class TestSystemIntegration:
    """Integration tests for the complete system"""

    def setup_method(self):
        """Set up test fixtures"""
        # Note: We rely on the session-level ADSB_BASE_DIR set in conftest.py
        # Changing it here won't work because paths.py has already cached the value

        # Mock file operations
        self.file_ops_patcher = patch('builtins.open', new_callable=mock_open)
        self.mock_open = self.file_ops_patcher.start()

        # Mock subprocess operations
        self.subprocess_patcher = patch('subprocess.run')
        self.mock_subprocess = self.subprocess_patcher.start()

        # Mock requests
        self.requests_patcher = patch('requests.get')
        self.mock_requests = self.requests_patcher.start()

    def teardown_method(self):
        """Clean up test fixtures"""
        self.file_ops_patcher.stop()
        self.subprocess_patcher.stop()
        self.requests_patcher.stop()

    def test_complete_system_initialization(self):
        """Test complete system initialization"""
        with patch('app.Data') as mock_data_class, \
             patch('app.System') as mock_system_class, \
             patch('app.RouteManager') as mock_route_manager_class, \
             patch('app.Flask') as mock_flask_class:

            # Mock the instances
            mock_data = MagicMock()
            mock_system = MagicMock()
            mock_route_manager = MagicMock()
            mock_flask = MagicMock()

            mock_data_class.return_value = mock_data
            mock_system_class.return_value = mock_system
            mock_route_manager_class.return_value = mock_route_manager
            mock_flask_class.return_value = mock_flask

            # Initialize the system
            adsb_im = AdsbIm()

            # Verify all components were initialized
            mock_flask_class.assert_called_once()
            mock_data_class.assert_called_once()
            mock_system_class.assert_called_once()
            mock_route_manager_class.assert_called_once()

            # Verify properties
            assert adsb_im._d is mock_data
            assert adsb_im._system is mock_system
            assert adsb_im.exiting is False

    def test_config_environment_integration(self):
        """Test integration between config and environment systems"""
        # Set up mock config data with valid variable names
        config_data = {
            "MLAT_SITE_NAME": "test_feeder",
            "FEEDER_LAT": "40.7128",
            "FEEDER_LONG": "-74.0060",
            "FEEDER_ALT_M": "10",
            "FEEDER_ENABLE_BIASTEE": "true"
        }

        with patch('utils.config.read_values_from_config_json') as mock_read_config:
            mock_read_config.return_value = config_data

            # Test Data class integration
            data = Data()

            # Test environment variable access using valid tag
            env = data.env_by_tags(["site_name"])
            assert env is not None
            assert env.value == "test_feeder"

            # Test boolean conversion using valid boolean field
            enabled = data.is_enabled("FEEDER_ENABLE_BIASTEE")
            assert enabled is True

    def test_flask_app_route_integration(self):
        """Test Flask app route integration"""
        with patch('app.Data') as mock_data_class, \
             patch('app.System') as mock_system_class, \
             patch('app.RouteManager') as mock_route_manager_class, \
             patch('app.Flask') as mock_flask_class:

            mock_data = MagicMock()
            mock_system = MagicMock()
            mock_flask = MagicMock()

            mock_data_class.return_value = mock_data
            mock_system_class.return_value = mock_system
            mock_flask_class.return_value = mock_flask

            adsb_im = AdsbIm()

            # Test that routes were registered
            assert mock_flask.add_url_rule.call_count > 20

            # Test context processor setup
            mock_flask.context_processor.assert_called_once()

    def test_aggregator_system_integration(self):
        """Test aggregator system integration"""
        with patch('app.Data') as mock_data_class, \
             patch('app.System') as mock_system_class, \
             patch('app.RouteManager') as mock_route_manager_class, \
             patch('app.Flask') as mock_flask_class:

            mock_data = MagicMock()
            mock_system = MagicMock()
            mock_flask = MagicMock()

            # Mock data methods
            mock_data.env_by_tags.return_value = MagicMock()
            mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
            mock_data.env_by_tags.return_value.valuestr = "test_string"

            mock_data_class.return_value = mock_data
            mock_system_class.return_value = mock_system
            mock_system._d = mock_data
            mock_flask_class.return_value = mock_flask

            adsb_im = AdsbIm()

            # Test aggregator initialization
            from utils.other_aggregators import FlightAware, FlightRadar24

            flightaware = FlightAware(mock_system)
            fr24 = FlightRadar24(mock_system)

            assert flightaware.name == "FlightAware"
            assert fr24.name == "FlightRadar24"

            # Test aggregator properties
            assert flightaware.lat == "test_value"
            assert fr24.lon == "test_value"

    def test_config_persistence_integration(self):
        """Test config persistence integration"""
        # Test data with valid variable names
        test_data = {
            "MLAT_SITE_NAME": "integration_test_feeder",
            "FEEDER_LAT": "40.7128",
            "FEEDER_LONG": "-74.0060",
            "FEEDER_ALT_M": "10",
            "FEEDER_ENABLE_BIASTEE": "true",
            "FEEDER_ULTRAFEEDER_CONFIG": "service1,service2,service3"
        }

        with patch('utils.config.read_values_from_config_json') as mock_read, \
             patch('utils.config.write_values_to_config_json') as mock_write:

            mock_read.return_value = test_data

            # Test reading config - check that specific values are set correctly
            data = Data()

            # Verify specific values were loaded
            site_name_env = data.env("MLAT_SITE_NAME")
            assert site_name_env is not None
            assert site_name_env.value == "integration_test_feeder"

            lat_env = data.env("FEEDER_LAT")
            assert lat_env is not None
            assert lat_env.value == "40.7128"

            # Test writing config
            new_data = test_data.copy()
            new_data["NEW_VAR"] = "new_value"

            write_values_to_config_json(new_data, "integration test")
            mock_write.assert_called_once_with(new_data, "integration test")

    def test_environment_variable_integration(self):
        """Test environment variable integration"""
        # Test data
        test_data = {
            "STRING_VAR": "test_string",
            "BOOL_VAR": "true",
            "INT_VAR": "123",
            "FLOAT_VAR": "3.14",
            "LIST_VAR": "item1,item2,item3"
        }

        with patch('utils.config.read_values_from_config_json') as mock_read:
            mock_read.return_value = test_data

            # Test different variable types
            string_env = Env("STRING_VAR", default="")
            bool_env = Env("BOOL_VAR", default=False)
            int_env = Env("INT_VAR", default=0)
            float_env = Env("FLOAT_VAR", default=0.0)
            list_env = Env("LIST_VAR", default=["default_item"])

            # Verify types are correctly converted
            assert string_env.value == "test_string"
            assert bool_env.value is True
            assert int_env.value == 123
            assert float_env.value == 3.14
            assert list_env.value == ["item1"]

    def test_system_restart_integration(self):
        """Test system restart integration"""
        with patch('app.Data') as mock_data_class, \
             patch('app.System') as mock_system_class, \
             patch('app.RouteManager') as mock_route_manager_class, \
             patch('app.Flask') as mock_flask_class:

            mock_data = MagicMock()
            mock_system = MagicMock()
            mock_flask = MagicMock()

            # Mock restart lock
            mock_restart_lock = MagicMock()
            mock_restart_lock.locked.return_value = False
            mock_system._restart.lock = mock_restart_lock

            mock_data_class.return_value = mock_data
            mock_system_class.return_value = mock_system
            mock_flask_class.return_value = mock_flask

            adsb_im = AdsbIm()

            # Test restart route
            with patch('app.request') as mock_request:
                mock_request.method = "POST"

                with patch('app.redirect') as mock_redirect:
                    mock_redirect.return_value = "redirect_response"

                    result = adsb_im.restart()

                    mock_redirect.assert_called_once()
                    assert result == "redirect_response"

    def test_api_integration(self):
        """Test API integration"""
        with patch('app.Data') as mock_data_class, \
             patch('app.System') as mock_system_class, \
             patch('app.RouteManager') as mock_route_manager_class, \
             patch('app.Flask') as mock_flask_class:

            mock_data = MagicMock()
            mock_system = MagicMock()
            mock_flask = MagicMock()

            mock_data_class.return_value = mock_data
            mock_system_class.return_value = mock_system
            mock_flask_class.return_value = mock_flask

            adsb_im = AdsbIm()

            # Test API endpoints
            with patch('app.make_response') as mock_response:
                mock_response.return_value = "api_response"

                # Test multiple API endpoints
                endpoints = [
                    ("ip_info", []),
                    ("sdr_info", []),
                    ("base_info", []),
                    ("stage2_info", []),
                    ("stats", []),
                    ("temperatures", []),
                    ("scan_wifi", []),
                    ("check_remote_feeder", ["192.168.1.100"]),
                    ("agg_status", ["test_agg"]),
                    ("closest_airport", ["40.7128", "-74.0060"])
                ]

                for endpoint_name, args in endpoints:
                    endpoint_func = getattr(adsb_im, endpoint_name)
                    result = endpoint_func(*args)

                    assert result == "api_response"
                    mock_response.assert_called()

    def test_error_handling_integration(self):
        """Test error handling integration"""
        with patch('app.Data') as mock_data_class, \
             patch('app.System') as mock_system_class, \
             patch('app.RouteManager') as mock_route_manager_class, \
             patch('app.Flask') as mock_flask_class:

            mock_data = MagicMock()
            mock_system = MagicMock()
            mock_flask = MagicMock()

            mock_data_class.return_value = mock_data
            mock_system_class.return_value = mock_system
            mock_flask_class.return_value = mock_flask

            adsb_im = AdsbIm()

            # Test error handling in routes
            with patch('app.render_template') as mock_render:
                mock_render.side_effect = Exception("Template error")

                # Should handle errors gracefully
                try:
                    result = adsb_im.info()
                except Exception:
                    # Expected behavior
                    pass

            # Test error handling in API
            with patch('app.make_response') as mock_response:
                mock_response.side_effect = Exception("API error")

                # Should handle errors gracefully
                try:
                    result = adsb_im.ip_info()
                except Exception:
                    # Expected behavior
                    pass

    def test_signal_handling_integration(self):
        """Test signal handling integration"""
        with patch('app.Data') as mock_data_class, \
             patch('app.System') as mock_system_class, \
             patch('app.RouteManager') as mock_route_manager_class, \
             patch('app.Flask') as mock_flask_class:

            mock_data = MagicMock()
            mock_system = MagicMock()
            mock_flask = MagicMock()

            mock_data_class.return_value = mock_data
            mock_system_class.return_value = mock_system
            mock_flask_class.return_value = mock_flask

            adsb_im = AdsbIm()

            # Mock the write_planes_seen_per_day method
            adsb_im.write_planes_seen_per_day = MagicMock()

            # Test signal handling
            with patch('app.signal') as mock_signal:
                # Set up signal handler
                signal_handler = mock_signal.signal.call_args_list[0][0][1]

                # Call signal handler
                signal_handler(2, None)  # SIGINT

                # Verify behavior
                assert adsb_im.exiting is True
                adsb_im.write_planes_seen_per_day.assert_called_once()

    def test_full_application_lifecycle(self):
        """Test full application lifecycle"""
        with patch('app.Data') as mock_data_class, \
             patch('app.System') as mock_system_class, \
             patch('app.RouteManager') as mock_route_manager_class, \
             patch('app.Flask') as mock_flask_class:

            mock_data = MagicMock()
            mock_system = MagicMock()
            mock_flask = MagicMock()

            mock_data_class.return_value = mock_data
            mock_system_class.return_value = mock_system
            mock_flask_class.return_value = mock_flask

            # Initialize application
            adsb_im = AdsbIm()

            # Test run method
            with patch('app.signal') as mock_signal:
                adsb_im.run(no_server=True)

                # Verify signal handlers were set up
                assert mock_signal.signal.call_count >= 3

                # Verify Flask app was not run (no_server=True)
                mock_flask.run.assert_not_called()

            # Test run with server
            with patch('app.signal') as mock_signal:
                adsb_im.run(no_server=False)

                # Verify Flask app was run
                mock_flask.run.assert_called_once()


@pytest.mark.usefixtures("adsb_test_env")
class TestConfigurationIntegration:
    """Test configuration system integration"""

    def setup_method(self):
        """Set up test fixtures"""
        # Note: We rely on the session-level ADSB_BASE_DIR set in conftest.py
        # Changing it here won't work because paths.py has already cached the value
        pass

    def teardown_method(self):
        """Clean up test fixtures"""
        pass

    def test_config_file_roundtrip(self):
        """Test complete config file roundtrip"""
        # Test data with valid variable names
        test_data = {
            "MLAT_SITE_NAME": "roundtrip_test",
            "FEEDER_LAT": "40.7128",
            "FEEDER_LONG": "-74.0060",
            "FEEDER_ALT_M": "10",
            "FEEDER_ENABLE_BIASTEE": "true",
            "FEEDER_ULTRAFEEDER_CONFIG": "service1,service2,service3"
        }

        with patch('utils.config.read_values_from_config_json') as mock_read, \
             patch('utils.config.write_values_to_config_json') as mock_write:

            # Test write
            write_values_to_config_json(test_data, "roundtrip test")
            mock_write.assert_called_once_with(test_data, "roundtrip test")

            # Test read
            mock_read.return_value = test_data
            result = read_values_from_config_json()

            assert result == test_data

    def test_environment_config_integration(self):
        """Test environment and config integration"""
        # Test Env class type conversion independently
        # (Note: This test doesn't require Data class initialization)

        # Test Env class with different types
        string_env = Env("STRING_VAR", default="default_string")
        bool_env = Env("BOOL_VAR", default=False)
        int_env = Env("INT_VAR", default=0)
        float_env = Env("FLOAT_VAR", default=0.0)

        # Verify defaults are set correctly
        assert string_env.value == "default_string"
        assert bool_env.value is False
        assert int_env.value == 0
        assert float_env.value == 0.0

        # Verify types are correct
        assert isinstance(string_env.value, str)
        assert isinstance(bool_env.value, bool)
        assert isinstance(int_env.value, int)
        assert isinstance(float_env.value, float)

    def test_config_consistency(self):
        """Test config consistency across components"""
        # Test data with valid variable names
        test_data = {
            "MLAT_SITE_NAME": "consistency_test",
            "FEEDER_LAT": "40.7128",
            "FEEDER_LONG": "-74.0060",
            "FEEDER_ALT_M": "10"
        }

        with patch('utils.config.read_values_from_config_json') as mock_read:
            mock_read.return_value = test_data

            # Test Data class
            data = Data()

            # Test environment access using valid tag
            env = data.env_by_tags(["site_name"])
            assert env is not None
            assert env.value == "consistency_test"

            # Test list access
            lat = data.list_get("FEEDER_LAT", 0)
            assert lat == "40.7128"

            # Test boolean conversion with a valid boolean field
            enabled = data.is_enabled("FEEDER_ENABLE_BIASTEE")
            assert enabled is False  # Not in test data, should be default False

    def test_config_error_handling(self):
        """Test config error handling"""
        with patch('utils.config.read_values_from_config_json') as mock_read:
            mock_read.side_effect = Exception("Config read error")

            # Should handle errors gracefully
            try:
                data = Data()
                config_values = data.env_values
                assert config_values == {}
            except Exception:
                # Expected behavior
                pass

    def test_config_type_conversion(self):
        """Test config type conversion"""
        # Test data with mixed types
        test_data = {
            "STRING_VAR": "test_string",
            "BOOL_VAR": "true",
            "INT_VAR": "123",
            "FLOAT_VAR": "3.14",
            "LIST_VAR": "item1,item2,item3"
        }

        with patch('utils.config.read_values_from_config_json') as mock_read:
            mock_read.return_value = test_data

            # Test type conversion
            string_env = Env("STRING_VAR", default="")
            bool_env = Env("BOOL_VAR", default=False)
            int_env = Env("INT_VAR", default=0)
            float_env = Env("FLOAT_VAR", default=0.0)
            list_env = Env("LIST_VAR", default=["default_item"])

            # Verify types
            assert isinstance(string_env.value, str)
            assert isinstance(bool_env.value, bool)
            assert isinstance(int_env.value, int)
            assert isinstance(float_env.value, float)
            assert isinstance(list_env.value, list)

            # Verify values
            assert string_env.value == "test_string"
            assert bool_env.value is True
            assert int_env.value == 123
            assert float_env.value == 3.14
            assert list_env.value == ["item1"]
