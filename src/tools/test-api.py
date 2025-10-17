#!/usr/bin/env python3
"""
Simple test script for the ADS-B Test Service API.
"""

import requests
import json
import time
import sys

def test_api(base_url="http://127.0.0.1:9456"):
    """Test the API endpoints."""

    print(f"🧪 Testing ADS-B Test Service API at {base_url}")

    # Test health endpoint
    print("\n1. Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False

    # Test status endpoint
    print("\n2. Testing status endpoint...")
    try:
        response = requests.get(f"{base_url}/api/status", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Status check failed: {e}")
        return False

    # Test invalid URL
    print("\n3. Testing invalid URL...")
    try:
        response = requests.post(
            f"{base_url}/api/trigger-boot-test",
            json={"url": "https://example.com/invalid.img.xz"},
            timeout=5
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Invalid URL test failed: {e}")
        return False

    # Test valid URL
    print("\n4. Testing valid URL...")
    try:
        test_url = "https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6-beta.6/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz"
        response = requests.post(
            f"{base_url}/api/trigger-boot-test",
            json={"url": test_url},
            timeout=5
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Valid URL test failed: {e}")
        return False

    # Test duplicate URL (should be ignored)
    print("\n5. Testing duplicate URL (should be ignored)...")
    try:
        test_url = "https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6-beta.6/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz"
        response = requests.post(
            f"{base_url}/api/trigger-boot-test",
            json={"url": test_url},
            timeout=5
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Duplicate URL test failed: {e}")
        return False

    print("\n✅ All API tests completed!")
    return True

if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9456"
    test_api(base_url)
