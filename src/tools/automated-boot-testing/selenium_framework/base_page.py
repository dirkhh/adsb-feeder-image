"""Base page class for Page Object Model."""

import logging
import time
from pathlib import Path
from typing import Tuple, Union

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config import Timeouts
from .exceptions import ElementNotFoundError, ValidationError

logger = logging.getLogger(__name__)


class BasePage:
    """Base class for all page objects."""

    def __init__(self, driver: WebDriver, base_url: str):
        """
        Initialize page object.

        Args:
            driver: Selenium WebDriver instance
            base_url: Base URL for the application
        """
        self.driver = driver
        self.base_url = base_url
        self.wait = WebDriverWait(driver, Timeouts.SHORT_WAIT)
        self.long_wait = WebDriverWait(driver, Timeouts.LONG_WAIT)

    def navigate_to(self, path: str = "") -> None:
        """Navigate to a specific path."""
        url = f"{self.base_url}{path}"
        logger.info(f"Navigating to {url}")
        self.driver.get(url)

    def get_current_url(self) -> str:
        """Return current page URL."""
        return self.driver.current_url

    def get_current_title(self) -> str:
        """Return current page title."""
        return self.driver.title

    def verify_page_loaded(self, expected_title) -> bool:
        title = self.get_current_title()
        if expected_title not in title:
            raise ValidationError(f"Wrong page title. Expected '{expected_title}' in title, got '{title}'")
        logger.info(f"Page loaded: {title}")
        return True

    def find_element(self, locator: Tuple[str, str], timeout: int = Timeouts.SHORT_WAIT) -> WebElement:
        """
        Find element with explicit wait.

        Args:
            locator: Tuple of (By.TYPE, value)
            timeout: Maximum wait time

        Returns:
            WebElement instance

        Raises:
            ElementNotFoundError: If element not found within timeout
        """
        try:
            wait = WebDriverWait(self.driver, timeout)
            element = wait.until(EC.presence_of_element_located(locator))
            return element
        except TimeoutException as e:
            raise ElementNotFoundError(f"Element not found: {locator}") from e

    def find_elements(self, locator: Tuple[str, str]) -> list[WebElement]:
        """
        Find multiple elements.

        Args:
            locator: Tuple of (By.TYPE, value)

        Returns:
            List of WebElement instances
        """
        return self.driver.find_elements(*locator)

    def click_element(self, locator_or_element: Union[Tuple[str, str], WebElement], timeout: int = Timeouts.SHORT_WAIT) -> None:
        """
        Click an element specified either by locator or by WebElement instance.

        Args:
            locator_or_element: Tuple locator (By, value) or an already-located WebElement
            timeout: Maximum wait time when a locator is provided

        Raises:
            ElementNotFoundError: If element not found or not clickable (when using a locator)
        """
        try:
            # If a locator tuple is passed, wait for it to be clickable
            if isinstance(locator_or_element, tuple):
                wait = WebDriverWait(self.driver, timeout)
                element = wait.until(EC.element_to_be_clickable(locator_or_element))
            else:
                # Assume it's a WebElement-like object
                element = locator_or_element

            try:
                element.click()
            except Exception:
                # Fallback to JavaScript click if regular click fails
                logger.debug(f"Regular click failed for {locator_or_element}, trying JavaScript")
                self.driver.execute_script("arguments[0].click();", element)
        except TimeoutException as e:
            raise ElementNotFoundError(f"Element not clickable: {locator_or_element}") from e

    def enter_text(self, locator: Tuple[str, str], text: str, clear_first: bool = True) -> None:
        """
        Enter text into an input field.

        Args:
            locator: Tuple of (By.TYPE, value)
            text: Text to enter
            clear_first: Whether to clear field before entering text
        """
        # Wait for element to be clickable (interactive) not just present
        try:
            wait = WebDriverWait(self.driver, Timeouts.SHORT_WAIT)
            element = wait.until(EC.element_to_be_clickable(locator))
        except TimeoutException as e:
            raise ElementNotFoundError(f"Element not interactive: {locator}") from e

        if clear_first:
            element.clear()
        element.send_keys(text)

    def scroll_to_element(self, element: WebElement) -> None:
        """Scroll element into view."""
        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(Timeouts.JS_SETTLE)

    def wait_for_element_visible(self, locator: Tuple[str, str], timeout: int = Timeouts.MEDIUM_WAIT) -> WebElement:
        """Wait for element to be visible."""
        try:
            wait = WebDriverWait(self.driver, timeout)
            return wait.until(EC.visibility_of_element_located(locator))
        except TimeoutException as e:
            raise ElementNotFoundError(f"Element not visible: {locator}") from e

    def wait_for_element_invisible(self, locator: Tuple[str, str], timeout: int = Timeouts.SHORT_WAIT) -> bool:
        """Wait for element to become invisible."""
        try:
            wait = WebDriverWait(self.driver, timeout)
            result = wait.until(EC.invisibility_of_element_located(locator))
            return bool(result)
        except TimeoutException:
            return False

    def is_element_present(self, locator: Tuple[str, str]) -> bool:
        """Check if element is present in DOM."""
        return len(self.find_elements(locator)) > 0

    def save_screenshot(self, artifacts_dir: str, name: str) -> str:
        """
        Save a screenshot using the WebDriver's save_screenshot method.

        Args:
            artifacts_dir: Directory to write the screenshot into
            name: Base name for the screenshot file (no extension)

        Returns:
            Path to the saved screenshot file as string
        """
        try:
            Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            path = Path(artifacts_dir) / f"{name}-{timestamp}.png"
            # driver.save_screenshot returns True/False; we ignore it here
            self.driver.save_screenshot(str(path))
            return str(path)
        except Exception as e:
            logger.warning(f"Failed to save screenshot: {e}")
            return ""

    def save_page_source(self, artifacts_dir: str, name: str) -> str:
        """
        Save the current page source to a file.

        Args:
            artifacts_dir: Directory to write the page source into
            name: Base name for the file (no extension)

        Returns:
            Path to the saved page source file as string
        """
        try:
            Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            path = Path(artifacts_dir) / f"{name}-{timestamp}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            return str(path)
        except Exception as e:
            logger.warning(f"Failed to save page source: {e}")
            return ""

    def save_debug_artifacts(self, artifacts_dir: str, name: str) -> dict:
        """Save screenshot and page source and return their paths."""
        return {
            "screenshot": self.save_screenshot(artifacts_dir, name),
            "page_source": self.save_page_source(artifacts_dir, name),
        }
