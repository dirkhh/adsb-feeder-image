#!/usr/bin/env python3
"""
CLI tool for querying boot test metrics
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from metrics import TestMetrics  # noqa: E402


def format_status_emoji(status: str) -> str:
    """Get emoji for status"""
    return {
        "passed": "✅",
        "failed": "❌",
        "error": "⚠️",
        "running": "🔄",
    }.get(status, "❓")


def format_stage_status(status: str) -> str:
    """Format stage status with color/emoji"""
    if status == "passed":
        return "✓"
    elif status == "failed":
        return "✗"
    elif status == "running":
        return "⋯"
    else:
        return "-"


def show_stats(metrics: TestMetrics, days: int):
    """Show statistics summary"""
    stats = metrics.get_stats(days=days)
    print(f"\n📊 Test Statistics (Last {days} days)")
    print("━" * 50)
    print(f"Total Tests:    {stats['total']}")
    print(f"  ✅ Passed:    {stats['passed']}")
    print(f"  ❌ Failed:    {stats['failed']}")
    print(f"  ⚠️  Errors:    {stats['errors']}")
    print(f"Pass Rate:      {stats['pass_rate']}%")
    print(f"Avg Duration:   {stats['avg_duration']}s")
    print()


def show_recent(metrics: TestMetrics, limit: int, failures_only: bool = False, version: Optional[str] = None):
    """Show recent test results"""
    if version:
        results = metrics.get_version_results(version, limit=limit)
        print(f"\n📋 Test Results for {version}")
    elif failures_only:
        results = metrics.get_failures(limit=limit)
        print(f"\n❌ Recent Failures")
    else:
        results = metrics.get_recent_results(limit=limit)
        print(f"\n📋 Recent Test Results")

    print("━" * 50)

    if not results:
        print("\nNo results found.")
        return

    for r in results:
        # Format status emoji
        status_emoji = format_status_emoji(r["status"])

        # Format timestamp
        started = datetime.fromisoformat(r["started_at"])
        time_str = started.strftime("%Y-%m-%d %H:%M")

        # Format duration
        if r["duration_seconds"]:
            minutes = r["duration_seconds"] // 60
            seconds = r["duration_seconds"] % 60
            duration = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        else:
            duration = "ongoing"

        print(f"\n{status_emoji} {r['image_version'] or 'unknown'}")
        print(f"   Time: {time_str}  Duration: {duration}")
        print(
            f"   Stages: Download:{format_stage_status(r['download_status'])} "
            f"Boot:{format_stage_status(r['boot_status'])} "
            f"Network:{format_stage_status(r['network_status'])} "
            f"Browser:{format_stage_status(r['browser_test_status'])}"
        )

        if r["triggered_by"]:
            trigger_info = f"{r['triggered_by']}"
            if r["trigger_source"]:
                trigger_info += f" ({r['trigger_source']})"
            print(f"   Triggered: {trigger_info}")

        if r["error_message"]:
            error_msg = r["error_message"]
            if len(error_msg) > 80:
                error_msg = error_msg[:77] + "..."
            print(f"   ⚠️  Error: {error_msg}")
            if r["error_stage"]:
                print(f"   Failed at: {r['error_stage']}")


def show_details(metrics: TestMetrics, test_id: int):
    """Show detailed information about a specific test"""
    results = metrics.get_recent_results(limit=1000)  # Get many to find the ID
    result = next((r for r in results if r["id"] == test_id), None)

    if not result:
        print(f"\n❌ Test ID {test_id} not found")
        return

    status_emoji = format_status_emoji(result["status"])
    started = datetime.fromisoformat(result["started_at"])

    print(f"\n📝 Test Details - ID {test_id}")
    print("━" * 50)
    print(f"Status:         {status_emoji} {result['status']}")
    print(f"Version:        {result['image_version'] or 'unknown'}")
    print(f"Started:        {started.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    if result["completed_at"]:
        completed = datetime.fromisoformat(result["completed_at"])
        print(f"Completed:      {completed.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Duration:       {result['duration_seconds']}s")

    print(f"\nTriggered by:   {result['triggered_by']}")
    if result["trigger_source"]:
        print(f"Source:         {result['trigger_source']}")
    print(f"RPI IP:         {result['rpi_ip']}")

    print(f"\nStage Results:")
    print(f"  Download:     {result['download_status'] or 'not started'}")
    print(f"  Boot:         {result['boot_status'] or 'not started'}")
    print(f"  Network:      {result['network_status'] or 'not started'}")
    print(f"  Browser Test: {result['browser_test_status'] or 'not started'}")

    if result["error_message"]:
        print(f"\nError Details:")
        print(f"  Stage:   {result['error_stage'] or 'unknown'}")
        print(f"  Message: {result['error_message']}")

    print(f"\nImage URL:")
    print(f"  {result['image_url']}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Query boot test metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show last 10 test results
  %(prog)s --recent 10

  # Show stats for last 7 days
  %(prog)s --stats 7

  # Show only failures
  %(prog)s --failures --recent 20

  # Filter by version
  %(prog)s --version "v3.0.6-beta.8"

  # Show details for specific test
  %(prog)s --details 42
        """,
    )

    parser.add_argument("--recent", type=int, metavar="N", help="Show N most recent tests (default: 10)")
    parser.add_argument("--stats", type=int, metavar="DAYS", help="Show statistics for last N days")
    parser.add_argument("--failures", action="store_true", help="Show only failed tests")
    parser.add_argument("--version", metavar="VERSION", help="Filter by version")
    parser.add_argument("--details", type=int, metavar="ID", help="Show details for specific test ID")
    parser.add_argument(
        "--db",
        default="/var/lib/adsb-boot-test/metrics.db",
        help="Path to metrics database (default: /var/lib/adsb-boot-test/metrics.db)",
    )

    args = parser.parse_args()

    # Initialize metrics
    try:
        metrics = TestMetrics(db_path=args.db)
    except Exception as e:
        print(f"❌ Error accessing database: {e}", file=sys.stderr)
        return 1

    # Show details if requested
    if args.details is not None:
        show_details(metrics, args.details)
        return 0

    # Show stats if requested
    if args.stats:
        show_stats(metrics, args.stats)

    # Show recent results (default or explicit)
    limit = args.recent if args.recent is not None else (10 if not args.stats else 0)
    if limit > 0:
        show_recent(metrics, limit=limit, failures_only=args.failures, version=args.version)

    # If no options given, show default view
    if not any([args.stats, args.recent, args.failures, args.version, args.details]):
        show_stats(metrics, days=7)
        show_recent(metrics, limit=10)

    return 0


if __name__ == "__main__":
    sys.exit(main())
