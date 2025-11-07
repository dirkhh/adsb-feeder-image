"""Page Object for Basic Setup page."""

import logging
import re
from html import unescape

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..base_page import BasePage
from ..config import Timeouts
from ..exceptions import ValidationError

logger = logging.getLogger(__name__)


class BasicSetupPage(BasePage):
    """Page object for the Basic Setup page."""

    # Locators
    PAGE_TITLE_TEXT = "Basic Setup"
    CPU_TEMP_BLOCK = (By.ID, "cpu_temp_block")
    CPU_TEMP = (By.ID, "cpu_temp")
    SITE_NAME_INPUT = (By.ID, "site_name")
    LAT_INPUT = (By.ID, "lat")
    LON_INPUT = (By.ID, "lon")
    ALT_INPUT = (By.ID, "alt")
    ADSB_CHECKBOX = (By.ID, "is_adsb_feeder")
    SUBMIT_BUTTON_PRIMARY = (By.XPATH, "//button[@type='submit'][@name='submit'][@value='go']")
    SUBMIT_BUTTON_FALLBACK = (By.XPATH, "//button[@type='submit']")

    def navigate(self) -> None:
        """Navigate to the basic setup page."""
        self.navigate_to("/setup")

    def verify_page_loaded(self) -> bool:
        """
        Verify we're on the basic setup page.

        Returns:
            True if on correct page

        Raises:
            ValidationError: If page title is incorrect
        """
        title = self.get_current_title()
        if self.PAGE_TITLE_TEXT not in title:
            raise ValidationError(f"Wrong page title. Expected '{self.PAGE_TITLE_TEXT}' in title, got '{title}'")
        logger.info(f"Basic Setup page loaded: {title}")
        return True

    def get_declared_hardware(self) -> str:
        """Return hardware information as shown in the footer."""
        source = self.driver.page_source
        # Look for a <div> that contains "Running on ... • adsb-im-"
        # Capture text between "on" and the bullet/adsb-im- marker.
        pattern = re.compile(
            r"<div[^>]*>(?:.*?)Running\s+on\s*(?P<hw>.*?)\s*(?:•|&bull;|&#\d+;|&[^;]+;)\s*adsb-im-.*?</div>",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(source)
        if not match:
            logger.debug("Declared hardware string not found in page source.")
            return ""

        hw_raw = match.group("hw")
        # Strip any HTML tags that might be inside the captured region
        hw_text = re.sub(r"<[^>]+>", "", hw_raw)
        # Unescape HTML entities and trim whitespace
        hw_text = unescape(hw_text).strip()
        return hw_text

    def check_virtualized(self) -> bool:
        """On virtualized platforms several of the tests need to be skipped"""
        return "Virtualized" in self.get_declared_hardware()

    def get_cpu_temperature(self) -> float:
        """
        Get CPU temperature from the page.

        Returns:
            CPU temperature in Celsius

        Raises:
            ValidationError: If temperature cannot be parsed
            TimeoutException: If temperature doesn't appear within timeout
        """
        logger.info("Reading CPU temperature...")
        temp_text = ""

        try:
            # Wait up to 5 seconds for the temperature element to be present
            cpu_temp_element = WebDriverWait(self.driver, 5).until(lambda driver: driver.find_element(*self.CPU_TEMP))

            # Wait for the element to have non-empty text
            WebDriverWait(self.driver, 5).until(lambda _: cpu_temp_element.text.strip() != "")

            temp_text = cpu_temp_element.text.strip()

            # Extract numeric value (handle formats like "65.5°C" or "65.5")
            temp_value = float("".join(filter(lambda x: x.isdigit() or x == ".", temp_text)))
            logger.info(f"CPU temperature: {temp_text}, extracted {temp_value}")
            return temp_value

        except TimeoutException:
            raise ValidationError("CPU temperature did not appear within 5 seconds")
        except ValueError as e:
            raise ValidationError(f"Could not parse CPU temperature from text: {temp_text}") from e

    def verify_cpu_temperature(self, min_temp: float = 30.0, max_temp: float = 85.0) -> bool:
        """
        Verify CPU temperature is in reasonable range.

        Args:
            min_temp: Minimum acceptable temperature
            max_temp: Maximum acceptable temperature

        Returns:
            True if temperature is in range

        Raises:
            ValidationError: If temperature is out of range
        """
        temp = self.get_cpu_temperature()
        if not (min_temp <= temp <= max_temp):
            raise ValidationError(f"CPU temperature out of range: {temp}°C (expected {min_temp}-{max_temp})")
        return True

    def fill_site_information(self, site_name: str, latitude: float, longitude: float, altitude: int) -> None:
        """
        Fill in site information form fields.

        Args:
            site_name: Name of the site
            latitude: Site latitude
            longitude: Site longitude
            altitude: Site altitude in meters
        """
        logger.info(f"Filling site information: {site_name} at ({latitude}, {longitude}), alt={altitude}m")

        self.enter_text(self.SITE_NAME_INPUT, site_name)
        self.enter_text(self.LAT_INPUT, str(latitude))
        self.enter_text(self.LON_INPUT, str(longitude))
        self.enter_text(self.ALT_INPUT, str(altitude))

        logger.info("Site information filled")

    def select_adsb_feeder(self) -> None:
        """Select the ADSB feeder checkbox."""
        logger.info("Selecting ADSB feeder checkbox...")
        checkbox = self.find_element(self.ADSB_CHECKBOX)

        # Scroll into view
        self.scroll_to_element(checkbox)

        if not checkbox.is_selected():
            self.click_element(self.ADSB_CHECKBOX)
            logger.info("ADSB checkbox checked")
        else:
            logger.info("ADSB checkbox already checked")

    def submit_form(self) -> None:
        """Submit the basic setup form."""
        logger.info("Looking for submit button...")
        # Try primary selector first, fall back to generic
        submit_button = None
        for locator in [self.SUBMIT_BUTTON_PRIMARY, self.SUBMIT_BUTTON_FALLBACK]:
            try:
                submit_button = self.find_element(locator, timeout=Timeouts.SHORT_WAIT)
                logger.info("Found submit button")
                break
            except Exception:
                submit_button = None
                continue

        if not submit_button:
            raise ValidationError("Could not find submit button")

        # Log current field values for debugging
        try:
            site_name = self.driver.find_element(*self.SITE_NAME_INPUT).get_attribute("value")
            lat = self.driver.find_element(*self.LAT_INPUT).get_attribute("value")
            lon = self.driver.find_element(*self.LON_INPUT).get_attribute("value")
            alt = self.driver.find_element(*self.ALT_INPUT).get_attribute("value")
            checkbox = self.driver.find_element(*self.ADSB_CHECKBOX)
            is_checked = checkbox.is_selected()
            logger.info(
                f"Form values before submit: site_name='{site_name}', lat='{lat}', lon='{lon}', alt='{alt}', is_adsb_feeder={is_checked}"
            )
        except Exception as e:
            logger.warning(f"Could not read form values: {e}")

        # Scroll button into view with extra offset to account for fixed navbar
        # The navbar is covering the button, so we need to scroll it away from the top
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", submit_button)
        import time

        time.sleep(0.5)  # Let the scroll settle

        try:
            submit_button.click()
            logger.info("Submit button clicked")
        except Exception as e:
            logger.debug(f"Regular click failed for submit button ({e}), trying JavaScript click")
            # Use JS click directly on the button element
            # This is more reliable than form.submit() for forms with JS handlers
            self.driver.execute_script("arguments[0].click();", submit_button)
            logger.info("Submit button clicked via JavaScript")
