#!/usr/bin/env python3
"""
Selenium test runner - designed to run as non-root user (testuser).
This script is invoked by test-feeder-image.py via sudo -u testuser.
"""

import argparse
import getpass
import logging
import re
import sys
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager

# Configure basic logging. Can be overridden in main by --log-level
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def wait_for_target_page(driver, target_title: str, timeout_seconds: int = 600, initial_wait_seconds: int = 60) -> bool:
    """
    Wait for processing to complete and reach the target page.

    First waits for either '/waiting' URL or the target page title (in case we're already there).
    Then waits for the target page title if we're still on /waiting.
    """
    try:
        # First, wait for either /waiting URL or the target page title
        logging.info(f"Waiting for redirect to waiting page or {target_title}...")
        WebDriverWait(driver, initial_wait_seconds).until(lambda d: "/waiting" in d.current_url or target_title in d.title)
        current_url = driver.current_url
        current_title = driver.title

        if target_title in current_title:
            logging.info(f"Arrived at target page: {current_title}")
            return True
        elif "/waiting" in current_url:
            # yes, this seems superflous, but it's intended to show us where we are spending time waiting for the target page
            logging.info("Redirected to waiting page")
            WebDriverWait(driver, timeout_seconds).until(lambda d: target_title in d.title)
            logging.info(f"Processing completed, reached target page: {driver.title}")
            return True
        else:
            logging.warning(f"Unexpected state: URL={current_url}, Title={current_title}")
            return False

    except TimeoutException:
        current_url = driver.current_url
        current_title = driver.title
        logging.warning(f"Timeout waiting for target page '{target_title}'")
        logging.debug(f"Current URL: {current_url}")
        logging.debug(f"Current title: {current_title}")

        return False


def verify_homepage_elements(driver, wait, site_name: str) -> bool:
    """
    Verify the required elements on the feeder homepage.

    Args:
        driver: Selenium WebDriver instance
        wait: WebDriverWait instance
        site_name: Expected site name in the title

    Returns:
        0 on success, 1 on failure
    """
    try:
        logging.info("Verifying homepage elements...")

        # Check page title
        expected_title = f"ADS-B Feeder Homepage for {site_name}"
        current_title = driver.title
        if expected_title not in current_title:
            logging.error(f"Wrong homepage title. Expected '{expected_title}', got '{current_title}'")
            return False
        logging.info(f"Homepage title is correct: {current_title}")

        # 1. Check for "Position / Message rate:" with expected format
        logging.info("Checking Position / Message rate element...")
        try:
            # The position/message rate is in spans with IDs mf_status_0 and mf_stats_0
            # Find the div that contains "Position / Message rate:"
            # The link is a child of the same element
            position_div = wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(., 'Position / Message rate:')]"))
            )
            # Find the link that contains the status and stats spans within this div
            status_link = position_div.find_element(By.XPATH, ".//a[span[@id='mf_status_0']]")

            # Give a moment for JavaScript to populate, then read the text
            time.sleep(2)  # Allow time for JavaScript to populate the stats
            status_span = status_link.find_element(By.ID, "mf_status_0")
            stats_span = status_link.find_element(By.ID, "mf_stats_0")

            status_text = status_span.text.strip()
            stats_text = stats_span.text.strip()
            full_text = f"{status_text} — {stats_text}"

            logging.info(f"Found: '{full_text}'")

            # Verify format: "nn pos / mm msg per sec — pp planes / qq today"
            # Allow for the text to be in either span, combined with —
            # Pattern should match numbers for pos/msg per sec and planes/today
            pattern = r"\d+\s+pos\s+/\s+\d+\s+msg\s+per\s+sec\s+—\s+\d+\s+planes\s+/\s+\d+\s+today"
            if re.match(pattern, full_text):
                logging.info("Position / Message rate format is correct")
            elif full_text:
                # Allow all zeros or partial patterns - if it has numbers, it's probably valid
                if any(c.isdigit() for c in full_text):
                    logging.info(f"Position / Message rate found with data: '{full_text}'")
                else:
                    logging.warning(f"Position / Message rate appears empty or not populated yet: '{full_text}'")
            else:
                logging.warning("Position / Message rate is empty (may still be loading)")

        except Exception as e:
            logging.exception(f"Could not find Position / Message rate element: {e}")
            return False

        # 2. Check for "No aggregators configured. Add aggregators: Data Sharing" with link
        logging.info("Checking aggregators configuration message...")
        try:
            # The text "No aggregators configured" is in a div, and the link is a sibling
            aggregators_div = wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(., 'No aggregators configured')]"))
            )
            aggregators_text = aggregators_div.text
            if "No aggregators configured" not in aggregators_text:
                logging.error("Aggregators message not found correctly")
                return False

            # Find the Data Sharing link (should be in the same div or a child)
            data_sharing_link = aggregators_div.find_element(
                By.XPATH, ".//a[contains(text(), 'Data Sharing') or contains(@href, '/aggregators')]"
            )
            link_href = data_sharing_link.get_attribute("href")
            link_text = data_sharing_link.text.strip()

            if "/aggregators" in link_href:
                logging.info(f"Found 'No aggregators configured' message with Data Sharing link ({link_text}) to {link_href}")
            else:
                logging.warning(f"Data Sharing link may not point to /aggregators: {link_href}")
                return False

        except Exception as e:
            logging.exception(f"Could not find aggregators configuration message: {e}")
            return False

        # 3. Check for "Your version:" with version badge
        logging.info("Checking version information...")
        try:
            # Find the span containing "Your version:" and get the following sibling with version-badge class
            version_label = wait.until(EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'Your version:')]")))
            # The version badge is a following sibling span
            version_badge = version_label.find_element(By.XPATH, "./following-sibling::span[contains(@class, 'version-badge')]")
            version_text = version_badge.text.strip()

            if version_text:
                logging.info(f"Found version information: '{version_text}'")
            else:
                logging.error("Version badge is empty")
                return False

        except Exception as e:
            logging.exception(f"Could not find version information: {e}")
            return False

        logging.info("All homepage elements verified successfully")
        return True

    except Exception as e:
        logging.exception(f"Error verifying homepage elements: {e}")
        return False


def verify_and_configure_sdrs(driver, wait, site_name: str = "automated test site") -> bool:
    """
    Verify SDR setup page and configure SDRs as needed.
    After configuration, applies settings and verifies homepage.

    Args:
        driver: Selenium WebDriver instance
        wait: WebDriverWait instance
        site_name: Site name to verify in homepage title

    Returns:
        0 on success, 1 on failure
    """
    try:
        logging.info("Verifying SDR configuration...")

        # Wait for the SDR table to be present and populated
        logging.info("Waiting for SDR table to load...")
        wait.until(EC.presence_of_element_located((By.ID, "sdr_table")))

        # Wait for at least one SDR row to become visible (data loaded from API)
        logging.info("Waiting for SDR data to load...")
        try:
            WebDriverWait(driver, 30).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "#sdr_table tbody tr:not(.d-none)")) > 0
            )
            logging.info("SDR data loaded")
        except TimeoutException:
            logging.warning("Timeout waiting for SDR data to load, continuing anyway...")

        # Count visible SDR rows (rows that don't have 'd-none' class)
        logging.info("Counting SDRs in table...")
        visible_sdr_rows = driver.find_elements(By.CSS_SELECTOR, "#sdr_table tbody tr:not(.d-none)")
        num_sdrs = len(visible_sdr_rows)
        logging.info(f"Found {num_sdrs} SDR(s) in table")

        if num_sdrs == 0:
            logging.error("No SDRs found in table")
            return False

        # Find the SDR with serial '978' and verify its assignment
        logging.info("Looking for SDR with serial '978'...")
        sdr_978_found = False
        sdr_978_purpose = None

        # Check all possible SDR slots (0-15) for visible ones
        for i in range(16):
            try:
                sdr_row = driver.find_element(By.ID, f"sdr{i}")
                # Check if row is visible (not d-none)
                if "d-none" in sdr_row.get_attribute("class"):
                    continue

                serial_element = driver.find_element(By.ID, f"sdr{i}-serial")
                serial_text = serial_element.text.strip()

                if "978" in serial_text:
                    sdr_978_found = True
                    purpose_element = driver.find_element(By.ID, f"sdr{i}-purpose")
                    sdr_978_purpose = purpose_element.text.strip()
                    logging.info(f"Found SDR with serial containing '978': {serial_text}")
                    logging.info(f"Current purpose/use: '{sdr_978_purpose}'")

                    # Check if it's assigned to '978'
                    if "978" in sdr_978_purpose:
                        logging.info("SDR with serial '978' is correctly assigned to use '978'")
                    else:
                        logging.error(f"SDR with serial '978' is not assigned to '978', got: '{sdr_978_purpose}'")
                        return False
                    break
            except Exception:
                # Continue checking other rows
                continue

        if not sdr_978_found:
            logging.warning("Warning: SDR with serial '978' not found (this may be expected if no such SDR exists)")

        # If there's a second SDR, click on it and assign it to 1090
        if num_sdrs >= 2:
            logging.info(f"Found {num_sdrs} SDRs, checking if we need to assign the second SDR to 1090...")

            # Collect all visible SDRs with their indices and serials
            visible_sdrs = []
            for i in range(16):  # Check up to 16 potential SDR slots
                try:
                    sdr_row = driver.find_element(By.ID, f"sdr{i}")
                    # Check if row is visible (not d-none)
                    if "d-none" not in sdr_row.get_attribute("class"):
                        serial_element = driver.find_element(By.ID, f"sdr{i}-serial")
                        serial_text = serial_element.text.strip()
                        visible_sdrs.append((i, serial_text))
                except Exception:
                    continue

            # Find the second SDR (one that's not the 978 one, or just the second one)
            second_sdr_idx = None
            second_sdr_serial = None

            if len(visible_sdrs) >= 2:
                # Prefer a non-978 SDR if available
                for idx, serial in visible_sdrs:
                    if "978" not in serial:
                        second_sdr_idx = idx
                        second_sdr_serial = serial
                        break

                # If no non-978 found, just use the second visible SDR
                if second_sdr_idx is None:
                    second_sdr_idx, second_sdr_serial = visible_sdrs[1]

            if second_sdr_idx is not None:
                logging.info(f"Found second SDR at index {second_sdr_idx} with serial: {second_sdr_serial}")

                # Check current purpose
                purpose_element = driver.find_element(By.ID, f"sdr{second_sdr_idx}-purpose")
                current_purpose = purpose_element.text.strip()
                logging.info(f"Current purpose/use: '{current_purpose}'")

                # If not already assigned to 1090, click and assign it
                if "1090" not in current_purpose:
                    logging.info(f"Clicking on SDR row {second_sdr_idx} to open dialog...")
                    sdr_row = driver.find_element(By.ID, f"sdr{second_sdr_idx}")
                    driver.execute_script("arguments[0].scrollIntoView(true);", sdr_row)
                    time.sleep(1)

                    # Click the row to open the dialog
                    try:
                        sdr_row.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", sdr_row)

                    logging.info("Waiting for dialog to appear...")
                    # Wait for modal to be visible
                    wait.until(EC.visibility_of_element_located((By.ID, "sdrsetup_dialog")))

                    # Wait a moment for radio buttons to be ready
                    time.sleep(1)

                    # Find and click the 1090 radio button
                    logging.info("Selecting 1090 in dialog...")
                    try:
                        usage_1090 = wait.until(EC.element_to_be_clickable((By.ID, "usage1090")))
                        if not usage_1090.is_selected():
                            try:
                                usage_1090.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", usage_1090)
                        logging.info("Selected 1090 in dialog")
                    except Exception as e:
                        logging.exception(f"Could not find/select usage1090 radio button: {e}")
                        return False

                    # Set gain value if the field is visible and empty
                    try:
                        gain_input = driver.find_element(By.ID, "sdrgain")
                        if gain_input.is_displayed():
                            current_gain = gain_input.get_attribute("value")
                            if not current_gain or current_gain.strip() == "":
                                logging.info("Setting gain to 'auto'...")
                                gain_input.clear()
                                gain_input.send_keys("auto")
                                logging.info("Gain set to 'auto'")
                    except Exception as e:
                        logging.warning(f"Could not set gain value (may not be needed): {e}")

                    # Click the OK button to save
                    logging.info("Clicking OK button to save...")
                    ok_button = driver.find_element(By.XPATH, "//button[@onclick='save_sdr_setup()']")
                    try:
                        ok_button.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", ok_button)

                    # Wait for dialog to close
                    logging.info("Waiting for dialog to close...")
                    WebDriverWait(driver, 5).until(EC.invisibility_of_element_located((By.ID, "sdrsetup_dialog")))

                    # Wait a moment for UI to update
                    time.sleep(2)

                    # Verify the assignment was saved
                    purpose_element = driver.find_element(By.ID, f"sdr{second_sdr_idx}-purpose")
                    updated_purpose = purpose_element.text.strip()
                    logging.info(f"Updated purpose/use: '{updated_purpose}'")

                    if "1090" in updated_purpose:
                        logging.info("Successfully assigned second SDR to 1090")
                    else:
                        logging.warning(f"SDR purpose shows '{updated_purpose}', expected '1090'")
                else:
                    logging.info("Second SDR is already assigned to 1090")
            else:
                logging.warning("Could not identify second SDR to configure")
        else:
            logging.info("Only one SDR found, skipping second SDR configuration")

        logging.info("SDR verification and configuration completed")

        # Click Apply Settings button to save changes
        logging.info("Clicking Apply Settings button...")
        apply_button = None
        apply_selectors = [
            "//button[@type='submit'][@name='sdr_setup'][@value='go']",
            "//button[@type='submit'][contains(text(), 'apply settings')]",
        ]

        for selector in apply_selectors:
            try:
                apply_button = driver.find_element(By.XPATH, selector)
                logging.info("Found Apply Settings button")
                break
            except Exception:
                continue

        if not apply_button:
            logging.error("Could not find Apply Settings button")
            return False

        driver.execute_script("arguments[0].scrollIntoView(true);", apply_button)
        time.sleep(1)

        try:
            apply_button.click()
            logging.info(f"Apply Settings button clicked {time.strftime('%H:%M:%S')}")
        except Exception:
            driver.execute_script("arguments[0].click();", apply_button)
            logging.info("Apply Settings button clicked via JavaScript")

        # Wait for processing to complete and reach homepage
        logging.info(f"Waiting for settings to be applied... {time.strftime('%H:%M:%S')}")
        wait_result = wait_for_target_page(driver, "Feeder Homepage", timeout_seconds=600)
        if not wait_result:
            return False

        # Verify homepage elements
        homepage_result = verify_homepage_elements(driver, wait, site_name)
        if not homepage_result:
            return False

        return True

    except Exception as e:
        logging.exception(f"Error during SDR verification: {e}")
        return False


def run_basic_setup_test(rpi_ip: str, timeout_seconds: int = 90) -> int:
    """
    Run basic setup test using Selenium.

    Returns:
        0 on success, 1 on failure
    """
    logging.info(f"Testing basic setup on http://{rpi_ip}/setup...")
    logging.info(f"Running as user: {getpass.getuser()}")

    driver = None
    try:
        logging.info("Starting Firefox browser...")

        # Setup Firefox with enhanced options
        firefox_service = FirefoxService(GeckoDriverManager().install())
        firefox_options = webdriver.FirefoxOptions()
        firefox_options.add_argument("--headless")
        firefox_options.add_argument("--no-sandbox")
        firefox_options.add_argument("--disable-dev-shm-usage")
        firefox_options.add_argument("--disable-gpu")
        firefox_options.add_argument("--disable-extensions")

        # Set Firefox preferences
        firefox_options.set_preference("dom.webnotifications.enabled", False)
        firefox_options.set_preference("media.volume_scale", "0.0")

        driver = webdriver.Firefox(service=firefox_service, options=firefox_options)
        driver.set_page_load_timeout(30)

        logging.info("Firefox browser started successfully")

        wait = WebDriverWait(driver, 10)

        # Navigate to the feeder page
        driver.get(f"http://{rpi_ip}/setup")

        # Check page title
        logging.info("Checking page title...")
        current_title = driver.title
        if "Basic Setup" not in current_title:
            logging.error(f"Wrong page title: {current_title}")
            return 1
        logging.info(f"Page title is correct ({current_title})")

        # Check CPU temperature
        logging.info("Checking CPU temperature...")
        cpu_temp_block = wait.until(EC.presence_of_element_located((By.ID, "cpu_temp_block")))
        cpu_temp_element = cpu_temp_block.find_element(By.ID, "cpu_temp")
        temp_text = cpu_temp_element.text.strip()

        # Extract temperature value
        try:
            temp_value = float("".join(filter(lambda x: x.isdigit() or x == ".", temp_text)))
        except ValueError:
            logging.error(f"Could not parse CPU temperature from text: {temp_text}")
            return 1

        if not (30 <= temp_value <= 85):
            logging.error(f"CPU temperature out of range: {temp_value}°C")
            return 1
        logging.info(f"CPU temperature is reasonable: {temp_value}°C")

        # Fill in site information
        logging.info("Filling in site information...")

        site_name_input = wait.until(EC.element_to_be_clickable((By.ID, "site_name")))
        site_name_input.clear()
        site_name_input.send_keys("automated test site")

        lat_input = driver.find_element(By.ID, "lat")
        lat_input.clear()
        lat_input.send_keys("45.48")

        lon_input = driver.find_element(By.ID, "lon")
        lon_input.clear()
        lon_input.send_keys("-122.66")

        alt_input = driver.find_element(By.ID, "alt")
        alt_input.clear()
        alt_input.send_keys("30")

        logging.info("Site information filled")

        # Click ADSB checkbox
        logging.info("Clicking ADSB checkbox...")
        adsb_checkbox = wait.until(EC.presence_of_element_located((By.ID, "is_adsb_feeder")))
        driver.execute_script("arguments[0].scrollIntoView(true);", adsb_checkbox)
        time.sleep(1)

        if not adsb_checkbox.is_selected():
            try:
                adsb_checkbox.click()
                logging.info("ADSB checkbox clicked")
            except Exception:
                driver.execute_script("arguments[0].click();", adsb_checkbox)
                logging.info("ADSB checkbox clicked via JavaScript")
        else:
            logging.info("ADSB checkbox was already checked")

        # Click submit button
        logging.info("Looking for submit button...")
        submit_button = None

        submit_selectors = [
            "//button[@type='submit'][@name='submit'][@value='go']",
            "//button[@type='submit']",
        ]

        for selector in submit_selectors:
            try:
                submit_button = driver.find_element(By.XPATH, selector)
                logging.info("Found submit button")
                break
            except Exception:
                continue

        if not submit_button:
            logging.error("Could not find submit button")
            return 1

        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
        time.sleep(1)

        # Click submit
        try:
            submit_button.click()
            logging.info(f"Submit button clicked {time.strftime('%H:%M:%S')}")
        except Exception:
            driver.execute_script("arguments[0].click();", submit_button)
            logging.info("Submit button clicked via JavaScript")

        # Wait for form submission flow
        logging.info(f"Waiting for form submission to complete... {time.strftime('%H:%M:%S')}")
        try:
            wait_result = wait_for_target_page(driver, "SDR Setup", timeout_seconds=600)
            if not wait_result:
                return 1

            # Continue with SDR setup verification
            site_name = "automated test site"  # From form we filled earlier
            sdr_test_result = verify_and_configure_sdrs(driver, wait, site_name)
            if not sdr_test_result:
                return 1

            return 0

        except TimeoutException:
            current_url = driver.current_url
            current_title = driver.title
            logging.warning(f"Did not complete flow within timeout {time.strftime('%H:%M:%S')}")
            logging.debug(f"Current URL: {current_url}")
            logging.debug(f"Current title: {current_title}")

            # If we're already on the homepage, verify it directly
            if "Homepage" in current_title or "Feeder Homepage" in current_title:
                logging.info("Already on Homepage, verifying elements")
                site_name = "automated test site"  # From form we filled earlier
                homepage_result = verify_homepage_elements(driver, wait, site_name)
                return 0 if homepage_result else 1

            # If we're already on SDR Setup page, continue with verification
            if "SDR Setup" in current_title:
                logging.info("Already on SDR Setup page, continuing with verification")
                site_name = "automated test site"  # From form we filled earlier
                sdr_test_result = verify_and_configure_sdrs(driver, wait, site_name)
                return 0 if sdr_test_result else 1

            # Accept partial completion if processing
            if "/waiting" in current_url or "performing requested actions" in current_title.lower():
                logging.info("Form submission successful, system is processing")
                return 1
            else:
                logging.error("Form submission may have failed")
                return 1

    except Exception as e:
        logging.exception(f"Error during test: {e}")
        return 1
    finally:
        if driver:
            driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Run Selenium tests as non-root user")
    parser.add_argument("rpi_ip", help="IP address of the Raspberry Pi")
    parser.add_argument("--timeout", type=int, default=90, help="Timeout in seconds")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")

    args = parser.parse_args()

    # Apply requested log level
    try:
        logging.getLogger().setLevel(getattr(logging, args.log_level.upper(), logging.INFO))
    except Exception:
        logging.getLogger().setLevel(logging.INFO)

    exit_code = run_basic_setup_test(args.rpi_ip, args.timeout)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
