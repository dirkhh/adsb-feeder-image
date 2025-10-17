#!/usr/bin/env python3
"""
Test script for the webhook endpoint
"""

import hashlib
import hmac
import json
import threading
import time

import requests
import uvicorn
from webhook_service import app


def create_test_payload():
    """Create a test GitHub release webhook payload."""
    return {
        "action": "published",
        "release": {
            "id": 12345,
            "tag_name": "v1.0.0",
            "name": "Test Release",
            "assets": [
                {
                    "id": 1,
                    "name": "myapp-raspberrypi64-pi-2-3-4-v1.0.0.tar.gz",
                    "browser_download_url": "https://github.com/user/repo/releases/download/v1.0.0/myapp-raspberrypi64-pi-2-3-4-v1.0.0.tar.gz",
                },
                {
                    "id": 2,
                    "name": "myapp-raspberrypi64-pi-5-v1.0.0.tar.gz",
                    "browser_download_url": "https://github.com/user/repo/releases/download/v1.0.0/myapp-raspberrypi64-pi-5-v1.0.0.tar.gz",
                },
                {
                    "id": 3,
                    "name": "myapp-arm64-pi-2-3-4-v1.0.0.tar.gz",
                    "browser_download_url": "https://github.com/user/repo/releases/download/v1.0.0/myapp-arm64-pi-2-3-4-v1.0.0.tar.gz",
                },
            ],
        },
    }


def create_signature(payload_body, secret):
    """Create GitHub webhook signature."""
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()


def start_server():
    """Start the webhook server in a separate thread."""
    uvicorn.run(app, host="127.0.0.1", port=9111, log_level="error")


def test_webhook():
    """Test the webhook endpoint."""
    print("Testing GitHub Webhook Service...")
    print("=" * 50)

    # Start server in background
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for server to start
    time.sleep(2)

    # Test data
    test_secret = "test_secret_123"
    payload = create_test_payload()
    payload_body = json.dumps(payload).encode("utf-8")
    signature = create_signature(payload_body, test_secret)

    # Test webhook endpoint
    url = "http://127.0.0.1:9111/cicd-webhook/binary-test"
    headers = {"Content-Type": "application/json", "X-GitHub-Event": "release", "X-Hub-Signature-256": signature}

    print("Sending test webhook payload...")
    print(f"Expected qualifying binary: {payload['release']['assets'][0]['browser_download_url']}")
    print()

    try:
        response = requests.post(url, data=payload_body, headers=headers, timeout=10)
        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {response.json()}")

        if response.status_code == 200:
            print("✅ Webhook test passed!")
        else:
            print("❌ Webhook test failed!")

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

    # Test health endpoint
    print("\nTesting health endpoint...")
    try:
        response = requests.get("http://127.0.0.1:9111/health", timeout=5)
        print(f"Health Status: {response.status_code}")
        print(f"Health Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Health check failed: {e}")

    # Test root endpoint
    print("\nTesting root endpoint...")
    try:
        response = requests.get("http://127.0.0.1:9111/", timeout=5)
        print(f"Root Status: {response.status_code}")
        print(f"Root Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Root endpoint failed: {e}")


if __name__ == "__main__":
    test_webhook()
