"""Disk space diagnostic utilities for boot testing."""

import errno
import logging
import subprocess
from pathlib import Path

import humanize

logger = logging.getLogger(__name__)


def show_large_files_diagnostic(directory: Path, num_files: int = 5) -> None:
    """
    Show the N largest files in a directory with size and modification time.

    Args:
        directory: Directory to scan
        num_files: Number of largest files to show (default: 5)
    """
    try:
        # Get all files with their sizes
        files = []
        for file_path in directory.iterdir():
            if file_path.is_file():
                try:
                    stat = file_path.stat()
                    files.append((file_path, stat.st_size, stat.st_mtime))
                except (OSError, PermissionError):
                    continue

        if not files:
            logger.error(f"No files found in {directory}")
            return

        # Sort by size (descending)
        files.sort(key=lambda x: x[1], reverse=True)

        # Show top N files
        logger.error(f"Largest {min(num_files, len(files))} files in {directory}:")

        for file_path, size, mtime in files[:num_files]:
            # Format size in human-readable format
            if size >= 1024 * 1024 * 1024:
                size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
            elif size >= 1024 * 1024:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            elif size >= 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} bytes"

            # Format time relative to now
            import datetime

            time_str = humanize.naturaltime(datetime.datetime.fromtimestamp(mtime))

            logger.error(f"  {size_str:>10}  {file_path.name}  ({time_str})")

    except Exception as e:
        logger.error(f"Failed to list files: {e}")


def is_likely_space_error(exception: Exception) -> bool:
    """
    Check if an exception is likely caused by disk space issues.

    Args:
        exception: Exception to check

    Returns:
        True if likely a space error, False otherwise
    """
    # Check for ENOSPC errno
    if isinstance(exception, OSError):
        if exception.errno == errno.ENOSPC:
            return True
        # Check error message for space-related keywords
        error_msg = str(exception).lower()
        if any(keyword in error_msg for keyword in ["no space left", "disk full", "cannot allocate"]):
            return True

    # Check for subprocess errors with space-related messages
    if isinstance(exception, subprocess.CalledProcessError):
        if exception.stderr:
            stderr = exception.stderr.lower() if isinstance(exception.stderr, str) else ""
            if any(keyword in stderr for keyword in ["no space left", "cannot allocate", "disk full"]):
                return True

    return False


def handle_space_error(directory: Path, operation: str) -> None:
    """
    Handle a disk space error by logging diagnostics.

    Args:
        directory: Directory to diagnose
        operation: Name of operation that failed (e.g., "download", "decompression")
    """
    logger.error(f"{operation.capitalize()} failed - possibly due to insufficient disk space")
    show_large_files_diagnostic(directory)
