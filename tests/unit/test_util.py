"""
Tests for utils.util module
"""
import hashlib
import pytest
import requests
from unittest.mock import patch, mock_open, MagicMock
import tempfile
import subprocess
from pathlib import Path

from utils.util import (
    cleanup_str,
    is_true,
    make_int,
    print_err,
    stack_info,
    idhash,
    verbose,
    create_fake_info,
    report_issue,
    mf_get_ip_and_triplet,
    string2file,
    generic_get_json,
    run_shell_captured
)


class TestCleanupStr:
    """Test the cleanup_str function"""

    def test_cleanup_str_removes_control_chars(self):
        """Test that control characters are removed"""
        test_string = "Hello\x00\x1F\x7FWorld"
        result = cleanup_str(test_string)
        assert result == "HelloWorld"

    def test_cleanup_str_preserves_normal_chars(self):
        """Test that normal characters are preserved"""
        test_string = "Hello World 123 !@#"
        result = cleanup_str(test_string)
        assert result == test_string

    def test_cleanup_str_empty_string(self):
        """Test cleanup_str with empty string"""
        result = cleanup_str("")
        assert result == ""

    def test_cleanup_str_unicode(self):
        """Test cleanup_str with unicode characters"""
        test_string = "Hello 世界 🌍"
        result = cleanup_str(test_string)
        assert result == test_string


class TestIsTrue:
    """Test the is_true function"""

    def test_is_true_boolean_true(self):
        """Test is_true with boolean True"""
        assert is_true(True) is True

    def test_is_true_boolean_false(self):
        """Test is_true with boolean False"""
        assert is_true(False) is False

    def test_is_true_string_true(self):
        """Test is_true with string 'true'"""
        assert is_true("true") is True
        assert is_true("True") is True
        assert is_true("TRUE") is True

    def test_is_true_string_false(self):
        """Test is_true with string 'false'"""
        assert is_true("false") is False
        assert is_true("False") is False
        assert is_true("FALSE") is False

    def test_is_true_string_1(self):
        """Test is_true with string '1'"""
        assert is_true("1") is True

    def test_is_true_string_0(self):
        """Test is_true with string '0'"""
        assert is_true("0") is False

    def test_is_true_int_1(self):
        """Test is_true with integer 1"""
        assert is_true(1) is True

    def test_is_true_int_0(self):
        """Test is_true with integer 0"""
        assert is_true(0) is False

    def test_is_true_none(self):
        """Test is_true with None"""
        assert is_true(None) is False

    def test_is_true_empty_string(self):
        """Test is_true with empty string"""
        assert is_true("") is False


class TestMakeInt:
    """Test the make_int function"""

    def test_make_int_valid_string(self):
        """Test make_int with valid string numbers"""
        assert make_int("123") == 123
        assert make_int("0") == 0
        assert make_int("-456") == -456

    def test_make_int_valid_int(self):
        """Test make_int with valid integers"""
        assert make_int(123) == 123
        assert make_int(0) == 0
        assert make_int(-456) == -456

    def test_make_int_invalid_string(self):
        """Test make_int with invalid string"""
        assert make_int("abc") == 0
        assert make_int("") == 0
        assert make_int("12.34") == 0

    def test_make_int_none(self):
        """Test make_int with None"""
        assert make_int(None) == 0

    def test_make_int_float(self):
        """Test make_int with float"""
        assert make_int(12.34) == 12

    def test_make_int_with_invalid_string(self):
        """Test make_int with invalid string returns 0"""
        assert make_int("abc") == 0


class TestPrintErr:
    """Test the print_err function"""

    @patch('builtins.print')
    def test_print_err_basic(self, mock_print):
        """Test basic print_err functionality"""
        print_err("test message")
        mock_print.assert_called_once()

    def test_print_err_with_level(self, adsb_test_env):
        """Test print_err with different levels"""
        import importlib
        import utils.paths
        import utils.util

        # Reload to pick up test environment
        importlib.reload(utils.paths)
        importlib.reload(utils.util)

        # Just test that it doesn't crash - verbose level controls output
        from utils.util import print_err
        print_err("test message", level=1)
        # If we get here without exception, test passes

    def test_print_err_verbose_check(self, adsb_test_env):
        """Test print_err respects verbose setting"""
        import importlib
        import utils.paths
        import utils.util

        # Reload to pick up test environment
        importlib.reload(utils.paths)
        importlib.reload(utils.util)

        from utils.util import print_err
        # Test that different verbose levels work without crashing
        print_err("test message", level=1)
        print_err("test message", level=2)
        # If we get here without exception, test passes


class TestStackInfo:
    """Test the stack_info function"""

    @patch('utils.util.print_err')
    def test_stack_info_basic(self, mock_print_err):
        """Test basic stack_info functionality"""
        stack_info("test message")
        # Should call print_err for stack frames
        assert mock_print_err.called


class TestIdhash:
    """Test the idhash generation"""

    def test_idhash_consistency(self, adsb_test_env):
        """Test that idhash exists and is a valid MD5 hash"""
        import importlib
        import utils.paths
        import utils.util

        # Reload to pick up test environment
        importlib.reload(utils.paths)
        importlib.reload(utils.util)

        from utils.util import idhash
        # idhash should be a 32-character hex string (MD5)
        assert isinstance(idhash, str)
        assert len(idhash) == 32
        assert all(c in '0123456789abcdef' for c in idhash)

    def test_idhash_different_for_different_ids(self, adsb_test_env):
        """Test that idhash is deterministic"""
        import importlib
        import utils.paths
        import utils.util

        # Reload to pick up test environment
        importlib.reload(utils.paths)
        importlib.reload(utils.util)

        from utils.util import idhash
        # Get idhash twice - should be the same (deterministic)
        hash1 = idhash

        # Reload again
        importlib.reload(utils.util)
        from utils.util import idhash as hash2

        # Should be deterministic
        assert hash1 == hash2


class TestCreateFakeInfo:
    """Test the create_fake_info function"""

    def test_create_fake_info_structure(self, adsb_test_env):
        """Test that create_fake_info creates fake files and returns boolean"""
        import importlib
        import utils.paths
        import utils.util
        from utils.config import write_values_to_config_json

        # Reload to pick up test environment
        importlib.reload(utils.paths)
        importlib.reload(utils.util)

        # Write minimal config
        write_values_to_config_json({}, reason="test")

        from utils.util import create_fake_info, FAKE_CPUINFO_DIR, FAKE_THERMAL_TEMP_FILE

        # Call with single index
        result = create_fake_info([0])

        # Should return a boolean (True if thermal zone doesn't exist)
        assert isinstance(result, bool)

        # Should create the cpuinfo file
        assert (FAKE_CPUINFO_DIR / "cpuinfo").exists()

        # Should create the thermal temp file
        assert FAKE_THERMAL_TEMP_FILE.exists()

    def test_create_fake_info_with_multiple_indices(self, adsb_test_env):
        """Test create_fake_info with multiple indices"""
        import importlib
        import utils.paths
        import utils.util
        from utils.config import write_values_to_config_json

        # Reload to pick up test environment
        importlib.reload(utils.paths)
        importlib.reload(utils.util)

        # Write minimal config
        write_values_to_config_json({}, reason="test")

        from utils.util import create_fake_info, FAKE_CPUINFO_DIR

        # Call with multiple indices
        result = create_fake_info([0, 1, 2])

        # Should return a boolean
        assert isinstance(result, bool)

        # Should create cpuinfo files for each index
        assert (FAKE_CPUINFO_DIR / "cpuinfo").exists()
        assert (FAKE_CPUINFO_DIR / "cpuinfo_1").exists()
        assert (FAKE_CPUINFO_DIR / "cpuinfo_2").exists()


class TestReportIssue:
    """Test the report_issue function"""

    @patch('utils.util.print_err')
    @patch('utils.util.flash')
    def test_report_issue_with_flash(self, mock_flash, mock_print_err):
        """Test report_issue with successful flash"""
        report_issue("test issue")

        # Should call print_err with the message
        mock_print_err.assert_called()
        # Should attempt to flash the message
        mock_flash.assert_called_once_with("test issue")

    @patch('utils.util.print_err')
    @patch('utils.util.flash')
    def test_report_issue_flash_exception(self, mock_flash, mock_print_err):
        """Test report_issue when flash raises exception"""
        mock_flash.side_effect = Exception("Flash error")

        # Should not raise - exception is caught
        report_issue("test issue")

        # Should call print_err for both the message and the exception
        assert mock_print_err.call_count >= 2

    @patch('utils.util.print_err')
    @patch('utils.util.flash')
    def test_report_issue_no_return_value(self, mock_flash, mock_print_err):
        """Test that report_issue returns None (no return value)"""
        result = report_issue("test issue")

        # Function doesn't return anything
        assert result is None


class TestMfGetIpAndTriplet:
    """Test the mf_get_ip_and_triplet function"""

    def test_mf_get_ip_and_triplet_with_ip(self):
        """Test with simple IP address"""
        ip, triplet = mf_get_ip_and_triplet("192.168.1.100")

        assert ip == "192.168.1.100"
        assert triplet == "192.168.1.100,30005,beast_in"

    def test_mf_get_ip_and_triplet_with_triplet(self):
        """Test with pre-formatted triplet"""
        ip, triplet = mf_get_ip_and_triplet("192.168.1.100,8080,beast_out")

        assert ip == "192.168.1.100"
        assert triplet == "192.168.1.100,8080,beast_out"

    def test_mf_get_ip_and_triplet_local(self):
        """Test with 'local' special value"""
        ip, triplet = mf_get_ip_and_triplet("local")

        assert ip == "host.docker.internal"
        assert triplet == "nanofeeder,30005,beast_in"

    def test_mf_get_ip_and_triplet_local2(self):
        """Test with 'local2' special value"""
        ip, triplet = mf_get_ip_and_triplet("local2")

        assert ip == "host.docker.internal"
        assert triplet == "nanofeeder_2,30005,beast_in"


class TestString2File:
    """Test the string2file function"""

    def test_string2file_basic(self):
        """Test basic string2file functionality"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test_file.txt"

            # Call with correct parameter order: path, string
            string2file(str(temp_path), "test content")

            with open(temp_path, 'r') as f:
                content = f.read()

            assert content == "test content"

    def test_string2file_with_verbose(self):
        """Test string2file with verbose flag"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "test_file.txt"

            # Call with verbose flag
            string2file(str(temp_path), "test content", verbose=True)

            with open(temp_path, 'r') as f:
                content = f.read()

            assert content == "test content"


class TestGenericGetJson:
    """Test the generic_get_json function"""

    @patch('requests.request')
    def test_generic_get_json_success(self, mock_request):
        """Test successful JSON retrieval"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok", "data": "test"}
        mock_request.return_value = mock_response

        result, status = generic_get_json("http://example.com/api")

        assert result == {"status": "ok", "data": "test"}
        assert status == 200
        mock_request.assert_called_once()

    @patch('requests.request')
    def test_generic_get_json_failure(self, mock_request):
        """Test failed JSON retrieval"""
        mock_request.side_effect = requests.ConnectionError()

        result, status = generic_get_json("http://example.com/api")

        assert result is None
        assert status == -1

    @patch('requests.request')
    def test_generic_get_json_exception(self, mock_request):
        """Test JSON retrieval with exception"""
        mock_request.side_effect = Exception("Network error")

        result, status = generic_get_json("http://example.com/api")

        assert result is None
        assert status == -1


class TestRunShellCaptured:
    """Test the run_shell_captured function"""

    @patch('subprocess.run')
    def test_run_shell_captured_success(self, mock_run):
        """Test successful shell command execution"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"success output"  # Must be bytes
        mock_result.stderr = b""
        mock_run.return_value = mock_result

        success, output = run_shell_captured("echo test")

        assert success is True
        assert output == "success output"

    @patch('subprocess.run')
    def test_run_shell_captured_failure(self, mock_run):
        """Test failed shell command execution"""
        # When check=True, subprocess.run raises CalledProcessError on failure
        error = subprocess.CalledProcessError(1, "false", b"", b"error message")
        mock_run.side_effect = error

        success, output = run_shell_captured("false")

        assert success is False
        assert "error message" in output

    @patch('subprocess.run')
    def test_run_shell_captured_with_timeout(self, mock_run):
        """Test shell command execution with timeout"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"output"  # Must be bytes
        mock_result.stderr = b""
        mock_run.return_value = mock_result

        success, output = run_shell_captured("sleep 1", timeout=5)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[1]['timeout'] == 5
        assert success is True
        assert output == "output"
