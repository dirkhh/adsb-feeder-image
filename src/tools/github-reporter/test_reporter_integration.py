#!/usr/bin/env python3
"""
Integration tests for GitHub reporter.

Tests the complete workflow:
1. Webhook receives event
2. Boot test service queues test
3. Reporter finds and posts results
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

# Add metrics to path
sys.path.insert(0, str(Path(__file__).parent.parent / "automated-boot-testing"))
from metrics import TestMetrics  # noqa: E402


def test_metrics_github_context():
    """Test metrics can store and retrieve GitHub context"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        metrics = TestMetrics(str(db_path))

        # Create test with GitHub context
        test_id = metrics.start_test(
            image_url="https://example.com/test.img.xz",
            triggered_by="github_webhook",
            github_event_type="release",
            github_release_id=12345,
            github_commit_sha="abc123",
        )

        # Verify stored correctly
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM test_runs WHERE id = ?", (test_id,))
        row = dict(cursor.fetchone())
        conn.close()

        assert row["github_event_type"] == "release"
        assert row["github_release_id"] == 12345
        assert row["github_commit_sha"] == "abc123"
        assert row["status"] == "queued"
        assert row["github_report_status"] == "pending"

        print("✓ Metrics stores GitHub context correctly")


def test_queued_test_workflow():
    """Test queued -> running -> passed workflow"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        metrics = TestMetrics(str(db_path))

        # Create queued test
        test_id = metrics.start_test(
            image_url="https://example.com/test.img.xz",
            triggered_by="github_webhook",
            github_event_type="release",
            github_release_id=999,
        )

        # Should appear in queued tests
        queued = metrics.get_queued_tests()
        assert len(queued) == 1
        assert queued[0]["id"] == test_id
        assert queued[0]["status"] == "queued"

        print("✓ Test appears in queued list")

        # Transition to running
        metrics.update_test_status(test_id, "running")

        # Should not appear in queued anymore
        queued = metrics.get_queued_tests()
        assert len(queued) == 0

        print("✓ Running test removed from queue")

        # Complete test
        metrics.complete_test(test_id, status="passed")

        # Should appear in unreported
        unreported = metrics.get_unreported_tests()
        assert len(unreported) == 1
        assert unreported[0]["id"] == test_id
        assert unreported[0]["status"] == "passed"
        assert unreported[0]["github_report_status"] == "pending"

        print("✓ Completed test appears in unreported")

        # Mark as reported
        metrics.mark_reported(test_id, "posted")

        # Should not appear in unreported anymore
        unreported = metrics.get_unreported_tests()
        assert len(unreported) == 0

        print("✓ Reported test removed from unreported list")


def test_get_tests_by_github_context():
    """Test grouping tests by release/PR"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        metrics = TestMetrics(str(db_path))

        # Create tests for release 123
        test1 = metrics.start_test(
            image_url="https://example.com/image1.img.xz",
            github_event_type="release",
            github_release_id=123,
        )

        test2 = metrics.start_test(
            image_url="https://example.com/image2.img.xz",
            github_event_type="release",
            github_release_id=123,
        )

        # Create test for different release
        test3 = metrics.start_test(
            image_url="https://example.com/image3.img.xz",
            github_event_type="release",
            github_release_id=456,
        )

        # Get tests for release 123
        tests_123 = metrics.get_tests_by_github_context("release", release_id=123)
        assert len(tests_123) == 2
        assert {t["id"] for t in tests_123} == {test1, test2}

        # Get tests for release 456
        tests_456 = metrics.get_tests_by_github_context("release", release_id=456)
        assert len(tests_456) == 1
        assert tests_456[0]["id"] == test3

        print("✓ Tests grouped by release correctly")


def test_failed_report_retry():
    """Test that failed reports are retried"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        metrics = TestMetrics(str(db_path))

        # Create and complete test
        test_id = metrics.start_test(
            image_url="https://example.com/test.img.xz",
            github_event_type="release",
            github_release_id=999,
        )
        metrics.complete_test(test_id, status="passed")

        # Simulate failed report
        metrics.mark_reported(test_id, "failed")

        # Should still appear in unreported for retry
        unreported = metrics.get_unreported_tests()
        assert len(unreported) == 1
        assert unreported[0]["id"] == test_id
        assert unreported[0]["github_report_status"] == "failed"

        print("✓ Failed reports appear in unreported for retry")

        # Successful retry
        metrics.mark_reported(test_id, "posted")

        # Should not appear anymore
        unreported = metrics.get_unreported_tests()
        assert len(unreported) == 0

        print("✓ Successful retry removes from unreported")


if __name__ == "__main__":
    print("Running GitHub reporter integration tests...")
    print()

    try:
        test_metrics_github_context()
        test_queued_test_workflow()
        test_get_tests_by_github_context()
        test_failed_report_retry()

        print()
        print("=" * 50)
        print("All integration tests passed! ✓")
        print("=" * 50)

    except AssertionError as e:
        print()
        print("=" * 50)
        print(f"Test failed: {e}")
        print("=" * 50)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 50)
        print(f"Error: {e}")
        print("=" * 50)
        sys.exit(1)
