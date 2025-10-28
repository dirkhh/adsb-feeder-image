#!/usr/bin/env python3
"""
Simple metrics tracking for boot tests using SQLite
"""

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class TestMetrics:
    """Simple metrics tracking for boot tests"""

    __test__ = False  # Tell pytest not to collect this as a test class

    def __init__(self, db_path: str = "/var/lib/adsb-boot-test/metrics.db"):
        self.db_path = db_path if db_path == ":memory:" else Path(db_path)
        self._memory_conn: Optional[sqlite3.Connection] = None  # Keep persistent connection for :memory: databases
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        """Get database connection, reusing persistent connection for :memory:"""
        if self.db_path == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(self.db_path)
            return self._memory_conn
        return sqlite3.connect(self.db_path)

    def _close_connection(self, conn):
        """Close connection unless it's the persistent :memory: connection"""
        if conn is not self._memory_conn:
            conn.close()

    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_url TEXT NOT NULL,
                image_version TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_seconds INTEGER,
                status TEXT NOT NULL,
                download_status TEXT,
                boot_status TEXT,
                network_status TEXT,
                browser_test_status TEXT,
                triggered_by TEXT,
                trigger_source TEXT,
                rpi_ip TEXT,
                error_message TEXT,
                error_stage TEXT,
                github_event_type TEXT,
                github_release_id INTEGER,
                github_pr_number INTEGER,
                github_commit_sha TEXT,
                github_workflow_run_id INTEGER,
                github_reported_at TEXT,
                github_report_status TEXT
            )
        """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_started_at ON test_runs(started_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON test_runs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_image_version ON test_runs(image_version)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_github_report_status ON test_runs(github_report_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_github_event_type ON test_runs(github_event_type)")
        conn.commit()
        self._close_connection(conn)

    def start_test(
        self,
        image_url: str,
        triggered_by: str = "manual",
        trigger_source: Optional[str] = None,
        rpi_ip: Optional[str] = None,
        github_event_type: Optional[str] = None,
        github_release_id: Optional[int] = None,
        github_pr_number: Optional[int] = None,
        github_commit_sha: Optional[str] = None,
        github_workflow_run_id: Optional[int] = None,
    ) -> int:
        """
        Record test start in 'queued' state, return test run ID.

        GitHub context parameters are optional and used for posting results back to GitHub.
        """
        # Extract version from URL
        version = self._extract_version(image_url)

        # Determine initial report status
        report_status = "pending" if github_event_type else None

        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO test_runs
            (image_url, image_version, started_at, status, triggered_by, trigger_source, rpi_ip,
             github_event_type, github_release_id, github_pr_number, github_commit_sha,
             github_workflow_run_id, github_report_status)
            VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                image_url,
                version,
                datetime.utcnow().isoformat(),
                triggered_by,
                trigger_source,
                rpi_ip,
                github_event_type,
                github_release_id,
                github_pr_number,
                github_commit_sha,
                github_workflow_run_id,
                report_status,
            ),
        )
        test_id = cursor.lastrowid
        conn.commit()
        self._close_connection(conn)
        if test_id is None:
            raise RuntimeError("Failed to create test record")
        return test_id

    def update_stage(self, test_id: int, stage: str, status: str):
        """Update individual stage status"""
        valid_stages = ["download", "boot", "network", "browser_test"]
        if stage not in valid_stages:
            raise ValueError(f"Invalid stage: {stage}. Must be one of {valid_stages}")

        stage_column = f"{stage}_status"
        conn = self._get_connection()
        conn.execute(f"UPDATE test_runs SET {stage_column} = ? WHERE id = ?", (status, test_id))
        conn.commit()
        self._close_connection(conn)

    def update_test_status(self, test_id: int, status: str):
        """
        Update overall test status (queued -> running -> passed/failed).

        When transitioning to 'running', also updates started_at to current time,
        ensuring duration_seconds reflects actual execution time, not queue wait time.
        """
        valid_statuses = ["queued", "running", "passed", "failed", "error"]
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

        conn = self._get_connection()

        # When test starts running, update started_at to current time
        # This makes duration_seconds reflect actual execution time
        if status == "running":
            conn.execute(
                "UPDATE test_runs SET status = ?, started_at = ? WHERE id = ?",
                (status, datetime.utcnow().isoformat(), test_id)
            )
        else:
            conn.execute("UPDATE test_runs SET status = ? WHERE id = ?", (status, test_id))

        conn.commit()
        self._close_connection(conn)

    def complete_test(
        self,
        test_id: int,
        status: str,
        error_message: Optional[str] = None,
        error_stage: Optional[str] = None,
    ):
        """Record test completion"""
        conn = self._get_connection()
        completed_at = datetime.utcnow().isoformat()

        # Get start time to calculate duration
        cursor = conn.execute("SELECT started_at FROM test_runs WHERE id = ?", (test_id,))
        row = cursor.fetchone()
        if row:
            start_time = datetime.fromisoformat(row[0])
            duration = int((datetime.utcnow() - start_time).total_seconds())
        else:
            duration = None

        conn.execute(
            """
            UPDATE test_runs
            SET completed_at = ?, duration_seconds = ?, status = ?,
                error_message = ?, error_stage = ?
            WHERE id = ?
        """,
            (completed_at, duration, status, error_message, error_stage, test_id),
        )
        conn.commit()
        self._close_connection(conn)

    def _extract_version(self, url: str) -> Optional[str]:
        """
        Extract version from image filename (not path).

        Example URL:
        https://github.com/.../releases/download/v3.0.6-beta.6/adsb-im-...-v3.0.6-beta.9.img.xz
        Should extract: v3.0.6-beta.9 (from filename, not from path)
        """
        # Extract filename from URL (last component after /)
        filename = url.split("/")[-1]

        # Extract version from filename only
        match = re.search(r"v?\d+\.\d+\.\d+(?:-beta\.\d+)?", filename)
        return match.group(0) if match else None

    def get_recent_results(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent test results"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT * FROM test_runs
            ORDER BY started_at DESC
            LIMIT ?
        """,
            (limit,),
        )
        results = [dict(row) for row in cursor.fetchall()]
        self._close_connection(conn)
        return results

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get summary statistics for last N days"""
        conn = self._get_connection()
        since_dt = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        since = (since_dt - timedelta(days=days)).isoformat()

        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                AVG(duration_seconds) as avg_duration
            FROM test_runs
            WHERE started_at >= ?
        """,
            (since,),
        )
        row = cursor.fetchone()
        self._close_connection(conn)

        total = row[0] or 0
        passed = row[1] or 0

        return {
            "total": total,
            "passed": passed,
            "failed": row[2] or 0,
            "errors": row[3] or 0,
            "avg_duration": int(row[4]) if row[4] else 0,
            "pass_rate": round((passed / total * 100), 1) if total > 0 else 0.0,
        }

    def get_version_results(self, version: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get test results for a specific version"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT * FROM test_runs
            WHERE image_version LIKE ?
            ORDER BY started_at DESC
            LIMIT ?
        """,
            (f"%{version}%", limit),
        )
        results = [dict(row) for row in cursor.fetchall()]
        self._close_connection(conn)
        return results

    def get_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent failures"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT * FROM test_runs
            WHERE status IN ('failed', 'error')
            ORDER BY started_at DESC
            LIMIT ?
        """,
            (limit,),
        )
        results = [dict(row) for row in cursor.fetchall()]
        self._close_connection(conn)
        return results

    def get_queued_tests(self) -> List[Dict[str, Any]]:
        """
        Get all tests in queued state (for persistent queue processing).

        Prioritizes non-DietPi images when selecting next test to run,
        while maintaining chronological order as secondary sort.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT * FROM test_runs
            WHERE status = 'queued'
            ORDER BY started_at ASC
        """
        )
        results = [dict(row) for row in cursor.fetchall()]
        self._close_connection(conn)

        # Prioritize non-DietPi images (they test faster)
        # Sort by: 1) has 'dietpi' in name (False first = non-dietpi first)
        #          2) started_at timestamp (oldest first)
        results.sort(key=lambda test: ("dietpi" in test.get("image_url", "").lower(), test.get("started_at", "")))

        return results

    def get_unreported_tests(self) -> List[Dict[str, Any]]:
        """
        Get tests that need GitHub reporting.

        Returns tests that:
        - Have GitHub context (event_type set)
        - Haven't been reported yet (reported_at is NULL)
        - Or failed to report (report_status = 'failed')
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT * FROM test_runs
            WHERE github_event_type IS NOT NULL
            AND (github_reported_at IS NULL
                 OR github_report_status = 'failed')
            ORDER BY started_at ASC
        """
        )
        results = [dict(row) for row in cursor.fetchall()]
        self._close_connection(conn)
        return results

    def get_tests_by_github_context(
        self, event_type: str, release_id: Optional[int] = None, pr_number: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all tests for a specific GitHub release or PR.

        Used by reporter to group tests for batch updates.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row

        if event_type == "release" and release_id:
            cursor = conn.execute(
                """
                SELECT * FROM test_runs
                WHERE github_event_type = 'release'
                AND github_release_id = ?
                ORDER BY started_at ASC
            """,
                (release_id,),
            )
        elif event_type == "pull_request" and pr_number:
            cursor = conn.execute(
                """
                SELECT * FROM test_runs
                WHERE github_event_type = 'pull_request'
                AND github_pr_number = ?
                ORDER BY started_at ASC
            """,
                (pr_number,),
            )
        else:
            self._close_connection(conn)
            return []

        results = [dict(row) for row in cursor.fetchall()]
        self._close_connection(conn)
        return results

    def mark_reported(self, test_id: int, status: str = "posted"):
        """
        Mark test as reported to GitHub.

        Args:
            test_id: Test run ID
            status: 'posted' (success) or 'failed' (retry later)
        """
        if status not in ["posted", "failed"]:
            raise ValueError(f"Invalid report status: {status}")

        conn = self._get_connection()
        conn.execute(
            """
            UPDATE test_runs
            SET github_reported_at = ?, github_report_status = ?
            WHERE id = ?
        """,
            (datetime.utcnow().isoformat(), status, test_id),
        )
        conn.commit()
        self._close_connection(conn)

    def check_duplicate(
        self, image_url: str, github_release_id: Optional[int], window_hours: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Check if this URL + release_id combination was tested recently.

        Args:
            image_url: The image URL to check
            github_release_id: The GitHub release ID (None means skip check)
            window_hours: Time window in hours (default 1)

        Returns:
            Dict with duplicate info if found, None if not a duplicate
            {
                "test_id": int,
                "started_at": str,
                "minutes_ago": int
            }
        """
        # Skip check if release_id not provided
        if github_release_id is None:
            return None

        try:
            # Calculate cutoff time
            cutoff = (datetime.utcnow() - timedelta(hours=window_hours)).isoformat()

            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT id, started_at, image_url
                FROM test_runs
                WHERE image_url = ?
                  AND github_release_id = ?
                  AND started_at >= ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (image_url, github_release_id, cutoff),
            )

            row = cursor.fetchone()
            self._close_connection(conn)

            if row:
                started_at = datetime.fromisoformat(row["started_at"])
                minutes_ago = int((datetime.utcnow() - started_at).total_seconds() / 60)
                return {"test_id": row["id"], "started_at": row["started_at"], "minutes_ago": minutes_ago}

            return None

        except Exception as e:
            # Fail-safe: Allow test to proceed but log warning
            import logging

            logging.warning(f"Duplicate check failed for URL={image_url}, release_id={github_release_id}: {e}")
            return None
