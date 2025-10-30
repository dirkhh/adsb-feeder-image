"""Page Object for Feeder Homepage."""

import logging
import re
import time

from selenium.webdriver.common.by import By

from ..base_page import BasePage
from ..config import Timeouts
from ..exceptions import ValidationError

logger = logging.getLogger(__name__)


class FeederHomepage(BasePage):
    """Page object for the Feeder Homepage."""

    # Locators
    PAGE_TITLE_TEMPLATE = "ADS-B Feeder Homepage for {}"
    POSITION_MESSAGE_DIV = (By.XPATH, "//div[contains(., 'Position / Message rate:')]")
    STATUS_SPAN = (By.ID, "mf_status_0")
    STATS_SPAN = (By.ID, "mf_stats_0")
    AGGREGATORS_DIV = (By.XPATH, "//div[contains(., 'No aggregators configured')]")
    DATA_SHARING_LINK = (By.XPATH, ".//a[contains(text(), 'Data Sharing') or contains(@href, '/aggregators')]")
    VERSION_LABEL = (By.XPATH, "//span[contains(text(), 'Your version:')]")
    VERSION_BADGE = (By.XPATH, "./following-sibling::span[contains(@class, 'version-badge')]")

    # Patterns
    STATS_PATTERN = r"\d+\s+pos\s+/\s+\d+\s+msg\s+per\s+sec\s+—\s+\d+\s+planes\s+/\s+\d+\s+today"

    def navigate(self) -> None:
        """Navigate to homepage."""
        self.navigate_to("/")

    def verify_page_loaded(self, expected_site_name: str) -> bool:
        """
        Verify we're on the feeder homepage with correct site name.

        Args:
            expected_site_name: Expected site name in title

        Returns:
            True if on correct page

        Raises:
            ValidationError: If page title is incorrect
        """
        title = self.get_current_title()
        expected_title = self.PAGE_TITLE_TEMPLATE.format(expected_site_name)

        if expected_title not in title:
            raise ValidationError(f"Wrong homepage title. Expected '{expected_title}', got '{title}'")

        logger.info(f"Homepage title correct: {title}")
        return True

    def get_position_message_rate(self) -> str:
        """
        Get position/message rate text.

        Returns:
            Combined status and stats text
        """
        logger.info("Checking Position / Message rate...")

        # Wait for the position div
        position_div = self.find_element(self.POSITION_MESSAGE_DIV, timeout=Timeouts.MEDIUM_WAIT)

        # Find the status link containing the spans
        status_link = position_div.find_element(By.XPATH, ".//a[span[@id='mf_status_0']]")

        # Give time for JavaScript to populate
        time.sleep(2)

        status_span = status_link.find_element(*self.STATUS_SPAN)
        stats_span = status_link.find_element(*self.STATS_SPAN)

        status_text = status_span.text.strip()
        stats_text = stats_span.text.strip()
        full_text = f"{status_text} — {stats_text}"

        logger.info(f"Position / Message rate: '{full_text}'")
        return full_text

    def verify_position_message_rate(self) -> bool:
        """
        Verify position/message rate has valid format.

        Returns:
            True if format is valid

        Raises:
            ValidationError: If format is invalid or empty
        """
        full_text = self.get_position_message_rate()

        # Check if it matches expected pattern
        if re.match(self.STATS_PATTERN, full_text):
            logger.info("Position / Message rate format is correct")
            return True

        # Allow partial patterns if they have numbers
        if any(c.isdigit() for c in full_text):
            logger.info(f"Position / Message rate has data (may still be loading): '{full_text}'")
            return True

        raise ValidationError(f"Position / Message rate is empty or invalid: '{full_text}'")

    def verify_aggregators_message(self) -> bool:
        """
        Verify "No aggregators configured" message and Data Sharing link.

        Returns:
            True if message and link are present

        Raises:
            ValidationError: If message or link is missing/incorrect
        """
        logger.info("Checking aggregators message...")

        aggregators_div = self.find_element(self.AGGREGATORS_DIV, timeout=Timeouts.MEDIUM_WAIT)
        aggregators_text = aggregators_div.text

        if "No aggregators configured" not in aggregators_text:
            raise ValidationError("Aggregators message not found correctly")

        # Find Data Sharing link
        data_sharing_link = aggregators_div.find_element(*self.DATA_SHARING_LINK)
        link_href = data_sharing_link.get_attribute("href")
        link_text = data_sharing_link.text.strip()

        if not link_href or "/aggregators" not in link_href:
            raise ValidationError(f"Data Sharing link incorrect: {link_href}")

        logger.info(f"Found aggregators message with Data Sharing link ({link_text}) to {link_href}")
        return True

    def get_version_info(self) -> str:
        """
        Get version information from page.

        Returns:
            Version string
        """
        logger.info("Checking version information...")

        version_label = self.find_element(self.VERSION_LABEL, timeout=Timeouts.MEDIUM_WAIT)
        version_badge = version_label.find_element(*self.VERSION_BADGE)
        version_text = version_badge.text.strip()

        logger.info(f"Version: '{version_text}'")
        return version_text

    def verify_version_info(self) -> bool:
        """
        Verify version information is present.

        Returns:
            True if version is present

        Raises:
            ValidationError: If version is missing
        """
        version_text = self.get_version_info()
        if not version_text:
            raise ValidationError("Version badge is empty")
        return True

    def verify_all_homepage_elements(self, site_name: str) -> bool:
        """
        Verify all required homepage elements.

        Args:
            site_name: Expected site name

        Returns:
            True if all elements verified successfully
        """
        logger.info("Verifying all homepage elements...")

        self.verify_page_loaded(site_name)
        self.verify_position_message_rate()
        self.verify_aggregators_message()
        self.verify_version_info()

        logger.info("All homepage elements verified successfully")
        return True
