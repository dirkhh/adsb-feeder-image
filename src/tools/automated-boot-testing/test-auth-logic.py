#!/usr/bin/env python3
"""
Simple test of authentication logic without Flask dependencies.

Tests the core security properties of the authentication implementation.
"""

import hmac
import secrets
import sys


def test_timing_safe_comparison():
    """Test that timing-safe comparison works correctly."""
    print("Testing timing-safe comparison...")

    key1 = "abc123def456"
    key2 = "abc123def456"
    key3 = "abc123def457"  # One char different

    # Test exact match
    assert hmac.compare_digest(key1, key2), "Same keys should match"

    # Test different keys
    assert not hmac.compare_digest(key1, key3), "Different keys should not match"

    # Test empty strings
    assert hmac.compare_digest("", ""), "Empty strings should match"
    assert not hmac.compare_digest("key", ""), "Key and empty should not match"

    print("  ✓ Timing-safe comparison works correctly")


def test_key_generation():
    """Test that generated keys have sufficient entropy."""
    print("Testing API key generation...")

    # Generate multiple keys
    keys = set()
    for _ in range(100):
        key = secrets.token_urlsafe(32)
        keys.add(key)

        # Check length (32 bytes base64-encoded should be ~43 chars)
        assert len(key) >= 40, f"Key too short: {len(key)}"

    # All keys should be unique
    assert len(keys) == 100, "Generated keys should be unique"

    print("  ✓ Generated 100 unique keys with sufficient entropy")
    print(f"  ✓ Average key length: {sum(len(k) for k in keys) / len(keys):.1f} characters")


def test_validation_logic():
    """Test the validation logic."""
    print("Testing validation logic...")

    # Simulate the APIKeyAuth.validate_key logic
    api_keys = {
        "valid_key_1": "user1",
        "valid_key_2": "user2",
    }

    def validate_key(provided_key):
        """Simulated validate_key method."""
        if not provided_key:
            return None

        for valid_key, user_id in api_keys.items():
            if hmac.compare_digest(provided_key, valid_key):
                return user_id
        return None

    # Test valid keys
    assert validate_key("valid_key_1") == "user1", "Valid key 1 should authenticate"
    assert validate_key("valid_key_2") == "user2", "Valid key 2 should authenticate"

    # Test invalid keys
    assert validate_key("invalid_key") is None, "Invalid key should fail"
    assert validate_key("") is None, "Empty key should fail"
    assert validate_key(None) is None, "None key should fail"
    assert validate_key("valid_key_3") is None, "Unknown key should fail"

    print("  ✓ Validation logic works correctly")


def test_security_properties():
    """Test security properties."""
    print("Testing security properties...")

    # Test key should not be easily guessable
    key1 = secrets.token_urlsafe(32)
    key2 = secrets.token_urlsafe(32)

    assert key1 != key2, "Sequential keys should be different"

    # Test that similar keys don't match
    test_key = "AbCdEf123456"
    similar_key = "AbCdEf123457"

    assert not hmac.compare_digest(test_key, similar_key), "Similar keys should not match"

    print("  ✓ Security properties verified")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Authentication Logic Tests")
    print("=" * 70)
    print()

    tests = [
        test_timing_safe_comparison,
        test_key_generation,
        test_validation_logic,
        test_security_properties,
    ]

    failed = False
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"  ✗ Test failed: {e}")
            failed = True
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            failed = True

    print()
    print("=" * 70)
    if not failed:
        print("✅ All authentication logic tests passed!")
        print("=" * 70)
        return 0
    else:
        print("❌ Some tests failed")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
