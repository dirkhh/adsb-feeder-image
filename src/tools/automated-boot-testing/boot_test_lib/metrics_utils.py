"""Consistent metrics tracking utilities."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def update_stage(metrics_id: Optional[int], metrics_db: Path, stage: str, status: str) -> None:
    """
    Update metrics stage with consistent error handling.

    Args:
        metrics_id: Test ID (None = metrics disabled)
        metrics_db: Path to metrics database
        stage: Stage name (download, boot, network, browser_test)
        status: Status (running, passed, failed)
    """
    if metrics_id is None:
        return

    try:
        # Import here to avoid circular dependency
        from metrics import TestMetrics  # type: ignore

        metrics = TestMetrics(db_path=str(metrics_db))
        metrics.update_stage(metrics_id, stage, status)
    except Exception as e:
        logger.warning(f"Failed to update metrics: {e}")


def complete_test(metrics_id: Optional[int], metrics_db: Path, status: str, error_message: Optional[str] = None) -> None:
    """
    Mark test as complete in metrics database.

    Args:
        metrics_id: Test ID (None = metrics disabled)
        metrics_db: Path to metrics database
        status: Final status (passed, failed)
        error_message: Optional error message
    """
    if metrics_id is None:
        return

    try:
        # Import here to avoid circular dependency
        from metrics import TestMetrics  # type: ignore

        metrics = TestMetrics(db_path=str(metrics_db))
        metrics.complete_test(metrics_id, status=status, error_message=error_message)
    except Exception as e:
        logger.warning(f"Failed to complete test in metrics: {e}")
