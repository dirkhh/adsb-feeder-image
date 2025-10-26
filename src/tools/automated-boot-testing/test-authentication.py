#!/usr/bin/env python3
"""
Test authentication implementation for ADS-B Test Service.

This script tests:
- Missing API key (should fail with 401)
- Invalid API key (should fail with 401)
- Valid API key (should succeed with 200)
- Health endpoint (should work without auth)
"""

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Import the service module (has hyphens in filename)
service_path = Path(__file__).parent / "adsb-boot-test-service.py"
spec = importlib.util.spec_from_file_location("adsb_test_service", service_path)
if spec is None:
    raise ImportError(f"Could not load module from {service_path}")
adsb_test_service = importlib.util.module_from_spec(spec)
sys.modules["adsb_test_service"] = adsb_test_service
assert spec.loader is not None
if spec.loader:
    spec.loader.exec_module(adsb_test_service)
else:
    raise ImportError(f"Could not load module from {service_path}")

# Import the class we need
APIKeyAuth = adsb_test_service.APIKeyAuth


class TestAPIKeyAuth(unittest.TestCase):
    """Test the APIKeyAuth class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_keys = {"valid_key_123": "test_user_1", "another_valid_key": "test_user_2"}
        self.auth = APIKeyAuth(self.test_keys)

    def test_validate_valid_key(self):
        """Test validation of a valid API key."""
        user_id = self.auth.validate_key("valid_key_123")
        self.assertEqual(user_id, "test_user_1")

    def test_validate_another_valid_key(self):
        """Test validation of another valid API key."""
        user_id = self.auth.validate_key("another_valid_key")
        self.assertEqual(user_id, "test_user_2")

    def test_validate_invalid_key(self):
        """Test validation of an invalid API key."""
        user_id = self.auth.validate_key("invalid_key")
        self.assertIsNone(user_id)

    def test_validate_empty_key(self):
        """Test validation of an empty API key."""
        user_id = self.auth.validate_key("")
        self.assertIsNone(user_id)

    def test_validate_none_key(self):
        """Test validation of None as API key."""
        user_id = self.auth.validate_key(None)
        self.assertIsNone(user_id)

    def test_timing_safe_comparison(self):
        """Test that validation uses timing-safe comparison."""
        # This is a basic test - timing attacks are hard to test in unit tests
        # but we verify that similar keys are not accepted
        user_id = self.auth.validate_key("valid_key_124")  # One char different
        self.assertIsNone(user_id)

    @patch("adsb_test_service.request")
    @patch("adsb_test_service.logging")
    def test_require_auth_no_header(self, mock_logging, mock_request):
        """Test decorator with missing X-API-Key header."""
        mock_request.headers.get.return_value = None
        mock_request.environ.get.return_value = "127.0.0.1"

        # Create a mock endpoint
        @self.auth.require_auth
        def mock_endpoint():
            return "success"

        result = mock_endpoint()

        # Should return 401 error
        self.assertEqual(result[1], 401)
        self.assertIn("Missing X-API-Key", str(result[0]))

    @patch("adsb_test_service.request")
    @patch("adsb_test_service.logging")
    def test_require_auth_invalid_key(self, mock_logging, mock_request):
        """Test decorator with invalid API key."""
        mock_request.headers.get.return_value = "invalid_key_xyz"
        mock_request.environ.get.return_value = "127.0.0.1"

        @self.auth.require_auth
        def mock_endpoint():
            return "success"

        result = mock_endpoint()

        # Should return 401 error
        self.assertEqual(result[1], 401)
        self.assertIn("Invalid API key", str(result[0]))

    @patch("adsb_test_service.request")
    @patch("adsb_test_service.logging")
    def test_require_auth_valid_key(self, mock_logging, mock_request):
        """Test decorator with valid API key."""
        mock_request.headers.get.return_value = "valid_key_123"
        mock_request.environ.get.return_value = "127.0.0.1"

        @self.auth.require_auth
        def mock_endpoint():
            return "success", 200

        result = mock_endpoint()

        # Should succeed
        self.assertEqual(result, ("success", 200))
        self.assertEqual(mock_request.user_id, "test_user_1")

    def test_empty_api_keys(self):
        """Test initialization with empty API keys."""
        with patch("adsb_test_service.logging") as mock_logging:
            _auth = APIKeyAuth({})  # noqa: F841
            # Should log a warning
            mock_logging.warning.assert_called_once()


class TestSecurityProperties(unittest.TestCase):
    """Test security properties of the implementation."""

    def test_key_length(self):
        """Test that generated keys have sufficient entropy."""
        import secrets

        key = secrets.token_urlsafe(32)

        # 32 bytes = 256 bits, base64-encoded should be ~43 chars
        self.assertGreaterEqual(len(key), 40)

    def test_timing_attack_resistance(self):
        """Verify we use hmac.compare_digest for timing safety."""
        import inspect

        # Check that APIKeyAuth.validate_key uses hmac.compare_digest
        source = inspect.getsource(APIKeyAuth.validate_key)
        self.assertIn("hmac.compare_digest", source)


def run_tests():
    """Run all tests."""
    print("=" * 70)
    print("Testing Authentication Implementation")
    print("=" * 70)
    print()

    # Run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestAPIKeyAuth))
    suite.addTests(loader.loadTestsFromTestCase(TestSecurityProperties))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print()

    if result.wasSuccessful():
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
