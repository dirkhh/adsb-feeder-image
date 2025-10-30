"""Browser factory for creating WebDriver instances."""

import logging
import platform
import shutil
from typing import Literal

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.remote.webdriver import WebDriver

from .config import Timeouts
from .exceptions import BrowserSetupError

logger = logging.getLogger(__name__)


class BrowserFactory:
    """Factory for creating browser instances."""

    @staticmethod
    def create_driver(browser_type: Literal["chrome", "firefox"] = "chrome", headless: bool = True) -> WebDriver:
        """
        Create a WebDriver instance.

        Args:
            browser_type: Type of browser ('chrome' or 'firefox')
            headless: Whether to run in headless mode

        Returns:
            Configured WebDriver instance

        Raises:
            BrowserSetupError: If browser creation fails
        """
        try:
            if browser_type == "chrome":
                return BrowserFactory._create_chrome(headless)
            elif browser_type == "firefox":
                return BrowserFactory._create_firefox(headless)
            else:
                raise ValueError(f"Unsupported browser type: {browser_type}")
        except Exception as e:
            raise BrowserSetupError(f"Failed to create {browser_type} browser: {e}") from e

    @staticmethod
    def _create_chrome(headless: bool) -> WebDriver:
        """
        Create Chrome WebDriver with standard options.

        On x86_64: Uses Selenium Manager to auto-download chromedriver
        On ARM64: Uses system-installed chromium and chromedriver (must be pre-installed)
        """
        logger.info("Creating Chrome browser...")
        options = ChromeOptions()

        if headless:
            options.add_argument("--headless=new")

        # Standard options for stability
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")

        # Set preferences
        options.set_capability("pageLoadStrategy", "normal")

        # ARM64 systems (like Raspberry Pi) need system-installed drivers
        # Selenium Manager doesn't support ARM64
        arch = platform.machine().lower()
        if arch in ("aarch64", "arm64", "armv7l"):
            logger.info(f"Detected ARM architecture ({arch}), using system chromedriver")

            # Try to find system chromium binary
            chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
            if chromium_path:
                options.binary_location = chromium_path
                logger.info(f"Using chromium at: {chromium_path}")

            # Try to find system chromedriver
            chromedriver_path = shutil.which("chromedriver")
            if chromedriver_path:
                logger.info(f"Using chromedriver at: {chromedriver_path}")
                service = ChromeService(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=options)
            else:
                # Let Selenium try without explicit service (may work if in PATH)
                logger.warning("chromedriver not found in PATH, attempting without explicit path")
                driver = webdriver.Chrome(options=options)
        else:
            # x86_64: Use Selenium Manager for automatic driver management
            logger.info(f"Detected x86_64 architecture, using Selenium Manager")
            driver = webdriver.Chrome(options=options)

        driver.set_page_load_timeout(Timeouts.PAGE_LOAD)
        logger.info("Chrome browser created successfully")
        return driver

    @staticmethod
    def _create_firefox(headless: bool) -> WebDriver:
        """
        Create Firefox WebDriver with standard options.

        On x86_64: Uses Selenium Manager to auto-download geckodriver
        On ARM64: Uses system-installed firefox and geckodriver (must be pre-installed)
        """
        logger.info("Creating Firefox browser...")
        options = FirefoxOptions()

        if headless:
            options.add_argument("--headless")

        # Standard options for stability
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")

        # Set preferences
        options.set_preference("dom.webnotifications.enabled", False)
        options.set_preference("media.volume_scale", "0.0")

        # ARM64 systems (like Raspberry Pi) need system-installed drivers
        # Selenium Manager doesn't support ARM64
        arch = platform.machine().lower()
        if arch in ("aarch64", "arm64", "armv7l"):
            logger.info(f"Detected ARM architecture ({arch}), using system geckodriver")

            # Try to find system firefox binary
            firefox_path = shutil.which("firefox") or shutil.which("firefox-esr")
            if firefox_path:
                options.binary_location = firefox_path
                logger.info(f"Using firefox at: {firefox_path}")

            # Try to find system geckodriver
            geckodriver_path = shutil.which("geckodriver")
            if geckodriver_path:
                logger.info(f"Using geckodriver at: {geckodriver_path}")
                service = FirefoxService(executable_path=geckodriver_path)
                driver = webdriver.Firefox(service=service, options=options)
            else:
                # Let Selenium try without explicit service (may work if in PATH)
                logger.warning("geckodriver not found in PATH, attempting without explicit path")
                driver = webdriver.Firefox(options=options)
        else:
            # x86_64: Use Selenium Manager for automatic driver management
            logger.info(f"Detected x86_64 architecture, using Selenium Manager")
            driver = webdriver.Firefox(options=options)

        driver.set_page_load_timeout(Timeouts.PAGE_LOAD)
        logger.info("Firefox browser created successfully")
        return driver
