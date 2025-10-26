#!/usr/bin/env python3
"""
Simple test to verify metrics module works correctly
"""

import tempfile
from pathlib import Path
from metrics import TestMetrics


def test_metrics():
    """Test basic metrics functionality"""
    # Use temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test-metrics.db"
        metrics = TestMetrics(db_path=str(db_path))

        print("✓ Metrics initialized")

        # Test 1: Start a test
        test_id = metrics.start_test(
            image_url="https://example.com/image-v1.0.0-beta.1.img.xz",
            triggered_by="manual",
            trigger_source="test-script",
            rpi_ip="192.168.1.100"
        )
        print(f"✓ Started test ID: {test_id}")

        # Test 2: Update stages
        metrics.update_stage(test_id, "download", "passed")
        print("✓ Updated download stage")

        metrics.update_stage(test_id, "boot", "passed")
        print("✓ Updated boot stage")

        metrics.update_stage(test_id, "network", "passed")
        print("✓ Updated network stage")

        metrics.update_stage(test_id, "browser_test", "passed")
        print("✓ Updated browser test stage")

        # Test 3: Complete test
        metrics.complete_test(test_id, "passed")
        print("✓ Completed test")

        # Test 4: Query results
        results = metrics.get_recent_results(limit=10)
        assert len(results) == 1
        assert results[0]["status"] == "passed"
        assert results[0]["image_version"] == "v1.0.0-beta.1"
        print(f"✓ Query returned {len(results)} result(s)")

        # Test 5: Get stats
        stats = metrics.get_stats(days=7)
        assert stats["total"] == 1
        assert stats["passed"] == 1
        assert stats["pass_rate"] == 100.0
        print(f"✓ Stats: {stats['total']} total, {stats['pass_rate']}% pass rate")

        # Test 6: Create a failed test
        test_id2 = metrics.start_test(
            image_url="https://example.com/image-v1.0.0-beta.2.img.xz",
            triggered_by="webhook",
            trigger_source="github",
            rpi_ip="192.168.1.100"
        )
        metrics.update_stage(test_id2, "download", "passed")
        metrics.update_stage(test_id2, "boot", "failed")
        metrics.complete_test(
            test_id2,
            "failed",
            error_message="Boot timeout",
            error_stage="boot"
        )
        print(f"✓ Created failed test ID: {test_id2}")

        # Test 7: Query failures
        failures = metrics.get_failures(limit=10)
        assert len(failures) == 1
        assert failures[0]["status"] == "failed"
        assert failures[0]["error_message"] == "Boot timeout"
        print(f"✓ Query returned {len(failures)} failure(s)")

        # Test 8: Updated stats
        stats = metrics.get_stats(days=7)
        assert stats["total"] == 2
        assert stats["passed"] == 1
        assert stats["failed"] == 1
        assert stats["pass_rate"] == 50.0
        print(f"✓ Updated stats: {stats['total']} total, {stats['pass_rate']}% pass rate")

        print("\n🎉 All tests passed!")
        return True


def test_check_duplicate_skips_when_release_id_none():
    """Should return None immediately when release_id is None"""
    metrics = TestMetrics(db_path=":memory:")

    # Create a test to potentially match
    metrics.start_test(
        image_url="https://example.com/test.img",
        github_release_id=123
    )

    # Check with release_id=None should skip check entirely
    result = metrics.check_duplicate(
        image_url="https://example.com/test.img",
        github_release_id=None
    )

    assert result is None


if __name__ == "__main__":
    try:
        test_metrics()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
