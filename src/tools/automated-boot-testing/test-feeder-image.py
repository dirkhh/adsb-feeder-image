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
    python3 test-feeder-image.py <image_url> <rpi_ip> <power_toggle_script>
"""

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
from metrics import TestMetrics  # type: ignore # noqa: E402
from selenium.common.exceptions import TimeoutException
from serial_console_reader import SerialConsoleReader  # type: ignore # noqa: E402

# Configure line-buffered output for real-time logging when running as a systemd service
# This ensures all output appears immediately in journalctl without manual flush() calls
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr,attr-defined]
sys.stderr.reconfigure(line_buffering=True)  # type: ignore[union-attr,attr-defined]


def update_metrics_stage(metrics_id: int, metrics_db: str, stage: str, status: str):
    """Update metrics stage if metrics tracking is enabled."""
    if metrics_id is None:
        return

    try:
        metrics = TestMetrics(db_path=metrics_db)
        metrics.update_stage(metrics_id, stage, status)
    except Exception as e:
        print(f"⚠️  Failed to update metrics: {e}")


def save_serial_log(serial_reader, metrics_id: Optional[int] = None, script_dir: Optional[Path] = None):
    """Save serial console log to file on test failure."""
    if not serial_reader or not serial_reader.is_running():
        return

    try:
        # Create logs directory if needed
        log_dir = script_dir / "serial-logs" if script_dir else Path("serial-logs")
        log_dir.mkdir(exist_ok=True)

        # Generate log filename with metrics ID if available
        if metrics_id:
            log_file = log_dir / f"serial-console-test-{metrics_id}.log"
        else:
            import time

            timestamp = int(time.time())
            log_file = log_dir / f"serial-console-{timestamp}.log"

        # Save the log
        if serial_reader.save_to_file(str(log_file)):
            print(f"📝 Serial console log saved to: {log_file}")
        else:
            print(f"⚠️  Failed to save serial console log")

    except Exception as e:
        print(f"⚠️  Error saving serial log: {e}")


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


def power_toggle(script_path: str, turn_on: bool) -> bool:
    """
    Toggle power using external script.

    Args:
        script_path: Path to power toggle script
        turn_on: True to turn on, False to turn off

    Returns:
        True on success, False on failure
    """
    action = "on" if turn_on else "off"
    base_dir = Path(__file__).parent
    python_venv = base_dir / "venv/bin/python3"
    process: Optional[subprocess.Popen] = None
    try:
        # Use Popen for real-time output forwarding to systemd journal
        process = subprocess.Popen(
            [str(python_venv), script_path, action],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Forward output in real-time to journal
        if process.stdout:
            for line in process.stdout:
                print(line, end="", flush=True)

        # Wait for process to complete with timeout
        returncode = process.wait(timeout=30)

        if returncode == 0:
            return True
        else:
            print(f"Power toggle script failed with exit code {returncode}")
            return False

    except subprocess.TimeoutExpired:
        if process:
            process.kill()
            process.wait()
        print(f"Power toggle script timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"Error running power toggle script: {e}")
        return False


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
    cmd = [
        "stdbuf",
        "-oL",
        "bash",
        str(Path(__file__).parent / "setup-tftp-iscsi.sh"),
        str(cached_decompressed),
        str(target_path),
    ]
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
    if process and process.stdout:
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


def show_serial_context(serial_reader, num_lines: int = 3):
    """Show the last N lines from serial console for debugging."""
    if not serial_reader or not serial_reader.is_running():
        return

    try:
        recent_lines = serial_reader.get_recent(num_lines)
        if recent_lines:
            print(f"  Serial console (last {len(recent_lines)} lines):")
            for line in recent_lines:
                print(f"    {line}")
    except Exception as e:
        print(f"  (Could not read serial console: {e})")


def wait_for_feeder_online(
    rpi_ip: str, expected_image_name: str, timeout_minutes: int = 5, serial_reader=None
) -> tuple[bool, str]:
    """Wait for the feeder to come online and verify the correct image is running."""
    print(f"Waiting for feeder at {rpi_ip} to come online (timeout: {timeout_minutes} minutes)...")

    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    watching_first_boot = -1
    status_string: str = ""
    while time.time() - start_time < timeout_seconds:
        status_string = ""
        try:
            # ping the RPi to see if it's online
            result = subprocess.run(["ping", "-c", "1", "-W", "2", rpi_ip], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                status_string = "ping down"
                # let's check if the serial console data indicates a hang during shutdown
                if serial_reader:
                    # Patterns indicating shutdown hangs or failures
                    # Add new patterns here as they are discovered
                    shutdown_hang_patterns = [
                        "Failed to send WATCHDOG",
                        "Syncing filesystems and block devices - timed out, issuing SIGKILL",
                        "rejecting I/O to offline device",
                        "Failed to execute shutdown binary",
                    ]
                    # Combine into single regex pattern (escape special chars for literal matching)
                    pattern = "|".join(re.escape(p) for p in shutdown_hang_patterns)

                    # Use start_from_last=True to only check new serial data since last poll
                    if serial_reader.search_recent(pattern, max_lines=15, regex=True):
                        status_string += " - hang during shutdown"
                        print(status_string)
                        return False, status_string
                print("ping down - wait 10 seconds")
                show_serial_context(serial_reader)
                if watching_first_boot >= 0:
                    watching_first_boot += 1
                    if watching_first_boot > 10:
                        return False, "ping down"
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
                elif "boot of ADS-B Feeder System" in title:
                    if watching_first_boot < 0:
                        watching_first_boot = 0
                else:
                    status_string += f" - can't find expected image: {expected_image_name}"
                    print(status_string)
                    return False, "expected image not found"

        # time out
        except TimeoutException:
            status_string += " timeout during http request"

        except Exception:
            status_string += " exception during http request"
            if serial_reader and serial_reader.search_recent("iSCSI driver not found", 15):
                # oops, the initramdisk is missing iSCSI, let's rebuild the image
                status_string += " - iSCSI driver not found"
                print(status_string)
                return False, status_string

        print(f"{status_string} - wait 10 seconds")
        show_serial_context(serial_reader)
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

        pwd.getpwnam("testuser")
        print("✓ testuser exists")
    except KeyError:
        print("⚠ testuser does not exist - creating it")
        try:
            subprocess.run(
                ["useradd", "-r", "-m", "-s", "/bin/bash", "-c", "User for running browser tests", "testuser"],
                check=True,
                capture_output=True,
            )
            print("✓ testuser created")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to create testuser: {e.stderr.decode()}")
            print("  Cannot run browser tests as root - security risk")
            return False

    # Prepare test environment for testuser
    base_dir = Path(__file__).parent
    test_script = base_dir / "run-selenium-test.py"
    if not test_script.exists():
        print(f"✗ Test script not found: {test_script}")
        return False

    # Run Selenium test as testuser (not root - security requirement)
    print("Running browser test as non-root user (testuser)...")
    print("=" * 70)
    process = None
    try:
        # Use Popen with real-time output forwarding (same as shell script)
        process = subprocess.Popen(
            [
                "sudo",
                "-u",
                "testuser",
                "env",
                f"HOME=/home/testuser",
                f"{base_dir}/venv/bin/python3",
                str(test_script),
                rpi_ip,
                "--timeout",
                str(timeout_seconds),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Forward each line of output immediately to journal
        if process and process.stdout:
            for line in process.stdout:
                print(line, end="", flush=True)
        else:
            print("No output from process")

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


def main():
    parser = argparse.ArgumentParser(
        description="Test feeder image on actual hardware",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    .venv/bin/python test-feeder-image.py https://example.com/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 /opt/adsb-boot-test/power-toggle-kasa.py
    .venv/bin/python test-feeder-image.py --test-setup https://example.com/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 /opt/adsb-boot-test/power-toggle-kasa.py
    .venv/bin/python test-feeder-image.py --test-only --visible-browser --test-setup https://example.com/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 /opt/adsb-boot-test/power-toggle-kasa.py
        """,
    )

    parser.add_argument("image_url", help="URL or file path to the .img.xz image file")
    parser.add_argument("rpi_ip", help="IP address of the Raspberry Pi")
    parser.add_argument("power_toggle_script", help="Path to power toggle script")
    parser.add_argument("--force-download", action="store_true", help="Force re-download even if cached files exist")
    parser.add_argument("--force-off", action="store_true", help="Force shutdown and turn off power")
    parser.add_argument("--user", default="root", help="SSH user (default: root)")
    parser.add_argument("--ssh-key", help="Path to SSH private key")
    parser.add_argument("--shutdown-timeout", type=int, default=20, help="SSH connection timeout in seconds (default: 20)")
    parser.add_argument("--timeout", type=int, default=5, help="Timeout in minutes (default: 5)")
    parser.add_argument("--test-setup", action="store_true", help="Run basic setup test after feeder comes online")
    parser.add_argument("--metrics-id", type=int, help="Metrics test ID for tracking progress")
    parser.add_argument("--metrics-db", default="/var/lib/adsb-boot-test/metrics.db", help="Path to metrics database")
    parser.add_argument(
        "--serial-console", default="", help="Path to serial console device (e.g., /dev/ttyUSB0), empty to disable"
    )
    parser.add_argument("--serial-baud", type=int, default=115200, help="Serial console baud rate (default: 115200)")
    parser.add_argument(
        "--log-all-serial", action="store_true", help="Save serial console logs for all tests (not just failures)"
    )

    args = parser.parse_args()

    # Start serial console reader if configured
    serial_reader = None
    script_dir = Path(__file__).parent
    if args.serial_console:
        # Determine log file path if real-time logging is enabled
        realtime_log_file = None
        if args.log_all_serial:
            log_dir = script_dir / "serial-logs"
            log_dir.mkdir(exist_ok=True)
            if args.metrics_id:
                realtime_log_file = str(log_dir / f"serial-console-test-{args.metrics_id}.log")
            else:
                timestamp = int(time.time())
                realtime_log_file = str(log_dir / f"serial-console-{timestamp}.log")

        serial_reader = SerialConsoleReader(
            device_path=args.serial_console,
            baud_rate=args.serial_baud,
            log_prefix=f"serial-{args.metrics_id}" if args.metrics_id else "serial",
            realtime_log_file=realtime_log_file,
        )
        if serial_reader.start():
            print(f"✓ Serial console monitoring enabled: {args.serial_console}")
            if realtime_log_file:
                print(f"✓ Real-time serial logging to: {realtime_log_file}")
        else:
            print(f"⚠️  Serial console monitoring failed to start")
            serial_reader = None
    cache_dir = script_dir / "test-images"
    expected_image_name = download_and_decompress_image(args.image_url, args.force_download, cache_dir)
    cached_image_path = cache_dir / expected_image_name

    # Update metrics: download stage completed
    update_metrics_stage(args.metrics_id, args.metrics_db, "download", "passed")

    try:
        if not args.force_off:
            try_ssh_shutdown(args.rpi_ip, args.user, args.ssh_key, args.shutdown_timeout)
            wait_for_system_down(args.rpi_ip, args.shutdown_timeout)

        power_toggle(args.power_toggle_script, False)

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

        # Update metrics: boot stage starting
        update_metrics_stage(args.metrics_id, args.metrics_db, "boot", "running")

        power_toggle(args.power_toggle_script, True)
        count = 0
        success = False
        status_string = ""
        while not success and count < 3:
            success, status_string = wait_for_feeder_online(args.rpi_ip, expected_image_name, args.timeout, serial_reader)
            if success:
                break

            if "iSCSI driver not found" in status_string:
                print("iSCSI driver not found, rebuilding image")
                # power cycle, recreate the image from the compressed original, and try again
                power_toggle(args.power_toggle_script, False)
                cached_image_path.unlink()
                expected_image_name = download_and_decompress_image(args.image_url, False, cache_dir)
                cached_image_path = cache_dir / expected_image_name
                setup_iscsi_image(cached_image_path, ssh_public_key)
                power_toggle(args.power_toggle_script, True)
                time.sleep(10)
                continue

            if "dietpi" in expected_image_name:
                if "ping down" in status_string:
                    print("with DietPi we could be hung because of iSCSI root filesystem and shutdown failure")
                    # power cycle and try again
                    power_toggle(args.power_toggle_script, False)
                    time.sleep(10)
                    power_toggle(args.power_toggle_script, True)
                    time.sleep(20)  # give it time to boot and iSCSI to be initialized
                else:
                    print(
                        f"with DietPi this can take 20+ minutes because of iSCSI root filesystem and shutdown failure -- keep waiting"
                    )

            else:
                print(f"no success in {args.timeout} minutes")
                break
            count += 1

        if success:
            print("\n🎉 Feeder is online!")

            # Update metrics: boot and network stages passed
            update_metrics_stage(args.metrics_id, args.metrics_db, "boot", "passed")
            update_metrics_stage(args.metrics_id, args.metrics_db, "network", "passed")

            # Run basic setup test if requested
            if args.test_setup:
                print("\n🧪 Running basic setup test...")

                # Update metrics: browser_test stage starting
                update_metrics_stage(args.metrics_id, args.metrics_db, "browser_test", "running")

                setup_success = test_basic_setup(args.rpi_ip)

                # Update metrics: browser_test stage result
                if setup_success:
                    update_metrics_stage(args.metrics_id, args.metrics_db, "browser_test", "passed")
                    print("\n🎉 All tests completed successfully!")
                    if args.log_all_serial:
                        save_serial_log(serial_reader, args.metrics_id, script_dir)
                    if serial_reader:
                        serial_reader.stop()
                    sys.exit(0)
                else:
                    update_metrics_stage(args.metrics_id, args.metrics_db, "browser_test", "failed")
                    print("\n❌ Basic setup test failed!")
                    save_serial_log(serial_reader, args.metrics_id, script_dir)
                    if serial_reader:
                        serial_reader.stop()
                    sys.exit(1)
            else:
                print("\n🎉 Test completed successfully!")
                if args.log_all_serial:
                    save_serial_log(serial_reader, args.metrics_id, script_dir)
                if serial_reader:
                    serial_reader.stop()
                sys.exit(0)
        else:
            # Update metrics: boot or network failed
            update_metrics_stage(args.metrics_id, args.metrics_db, "boot", "failed")
            print("\n❌ Test failed!")
            save_serial_log(serial_reader, args.metrics_id, script_dir)
            if serial_reader:
                serial_reader.stop()
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        save_serial_log(serial_reader, args.metrics_id, script_dir)
        if serial_reader:
            serial_reader.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
