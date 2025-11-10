"""Page Object for SDR Setup page."""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..base_page import BasePage
from ..config import Timeouts
from ..exceptions import ElementNotFoundError, ValidationError

logger = logging.getLogger(__name__)


@dataclass
class SDRInfo:
    """Information about an SDR device."""

    index: int
    serial: str
    purpose: str


class SDRSetupPage(BasePage):
    """Page object for the SDR Setup page."""

    # Locators
    PAGE_TITLE_TEXT = "SDR Setup"
    SDR_TABLE = (By.ID, "sdr_table")
    SDR_ROW_TEMPLATE = "sdr{}"  # Format with index
    SDR_SERIAL_TEMPLATE = "sdr{}-serial"
    SDR_PURPOSE_TEMPLATE = "sdr{}-purpose"
    SDR_DIALOG = (By.ID, "sdrsetup_dialog")
    USAGE_1090_RADIO = (By.ID, "usage1090")
    USAGE_978_RADIO = (By.ID, "usage978")
    SDR_GAIN_INPUT = (By.ID, "sdrgain")
    DIALOG_OK_BUTTON = (By.XPATH, "//button[@onclick='save_sdr_setup()']")
    APPLY_BUTTON_PRIMARY = (By.XPATH, "//button[@type='submit'][@name='sdr_setup'][@value='go']")
    APPLY_BUTTON_FALLBACK = (By.XPATH, "//button[@type='submit'][contains(text(), 'apply settings')]")

    MAX_SDR_SLOTS = 16  # Maximum SDR slots to check

    def navigate(self) -> None:
        """Navigate to SDR setup page."""
        self.navigate_to("/sdr_setup")

    def verify_setup_page_loaded(self) -> bool:
        return self.verify_page_loaded(self.PAGE_TITLE_TEXT)

    def wait_for_sdr_table_loaded(self) -> None:
        """Wait for SDR table to be present and populated."""
        logger.info("Waiting for SDR table to load...")
        self.find_element(self.SDR_TABLE, timeout=Timeouts.MEDIUM_WAIT)

        # Wait for at least one visible SDR row
        logger.info("Waiting for SDR data to load...")
        try:
            WebDriverWait(self.driver, Timeouts.API_DATA_LOAD).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "#sdr_table tbody tr:not(.d-none)")) > 0
            )
            logger.info("SDR data loaded")
        except TimeoutException:
            logger.warning("Timeout waiting for SDR data, continuing anyway...")

    def get_visible_sdr_count(self) -> int:
        """
        Get count of visible SDRs in table.

        Returns:
            Number of visible SDR rows
        """
        visible_rows = self.driver.find_elements(By.CSS_SELECTOR, "#sdr_table tbody tr:not(.d-none)")
        count = len(visible_rows)
        logger.info(f"Found {count} SDR(s) in table")
        return count

    def get_all_visible_sdrs(self) -> List[SDRInfo]:
        """
        Get information about all visible SDRs.

        Returns:
            List of SDRInfo objects
        """
        sdrs = []
        for i in range(self.MAX_SDR_SLOTS):
            try:
                row_id = self.SDR_ROW_TEMPLATE.format(i)
                sdr_row = self.driver.find_element(By.ID, row_id)

                # Skip if hidden
                class_attr = sdr_row.get_attribute("class")
                if class_attr and "d-none" in class_attr:
                    continue

                serial_id = self.SDR_SERIAL_TEMPLATE.format(i)
                purpose_id = self.SDR_PURPOSE_TEMPLATE.format(i)

                serial_element = self.driver.find_element(By.ID, serial_id)
                purpose_element = self.driver.find_element(By.ID, purpose_id)

                sdr_info = SDRInfo(index=i, serial=serial_element.text.strip(), purpose=purpose_element.text.strip())
                sdrs.append(sdr_info)

            except Exception:
                # No SDR at this index
                continue

        return sdrs

    def find_sdr_by_serial(self, serial_substring: str) -> Optional[SDRInfo]:
        """
        Find SDR by serial number substring.

        Args:
            serial_substring: Substring to search for in serial number

        Returns:
            SDRInfo if found, None otherwise
        """
        logger.info(f"Looking for SDR with serial containing '{serial_substring}'...")
        sdrs = self.get_all_visible_sdrs()

        for sdr in sdrs:
            if serial_substring in sdr.serial:
                logger.info(f"Found SDR with serial '{sdr.serial}' at index {sdr.index}")
                logger.info(f"Current purpose: '{sdr.purpose}'")
                return sdr

        logger.warning(f"No SDR found with serial containing '{serial_substring}'")
        return None

    def verify_sdr_purpose(self, sdr: SDRInfo, expected_purpose: str) -> bool:
        """
        Verify SDR has expected purpose.

        Args:
            sdr: SDR information
            expected_purpose: Expected purpose string (e.g., "1090", "978")

        Returns:
            True if purpose matches

        Raises:
            ValidationError: If purpose doesn't match
        """
        if expected_purpose not in sdr.purpose:
            raise ValidationError(f"SDR {sdr.index} has purpose '{sdr.purpose}', expected '{expected_purpose}'")
        logger.info(f"SDR {sdr.index} correctly assigned to '{expected_purpose}'")
        return True

    def open_sdr_dialog(self, sdr_index: int) -> None:
        """
        Open configuration dialog for an SDR.

        Args:
            sdr_index: Index of the SDR to configure
        """
        logger.info(f"Opening dialog for SDR {sdr_index}...")
        row_id = self.SDR_ROW_TEMPLATE.format(sdr_index)
        sdr_row = self.driver.find_element(By.ID, row_id)

        # Scroll into view
        self.scroll_to_element(sdr_row)

        # Click row to open dialog
        try:
            sdr_row.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", sdr_row)

        # Wait for dialog to appear
        logger.info("Waiting for dialog to appear...")
        self.wait_for_element_visible(self.SDR_DIALOG, timeout=Timeouts.MEDIUM_WAIT)
        time.sleep(Timeouts.JS_SETTLE)  # Wait for dialog to fully initialize

    def select_usage_1090(self) -> None:
        """Select 1090 MHz usage in dialog."""
        logger.info("Selecting 1090 usage...")
        self.click_element(self.USAGE_1090_RADIO)
        logger.info("1090 usage selected")

    def select_usage_978(self) -> None:
        """Select 978 MHz usage in dialog."""
        logger.info("Selecting 978 usage...")
        self.click_element(self.USAGE_978_RADIO)
        logger.info("978 usage selected")

    def set_gain_if_empty(self, gain_value: str = "auto") -> None:
        """
        Set gain value if field is empty.

        Args:
            gain_value: Gain value to set (e.g., "auto", "49.6")
        """
        try:
            gain_input = self.driver.find_element(*self.SDR_GAIN_INPUT)
            if gain_input.is_displayed():
                current_gain = gain_input.get_attribute("value")
                if not current_gain or current_gain.strip() == "":
                    logger.info(f"Setting gain to '{gain_value}'...")
                    gain_input.clear()
                    gain_input.send_keys(gain_value)
                    logger.info(f"Gain set to '{gain_value}'")
        except Exception as e:
            logger.warning(f"Could not set gain value: {e}")

    def save_dialog(self) -> None:
        """Save SDR dialog and wait for it to close."""
        logger.info("Saving dialog...")
        self.click_element(self.DIALOG_OK_BUTTON)

        # Wait for dialog to close
        logger.info("Waiting for dialog to close...")
        self.wait_for_element_invisible(self.SDR_DIALOG, timeout=Timeouts.SHORT_WAIT)
        time.sleep(2)  # Wait for UI to update

    def configure_sdr_to_1090(self, sdr_index: int) -> None:
        """
        Configure SDR to use 1090 MHz.

        Args:
            sdr_index: Index of the SDR to configure
        """
        self.open_sdr_dialog(sdr_index)
        self.select_usage_1090()
        self.set_gain_if_empty()
        self.save_dialog()

    def get_sdr_purpose(self, sdr_index: int) -> str:
        """Get current purpose of an SDR."""
        purpose_id = self.SDR_PURPOSE_TEMPLATE.format(sdr_index)
        purpose_element = self.driver.find_element(By.ID, purpose_id)
        return purpose_element.text.strip()

    def apply_settings(self) -> None:
        """Click Apply Settings button."""
        logger.info("Clicking Apply Settings button...")

        # Try primary selector first
        apply_button = None
        for locator in [self.APPLY_BUTTON_PRIMARY, self.APPLY_BUTTON_FALLBACK]:
            try:
                apply_button = self.find_element(locator, timeout=Timeouts.SHORT_WAIT)
                logger.info("Found Apply Settings button")
                break
            except Exception:
                continue

        if not apply_button:
            raise ElementNotFoundError("Could not find Apply Settings button")

        # Scroll and click
        self.scroll_to_element(apply_button)
        self.click_element(self.APPLY_BUTTON_PRIMARY)
        logger.info("Apply Settings button clicked")
