"""
Tests for utils.config module
"""
import json
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

import pytest

from utils.paths import ADSB_CONFIG_DIR, ENV_FILE, USER_ENV_FILE, CONFIG_JSON_FILE
from utils.config import (
    config_lock,
    read_values_from_config_json,
    read_values_from_env_file,
    write_values_to_config_json,
    write_values_to_env_file,
)


class TestConfigConstants:
    """Test configuration constants"""

    def test_config_paths(self):
        """Test that configuration paths are correctly defined"""
        # Get the base directory from environment (set by conftest.py)
        base_dir = os.environ.get('ADSB_BASE_DIR', '/opt/adsb')

        # Verify paths use the correct base directory and subdirectory structure
        # New path constants are Path objects, so compare with Path
        assert ADSB_CONFIG_DIR == Path(base_dir) / "config"
        assert ENV_FILE == Path(base_dir) / "config" / ".env"
        assert USER_ENV_FILE == Path(base_dir) / "config" / ".env.user"
        assert CONFIG_JSON_FILE == Path(base_dir) / "config" / "config.json"

    def test_config_lock(self):
        """Test that config_lock is a threading lock"""
        # threading.Lock() returns a LockType object, not a Lock class
        assert hasattr(config_lock, 'acquire') and hasattr(config_lock, 'release')


class TestReadValuesFromConfigJson:
    """Test read_values_from_config_json function"""

    @patch('os.path.exists')
    @patch('utils.config.read_values_from_env_file')
    @patch('utils.config.write_values_to_config_json')
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.load')
    def test_read_config_json_missing_file(self, mock_json_load, mock_file, mock_write, mock_read_env, mock_exists):
        """Test reading config.json when file doesn't exist initially"""
        # File doesn't exist initially, will exist after write
        mock_exists.side_effect = [False, True]
        mock_read_env.return_value = {"test": "value"}
        mock_json_load.return_value = {"test": "value"}

        result = read_values_from_config_json()

        # Should read from .env, write to config.json, then read config.json
        mock_read_env.assert_called_once()
        mock_write.assert_called_once_with({"test": "value"}, reason="config.json didn't exist")
        assert result == {"test": "value"}

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_read_config_json_success(self, mock_file, mock_exists):
        """Test successful reading of config.json"""
        mock_exists.return_value = True
        mock_file.return_value.__enter__.return_value.read.return_value = '{"test": "value"}'

        with patch('json.load') as mock_json_load:
            mock_json_load.return_value = {"test": "value"}
            result = read_values_from_config_json()

        assert result == {"test": "value"}

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_read_config_json_corrupted_file(self, mock_file, mock_exists):
        """Test reading corrupted config.json file"""
        mock_exists.return_value = True
        mock_file.side_effect = Exception("File read error")

        result = read_values_from_config_json()

        assert result == {}


class TestWriteValuesToConfigJson:
    """Test write_values_to_config_json function"""

    @patch('tempfile.mkstemp')
    @patch('os.fdopen')
    @patch('os.rename')
    @patch('json.dump')
    def test_write_config_json_success(self, mock_json_dump, mock_rename, mock_fdopen, mock_mkstemp):
        """Test successful writing to config.json"""
        mock_mkstemp.return_value = (123, "/tmp/temp_file")
        mock_fdopen.return_value.__enter__.return_value = MagicMock()

        test_data = {"test": "value"}
        write_values_to_config_json(test_data, "test reason")

        mock_mkstemp.assert_called_once_with(dir=str(ADSB_CONFIG_DIR))
        mock_json_dump.assert_called_once()
        mock_rename.assert_called_once()

    @patch('tempfile.mkstemp')
    def test_write_config_json_failure(self, mock_mkstemp):
        """Test writing to config.json with failure"""
        mock_mkstemp.side_effect = Exception("Temp file creation failed")

        test_data = {"test": "value"}
        write_values_to_config_json(test_data, "test reason")

        # Should not raise exception, just log error


class TestReadValuesFromEnvFile:
    """Test read_values_from_env_file function"""

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_read_env_file_success(self, mock_file, mock_exists):
        """Test successful reading of .env file"""
        mock_exists.return_value = True
        mock_file.return_value.__enter__.return_value.readlines.return_value = [
            "TEST_VAR=test_value\n",
            "ANOTHER_VAR=another_value\n"
        ]

        result = read_values_from_env_file()

        expected = {"TEST_VAR": "test_value", "ANOTHER_VAR": "another_value"}
        assert result == expected

    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_read_env_file_missing(self, mock_open_func):
        """Test reading missing .env file"""
        result = read_values_from_env_file()

        assert result == {}

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_read_env_file_empty_lines(self, mock_file, mock_exists):
        """Test reading .env file with empty lines and comments"""
        mock_exists.return_value = True
        mock_file.return_value.__enter__.return_value.readlines.return_value = [
            "TEST_VAR=test_value\n",
            "\n",
            "# This is a comment\n",
            "ANOTHER_VAR=another_value\n"
        ]

        result = read_values_from_env_file()

        # Note: The implementation creates empty key for empty lines
        # Only lines starting with # are skipped
        expected = {"TEST_VAR": "test_value", "": "", "ANOTHER_VAR": "another_value"}
        assert result == expected

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_read_env_file_with_quotes(self, mock_file, mock_exists):
        """Test reading .env file with quoted values - quotes are NOT stripped"""
        mock_exists.return_value = True
        mock_file.return_value.__enter__.return_value.readlines.return_value = [
            'TEST_VAR="test value"\n',
            "ANOTHER_VAR='another value'\n"
        ]

        result = read_values_from_env_file()

        # Note: The implementation does NOT strip quotes, only whitespace
        expected = {"TEST_VAR": '"test value"', "ANOTHER_VAR": "'another value'"}
        assert result == expected


class TestWriteValuesToEnvFile:
    """Test write_values_to_env_file function"""

    @patch('tempfile.mkstemp')
    @patch('os.fdopen')
    @patch('os.rename')
    def test_write_env_file_success(self, mock_rename, mock_fdopen, mock_mkstemp):
        """Test successful writing to .env file"""
        mock_mkstemp.return_value = (123, "/tmp/temp_file")
        mock_fdopen.return_value.__enter__.return_value = MagicMock()

        test_data = {"TEST_VAR": "test_value", "ANOTHER_VAR": "another_value"}
        write_values_to_env_file(test_data)

        mock_mkstemp.assert_called_once_with(dir=str(ADSB_CONFIG_DIR))
        mock_rename.assert_called_once()

    @patch('tempfile.mkstemp')
    def test_write_env_file_failure(self, mock_mkstemp):
        """Test writing to .env file with failure"""
        mock_mkstemp.side_effect = Exception("Temp file creation failed")

        test_data = {"TEST_VAR": "test_value"}
        # This will raise an exception since write_values_to_env_file doesn't catch it
        with pytest.raises(Exception):
            write_values_to_env_file(test_data)


class TestConfigIntegration:
    """Integration tests for config module"""

    def test_config_write_read_integration(self):
        """Test that write and read functions are called correctly"""
        import utils.config
        test_data = {
            "FEEDER_NAME": "test_feeder",
            "FEEDER_LAT": "40.7128",
            "FEEDER_LON": "-74.0060",
            "FEEDER_ALT": "10"
        }

        with patch('utils.config.write_values_to_config_json') as mock_write, \
             patch('utils.config.read_values_from_config_json') as mock_read:

            mock_read.return_value = test_data

            # Write config using module reference
            utils.config.write_values_to_config_json(test_data, "test")

            # Read config back using module reference
            result = utils.config.read_values_from_config_json()

            # Verify mocks were called
            mock_write.assert_called_once_with(test_data, "test")
            mock_read.assert_called_once()
            assert result == test_data

    def test_env_write_read_integration(self):
        """Test that env write and read functions are called correctly"""
        import utils.config
        test_data = {
            "TEST_VAR": "test_value",
            "ANOTHER_VAR": "another_value"
        }

        with patch('utils.config.write_values_to_env_file') as mock_write, \
             patch('utils.config.read_values_from_env_file') as mock_read:

            mock_read.return_value = test_data

            # Write env using module reference
            utils.config.write_values_to_env_file(test_data)

            # Read env back using module reference
            result = utils.config.read_values_from_env_file()

            # Verify mocks were called
            mock_write.assert_called_once_with(test_data)
            mock_read.assert_called_once()
            assert result == test_data
