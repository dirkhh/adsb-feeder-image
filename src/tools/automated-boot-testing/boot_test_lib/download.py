"""Shared image download, caching, and validation utilities."""

import logging
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


@dataclass
class ImageInfo:
    """Metadata about a boot test image."""

    url: str
    filename: str
    expected_name: str  # Without compression extension
    image_type: str  # 'rpi' or 'vm'

    @classmethod
    def from_url(cls, url: str) -> "ImageInfo":
        """
        Parse image info from URL.

        Args:
            url: GitHub release URL

        Returns:
            ImageInfo with parsed metadata

        Raises:
            ValueError: If image type cannot be determined
        """
        parsed_url = urllib.parse.urlparse(url)
        filename = Path(parsed_url.path).name

        # Detect image type and extract expected name
        if "Proxmox-x86_64.qcow2" in filename:
            image_type = "vm"
            # Remove -Proxmox-x86_64.qcow2.xz to get expected name
            expected_name = filename.split("-Proxmox")[0]
        elif "raspberrypi64" in filename and filename.endswith(".img.xz"):
            image_type = "rpi"
            # Remove .xz to get expected .img name
            expected_name = filename.rsplit(".xz", 1)[0]
        else:
            raise ValueError(f"Unknown image type for filename: {filename}")

        return cls(url=url, filename=filename, expected_name=expected_name, image_type=image_type)


class ImageDownloader:
    """Download and cache boot images."""

    def __init__(self, cache_dir: Path = Path("/tmp")):
        """
        Initialize image downloader.

        Args:
            cache_dir: Directory for caching downloaded images
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def download(self, image_info: ImageInfo, force: bool = False) -> Path:
        """
        Download image with caching and progress reporting.

        Args:
            image_info: Image metadata
            force: Force re-download even if cached

        Returns:
            Path to downloaded (compressed) file

        Raises:
            requests.RequestException: On download failure
        """
        cached_path = self.cache_dir / image_info.filename

        if cached_path.exists() and not force:
            logger.info(f"Using cached image: {cached_path}")
            logger.info(f"Cache file size: {cached_path.stat().st_size / 1024 / 1024:.1f} MB")
            return cached_path

        logger.info(f"Downloading: {image_info.url}")
        logger.info(f"Saving to: {cached_path}")

        response = requests.get(image_info.url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        last_report = 0

        with open(cached_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    # Log progress every 5%
                    if total_size > 0 and downloaded > last_report:
                        pct = (downloaded / total_size) * 100
                        logger.info(f"Downloaded: {pct:.1f}% ({downloaded}/{total_size} bytes)")
                        last_report += int(0.05 * total_size)

        logger.info(f"✓ Download complete: {cached_path}")
        logger.info(f"Downloaded {cached_path.stat().st_size / 1024 / 1024:.1f} MB")
        return cached_path
