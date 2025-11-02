"""Tests for boot_test_lib.download module.

Note: Integration tests are marked with @pytest.mark.integration and can be run separately:
    pytest tests/test_download.py -m integration           # Run only integration tests
    pytest tests/test_download.py -m "not integration"     # Run only unit tests
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
from boot_test_lib.download import ImageDownloader, ImageInfo


class TestImageInfo:
    """Tests for ImageInfo dataclass and URL parsing."""

    def test_from_url_vm_image(self):
        """Test parsing VM image URL."""
        url = "https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6/adsb-im-x86-64-vm-v3.0.6-Proxmox-x86_64.qcow2.xz"

        info = ImageInfo.from_url(url)

        assert info.url == url
        assert info.filename == "adsb-im-x86-64-vm-v3.0.6-Proxmox-x86_64.qcow2.xz"
        assert info.expected_name == "adsb-im-x86-64-vm-v3.0.6"
        assert info.image_type == "vm"

    def test_from_url_rpi_image(self):
        """Test parsing Raspberry Pi image URL."""
        url = (
            "https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6.img.xz"
        )

        info = ImageInfo.from_url(url)

        assert info.url == url
        assert info.filename == "adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6.img.xz"
        assert info.expected_name == "adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6.img"
        assert info.image_type == "rpi"

    def test_from_url_unknown_type(self):
        """Test parsing URL with unknown image type raises ValueError."""
        url = "https://example.com/some-unknown-file.tar.gz"

        with pytest.raises(ValueError, match="Unknown image type"):
            ImageInfo.from_url(url)

    def test_from_url_without_xz_extension_vm(self):
        """Test VM image URL without .xz extension."""
        url = "https://example.com/adsb-im-x86-64-vm-v3.0.6-Proxmox-x86_64.qcow2"

        # This should still be recognized as VM type even without .xz
        info = ImageInfo.from_url(url)
        assert info.image_type == "vm"
        assert info.filename == "adsb-im-x86-64-vm-v3.0.6-Proxmox-x86_64.qcow2"


class TestImageDownloader:
    """Tests for ImageDownloader class."""

    def test_init_creates_cache_dir(self):
        """Test that __init__ creates cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            assert not cache_dir.exists()

            downloader = ImageDownloader(cache_dir=cache_dir)

            assert cache_dir.exists()
            assert downloader.cache_dir == cache_dir

    def test_init_with_existing_cache_dir(self):
        """Test __init__ works with existing cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            assert cache_dir.exists()

            downloader = ImageDownloader(cache_dir=cache_dir)

            assert cache_dir.exists()
            assert downloader.cache_dir == cache_dir

    @patch("boot_test_lib.download.requests.get")
    def test_download_success(self, mock_get):
        """Test successful download."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            downloader = ImageDownloader(cache_dir=cache_dir)

            # Setup mock response
            mock_response = Mock()
            mock_response.headers = {"content-length": "1024"}
            mock_response.iter_content = Mock(return_value=[b"test" * 256])  # 1024 bytes
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            # Create test ImageInfo
            image_info = ImageInfo(
                url="https://example.com/test.img.xz",
                filename="test.img.xz",
                expected_name="test.img",
                image_type="vm",
            )

            # Download
            result = downloader.download(image_info)

            # Verify
            assert result == cache_dir / "test.img.xz"
            assert result.exists()
            mock_get.assert_called_once_with("https://example.com/test.img.xz", stream=True, timeout=30)

    @patch("boot_test_lib.download.requests.get")
    def test_download_uses_cache(self, mock_get):
        """Test that cached files are reused."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            downloader = ImageDownloader(cache_dir=cache_dir)

            # Create a cached file
            cached_file = cache_dir / "test.img.xz"
            cached_file.write_bytes(b"cached content")

            image_info = ImageInfo(
                url="https://example.com/test.img.xz",
                filename="test.img.xz",
                expected_name="test.img",
                image_type="vm",
            )

            # Download (should use cache)
            result = downloader.download(image_info)

            # Verify cache was used
            assert result == cached_file
            assert result.read_bytes() == b"cached content"
            mock_get.assert_not_called()

    @patch("boot_test_lib.download.requests.get")
    def test_download_force_redownload(self, mock_get):
        """Test force re-download ignores cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            downloader = ImageDownloader(cache_dir=cache_dir)

            # Create a cached file
            cached_file = cache_dir / "test.img.xz"
            cached_file.write_bytes(b"old content")

            # Setup mock response
            mock_response = Mock()
            mock_response.headers = {"content-length": "11"}
            mock_response.iter_content = Mock(return_value=[b"new content"])
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            image_info = ImageInfo(
                url="https://example.com/test.img.xz",
                filename="test.img.xz",
                expected_name="test.img",
                image_type="vm",
            )

            # Download with force=True
            result = downloader.download(image_info, force=True)

            # Verify new content was downloaded
            assert result == cached_file
            assert result.read_bytes() == b"new content"
            mock_get.assert_called_once()

    @patch("boot_test_lib.download.requests.get")
    def test_download_http_error(self, mock_get):
        """Test download handles HTTP errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            downloader = ImageDownloader(cache_dir=cache_dir)

            # Setup mock to raise HTTP error
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
            mock_get.return_value = mock_response

            image_info = ImageInfo(
                url="https://example.com/test.img.xz",
                filename="test.img.xz",
                expected_name="test.img",
                image_type="vm",
            )

            # Download should raise HTTPError
            with pytest.raises(requests.HTTPError, match="404 Not Found"):
                downloader.download(image_info)

    @patch("boot_test_lib.download.requests.get")
    def test_download_network_timeout(self, mock_get):
        """Test download handles network timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            downloader = ImageDownloader(cache_dir=cache_dir)

            # Setup mock to raise timeout
            mock_get.side_effect = requests.Timeout("Connection timed out")

            image_info = ImageInfo(
                url="https://example.com/test.img.xz",
                filename="test.img.xz",
                expected_name="test.img",
                image_type="vm",
            )

            # Download should raise Timeout
            with pytest.raises(requests.Timeout):
                downloader.download(image_info)


class TestImageDownloaderIntegration:
    """Integration tests with real downloads (marked for optional execution)."""

    @pytest.mark.integration
    def test_download_real_vm_image(self):
        """Test downloading actual VM image."""
        url = "https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6/adsb-im-x86-64-vm-v3.0.6-Proxmox-x86_64.qcow2.xz"

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            downloader = ImageDownloader(cache_dir=cache_dir)
            image_info = ImageInfo.from_url(url)

            # Download
            result = downloader.download(image_info)

            # Verify
            assert result.exists()
            assert result.name == "adsb-im-x86-64-vm-v3.0.6-Proxmox-x86_64.qcow2.xz"
            assert result.stat().st_size > 0

            # Test caching - second download should be instant
            result2 = downloader.download(image_info)
            assert result2 == result
            assert result2.exists()

    @pytest.mark.integration
    def test_download_real_rpi_image(self):
        """Test downloading actual Raspberry Pi image."""
        url = (
            "https://github.com/dirkhh/adsb-feeder-image/releases/download/v3.0.6/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6.img.xz"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            downloader = ImageDownloader(cache_dir=cache_dir)
            image_info = ImageInfo.from_url(url)

            # Download
            result = downloader.download(image_info)

            # Verify
            assert result.exists()
            assert result.name == "adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6.img.xz"
            assert result.stat().st_size > 0

            # Test force re-download
            result3 = downloader.download(image_info, force=True)
            assert result3 == result
            assert result3.exists()
