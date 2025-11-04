"""Tests for VM libvirt backend temp file cleanup."""

from unittest.mock import MagicMock, patch

import pytest
from hardware_backends.base import TestConfig
from hardware_backends.vm_libvirt import VMLibvirtBackend


class TestVMTempFileCleanup:
    """Tests for VM backend temp file cleanup."""

    @pytest.fixture
    def backend(self, tmp_path):
        """Create VM backend with temp directory."""
        config = TestConfig(
            image_url="http://example.com/adsb-feeder-v1.0.0-Proxmox-x86_64.qcow2.xz",
            metrics_id=1,
            metrics_db=tmp_path / "metrics.db",
            timeout_minutes=10,
        )

        backend = VMLibvirtBackend(
            config=config,
            vm_server="192.168.1.200",
            vm_ssh_key=tmp_path / "key",
            vm_bridge="bridge77",
        )

        return backend

    def test_cleanup_removes_local_compressed_file(self, backend, tmp_path):
        """Test that cleanup removes local compressed temp file."""
        # Create fake local temp file
        compressed = tmp_path / "test.qcow2.xz"
        compressed.write_bytes(b"compressed")

        # Set temp file path
        backend.local_compressed = compressed

        # Mock remote operations
        with patch.object(backend.remote, "virsh"):
            with patch.object(backend.remote, "execute"):
                backend.cleanup()

        # Verify compressed file removed
        assert not compressed.exists()

    def test_cleanup_handles_missing_local_file(self, backend, tmp_path):
        """Test that cleanup doesn't fail if local file doesn't exist."""
        # Set path to non-existent file
        backend.local_compressed = tmp_path / "nonexistent.xz"

        # Mock remote operations
        with patch.object(backend.remote, "virsh"):
            with patch.object(backend.remote, "execute"):
                # Should not raise exception
                backend.cleanup()

    def test_cleanup_handles_missing_attribute(self, backend):
        """Test that cleanup works if attribute not set."""
        # Don't set local_compressed

        # Mock remote operations
        with patch.object(backend.remote, "virsh"):
            with patch.object(backend.remote, "execute"):
                # Should not raise exception
                backend.cleanup()

    def test_cleanup_still_cleans_remote_files(self, backend, tmp_path):
        """Test that cleanup still removes remote files."""
        # Set remote file paths
        backend.remote_compressed = "/tmp/test.qcow2.xz"
        backend.remote_qcow2 = "/tmp/test.qcow2"

        # Create local file
        compressed = tmp_path / "test.qcow2.xz"
        compressed.write_bytes(b"compressed")
        backend.local_compressed = compressed

        # Mock remote operations
        mock_virsh = MagicMock(return_value=MagicMock(returncode=0))
        mock_execute = MagicMock()

        with patch.object(backend.remote, "virsh", mock_virsh):
            with patch.object(backend.remote, "execute", mock_execute):
                backend.cleanup()

        # Verify remote files were deleted
        assert any("rm -f" in str(call) for call in mock_execute.call_args_list)

        # Verify local file removed
        assert not compressed.exists()

    def test_prepare_environment_tracks_local_file(self, backend, tmp_path):
        """Test that prepare_environment sets local_compressed attribute."""
        # Mock all dependencies
        with patch("hardware_backends.vm_libvirt.ImageDownloader") as mock_downloader_class:
            mock_downloader = MagicMock()
            mock_downloader_class.return_value = mock_downloader

            compressed = tmp_path / "test.qcow2.xz"
            compressed.write_bytes(b"compressed")
            mock_downloader.download.return_value = compressed

            # Mock remote operations
            with patch.object(backend, "_cleanup_existing_vm"):
                with patch.object(backend.remote, "execute"):
                    with patch.object(backend.remote, "scp_upload", return_value=True):
                        with patch.object(backend, "_decompress_remote_image"):
                            with patch.object(backend, "_create_vm"):
                                backend.prepare_environment()

        # Verify attribute is set
        assert hasattr(backend, "local_compressed")
        assert backend.local_compressed == compressed
