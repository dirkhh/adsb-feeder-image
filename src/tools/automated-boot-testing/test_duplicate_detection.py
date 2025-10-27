#!/usr/bin/env python3
"""Integration tests for duplicate detection in boot test service"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Import the adsb-boot-test-service module (has dashes, so use importlib)
service_path = Path(__file__).parent / "adsb-boot-test-service.py"
spec = importlib.util.spec_from_file_location("adsb_test_service", service_path)
if spec is None:
    raise ImportError(f"Could not load module from {service_path}")
service = importlib.util.module_from_spec(spec)
sys.modules["adsb_test_service"] = service
if spec.loader:
    spec.loader.exec_module(service)
else:
    raise ImportError(f"Could not load module from {service_path}")

# Now we can import the class
ADSBTestService = service.ADSBTestService


@pytest.fixture
def test_config():
    """Minimal test configuration"""
    return {
        "rpi_ip": "192.168.1.100",
        "power_toggle_script": "/tmp/fake-script.sh",
        "ssh_key": "/tmp/fake-key",
        "timeout_minutes": 10,
        "api_keys": {"test_key_123": "test_user"},
    }


@pytest.fixture
def app(test_config, tmp_path):
    """Create test Flask app with in-memory database"""
    # Create fake files
    (tmp_path / "fake-script.sh").write_text("#!/bin/bash\necho test")
    (tmp_path / "fake-script.sh").chmod(0o755)
    (tmp_path / "fake-key").write_text("fake-private-key")
    (tmp_path / "fake-key.pub").write_text("fake-public-key")

    # Override paths in config
    test_config["power_toggle_script"] = str(tmp_path / "fake-script.sh")
    test_config["ssh_key"] = str(tmp_path / "fake-key")

    # Mock SSH key validation and Python venv validation to bypass actual checks
    # fmt: off
    with patch.object(service.TestExecutor, "_validate_ssh_key", return_value=str(tmp_path / "fake-key")), patch.object(
        service.TestExecutor, "_validate_python_path", return_value=Path("/usr/bin/python3")
    ):
        # Create service with in-memory DB
        test_service = ADSBTestService(test_config)
        test_service.metrics.db_path = ":memory:"
        test_service.metrics._init_db()

        test_service.app.config["TESTING"] = True
        yield test_service.app
    # fmt: on


def test_duplicate_detection_blocks_second_request(app):
    """Second request with same URL+release_id should be ignored"""
    client = app.test_client()

    payload = {
        "url": "https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.0.0/test.img.xz",
        "github_context": {"event_type": "release", "release_id": 12345, "commit_sha": "abc123"},
    }

    # First request - should be queued
    response1 = client.post(
        "/api/trigger-boot-test", data=json.dumps(payload), content_type="application/json", headers={"X-API-Key": "test_key_123"}
    )

    assert response1.status_code == 200
    data1 = json.loads(response1.data)
    assert data1["status"] == "queued"
    test_id_1 = data1["test_id"]

    # Second request - should be ignored (duplicate)
    response2 = client.post(
        "/api/trigger-boot-test", data=json.dumps(payload), content_type="application/json", headers={"X-API-Key": "test_key_123"}
    )

    assert response2.status_code == 200
    data2 = json.loads(response2.data)
    assert data2["status"] == "ignored"
    assert "previous_test_id" in data2
    assert data2["previous_test_id"] == test_id_1


def test_different_release_ids_both_allowed(app):
    """Same URL with different release_ids should both be queued"""
    client = app.test_client()

    base_payload: dict[str, Any] = {
        "url": "https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.0.0/test.img.xz",
        "github_context": {"event_type": "release", "commit_sha": "abc123"},
    }

    # First request with release_id=100
    github_context: dict[str, Any] = {**base_payload["github_context"], "release_id": 100}
    payload1 = {**base_payload, "github_context": github_context}
    response1 = client.post(
        "/api/trigger-boot-test",
        data=json.dumps(payload1),
        content_type="application/json",
        headers={"X-API-Key": "test_key_123"},
    )

    assert response1.status_code == 200
    data1 = json.loads(response1.data)
    assert data1["status"] == "queued"

    # Second request with different release_id=200
    github_context = {**base_payload["github_context"], "release_id": 200}
    payload2 = {**base_payload, "github_context": github_context}
    response2 = client.post(
        "/api/trigger-boot-test",
        data=json.dumps(payload2),
        content_type="application/json",
        headers={"X-API-Key": "test_key_123"},
    )

    assert response2.status_code == 200
    data2 = json.loads(response2.data)
    assert data2["status"] == "queued"  # Should be queued, not ignored


def test_no_release_id_skips_duplicate_check(app):
    """Requests without release_id should always be queued"""
    client = app.test_client()

    payload = {
        "url": "https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.0.0/test.img.xz",
        "github_context": {
            "event_type": "manual"
            # No release_id
        },
    }

    # First request
    response1 = client.post(
        "/api/trigger-boot-test", data=json.dumps(payload), content_type="application/json", headers={"X-API-Key": "test_key_123"}
    )

    assert response1.status_code == 200
    data1 = json.loads(response1.data)
    assert data1["status"] == "queued"

    # Second request with same URL but no release_id
    # Should also be queued (duplicate check skipped)
    response2 = client.post(
        "/api/trigger-boot-test", data=json.dumps(payload), content_type="application/json", headers={"X-API-Key": "test_key_123"}
    )

    assert response2.status_code == 200
    data2 = json.loads(response2.data)
    assert data2["status"] == "queued"  # Not ignored, because no release_id
