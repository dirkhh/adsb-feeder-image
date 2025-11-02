"""Consistent logging setup for boot test scripts."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """
    Setup consistent logging configuration for boot test scripts.

    Configures:
    - Line-buffered stdout/stderr for systemd/journalctl compatibility
    - Consistent log format with timestamps
    - Specified log level

    Args:
        level: Logging level (default: INFO)
    """
    # Configure line-buffered output for real-time logging when running as systemd service
    # This ensures all output appears immediately in journalctl without manual flush() calls
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr,attr-defined]
    sys.stderr.reconfigure(line_buffering=True)  # type: ignore[union-attr,attr-defined]

    # Setup logging with consistent format
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
