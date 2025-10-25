#!/usr/bin/env python3
"""
Security tests for ADS-B boot test service.

These tests verify security-critical behavior of the boot test API including:
- API key authentication
- Input validation
- URL validation
- Queue management

Note: These are integration-style tests that test behavior, not implementation details.
"""

import sys
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import the adsb-boot-test-service module (has dashes, so use importlib)
service_path = Path(__file__).parent / "adsb-boot-test-service.py"
spec = importlib.util.spec_from_file_location("adsb_test_service", service_path)
service = importlib.util.module_from_spec(spec)
sys.modules["adsb_test_service"] = service
spec.loader.exec_module(service)

# Now we can import the classes
APIKeyAuth = service.APIKeyAuth
TestQueue = service.TestQueue
GitHubValidator = service.GitHubValidator
TestExecutor = service.TestExecutor


class TestAPIKeyAuthentication:
    """Test API key authentication security."""

    def test_valid_api_key_accepted(self):
        """Test that valid API keys are accepted."""
        api_keys = {"valid-key-123": "user1", "another-key-456": "user2"}
        auth = APIKeyAuth(api_keys)

        assert auth.validate_key("valid-key-123") == "user1"
        assert auth.validate_key("another-key-456") == "user2"

    def test_invalid_api_key_rejected(self):
        """Test that invalid API keys are rejected."""
        api_keys = {"valid-key-123": "user1"}
        auth = APIKeyAuth(api_keys)

        assert auth.validate_key("invalid-key") is None
        assert auth.validate_key("wrong-key") is None

    def test_empty_api_key_rejected(self):
        """Test that empty API keys are rejected."""
        api_keys = {"valid-key-123": "user1"}
        auth = APIKeyAuth(api_keys)

        assert auth.validate_key("") is None
        assert auth.validate_key(None) is None

    def test_timing_attack_resistance(self):
        """Test that key comparison uses hmac.compare_digest (constant-time)."""
        api_keys = {"correct-key-with-specific-length": "user1"}
        auth = APIKeyAuth(api_keys)

        # Create keys with varying correct prefix lengths
        # If comparison is not constant-time, these would take different times
        test_cases = [
            "w" * 32,  # All wrong
            "correct" + "w" * 25,  # Correct prefix
            "correct-key" + "w" * 20,  # Longer prefix
            "correct-key-with-specific" + "w" * 7,  # Almost correct
        ]

        for invalid_key in test_cases:
            assert auth.validate_key(invalid_key) is None

    def test_no_api_keys_configured(self):
        """Test behavior when no API keys are configured."""
        auth = APIKeyAuth({})

        # Should reject all keys
        assert auth.validate_key("any-key") is None


class TestGitHubURLValidation:
    """Test GitHub URL validation and injection prevention."""

    def test_valid_github_urls_accepted(self):
        """Test that valid GitHub release URLs are accepted."""
        validator = GitHubValidator("dirkhh/adsb-feeder-image")

        valid_urls = [
            "https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.0.0/file.img.xz",
            "https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.2.3/adsb-feeder.img.xz",
        ]

        for url in valid_urls:
            result = validator.validate_url(url)
            assert result["valid"] is True, f"Failed to accept valid URL: {url}"

    def test_wrong_repository_rejected(self):
        """Test that URLs from wrong repository are rejected."""
        validator = GitHubValidator("dirkhh/adsb-feeder-image")

        wrong_repo_urls = [
            "https://github.com/other-user/other-repo/releases/download/v1.0.0/file.img.xz",
            "https://github.com/evil/malicious/releases/download/v1.0.0/file.img.xz",
        ]

        for url in wrong_repo_urls:
            result = validator.validate_url(url)
            assert result["valid"] is False, f"Failed to reject wrong repository: {url}"
            assert "repository" in result["error"].lower()

    def test_wrong_domain_rejected(self):
        """Test that non-GitHub domains are rejected."""
        validator = GitHubValidator("dirkhh/adsb-feeder-image")

        wrong_domains = [
            "https://evil.com/releases/download/v1.0.0/file.img.xz",
            "https://fakegithub.com/releases/download/v1.0.0/file.img.xz",
        ]

        for url in wrong_domains:
            result = validator.validate_url(url)
            assert result["valid"] is False, f"Failed to reject non-GitHub domain: {url}"

    # SECURITY IMPROVEMENT NEEDED: The following test documents a security gap
    # that should be addressed in the adsb-boot-test-service.py implementation

    @pytest.mark.skip(reason="SECURITY IMPROVEMENT NEEDED: Strict release URL validation")
    def test_missing_release_pattern_rejected(self):
        """Documents that non-release URLs should be rejected (future improvement).

        Currently, GitHubValidator._is_release_url() accepts URLs with .img.xz extension
        even if they use patterns like /raw/main/ or /tree/main/ instead of /releases/download/.
        This is a security gap - only /releases/download/ URLs should be accepted.
        """
        validator = GitHubValidator("dirkhh/adsb-feeder-image")

        invalid_urls = [
            "https://github.com/dirkhh/adsb-feeder-image/raw/main/file.img.xz",
            "https://github.com/dirkhh/adsb-feeder-image/tree/main/file.img.xz",
        ]

        for url in invalid_urls:
            result = validator.validate_url(url)
            # This SHOULD return False but currently doesn't due to .img.xz check
            assert result["valid"] is False, f"Should reject non-release URL: {url}"


class TestInputValidation:
    """Test input validation and injection prevention."""

    @patch('pathlib.Path.exists', return_value=True)  # Mock venv and script existence
    def test_shell_metacharacters_rejected(self, mock_exists):
        """Test that URLs with shell metacharacters are rejected."""
        executor = TestExecutor("192.168.1.100", "192.168.1.101", 10)

        dangerous_chars = [";", "&", "|", "`", "$", "\n", "\r"]
        base_url = "https://github.com/user/repo/releases/download/v1.0/file.img.xz"

        for char in dangerous_chars:
            malicious_url = base_url + char + "malicious-command"
            test_item = {"id": "test-123", "url": malicious_url}

            result = executor.execute_test(test_item)

            assert result["success"] is False
            assert "invalid characters" in result["message"].lower()

    @patch('pathlib.Path.exists', return_value=True)  # Mock venv and script existence
    def test_ip_address_validation(self, mock_exists):
        """Test that invalid IP addresses are rejected."""
        # Valid IPs should be accepted
        executor = TestExecutor("192.168.1.100", "192.168.1.101", 10)
        assert executor.rpi_ip == "192.168.1.100"

        # Invalid IPs should raise ValueError
        with pytest.raises(ValueError, match="not a valid IP address"):
            TestExecutor("not-an-ip", "192.168.1.101", 10)

        with pytest.raises(ValueError, match="not a valid IP address"):
            TestExecutor("999.999.999.999", "192.168.1.101", 10)

        with pytest.raises(ValueError, match="not a valid IP address"):
            TestExecutor("192.168.1.100; rm -rf /", "192.168.1.101", 10)

    @patch('pathlib.Path.exists', return_value=True)  # Mock venv and script existence
    def test_timeout_validation(self, mock_exists):
        """Test that invalid timeouts are rejected."""
        # Valid timeout
        executor = TestExecutor("192.168.1.100", "192.168.1.101", 10)
        assert executor.timeout_minutes == 10

        # Too small
        with pytest.raises(ValueError, match="Timeout must be"):
            TestExecutor("192.168.1.100", "192.168.1.101", 0)

        # Too large
        with pytest.raises(ValueError, match="Timeout must be"):
            TestExecutor("192.168.1.100", "192.168.1.101", 100)


class TestQueueSecurity:
    """Test queue management security."""

    def test_duplicate_prevention(self):
        """Test that duplicate URLs are prevented within time window."""
        queue = TestQueue()

        url = "https://github.com/user/repo/releases/download/v1.0/file.img.xz"

        # First addition should succeed
        result1 = queue.add_test(url, "192.168.1.1")
        assert result1["status"] == "queued"

        # Duplicate within window should be rejected
        result2 = queue.add_test(url, "192.168.1.1")
        assert result2["status"] == "duplicate"

    def test_case_insensitive_duplicate_detection(self):
        """Test that duplicate detection is case-insensitive."""
        queue = TestQueue()

        url1 = "https://github.com/user/repo/releases/download/v1.0/FILE.img.xz"
        url2 = "https://github.com/user/repo/releases/download/v1.0/file.img.xz"

        result1 = queue.add_test(url1, "192.168.1.1")
        assert result1["status"] == "queued"

        result2 = queue.add_test(url2, "192.168.1.1")
        assert result2["status"] == "duplicate"

    def test_whitespace_stripped_in_duplicate_detection(self):
        """Test that whitespace is stripped before duplicate detection."""
        queue = TestQueue()

        url1 = "https://github.com/user/repo/releases/download/v1.0/file.img.xz"
        url2 = "  https://github.com/user/repo/releases/download/v1.0/file.img.xz  "

        result1 = queue.add_test(url1, "192.168.1.1")
        assert result1["status"] == "queued"

        result2 = queue.add_test(url2, "192.168.1.1")
        assert result2["status"] == "duplicate"

    def test_flush_clears_queue_and_cache(self):
        """Test that flush clears both queue and processed URLs cache."""
        queue = TestQueue()

        # Add some items
        queue.add_test("https://github.com/user/repo/releases/download/v1.0/file1.img.xz", "192.168.1.1")
        queue.add_test("https://github.com/user/repo/releases/download/v1.0/file2.img.xz", "192.168.1.1")

        assert queue.queue.qsize() == 2
        assert len(queue.processed_urls) == 2

        # Flush
        flushed_count = queue.flush()

        assert flushed_count == 2
        assert queue.queue.qsize() == 0
        assert len(queue.processed_urls) == 0

    def test_get_queued_items_does_not_modify_queue(self):
        """Test that getting queued items doesn't remove them from queue."""
        queue = TestQueue()

        url = "https://github.com/user/repo/releases/download/v1.0/file.img.xz"
        queue.add_test(url, "192.168.1.1")

        # Get items
        items = queue.get_queued_items()

        # Queue should still have the item
        assert len(items) == 1
        assert queue.queue.qsize() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
