"""Configuration classes for selenium tests."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class SeleniumConfig:
    """Selenium test configuration settings."""

    rpi_ip: str
    browser: Literal["chrome", "firefox"] = "chrome"
    headless: bool = True
    timeout: int = 90
    site_name: str = "automated test site"
    latitude: float = 45.48
    longitude: float = -122.66
    altitude: int = 30
    # Directory to save debug artifacts (screenshots, page sources)
    artifacts_dir: str = "/tmp/selenium-artifacts"

    @property
    def base_url(self) -> str:
        """Return base URL for the test device."""
        return f"http://{self.rpi_ip}"


class Timeouts:
    """Timeout constants for different wait scenarios."""

    PAGE_LOAD = 30  # Selenium page load timeout
    SHORT_WAIT = 5  # Quick element waits
    MEDIUM_WAIT = 30  # Form submissions, moderate operations
    LONG_WAIT = 600  # Processing pages, long operations
    JS_SETTLE = 1  # Time to wait after JS actions for DOM to settle
    API_DATA_LOAD = 30  # Waiting for API data to populate
