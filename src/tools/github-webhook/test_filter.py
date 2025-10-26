#!/usr/bin/env python3
"""
Test script for binary filtering logic
"""

import os
import sys

# Add the current directory to Python path to import webhook_service
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webhook_service import matches_binary_filter  # noqa: E402


def test_binary_filter():
    """Test the binary filtering logic with various examples."""

    test_cases = [
        # Should match (contain 'raspberrypi64' and '4' in pi-* pattern)
        ("myapp-raspberrypi64-pi-2-3-4-v1.0.0.tar.gz", True, "Contains raspberrypi64 and pi-2-3-4"),
        ("myapp-raspberrypi64-pi-2-3-4-5-v1.0.0.tar.gz", True, "Contains raspberrypi64 and pi-2-3-4-5"),
        ("raspberrypi64-pi-1-2-3-4-5-6-v2.1.0.zip", True, "Contains raspberrypi64 and pi-1-2-3-4-5-6"),
        # Should not match (missing 'raspberrypi64')
        ("myapp-arm64-pi-2-3-4-v1.0.0.tar.gz", False, "Missing raspberrypi64"),
        ("myapp-pi-2-3-4-v1.0.0.tar.gz", False, "Missing raspberrypi64"),
        # Should not match (missing '4' in pi-* pattern)
        ("myapp-raspberrypi64-pi-5-v1.0.0.tar.gz", False, "Contains raspberrypi64 but pi-5 (no '4')"),
        ("myapp-raspberrypi64-pi-2-3-v1.0.0.tar.gz", False, "Contains raspberrypi64 but pi-2-3 (no '4')"),
        ("myapp-raspberrypi64-pi-1-2-3-5-v1.0.0.tar.gz", False, "Contains raspberrypi64 but pi-1-2-3-5 (no '4')"),
        # Edge cases
        ("raspberrypi64-pi-4-v1.0.0.tar.gz", True, "Contains raspberrypi64 and pi-4"),
        ("raspberrypi64-pi-4-5-v1.0.0.tar.gz", True, "Contains raspberrypi64 and pi-4-5"),
        ("raspberrypi64-pi-40-v1.0.0.tar.gz", True, "Contains raspberrypi64 and pi-40 (contains '4')"),
        ("raspberrypi64-pi-14-v1.0.0.tar.gz", True, "Contains raspberrypi64 and pi-14 (contains '4')"),
        # Should not match (no pi-* pattern)
        ("myapp-raspberrypi64-v1.0.0.tar.gz", False, "Contains raspberrypi64 but no pi-* pattern"),
        ("raspberrypi64-something-else-v1.0.0.tar.gz", False, "Contains raspberrypi64 but no pi-* pattern"),
    ]

    print("Testing binary filtering logic...")
    print("=" * 60)

    passed = 0
    failed = 0

    for binary_name, expected, description in test_cases:
        result = matches_binary_filter(binary_name, "v1.0.0")  # Use dummy release name for basic filter testing
        status = "✅ PASS" if result == expected else "❌ FAIL"

        print(f"{status} | {binary_name}")
        print(f"      | Expected: {expected}, Got: {result}")
        print(f"      | {description}")
        print()

        if result == expected:
            passed += 1
        else:
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        print("❌ Some tests failed!")
        # Use assertion for pytest compatibility
        assert False, f"{failed} test cases failed"
    else:
        print("✅ All tests passed!")


if __name__ == "__main__":
    try:
        test_binary_filter()
        sys.exit(0)
    except AssertionError:
        sys.exit(1)
