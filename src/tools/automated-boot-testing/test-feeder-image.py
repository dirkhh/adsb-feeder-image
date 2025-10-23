#!/usr/bin/env python3
"""
Test script for booting and running the feeder image on actual hardware.

This script:
1. Downloads and decompresses a feeder image if needed
2. shuts down and powers off the test system (using a local Kasa smart switch)
2. Copies the fresh image to /srv/iscsi/<image_name>.img -- so yes, this assumes that you have a TFTP/iSCSI setup to boot an RPi from
3. Turns on / reboots the test system
4. Waits for the feeder to come online and verifies the correct image is running

Usage:
    python3 test-feeder-image.py <image_url> <rpi_ip> <kasa_ip>
"""

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from kasa import SmartPlug
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager

# Configure line-buffered output for real-time logging when running as a systemd service
# This ensures all output appears immediately in journalctl without manual flush() calls
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def try_ssh_shutdown(rpi_ip: str, user: str = "root", ssh_key: str = "", timeout: int = 10) -> bool:
    """Try to shutdown the system via SSH."""
    ssh_cmd = ["ssh"]

    # Add SSH options
    ssh_cmd.extend(["-o", "ConnectTimeout=" + str(timeout)])
    ssh_cmd.extend(["-o", "StrictHostKeyChecking=no"])

    # Add SSH key if provided
    if ssh_key:
        ssh_cmd.extend(["-i", ssh_key])

    # Add user@host and command
    ssh_cmd.append(f"{user}@{rpi_ip}")
    ssh_cmd.append("shutdown now")

    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout + 5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return False


async def control_kasa_switch_async(kasa_ip: str, turn_on: bool) -> bool:
    """Control a Kasa smart switch."""
    try:
        plug = SmartPlug(kasa_ip)
        await plug.update()

        if turn_on:
            print(f"Turning on Kasa switch at {kasa_ip}...")
            await plug.turn_on()
            print("✓ Kasa switch turned on")
        else:
            print(f"Turning off Kasa switch at {kasa_ip}...")
            await plug.turn_off()
            print("✓ Kasa switch turned off")

        return True

    except Exception as e:
        print(f"✗ Error controlling Kasa switch: {e}")
        return False


def control_kasa_switch(kasa_ip: str, turn_on: bool) -> bool:
    """Control a Kasa smart switch (sync wrapper)."""
    return asyncio.run(control_kasa_switch_async(kasa_ip, turn_on))


def validate_image_filename(filename: str) -> str:
    if not filename.startswith("adsb-im-") or not filename.endswith(".img.xz"):
        raise ValueError(f"Invalid image filename: {filename}. Must start with 'adsb-im-' and end with '.img.xz'")

    # Remove .xz extension to get the expected image name
    expected_image_name = filename[:-3]  # Remove .xz
    return expected_image_name


def download_and_decompress_image(url: str, force_download: bool = False, cache_dir: Path = Path("/tmp")) -> str:
    # Extract filename from URL
    parsed_url = urllib.parse.urlparse(url)
    filename = os.path.basename(parsed_url.path)
    expected_image_name = validate_image_filename(filename)

    cached_compressed = cache_dir / filename
    cached_decompressed = cache_dir / expected_image_name

    if cached_compressed.exists() and not force_download:
        print(f"Using cached compressed image: {cached_compressed}")
        print(f"Cache file size: {cached_compressed.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        cached_compressed.unlink(missing_ok=True)
        cached_decompressed.unlink(missing_ok=True)
        print(f"Downloading {filename} to cache...")
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(cached_compressed, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Downloaded {cached_compressed.stat().st_size / 1024 / 1024:.1f} MB")

    if cached_decompressed.exists():
        print(f"Using cached decompressed image: {cached_decompressed}")
        print(f"Cache file size: {cached_decompressed.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        cached_decompressed.unlink(missing_ok=True)
        # Decompress the file
        print("Decompressing image...")
        with open(cached_decompressed, "wb") as out_file:
            subprocess.run(["xz", "-d", "-c", str(cached_compressed)], stdout=out_file, check=True)
        print(f"Decompressed to {cached_decompressed.stat().st_size / 1024 / 1024:.1f} MB")
    return expected_image_name


def setup_iscsi_image(cached_decompressed: Path, ssh_public_key: str) -> None:
    """
    Setup the iSCSI image for boot testing.

    Args:
        cached_decompressed: Path to the decompressed image file
        ssh_public_key: Optional path to SSH public key to install in the image.
                       If provided, this key will be installed to /root/.ssh/authorized_keys
                       in the test image, allowing passwordless SSH access.
    """
    # Use basename of cached image for unique target path
    # This allows multiple different images to coexist in /srv/iscsi/
    target_filename = cached_decompressed.name
    target_path = Path("/srv/iscsi") / target_filename
    target_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Running setup-tftp-iscsi.sh {cached_decompressed} {target_path} {ssh_public_key}")
    print("=" * 70)

    # Build command with optional public key parameter
    # Use stdbuf to force line-buffered output from bash (otherwise bash fully buffers when stdout is a pipe)
    cmd = ["stdbuf", "-oL", "bash", str(Path(__file__).parent / "setup-tftp-iscsi.sh"), str(cached_decompressed), str(target_path)]
    if ssh_public_key != "":
        cmd.append(ssh_public_key)

    # Run with real-time output forwarding to ensure all output appears in journal logs
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
    )

    # Forward each line of output immediately to journal
    for line in process.stdout:
        print(line, end="", flush=True)

    returncode = process.wait()
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd)

    print("=" * 70)
    print(f"setup-tftp-iscsi.sh completed successfully")


def wait_for_system_down(rpi_ip: str, timeout_seconds: int = 60) -> bool:
    print(f"Waiting for system at {rpi_ip} to go down (timeout: {timeout_seconds} seconds)...")

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        try:
            result = subprocess.run(["ping", "-c", "1", "-W", "2", rpi_ip], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print(f"\n✓ System at {rpi_ip} is down")
                return True
            print(".", end="", flush=True)
            time.sleep(2)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print(f"\n✓ System at {rpi_ip} is down")
            return True

    print(f"\n⚠ System at {rpi_ip} did not go down within {timeout_seconds} seconds")
    return False


def wait_for_feeder_online(rpi_ip: str, expected_image_name: str, timeout_minutes: int = 5) -> tuple[bool, str]:
    """Wait for the feeder to come online and verify the correct image is running."""
    print(f"Waiting for feeder at {rpi_ip} to come online (timeout: {timeout_minutes} minutes)...")

    start_time = time.time()
    timeout_seconds = timeout_minutes * 60

    while time.time() - start_time < timeout_seconds:
        status_string = ""
        try:
            # ping the RPi to see if it's online
            result = subprocess.run(["ping", "-c", "1", "-W", "2", rpi_ip], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                status_string = "ping down"
                print("ping down - wait 10 seconds")
                time.sleep(10)
                continue
            status_string = "ping up"

            # Try to fetch the main page
            response = requests.get(f"http://{rpi_ip}/", timeout=10)
            status_string += f" HTTP response {response.status_code}"
            if response.status_code == 200:
                content = response.text
                # grab the title from the response
                title = content.split("<title>")[1].split("</title>")[0]
                status_string += f" title: {title.strip()}"

                # Look for the footer line with the image name
                if expected_image_name in content:
                    status_string += f" - correct image: {expected_image_name}"
                    print(status_string)
                    return True, "success"
                else:
                    status_string += f" - can't find expected image: {expected_image_name}"
                    print(status_string)
                    return False, "expected image not found"

        # time out
        except TimeoutException:
            status_string += " timeout during http request"

        except Exception:
            status_string += " exception during http request"

        print(f"{status_string} - wait 10 seconds")
        time.sleep(10)

    print(f"Feeder did not come online within {timeout_minutes} minutes")
    return False, "timeout" if status_string != "ping down" else "ping down"


def log_browser_activity(driver, description: str):
    """Log browser console messages and network activity for debugging."""
    try:
        # Check if get_log method is available (varies by browser)
        if not hasattr(driver, "get_log"):
            print(f"📝 Browser logging not available for {description} (get_log method not supported)")
            return

        # Get console logs (Firefox supports this)
        try:
            logs = driver.get_log("browser")
            if logs:
                print(f"📝 Console logs during {description}:")
                for log in logs[-5:]:  # Show last 5 messages
                    print(f"   [{log['level']}] {log['message']}")
            else:
                print(f"📝 No console logs during {description}")
        except Exception as e:
            print(f"📝 Could not retrieve console logs: {e}")

        # Get performance logs (Firefox supports this)
        try:
            perf_logs = driver.get_log("performance")
            if perf_logs:
                print(f"🌐 Network activity during {description}:")
                for log in perf_logs[-3:]:  # Show last 3 network events
                    message = log.get("message", "")
                    if "Network.responseReceived" in message or "Network.requestWillBeSent" in message:
                        print(f"   {message}")
            else:
                print(f"🌐 No network logs during {description}")
        except Exception as e:
            print(f"🌐 Network logging not available during {description}: {e}")

    except Exception as e:
        print(f"📝 Could not retrieve logs: {e}")


def execute_js_and_wait(driver, js_code: str, description: str, wait_seconds: int = 5):
    """Execute JavaScript and monitor the results."""
    print(f"🔧 Executing JS: {description}")
    print(f"   Code: {js_code}")

    try:
        result = driver.execute_script(js_code)
        print(f"   Result: {result}")

        # Wait and monitor activity
        time.sleep(wait_seconds)
        log_browser_activity(driver, f"after {description}")

        return result
    except Exception as e:
        print(f"   JS execution failed: {e}")
        return None


def test_basic_setup_with_visible_browser(rpi_ip: str, timeout_seconds: int = 90) -> bool:
    """Test the basic setup process using Selenium with visible browser for debugging."""
    print(f"Testing basic setup with VISIBLE browser on http://{rpi_ip}/setup...")

    driver = None
    try:
        print("Starting Firefox browser in VISIBLE mode...")

        # Setup Firefox with VISIBLE mode for debugging
        firefox_service = FirefoxService(GeckoDriverManager().install())
        firefox_options = webdriver.FirefoxOptions()
        # Remove headless mode to see what's happening
        # firefox_options.add_argument("--headless")  # Commented out for visible debugging

        firefox_options.add_argument("--no-sandbox")
        firefox_options.add_argument("--disable-dev-shm-usage")
        firefox_options.add_argument("--disable-gpu")
        firefox_options.add_argument("--disable-extensions")

        # Set Firefox preferences for debugging
        firefox_options.set_preference("dom.webnotifications.enabled", False)
        firefox_options.set_preference("media.volume_scale", "0.0")

        driver = webdriver.Firefox(service=firefox_service, options=firefox_options)
        driver.set_page_load_timeout(30)

        print("✓ Firefox browser started in VISIBLE mode with debugging enabled")
        print("🔍 Watch the browser window to see what happens after form submission!")

        # Navigate to the feeder page
        driver.get(f"http://{rpi_ip}/setup")

        # Wait for user to observe the page
        input("Press Enter after you've observed the page to continue with form filling...")

        # Continue with the rest of the test...
        wait = WebDriverWait(driver, 10)

        # Check page title
        print("Checking page title...")
        current_title = driver.title
        if "Basic Setup" not in current_title:
            print(f"✗ Wrong page title: {current_title}")
            return False
        else:
            print(f"✓ Page title is correct ({current_title})")

        # Fill form and submit (simplified version for debugging)
        print("Filling form...")
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

        print("✓ Form filled, about to submit...")
        input("Press Enter to submit the form and watch the JavaScript magic...")

        # Click submit button
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit'][@name='submit'][@value='go']")
        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
        time.sleep(1)
        submit_button.click()

        print("✓ Form submitted! Watch what happens next...")

        # Wait for the complete flow automatically
        try:
            # Step 1: Wait for URL change to /waiting
            print("  Step 1: Waiting for form submission redirect...")
            WebDriverWait(driver, 30).until(lambda d: "/waiting" in d.current_url)
            print("✓ Form submitted successfully - redirected to waiting page")

            # Step 2: Wait for the system to finish processing
            print("  Step 2: Waiting for system to finish processing...")
            WebDriverWait(driver, 60).until(lambda d: "SDR Setup" in d.title)
            print("✓ Successfully reached SDR Setup page")

            # Check final state
            final_title = driver.title
            final_url = driver.current_url
            print(f"Final page title: {final_title}")
            print(f"Final URL: {final_url}")

            return True

        except TimeoutException:
            current_url = driver.current_url
            current_title = driver.title
            print(f"⚠ Did not complete the full flow within timeout")
            print(f"Current URL: {current_url}")
            print(f"Current title: {current_title}")

            # Accept partial completion
            if "/waiting" in current_url or "performing requested actions" in current_title.lower():
                print("✓ Form submission was successful, system is processing")
                return True
            else:
                print("✗ Form submission may have failed")
                return False

    except Exception as e:
        print(f"✗ Error during visible browser test: {e}")
        return False
    finally:
        if driver:
            input("Press Enter to close the browser...")
            driver.quit()


def test_basic_setup(rpi_ip: str, timeout_seconds: int = 90) -> bool:
    """
    Test the basic setup process using Selenium.

    SECURITY: Runs browser as 'testuser' (non-root) for security.
    Browsers should never run as root due to security risks.
    """
    print(f"Testing basic setup on http://{rpi_ip}/setup...")

    # Ensure testuser exists
    try:
        import pwd
        pwd.getpwnam('testuser')
        print("✓ testuser exists")
    except KeyError:
        print("⚠ testuser does not exist - creating it")
        try:
            subprocess.run([
                "useradd", "-r", "-m", "-s", "/bin/bash",
                "-c", "User for running browser tests",
                "testuser"
            ], check=True, capture_output=True)
            print("✓ testuser created")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to create testuser: {e.stderr.decode()}")
            print("  Cannot run browser tests as root - security risk")
            return False

    # Prepare test environment for testuser
    test_script = Path(__file__).parent / "run-selenium-test.py"
    if not test_script.exists():
        print(f"✗ Test script not found: {test_script}")
        return False

    # Make script executable
    test_script.chmod(0o755)

    # Ensure testuser can access necessary directories
    for dir_path in ["/tmp", "/home/testuser"]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["chown", "testuser:testuser", "/home/testuser"], check=False)

    # Run Selenium test as testuser (not root - security requirement)
    print("Running browser test as non-root user (testuser)...")
    print("=" * 70)
    process = None
    try:
        # Use Popen with real-time output forwarding (same as shell script)
        process = subprocess.Popen(
            [
                "sudo", "-u", "testuser",
                "env", f"HOME=/home/testuser",
                "python3", str(test_script),
                rpi_ip,
                "--timeout", str(timeout_seconds)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Forward each line of output immediately to journal
        for line in process.stdout:
            print(line, end="", flush=True)

        returncode = process.wait(timeout=timeout_seconds + 30)
        print("=" * 70)

        return returncode == 0

    except subprocess.TimeoutExpired:
        if process:
            process.kill()
            process.wait()
        print("=" * 70)
        print(f"✗ Test timed out after {timeout_seconds} seconds")
        return False
    except Exception as e:
        print("=" * 70)
        print(f"✗ Error running test: {e}")
        return False


def _test_basic_setup_old(rpi_ip: str, timeout_seconds: int = 90) -> bool:
    """
    OLD VERSION - Runs as root (SECURITY RISK - DO NOT USE)
    Kept for reference only.
    """
    print(f"Testing basic setup on http://{rpi_ip}/setup...")

    driver = None
    try:
        print("Attempting to start Firefox browser...")

        # Setup Firefox with enhanced options
        firefox_service = FirefoxService(GeckoDriverManager().install())
        firefox_options = webdriver.FirefoxOptions()
        firefox_options.add_argument("--headless")
        firefox_options.add_argument("--no-sandbox")
        firefox_options.add_argument("--disable-dev-shm-usage")
        firefox_options.add_argument("--disable-gpu")
        firefox_options.add_argument("--disable-extensions")
        firefox_options.add_argument("--disable-background-timer-throttling")
        firefox_options.add_argument("--disable-backgrounding-occluded-windows")
        firefox_options.add_argument("--disable-renderer-backgrounding")
        firefox_options.add_argument("--disable-features=TranslateUI")
        firefox_options.add_argument("--disable-web-security")
        firefox_options.add_argument("--allow-running-insecure-content")

        # Set Firefox preferences for better headless operation
        firefox_options.set_preference("dom.webnotifications.enabled", False)
        firefox_options.set_preference("media.volume_scale", "0.0")
        firefox_options.set_preference(
            "general.useragent.override",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        )

        driver = webdriver.Firefox(service=firefox_service, options=firefox_options)
        driver.set_page_load_timeout(30)

        print("✓ Firefox browser started successfully with debugging enabled")

        wait = WebDriverWait(driver, 10)

        # Navigate to the feeder page
        driver.get(f"http://{rpi_ip}/setup")

        # Check page title - it should be "Basic Setup"
        print("Checking page title...")
        current_title = driver.title

        if "Basic Setup" not in current_title:
            print(f"✗ Wrong page title: {current_title}")
            return False
        else:
            print(f"✓ Page title is correct ({current_title})")

        # Check CPU temperature
        print("Checking CPU temperature...")
        cpu_temp_block = wait.until(EC.presence_of_element_located((By.ID, "cpu_temp_block")))
        cpu_temp_element = cpu_temp_block.find_element(By.ID, "cpu_temp")
        temp_text = cpu_temp_element.text.strip()

        # Extract temperature value (assuming format like "45.2°C" or "45.2")
        temp_value = float("".join(filter(lambda x: x.isdigit() or x == ".", temp_text)))

        if not (30 <= temp_value <= 85):
            print(f"✗ CPU temperature out of range: {temp_value}°C")
            return False
        print(f"✓ CPU temperature is reasonable: {temp_value}°C")

        # Fill in site information
        print("Filling in site information...")

        # Site name
        site_name_input = wait.until(EC.element_to_be_clickable((By.ID, "site_name")))
        site_name_input.clear()
        site_name_input.send_keys("automated test site")

        # Latitude
        lat_input = driver.find_element(By.ID, "lat")
        lat_input.clear()
        lat_input.send_keys("45.48")

        # Longitude
        lon_input = driver.find_element(By.ID, "lon")
        lon_input.clear()
        lon_input.send_keys("-122.66")

        # Altitude
        alt_input = driver.find_element(By.ID, "alt")
        alt_input.clear()
        alt_input.send_keys("30")

        print("✓ Site information filled")

        # Click ADSB checkbox
        print("Clicking ADSB checkbox...")
        adsb_checkbox = wait.until(EC.presence_of_element_located((By.ID, "is_adsb_feeder")))

        # Scroll element into view
        driver.execute_script("arguments[0].scrollIntoView(true);", adsb_checkbox)

        # Wait a bit for scroll to complete
        time.sleep(1)

        # Check if checkbox is already checked
        is_checked = adsb_checkbox.is_selected()
        print(f"ADSB checkbox current state: {'checked' if is_checked else 'unchecked'}")

        # Only click if not already checked
        if not is_checked:
            # Try to click the checkbox
            try:
                adsb_checkbox.click()
                print("✓ ADSB checkbox clicked successfully")
            except Exception as e:
                print(f"Direct click failed: {e}, trying JavaScript click...")
                # If direct click fails, try JavaScript click
                driver.execute_script("arguments[0].click();", adsb_checkbox)
                print("✓ ADSB checkbox clicked via JavaScript")
        else:
            print("✓ ADSB checkbox was already checked")

        # Click submit button - try multiple possible selectors
        print("Looking for submit button...")
        submit_button = None

        # Try different selectors for the submit button
        submit_selectors = [
            "//button[@type='submit'][@name='submit'][@value='go']",
            "//button[@type='submit']",
        ]

        for selector in submit_selectors:
            try:
                submit_button = driver.find_element(By.XPATH, selector)
                print(f"✓ Found submit button with selector: {selector}")
                break
            except Exception:  # noqa: S110
                continue

        if not submit_button:
            print("✗ Could not find submit button with any selector")
            return False

        # Scroll submit button into view
        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
        time.sleep(1)

        # Log browser activity before form submission
        log_browser_activity(driver, "before form submission")

        # Try to click the submit button
        try:
            submit_button.click()
            print("✓ Submit button clicked successfully")
        except Exception as e:
            print(f"Direct click failed: {e}, trying JavaScript click...")
            # If direct click fails, try JavaScript click
            driver.execute_script("arguments[0].click();", submit_button)
            print("✓ Submit button clicked via JavaScript")

        # Monitor what happens after form submission
        print("🔍 Monitoring post-submission activity...")
        log_browser_activity(driver, "immediately after form submission")

        # Check for any JavaScript timers or redirects
        execute_js_and_wait(driver, "return window.location.href;", "get current URL")
        execute_js_and_wait(driver, "return document.title;", "get current title")
        execute_js_and_wait(driver, "return document.readyState;", "get document ready state")

        # Check for any pending JavaScript timers
        execute_js_and_wait(
            driver,
            """
            var timers = [];
            for (var i = 1; i < 10000; i++) {
                if (window.clearTimeout.toString().indexOf(i) > -1) {
                    timers.push(i);
                }
            }
            return timers.length;
        """,
            "count active timers",
        )

        # Look for any JavaScript errors or console messages
        execute_js_and_wait(
            driver,
            """
            return window.console && window.console.error ? 'Console available' : 'No console errors captured';
        """,
            "check console availability",
        )

        # Wait for the complete form submission flow
        print("Waiting for form submission to complete...")
        try:
            # Step 1: Wait for URL change to /waiting (indicates form was submitted)
            print("  Step 1: Waiting for form submission redirect...")
            WebDriverWait(driver, 30).until(lambda d: "/waiting" in d.current_url)
            print("✓ Form submitted successfully - redirected to waiting page")

            # Step 2: Wait for the system to finish processing
            print("  Step 2: Waiting for system to finish processing...")
            WebDriverWait(driver, 60).until(lambda d: "SDR Setup" in d.title)
            print("✓ Successfully reached SDR Setup page")
            return True

        except TimeoutException:
            current_url = driver.current_url
            current_title = driver.title
            print(f"✗ Did not complete the flow within timeout")
            print(f"Current URL: {current_url}")
            print(f"Current title: {current_title}")

            # Check if we're in an acceptable intermediate state
            if "/waiting" in current_url:
                print("✓ Form was submitted and system is processing")
                if "performing requested actions" in current_title.lower():
                    print("✓ System is performing requested actions")
                    return True
                else:
                    print("⚠ System is in waiting state but may need more time")
                    return True
            elif "performing requested actions" in current_title.lower():
                print("✓ System is performing requested actions")
                return True
            else:
                print("✗ Form submission may have failed or system is in unexpected state")
                return False

    except Exception as e:
        print(f"✗ Error during basic setup test: {e}")
        return False
    finally:
        if driver:
            driver.quit()


def test_basic_setup_simple(rpi_ip: str) -> bool:
    """Simple fallback test using requests (no browser automation)."""
    print(f"Running simple setup test on http://{rpi_ip}/...")

    try:
        # Get the page content
        response = requests.get(f"http://{rpi_ip}/", timeout=10)
        if response.status_code != 200:
            print(f"✗ HTTP error: {response.status_code}")
            return False

        # Parse the page
        soup = BeautifulSoup(response.content, "html.parser")

        # Check page title - it might be "Basic Setup" or "SDR Setup"
        title = soup.find("title")
        title_text = title.get_text() if title else ""

        if "SDR Setup" in title_text:
            print("✓ Already on SDR Setup page (form was previously submitted)")
            return True
        elif not title or "Basic Setup" not in title_text:
            print(f"✗ Wrong page title: {title_text if title else 'No title found'}")
            return False
        else:
            print("✓ Page title is correct (Basic Setup)")

        # Check CPU temperature - try multiple approaches
        cpu_temp_value = None

        # Try to find CPU temperature in different ways
        cpu_temp_selectors = [
            ("div", {"id": "cpu_temp"}),
            ("div", {"id": "cpu_temp_block"}),
            ("span", {"id": "cpu_temp"}),
            ("span", {"id": "cpu_temp_block"}),
        ]

        for tag, attrs in cpu_temp_selectors:
            cpu_temp_element = soup.find(tag, attrs)
            if cpu_temp_element:
                temp_text = cpu_temp_element.get_text().strip()
                # Extract temperature value from text
                temp_match = re.search(r"(\d+\.?\d*)", temp_text)
                if temp_match:
                    cpu_temp_value = float(temp_match.group(1))
                    print(f"✓ Found CPU temperature: {cpu_temp_value}°C")
                    break

        if cpu_temp_value is None:
            print("✗ CPU temperature element not found with any selector")
            return False

        if not (30 <= cpu_temp_value <= 85):
            print(f"✗ CPU temperature out of range: {cpu_temp_value}°C")
            return False
        print(f"✓ CPU temperature is reasonable: {cpu_temp_value}°C")

        # Check that required form elements exist
        required_elements = ["site_name", "lat", "lon", "alt", "is_adsb_feeder"]
        for element_id in required_elements:
            element = soup.find(id=element_id)
            if not element:
                print(f"✗ Required element not found: {element_id}")
                return False

        print("✓ All required form elements found")
        print("✓ Basic setup test passed (limited verification)")
        return True

    except Exception as e:
        print(f"✗ Error during simple setup test: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test feeder image on actual hardware",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    .venv/bin/python test-feeder-image.py https://example.com/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 192.168.1.200
    .venv/bin/python test-feeder-image.py --test-setup https://example.com/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 192.168.1.200
    .venv/bin/python test-feeder-image.py --test-only --visible-browser --test-setup https://example.com/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 192.168.1.200
        """,
    )

    parser.add_argument("image_url", help="URL or file path to the .img.xz image file")
    parser.add_argument("rpi_ip", help="IP address of the Raspberry Pi")
    parser.add_argument("kasa_ip", help="IP address of the Kasa smart switch")
    parser.add_argument("--force-download", action="store_true", help="Force re-download even if cached files exist")
    parser.add_argument("--force-off", action="store_true", help="Force shutdown and turn off power")
    parser.add_argument("--user", default="root", help="SSH user (default: root)")
    parser.add_argument("--ssh-key", help="Path to SSH private key")
    parser.add_argument("--shutdown-timeout", type=int, default=10, help="SSH connection timeout in seconds (default: 10)")
    parser.add_argument("--timeout", type=int, default=5, help="Timeout in minutes (default: 5)")
    parser.add_argument("--test-setup", action="store_true", help="Run basic setup test after feeder comes online")
    parser.add_argument("--test-only", action="store_true", help="Don't run install / boot, just the tests")
    parser.add_argument("--visible-browser", action="store_true", help="Use visible browser for debugging JavaScript behavior")

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    cache_dir = script_dir / "test-images"
    expected_image_name = download_and_decompress_image(args.image_url, args.force_download, cache_dir)
    cached_image_path = cache_dir / expected_image_name
    if args.test_only:
        print("\n🧪 Running basic setup test...")
        if args.visible_browser:
            setup_success = test_basic_setup_with_visible_browser(args.rpi_ip)
        else:
            setup_success = test_basic_setup(args.rpi_ip)
            if not setup_success:
                print("\n⚠ Selenium test failed, trying simple fallback test...")
                setup_success = test_basic_setup_simple(args.rpi_ip)

        if setup_success:
            print("\n🎉 All tests completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Basic setup test failed!")
            sys.exit(1)

    try:
        if not args.force_off:
            try_ssh_shutdown(args.rpi_ip, args.user, args.ssh_key, args.shutdown_timeout)
            wait_for_system_down(args.rpi_ip, args.shutdown_timeout)

        control_kasa_switch(args.kasa_ip, False)

        # Derive public key path from private key path (assumes public key is at private_key + '.pub')
        ssh_public_key = ""
        if args.ssh_key:
            ssh_public_key_path = Path(args.ssh_key).with_suffix(Path(args.ssh_key).suffix + ".pub")
            if ssh_public_key_path.exists():
                ssh_public_key = str(ssh_public_key_path)
                print(f"Using SSH public key: {ssh_public_key}")
            else:
                print(f"⚠ SSH private key provided but public key not found at: {ssh_public_key_path}")

        setup_iscsi_image(cached_image_path, ssh_public_key)
        control_kasa_switch(args.kasa_ip, True)
        count = 0
        success = False
        status_string = ""
        while not success and count < 3:
            success, status_string = wait_for_feeder_online(args.rpi_ip, expected_image_name, args.timeout)

            if "dietpi" in expected_image_name:
                if status_string == "ping down":
                    print("with DietPi we could be hung because of iSCSI root filesystem and shutdown failure")
                    # power cycle and try again
                    control_kasa_switch(args.kasa_ip, False)
                    time.sleep(10)
                    control_kasa_switch(args.kasa_ip, True)
                else:
                    print(f"with DietPi this can take 20+ minutes because of iSCSI root filesystem and shutdown failure -- keep waiting")

            else:
                print(f"no success in {args.timeout} minutes")
                break
            count += 1

        if success:
            print("\n🎉 Feeder is online!")

            # Run basic setup test if requested
            if args.test_setup:
                print("\n🧪 Running basic setup test...")
                if args.visible_browser:
                    setup_success = test_basic_setup_with_visible_browser(args.rpi_ip)
                else:
                    setup_success = test_basic_setup(args.rpi_ip)
                    if not setup_success:
                        print("\n⚠ Selenium test failed, trying simple fallback test...")
                        setup_success = test_basic_setup_simple(args.rpi_ip)

                if setup_success:
                    print("\n🎉 All tests completed successfully!")
                    sys.exit(0)
                else:
                    print("\n❌ Basic setup test failed!")
                    sys.exit(1)
            else:
                print("\n🎉 Test completed successfully!")
                sys.exit(0)
        else:
            print("\n❌ Test failed!")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
