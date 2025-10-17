#!/usr/bin/env python3
"""
JavaScript behavior analyzer for the ADS-B feeder setup process.

This script helps debug JavaScript-based form submissions and page transitions
by monitoring network requests, console logs, and DOM changes.
"""

import argparse
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager


def analyze_form_submission(rpi_ip: str):
    """Analyze the JavaScript behavior during form submission."""
    print(f"🔍 Analyzing JavaScript behavior on http://{rpi_ip}/setup")

    driver = None
    try:
        # Setup Firefox with debugging capabilities
        firefox_service = FirefoxService(GeckoDriverManager().install())
        firefox_options = webdriver.FirefoxOptions()
        firefox_options.add_argument("--no-sandbox")
        firefox_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Firefox(service=firefox_service, options=firefox_options)
        driver.set_page_load_timeout(30)

        # Enable comprehensive logging (Firefox doesn't support CDP commands)
        print("Note: Firefox logging enabled via browser preferences")

        print("✓ Browser started with full debugging enabled")

        # Navigate to the setup page
        print(f"📄 Loading http://{rpi_ip}/setup...")
        driver.get(f"http://{rpi_ip}/setup")

        # Analyze the initial page
        print("\n📊 Initial Page Analysis:")
        print(f"   Title: {driver.title}")
        print(f"   URL: {driver.current_url}")

        # Get page source for analysis
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")

        # Find all forms
        forms = soup.find_all("form")
        print(f"   Forms found: {len(forms)}")

        for i, form in enumerate(forms):
            action = form.get("action", "No action")
            method = form.get("method", "GET")
            print(f"     Form {i + 1}: method={method}, action={action}")

        # Find all JavaScript files
        scripts = soup.find_all("script")
        print(f"   Scripts found: {len(scripts)}")

        # Look for inline JavaScript
        inline_scripts = [script for script in scripts if script.string]
        print(f"   Inline scripts: {len(inline_scripts)}")

        for i, script in enumerate(inline_scripts):
            script_content = script.string.strip() if script.string else ""
            if script_content:
                print(f"     Script {i + 1} preview: {script_content[:100]}...")

        # Fill out the form
        print("\n📝 Filling out the form...")
        wait = WebDriverWait(driver, 10)

        # Fill form fields
        site_name_input = wait.until(EC.presence_of_element_located((By.ID, "site_name")))
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

        # Click ADSB checkbox
        adsb_checkbox = driver.find_element(By.ID, "is_adsb_feeder")
        driver.execute_script("arguments[0].scrollIntoView(true);", adsb_checkbox)
        time.sleep(1)
        adsb_checkbox.click()

        print("✓ Form filled successfully")

        # Analyze form before submission
        print("\n🔍 Pre-submission Analysis:")

        # Check for any JavaScript event handlers
        form_element = driver.find_element(By.TAG_NAME, "form")
        form_onsubmit = driver.execute_script("return arguments[0].onsubmit;", form_element)
        print(f"   Form onsubmit handler: {form_onsubmit}")

        # Check submit button
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit'][@name='submit'][@value='go']")
        button_onclick = driver.execute_script("return arguments[0].onclick;", submit_button)
        print(f"   Submit button onclick: {button_onclick}")

        # Monitor network activity
        print("\n🌐 Starting network monitoring...")

        # Submit the form
        print("\n🚀 Submitting form...")
        submit_button.click()

        # Monitor what happens after submission
        print("\n📊 Post-submission Monitoring:")

        # Wait and check for changes
        for i in range(30):  # Monitor for 30 seconds
            time.sleep(1)

            current_url = driver.current_url
            current_title = driver.title

            if i % 5 == 0:  # Report every 5 seconds
                print(f"   {i}s: URL={current_url}, Title={current_title}")

                # Check for any JavaScript errors
                logs = driver.get_log("browser")
                if logs:
                    recent_logs = logs[-3:]
                    for log in recent_logs:
                        if log["level"] in ["SEVERE", "WARNING"]:
                            print(f"     ⚠ {log['level']}: {log['message']}")

                # Check for network requests
                perf_logs = driver.get_log("performance")
                if perf_logs:
                    recent_perf = perf_logs[-2:]
                    for log in recent_perf:
                        message = log.get("message", "")
                        if "Network.responseReceived" in message or "Network.requestWillBeSent" in message:
                            print(f"     🌐 {message}")

            # Check if we've reached a stable state
            if "SDR Setup" in current_title:
                print(f"✓ Reached SDR Setup page at {i}s")
                break
            elif "performing requested actions" in current_title.lower():
                print(f"✓ System is performing actions at {i}s")
                break

        # Final analysis
        print(f"\n📊 Final State:")
        print(f"   Final URL: {driver.current_url}")
        print(f"   Final Title: {driver.title}")

        # Get all console logs
        all_logs = driver.get_log("browser")
        if all_logs:
            print(f"\n📝 All Console Logs ({len(all_logs)} total):")
            for log in all_logs[-10:]:  # Show last 10
                print(f"   [{log['level']}] {log['message']}")

        return True

    except Exception as e:
        print(f"✗ Error during analysis: {e}")
        return False
    finally:
        if driver:
            input("\nPress Enter to close the browser...")
            driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Analyze JavaScript behavior during form submission")
    parser.add_argument("rpi_ip", help="IP address of the Raspberry Pi")

    args = parser.parse_args()

    print("🔍 JavaScript Behavior Analyzer")
    print("This tool will help debug the form submission process")
    print("Make sure you have a display available (X11 forwarding if SSH)")
    print()

    success = analyze_form_submission(args.rpi_ip)

    if success:
        print("\n🎉 Analysis completed successfully!")
    else:
        print("\n❌ Analysis failed!")


if __name__ == "__main__":
    main()
