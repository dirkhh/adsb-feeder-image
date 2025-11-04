"""Tests for disk space diagnostic utilities."""

import errno
import logging
import subprocess
from unittest.mock import patch

from boot_test_lib.disk_space_utils import (
    handle_space_error,
    is_likely_space_error,
    show_large_files_diagnostic,
)


class TestShowLargeFilesDiagnostic:
    """Tests for show_large_files_diagnostic function."""

    def test_shows_largest_files_with_sizes_and_times(self, tmp_path, caplog):
        """Test that it shows the N largest files with size and time info."""
        caplog.set_level(logging.ERROR)

        # Create test files with different sizes
        (tmp_path / "large.img").write_bytes(b"x" * (1024 * 1024 * 100))  # 100 MB
        (tmp_path / "medium.img").write_bytes(b"x" * (1024 * 1024 * 50))  # 50 MB
        (tmp_path / "small.img").write_bytes(b"x" * (1024 * 1024 * 10))  # 10 MB

        # Mock humanize.naturaltime to return predictable values
        with patch("boot_test_lib.disk_space_utils.humanize.naturaltime") as mock_time:
            mock_time.return_value = "2 minutes ago"

            show_large_files_diagnostic(tmp_path, num_files=3)

        # Verify logging output
        assert "Largest 3 files" in caplog.text
        assert "large.img" in caplog.text
        assert "medium.img" in caplog.text
        assert "small.img" in caplog.text
        assert "2 minutes ago" in caplog.text

    def test_handles_empty_directory(self, tmp_path, caplog):
        """Test handling of empty directory."""
        caplog.set_level(logging.ERROR)

        show_large_files_diagnostic(tmp_path, num_files=5)

        assert "No files found" in caplog.text

    def test_limits_to_num_files(self, tmp_path, caplog):
        """Test that only N files are shown."""
        caplog.set_level(logging.ERROR)

        # Create 10 files
        for i in range(10):
            (tmp_path / f"file{i}.img").write_bytes(b"x" * (1024 * (i + 1)))

        with patch("boot_test_lib.disk_space_utils.humanize.naturaltime") as mock_time:
            mock_time.return_value = "now"

            show_large_files_diagnostic(tmp_path, num_files=3)

        # Count file entries in log (should be exactly 3)
        log_text = caplog.text
        file_count = sum(1 for line in log_text.split("\n") if "file" in line and "KB" in line)
        assert file_count == 3


class TestIsLikelySpaceError:
    """Tests for is_likely_space_error function."""

    def test_detects_enospc_error(self):
        """Test detection of ENOSPC errno."""
        error = OSError(errno.ENOSPC, "No space left on device")
        assert is_likely_space_error(error) is True

    def test_detects_space_related_message(self):
        """Test detection of space-related error messages."""
        error = OSError("No space left on device")
        assert is_likely_space_error(error) is True

    def test_detects_xz_compression_error(self):
        """Test detection of xz compression space errors."""
        error = subprocess.CalledProcessError(1, ["xz"], stderr="Cannot allocate memory")
        assert is_likely_space_error(error) is True

    def test_ignores_other_errors(self):
        """Test that non-space errors return False."""
        error = ValueError("Something else went wrong")
        assert is_likely_space_error(error) is False

    def test_ignores_other_oserrors(self):
        """Test that non-space OSErrors return False."""
        error = OSError(errno.EACCES, "Permission denied")
        assert is_likely_space_error(error) is False


class TestHandleSpaceError:
    """Tests for handle_space_error function."""

    def test_logs_error_and_calls_diagnostic(self, tmp_path, caplog):
        """Test that it logs error and calls show_large_files_diagnostic."""
        caplog.set_level(logging.ERROR)

        # Create a test file
        (tmp_path / "test.img").write_bytes(b"x" * 1024)

        with patch("boot_test_lib.disk_space_utils.humanize.naturaltime") as mock_time:
            mock_time.return_value = "now"

            handle_space_error(tmp_path, "decompression")

        # Verify error message
        assert "decompression failed" in caplog.text.lower()
        assert "insufficient disk space" in caplog.text.lower()
        assert "Largest" in caplog.text
        assert "test.img" in caplog.text
