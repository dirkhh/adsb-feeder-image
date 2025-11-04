"""Tests for RPi iSCSI backend temp file cleanup."""

from unittest.mock import MagicMock, patch

import pytest
from hardware_backends.base import TestConfig
from hardware_backends.rpi_iscsi import RPiISCSIBackend


class TestRPiTempFileCleanup:
    """Tests for RPi backend temp file cleanup."""

    @pytest.fixture
    def backend(self, tmp_path):
        """Create RPi backend with temp directory."""
        config = TestConfig(
            image_url="http://example.com/test.img.xz",
            metrics_id=1,
            metrics_db=tmp_path / "metrics.db",
            timeout_minutes=10,
        )

        backend = RPiISCSIBackend(
            config=config,
            rpi_ip="192.168.1.100",
            power_toggle_script=tmp_path / "power.sh",
        )

        return backend

    def test_cleanup_removes_decompressed_file(self, backend, tmp_path):
        """Test that cleanup removes decompressed temp file."""
        # Create fake temp files
        compressed = tmp_path / "test.img.xz"
        decompressed = tmp_path / "test.img"
        compressed.write_bytes(b"compressed")
        decompressed.write_bytes(b"decompressed")

        # Set temp file paths
        backend.local_compressed = compressed
        backend.local_decompressed = decompressed

        # Mock power toggle
        with patch.object(backend, "_power_toggle"):
            backend.cleanup()

        # Verify decompressed file removed
        assert not decompressed.exists()

    def test_cleanup_removes_compressed_file(self, backend, tmp_path):
        """Test that cleanup removes compressed temp file."""
        # Create fake temp files
        compressed = tmp_path / "test.img.xz"
        decompressed = tmp_path / "test.img"
        compressed.write_bytes(b"compressed")
        decompressed.write_bytes(b"decompressed")

        # Set temp file paths
        backend.local_compressed = compressed
        backend.local_decompressed = decompressed

        # Mock power toggle
        with patch.object(backend, "_power_toggle"):
            backend.cleanup()

        # Verify compressed file removed
        assert not compressed.exists()

    def test_cleanup_handles_missing_files_gracefully(self, backend, tmp_path):
        """Test that cleanup doesn't fail if files don't exist."""
        # Set paths to non-existent files
        backend.local_compressed = tmp_path / "nonexistent.xz"
        backend.local_decompressed = tmp_path / "nonexistent.img"

        # Mock power toggle
        with patch.object(backend, "_power_toggle"):
            # Should not raise exception
            backend.cleanup()

    def test_cleanup_handles_missing_attributes(self, backend):
        """Test that cleanup works if attributes not set."""
        # Don't set local_compressed or local_decompressed

        # Mock power toggle
        with patch.object(backend, "_power_toggle"):
            # Should not raise exception
            backend.cleanup()

    def test_prepare_environment_tracks_temp_files(self, backend, tmp_path):
        """Test that prepare_environment sets temp file attributes."""
        # Mock all the dependencies
        with patch("hardware_backends.rpi_iscsi.ImageDownloader") as mock_downloader_class:
            mock_downloader = MagicMock()
            mock_downloader_class.return_value = mock_downloader

            compressed = tmp_path / "test.img.xz"
            compressed.write_bytes(b"compressed")
            mock_downloader.download.return_value = compressed

            # Create the decompressed file since subprocess.run will be mocked
            decompressed = tmp_path / "test.img"
            decompressed.write_bytes(b"decompressed")

            # Mock ImageInfo.from_url to return a valid ImageInfo
            from boot_test_lib.download import ImageInfo

            mock_image_info = ImageInfo(
                url="http://example.com/test.img.xz",
                filename="test.img.xz",
                expected_name="test.img",
                image_type="rpi",
            )

            with patch("hardware_backends.rpi_iscsi.ImageInfo.from_url", return_value=mock_image_info):
                # Mock subprocess for decompression
                with patch("hardware_backends.rpi_iscsi.subprocess.run"):
                    # Mock _setup_iscsi_image
                    with patch.object(backend, "_setup_iscsi_image"):
                        # Mock _start_serial_console
                        with patch.object(backend, "_start_serial_console"):
                            backend.prepare_environment()

        # Verify attributes are set
        assert hasattr(backend, "local_compressed")
        assert hasattr(backend, "local_decompressed")
        assert backend.local_compressed == compressed


class TestRPiDecompressionSpaceErrorHandling:
    """Tests for RPi decompression space error handling."""

    @pytest.fixture
    def backend(self, tmp_path):
        """Create RPi backend."""
        config = TestConfig(
            image_url="http://example.com/test.img.xz",
            metrics_id=1,
            metrics_db=tmp_path / "metrics.db",
            timeout_minutes=10,
        )

        return RPiISCSIBackend(
            config=config,
            rpi_ip="192.168.1.100",
            power_toggle_script=tmp_path / "power.sh",
        )

    def test_decompression_handles_space_error(self, backend, tmp_path):
        """Test that decompression detects and reports space errors."""
        # Mock dependencies
        with patch("hardware_backends.rpi_iscsi.ImageDownloader") as mock_downloader_class:
            mock_downloader = MagicMock()
            mock_downloader_class.return_value = mock_downloader

            compressed = tmp_path / "test.img.xz"
            compressed.write_bytes(b"compressed")
            mock_downloader.download.return_value = compressed

            # Mock ImageInfo.from_url to return a valid ImageInfo
            from boot_test_lib.download import ImageInfo

            mock_image_info = ImageInfo(
                url="http://example.com/test.img.xz",
                filename="test.img.xz",
                expected_name="test.img",
                image_type="rpi",
            )

            # Mock subprocess to raise space error
            import errno

            space_error = OSError(errno.ENOSPC, "No space")

            with patch("hardware_backends.rpi_iscsi.ImageInfo.from_url", return_value=mock_image_info):
                with patch("hardware_backends.rpi_iscsi.subprocess.run", side_effect=space_error):
                    with patch("hardware_backends.rpi_iscsi.handle_space_error") as mock_handle:
                        with patch.object(backend, "_setup_iscsi_image"):
                            with patch.object(backend, "_start_serial_console"):
                                with pytest.raises(OSError):
                                    backend.prepare_environment()

                        # Verify handle_space_error was called
                        mock_handle.assert_called_once()
