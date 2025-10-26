#!/usr/bin/env python3
"""
Selenium test runner - designed to run as non-root user (testuser).
This script is invoked by test-feeder-image.py via sudo -u testuser.
"""

import argparse
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager


def run_basic_setup_test(rpi_ip: str, timeout_seconds: int = 90) -> int:
    """
    Run basic setup test using Selenium.

    Returns:
        0 on success, 1 on failure
    """
    print(f"Testing basic setup on http://{rpi_ip}/setup...")
    print(f"Running as user: {Path.home()}")

    driver = None
    try:
        print("Starting Firefox browser...")

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

        print("✓ Firefox browser started successfully")

        wait = WebDriverWait(driver, 10)

        # Navigate to the feeder page
        driver.get(f"http://{rpi_ip}/setup")

        # Check page title
        print("Checking page title...")
        current_title = driver.title

        if "Basic Setup" not in current_title:
            print(f"✗ Wrong page title: {current_title}")
            return 1
        print(f"✓ Page title is correct ({current_title})")

        # Check CPU temperature
        print("Checking CPU temperature...")
        cpu_temp_block = wait.until(EC.presence_of_element_located((By.ID, "cpu_temp_block")))
        cpu_temp_element = cpu_temp_block.find_element(By.ID, "cpu_temp")
        temp_text = cpu_temp_element.text.strip()

        # Extract temperature value
        temp_value = float("".join(filter(lambda x: x.isdigit() or x == ".", temp_text)))

        if not (30 <= temp_value <= 85):
            print(f"✗ CPU temperature out of range: {temp_value}°C")
            return 1
        print(f"✓ CPU temperature is reasonable: {temp_value}°C")

        # Fill in site information
        print("Filling in site information...")

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

        print("✓ Site information filled")

        # Click ADSB checkbox
        print("Clicking ADSB checkbox...")
        adsb_checkbox = wait.until(EC.presence_of_element_located((By.ID, "is_adsb_feeder")))
        driver.execute_script("arguments[0].scrollIntoView(true);", adsb_checkbox)
        time.sleep(1)

        if not adsb_checkbox.is_selected():
            try:
                adsb_checkbox.click()
                print("✓ ADSB checkbox clicked")
            except Exception:
                driver.execute_script("arguments[0].click();", adsb_checkbox)
                print("✓ ADSB checkbox clicked via JavaScript")
        else:
            print("✓ ADSB checkbox was already checked")

        # Click submit button
        print("Looking for submit button...")
        submit_button = None

        submit_selectors = [
            "//button[@type='submit'][@name='submit'][@value='go']",
            "//button[@type='submit']",
        ]

        for selector in submit_selectors:
            try:
                submit_button = driver.find_element(By.XPATH, selector)
                print(f"✓ Found submit button")
                break
            except Exception:
                continue

        if not submit_button:
            print("✗ Could not find submit button")
            return 1

        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
        time.sleep(1)

        # Click submit
        try:
            submit_button.click()
            print("✓ Submit button clicked")
        except Exception:
            driver.execute_script("arguments[0].click();", submit_button)
            print("✓ Submit button clicked via JavaScript")

        # Wait for form submission flow
        print("Waiting for form submission to complete...")
        try:
            # Wait for redirect to /waiting
            print("  Step 1: Waiting for redirect...")
            WebDriverWait(driver, 60).until(lambda d: "/waiting" in d.current_url)
            print("✓ Form submitted - redirected to waiting page")

            # Wait for processing to complete
            print("  Step 2: Waiting for processing...")
            WebDriverWait(driver, 300).until(lambda d: "SDR Setup" in d.title)
            print("✓ Successfully reached SDR Setup page")
            return 0

        except TimeoutException:
            current_url = driver.current_url
            current_title = driver.title
            print(f"⚠ Did not complete flow within timeout")
            print(f"Current URL: {current_url}")
            print(f"Current title: {current_title}")

            # Accept partial completion
            if "/waiting" in current_url or "performing requested actions" in current_title.lower():
                print("✓ Form submission successful, system is processing")
                return 1
            else:
                print("✗ Form submission may have failed")
                return 1

    except Exception as e:
        print(f"✗ Error during test: {e}")
        return 1
    finally:
        if driver:
            driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Run Selenium tests as non-root user")
    parser.add_argument("rpi_ip", help="IP address of the Raspberry Pi")
    parser.add_argument("--timeout", type=int, default=90, help="Timeout in seconds")

    args = parser.parse_args()

    exit_code = run_basic_setup_test(args.rpi_ip, args.timeout)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
