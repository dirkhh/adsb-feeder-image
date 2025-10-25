#!/usr/bin/env python3
"""
Simple metrics tracking for boot tests using SQLite
"""

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List


class TestMetrics:
    """Simple metrics tracking for boot tests"""

    def __init__(self, db_path: str = "/var/lib/adsb-boot-test/metrics.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
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
                error_stage TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_started_at ON test_runs(started_at)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON test_runs(status)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_image_version ON test_runs(image_version)"
        )
        conn.commit()
        conn.close()

    def start_test(
        self,
        image_url: str,
        triggered_by: str = "manual",
        trigger_source: str = None,
        rpi_ip: str = None,
    ) -> int:
        """Record test start, return test run ID"""
        # Extract version from URL
        version = self._extract_version(image_url)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            INSERT INTO test_runs
            (image_url, image_version, started_at, status, triggered_by, trigger_source, rpi_ip)
            VALUES (?, ?, ?, 'running', ?, ?, ?)
        """,
            (
                image_url,
                version,
                datetime.utcnow().isoformat(),
                triggered_by,
                trigger_source,
                rpi_ip,
            ),
        )
        test_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return test_id

    def update_stage(self, test_id: int, stage: str, status: str):
        """Update individual stage status"""
        valid_stages = ["download", "boot", "network", "browser_test"]
        if stage not in valid_stages:
            raise ValueError(f"Invalid stage: {stage}. Must be one of {valid_stages}")

        stage_column = f"{stage}_status"
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            f"UPDATE test_runs SET {stage_column} = ? WHERE id = ?", (status, test_id)
        )
        conn.commit()
        conn.close()

    def complete_test(
        self,
        test_id: int,
        status: str,
        error_message: str = None,
        error_stage: str = None,
    ):
        """Record test completion"""
        conn = sqlite3.connect(self.db_path)
        completed_at = datetime.utcnow().isoformat()

        # Get start time to calculate duration
        cursor = conn.execute(
            "SELECT started_at FROM test_runs WHERE id = ?", (test_id,)
        )
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
        conn.close()

    def _extract_version(self, url: str) -> Optional[str]:
        """
        Extract version from image filename (not path).

        Example URL:
        https://github.com/.../releases/download/v3.0.6-beta.6/adsb-im-...-v3.0.6-beta.9.img.xz
        Should extract: v3.0.6-beta.9 (from filename, not from path)
        """
        # Extract filename from URL (last component after /)
        filename = url.split('/')[-1]

        # Extract version from filename only
        match = re.search(r"v?\d+\.\d+\.\d+(?:-beta\.\d+)?", filename)
        return match.group(0) if match else None

    def get_recent_results(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent test results"""
        conn = sqlite3.connect(self.db_path)
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
        conn.close()
        return results

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get summary statistics for last N days"""
        conn = sqlite3.connect(self.db_path)
        since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        since = (since - timedelta(days=days)).isoformat()

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
        conn.close()

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
        conn = sqlite3.connect(self.db_path)
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
        conn.close()
        return results

    def get_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent failures"""
        conn = sqlite3.connect(self.db_path)
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
        conn.close()
        return results
