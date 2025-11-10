"""Page Object for Waiting/Processing page."""

import logging

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from ..base_page import BasePage
from ..config import Timeouts
from ..exceptions import PageTransitionError

logger = logging.getLogger(__name__)


class WaitingPage(BasePage):
    """Page object for the waiting/processing page."""

    WAITING_URL_PART = "/waiting"
    RESTARTING_URL_PART = "Restarting"

    def wait_for_target_page(
        self, target_title: str, timeout_seconds: int = Timeouts.LONG_WAIT, initial_wait_seconds: int = 60
    ) -> bool:
        """
        Wait for processing to complete and reach target page.

        First waits for either /waiting URL or the target page title.
        Then waits for the target page title if still on /waiting.

        Args:
            target_title: Title of the target page to wait for
            timeout_seconds: Maximum time to wait for target page
            initial_wait_seconds: Time to wait for initial redirect

        Returns:
            True if reached target page

        Raises:
            PageTransitionError: If timeout reached without getting to target
        """
        current_timeout = initial_wait_seconds
        try:
            # Wait for either /waiting URL or target page title
            logger.info(f"Waiting for redirect to waiting page or {target_title}...")
            WebDriverWait(self.driver, initial_wait_seconds).until(
                lambda d: self.WAITING_URL_PART in d.current_url or target_title in d.title or self.RESTARTING_URL_PART in d.title
            )

            current_url = self.get_current_url()
            current_title = self.get_current_title()

            # Check if we're already at target
            if target_title in current_title:
                logger.info(f"Arrived at target page: {current_title}")
                return True

            # If on waiting page, wait for target
            current_timeout = timeout_seconds
            if self.WAITING_URL_PART in current_url or self.RESTARTING_URL_PART in current_title:
                logger.info("Redirected to waiting page, waiting for processing...")
                WebDriverWait(self.driver, timeout_seconds).until(lambda d: target_title in d.title)
                logger.info(f"Processing completed, reached target page: {self.get_current_title()}")
                return True

            # Unexpected state
            logger.warning(f"Unexpected state: URL={current_url}, Title={current_title}")
            return False

        except TimeoutException as e:
            current_url = self.get_current_url()
            current_title = self.get_current_title()
            logger.error(f"Timeout waiting for target page '{target_title}'")
            logger.error(f"Current URL: {current_url}")
            logger.error(f"Current title: {current_title}")
            raise PageTransitionError(f"Failed to reach page with title '{target_title}' within {current_timeout} seconds") from e
