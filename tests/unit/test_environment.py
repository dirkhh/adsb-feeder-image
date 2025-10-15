"""
Tests for utils.environment module
"""
import pytest
from unittest.mock import patch, MagicMock, call

from utils.environment import Env
from utils.config import write_values_to_config_json


class TestEnvClass:
    """Test the Env class"""

    def test_env_initialization_basic(self, adsb_test_env):
        """Test basic Env initialization"""
        env = Env("TEST_VAR", value="test_value")

        assert env.name == "TEST_VAR"
        assert env.value == "test_value"
        assert env.is_mandatory is False
        assert env.default is None

    def test_env_initialization_with_default(self, adsb_test_env):
        """Test Env initialization with default value"""
        env = Env("TEST_VAR", default="default_value")

        assert env.name == "TEST_VAR"
        assert env.value == "default_value"
        assert env.default == "default_value"

    def test_env_initialization_with_default_call(self, adsb_test_env):
        """Test Env initialization with default callable"""
        def default_func():
            return "dynamic_default"

        env = Env("TEST_VAR", default_call=default_func)

        assert env.name == "TEST_VAR"
        assert env.value == "dynamic_default"
        assert env.default == "dynamic_default"

    def test_env_initialization_mandatory(self, adsb_test_env):
        """Test Env initialization with mandatory flag"""
        env = Env("TEST_VAR", value="test_value", is_mandatory=True)

        assert env.name == "TEST_VAR"
        assert env.value == "test_value"
        assert env.is_mandatory is True

    def test_env_initialization_with_tags(self, adsb_test_env):
        """Test Env initialization with tags"""
        env = Env("TEST_VAR", value="test_value", tags=["tag1", "tag2"])

        assert env.name == "TEST_VAR"
        assert env.value == "test_value"
        assert env.tags == ["tag1", "tag2"]

    def test_env_initialization_list_default(self, adsb_test_env):
        """Test Env initialization with list default"""
        env = Env("TEST_VAR", default=["item1", "item2"])

        assert env.name == "TEST_VAR"
        assert env.value == ["item1"]
        assert env.default == ["item1", "item2"]

    def test_env_initialization_list_value(self, adsb_test_env):
        """Test Env initialization with list value"""
        env = Env("TEST_VAR", value=["value1", "value2"])

        assert env.name == "TEST_VAR"
        assert env.value == ["value1", "value2"]

    def test_env_str_representation(self, adsb_test_env):
        """Test string representation of Env"""
        env = Env("TEST_VAR", value="test_value")

        assert str(env) == "Env(TEST_VAR, test_value)"

    def test_env_list_str_representation(self, adsb_test_env):
        """Test string representation of Env with list value"""
        env = Env("TEST_VAR", value=["value1", "value2"])

        assert str(env) == "Env(TEST_VAR, ['value1', 'value2'])"

    def test_reconcile_pull_from_file(self, adsb_test_env):
        """Test _reconcile pulling value from file with real config"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write value to config file FIRST
        write_values_to_config_json({"TEST_VAR": "file_value"}, reason="test")

        # Create Env - will read from config
        env = Env("TEST_VAR", default="default_value")

        # Should have read value from file
        assert env.value == "file_value"

    def test_reconcile_no_file_value(self, adsb_test_env):
        """Test _reconcile when no value in file - writes to config when using setter"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json, read_values_from_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Start with empty config
        write_values_to_config_json({}, reason="test")

        # Create Env and use setter to write value to config
        env = Env("TEST_VAR")
        env.value = "new_value"  # Using setter writes to config

        # Verify it was written to config
        config = read_values_from_config_json()
        assert "TEST_VAR" in config
        assert config["TEST_VAR"] == "new_value"

    def test_reconcile_type_conversion_bool(self, adsb_test_env):
        """Test _reconcile type conversion for boolean"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write string value
        write_values_to_config_json({"TEST_VAR": "true"}, reason="test")

        # Create Env with boolean default - should convert string to bool
        env = Env("TEST_VAR", default=True)

        assert env.value is True

    def test_reconcile_type_conversion_int(self, adsb_test_env):
        """Test _reconcile type conversion for integer"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write string value
        write_values_to_config_json({"TEST_VAR": "123"}, reason="test")

        # Create Env with int default - should convert string to int
        env = Env("TEST_VAR", default=0)

        assert env.value == 123

    def test_reconcile_type_conversion_float(self, adsb_test_env):
        """Test _reconcile type conversion for float"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write int value
        write_values_to_config_json({"TEST_VAR": 456}, reason="test")

        # Create Env with float default - should convert int to float
        env = Env("TEST_VAR", default=0.0)

        assert env.value == 456.0

    def test_reconcile_type_conversion_list(self, adsb_test_env):
        """Test _reconcile type conversion for list"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write single value
        write_values_to_config_json({"TEST_VAR": "single_value"}, reason="test")

        # Create Env with list default - should convert to list
        env = Env("TEST_VAR", default=["default_value"])

        assert env.value == ["single_value"]

    def test_reconcile_type_conversion_list_bool(self, adsb_test_env):
        """Test _reconcile type conversion for boolean list"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write string value
        write_values_to_config_json({"TEST_VAR": "true"}, reason="test")

        # Create Env with bool list default - should convert to bool list
        env = Env("TEST_VAR", default=[False])

        assert env.value == [True]

    def test_reconcile_type_conversion_list_bool_existing(self, adsb_test_env):
        """Test _reconcile type conversion for existing boolean list"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write list with mixed bool types
        write_values_to_config_json({"TEST_VAR": [True, False, "true"]}, reason="test")

        # Create Env with bool list default and is_enabled tag - should convert all to bools
        env = Env("TEST_VAR", default=[False], tags=["is_enabled"])

        assert env.value == [True, False, True]

    def test_reconcile_invalid_type_conversion(self, adsb_test_env):
        """Test _reconcile with invalid type conversion"""
        from utils.config import write_values_to_config_json

        # Write invalid value for int conversion
        write_values_to_config_json({"TEST_VAR": "not_a_number"}, reason="test")

        # Create Env with int default - should keep default due to invalid conversion
        env = Env("TEST_VAR", default=0)

        # Should keep default value due to invalid conversion
        assert env.value == 0

    def test_reconcile_no_write_if_same(self, adsb_test_env):
        """Test _reconcile doesn't write if value is same as file"""
        from utils.config import write_values_to_config_json, read_values_from_config_json

        # Write value to config
        write_values_to_config_json({"TEST_VAR": "same_value"}, reason="test")

        # Read initial state
        config_before = read_values_from_config_json()

        # Create Env with same value - should not write again
        env = Env("TEST_VAR", value="same_value")

        # Config should be unchanged (no additional writes)
        config_after = read_values_from_config_json()
        assert config_before == config_after

    def test_reconcile_none_value(self, adsb_test_env):
        """Test _reconcile with None value - converts to empty string when using setter"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json, read_values_from_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write an initial value to config
        write_values_to_config_json({"TEST_VAR": "initial_value"}, reason="test")

        # Create Env (will read "initial_value" from config), then set to None - should write empty string
        env = Env("TEST_VAR", default="default_value")
        assert env.value == "initial_value"  # Verify it read from config

        env.value = None  # Using setter writes to config, None converts to ""

        # Should have written empty string
        config = read_values_from_config_json()
        assert config["TEST_VAR"] == ""

    def test_env_properties(self, adsb_test_env):
        """Test Env properties"""
        # Clear config to avoid interference from previous tests
        write_values_to_config_json({}, reason="test_env_properties")

        env = Env("TEST_VAR", value="test_value", is_mandatory=True)

        assert env.name == "TEST_VAR"
        assert env.value == "test_value"
        assert env.default is None
        assert env.is_mandatory is True
        assert env.tags == [""]

    def test_env_properties_with_values(self, adsb_test_env):
        """Test Env properties with all values set"""
        # Clear config to avoid interference from previous tests
        write_values_to_config_json({}, reason="test_env_properties_with_values")

        env = Env(
            "TEST_VAR",
            value="test_value",
            default="default_value",
            is_mandatory=True,
            tags=["tag1", "tag2"]
        )

        assert env.name == "TEST_VAR"
        assert env.value == "test_value"
        assert env.default == "default_value"
        assert env.is_mandatory is True
        assert env.tags == ["tag1", "tag2"]

    def test_env_properties_list(self, adsb_test_env):
        """Test Env properties with list values"""
        # Clear config to avoid interference from previous tests
        write_values_to_config_json({}, reason="test_env_properties_list")

        env = Env("TEST_VAR", value=["value1", "value2"], default=["default1"])

        assert env.name == "TEST_VAR"
        assert env.value == ["value1", "value2"]
        assert env.default == ["default1"]

    def test_env_properties_bool(self, adsb_test_env):
        """Test Env properties with boolean values"""
        # Clear config to avoid interference from previous tests
        write_values_to_config_json({}, reason="test_env_properties_bool")

        env = Env("TEST_VAR", value=True, default=False)

        assert env.name == "TEST_VAR"
        assert env.value is True
        assert env.default is False

    def test_env_properties_numeric(self, adsb_test_env):
        """Test Env properties with numeric values"""
        env = Env("TEST_VAR", value=42, default=0)

        assert env.name == "TEST_VAR"
        assert env.value == 42
        assert env.default == 0

    def test_env_properties_float(self, adsb_test_env):
        """Test Env properties with float values"""
        env = Env("TEST_VAR", value=3.14, default=0.0)

        assert env.name == "TEST_VAR"
        assert env.value == 3.14
        assert env.default == 0.0

    def test_env_integration_full_cycle(self, adsb_test_env):
        """Test full integration cycle of Env"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Start with empty config
        write_values_to_config_json({}, reason="test")

        # Create env with default - should write default to config
        env = Env("TEST_VAR", default="default_value")

        # Should have written default value
        assert env.value == "default_value"

        # Now write a different value to the file
        write_values_to_config_json({"TEST_VAR": "file_value"}, reason="test")

        # Create new env instance (should read from file)
        env2 = Env("TEST_VAR", default="default_value")

        assert env2.value == "file_value"

    @patch('utils.config.read_values_from_config_json')
    @patch('utils.config.write_values_to_config_json')
    def test_env_mandatory_validation(self, mock_write, mock_read):
        """Test mandatory field validation"""
        mock_read.return_value = {}

        # Create mandatory env without value
        env = Env("MANDATORY_VAR", is_mandatory=True)

        # Should still work, but value would be None/default
        assert env.is_mandatory is True

    def test_env_value_call(self, adsb_test_env):
        """Test env with value_call"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Start with empty config
        write_values_to_config_json({}, reason="test")

        # Define a dynamic value function
        def value_func():
            return "dynamic_value"

        # Create Env with value_call - the function should be called to get value
        env = Env("TEST_VAR", value_call=value_func)

        # Verify that calling env.value returns the result of value_func
        assert env.value == "dynamic_value"

    def test_env_complex_integration(self, adsb_test_env):
        """Test complex integration scenario"""
        import importlib
        import utils.paths
        import utils.config
        from utils.config import write_values_to_config_json

        # Reload modules to pick up new ADSB_BASE_DIR from fixture
        importlib.reload(utils.paths)
        importlib.reload(utils.config)

        # Write config with mixed types
        write_values_to_config_json({
            "STRING_VAR": "string_value",
            "BOOL_VAR": "true",
            "INT_VAR": "123",
            "FLOAT_VAR": 3.14,  # Write as float, not string
            "LIST_VAR": "item1,item2,item3"
        }, reason="test")

        # Create multiple env instances
        string_env = Env("STRING_VAR", default="")
        bool_env = Env("BOOL_VAR", default=False)
        int_env = Env("INT_VAR", default=0)
        float_env = Env("FLOAT_VAR", default=0.0)
        list_env = Env("LIST_VAR", default=["default_item"])

        # Verify all values are correctly typed
        assert string_env.value == "string_value"
        assert bool_env.value is True
        assert int_env.value == 123
        assert float_env.value == 3.14
        assert list_env.value == ["item1,item2,item3"]  # Single string converted to list
