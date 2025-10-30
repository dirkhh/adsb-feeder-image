#!/usr/bin/env python3
"""
Database migration script to add GitHub context columns to metrics DB.

Usage:
    python3 migrate_metrics_db.py [--db-path /path/to/metrics.db]
"""

import argparse
import sqlite3
from pathlib import Path


def migrate_database(db_path: str):
    """Add GitHub context columns to test_runs table."""
    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if migration already done
    cursor.execute("PRAGMA table_info(test_runs)")
    columns = [row[1] for row in cursor.fetchall()]

    migrations_needed = []

    # Check for initial GitHub columns
    if "github_event_type" not in columns:
        print("Adding initial GitHub context columns...")
        migrations_needed.extend(
            [
                "ALTER TABLE test_runs ADD COLUMN github_event_type TEXT",
                "ALTER TABLE test_runs ADD COLUMN github_release_id INTEGER",
                "ALTER TABLE test_runs ADD COLUMN github_pr_number INTEGER",
                "ALTER TABLE test_runs ADD COLUMN github_commit_sha TEXT",
                "ALTER TABLE test_runs ADD COLUMN github_workflow_run_id INTEGER",
                "ALTER TABLE test_runs ADD COLUMN github_reported_at TEXT",
                "ALTER TABLE test_runs ADD COLUMN github_report_status TEXT",
            ]
        )

    # Check for retry tracking column (new migration)
    if "github_report_attempts" not in columns:
        print("Adding retry tracking column...")
        migrations_needed.append("ALTER TABLE test_runs ADD COLUMN github_report_attempts INTEGER DEFAULT 0")

    if not migrations_needed:
        print("All migrations already applied - skipping")
        conn.close()
        return

    # Apply migrations
    for migration in migrations_needed:
        cursor.execute(migration)
        print(f"  ✓ {migration}")

    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_github_report_status ON test_runs(github_report_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_github_event_type ON test_runs(github_event_type)")
    print("  ✓ Created indexes")

    conn.commit()
    conn.close()

    print("Migration completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="Migrate metrics database schema")
    parser.add_argument(
        "--db-path",
        default="/var/lib/adsb-boot-test/metrics.db",
        help="Path to metrics database (default: /var/lib/adsb-boot-test/metrics.db)",
    )

    args = parser.parse_args()

    db_file = Path(args.db_path)
    if not db_file.exists():
        print(f"Error: Database file not found: {args.db_path}")
        print("This is normal if no tests have been run yet.")
        print("The database will be created with the new schema on first use.")
        return

    migrate_database(args.db_path)


if __name__ == "__main__":
    main()
