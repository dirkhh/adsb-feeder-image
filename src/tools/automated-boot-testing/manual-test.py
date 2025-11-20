#!/usr/bin/env python3
"""
Manual Boot Testing Tool

A command-line tool for one-off testing of ADS-B feeder images.
Reuses the existing automated boot testing infrastructure but allows
manual testing without the service taking over.

Usage:
    manual-test.py <image_url> <flag_filename>

Example:
    manual-test.py https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.2.0/adsb-feeder-raspberrypi64.img.xz usestaging
"""

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Dict, Optional

from boot_test_lib.logging_utils import setup_logging
from hardware_backends.base import TestConfig
from hardware_backends.rpi_iscsi import RPiISCSIBackend
from metrics import TestMetrics

logger = logging.getLogger(__name__)


def load_config(config_file: str = "/etc/adsb-boot-test/config.json") -> Dict:
    config_path = Path(config_file)

    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}")
        logger.warning("Using default configuration")
        # Return minimal defaults
        return {
            "rpi_ip": "192.168.77.190",
            "power_toggle_script": "/opt/adsb-boot-test/power-toggle-unifi.py",
            "ssh_key": "/etc/adsb-boot-test/ssh_key",
            "timeout_minutes": 10,
            "iscsi_server_ip": "192.168.77.252",
        }

    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        logger.warning("Using default configuration")
        return {
            "rpi_ip": "192.168.77.190",
            "power_toggle_script": "/opt/adsb-boot-test/power-toggle-unifi.py",
            "ssh_key": "/etc/adsb-boot-test/ssh_key",
            "timeout_minutes": 10,
            "iscsi_server_ip": "192.168.77.252",
        }


class ManualTestRunner:
    def __init__(
        self,
        image_url: str,
        flag_filename: str,
        rpi_ip: str,
        power_toggle_script: Path,
        ssh_key: Optional[Path],
        iscsi_server_ip: str,
        serial_console: Optional[str],
        serial_baud: int,
        timeout_minutes: int,
        metrics_db: Path,
    ):
        self.image_url = image_url
        self.flag_filename = flag_filename
        self.rpi_ip = rpi_ip
        self.power_toggle_script = power_toggle_script
        self.ssh_key = ssh_key
        self.iscsi_server_ip = iscsi_server_ip
        self.serial_console = serial_console
        self.serial_baud = serial_baud
        self.timeout_minutes = timeout_minutes
        self.metrics_db = metrics_db
        self.metrics = TestMetrics(db_path=str(metrics_db))
        self.test_id: Optional[int] = None
        self.backend: Optional[RPiISCSIBackend] = None
        self.interrupted = False

    def wait_for_service_idle(self) -> bool:
        logger.info("Checking if automated boot testing service is idle...")
        max_wait_seconds = 300  # 5 minutes max wait
        start_time = time.time()
        poll_interval = 10

        while time.time() - start_time < max_wait_seconds:
            # Check for running tests
            running_tests = self.metrics.get_tests_by_status("running")
            queued_tests = self.metrics.get_queued_tests()

            if not running_tests and not queued_tests:
                logger.info("✓ Service is idle, proceeding with manual test")
                return True

            logger.info(
                f"Service is busy: {len(running_tests)} running, {len(queued_tests)} queued. "
                f"Waiting... (checking again in {poll_interval}s)"
            )
            time.sleep(poll_interval)

        logger.error(f"Service did not become idle within {max_wait_seconds}s")
        return False

    def mark_test_running(self) -> int:
        logger.info("Creating test entry in metrics database...")
        test_id = self.metrics.start_test(
            image_url=self.image_url,
            triggered_by="manual",
            trigger_source="manual-test.py",
            rpi_ip=self.rpi_ip,
        )
        # Mark as running to prevent service from starting another test
        self.metrics.update_test_status(test_id, "running")
        logger.info(f"✓ Test marked as running (test_id={test_id})")
        return test_id

    def prepare_and_boot(self) -> bool:
        try:
            # Create test configuration
            config = TestConfig(
                image_url=self.image_url,
                metrics_id=self.test_id,
                metrics_db=self.metrics_db,
                timeout_minutes=self.timeout_minutes,
                ssh_key=self.ssh_key,
            )

            # Create RPi backend with flag file support
            self.backend = RPiISCSIBackend(
                config=config,
                rpi_ip=self.rpi_ip,
                power_toggle_script=self.power_toggle_script,
                serial_console=self.serial_console,
                serial_baud=self.serial_baud,
                iscsi_server_ip=self.iscsi_server_ip,
            )

            # Set flag filename for the backend to use
            self.backend.flag_filename = self.flag_filename

            # Stage 1-2: Download and setup iSCSI
            logger.info("=" * 70)
            logger.info("Preparing image (download and iSCSI setup)")
            logger.info("=" * 70)
            self.backend.prepare_environment()

            # Stage 3: Boot system
            logger.info("=" * 70)
            logger.info("Booting system")
            logger.info("=" * 70)
            self.backend.boot_system()

            # Stage 4: Wait for network
            logger.info("=" * 70)
            logger.info("Waiting for system to come online")
            logger.info("=" * 70)
            self.backend.wait_for_network()

            logger.info("✓ System is ready for testing")
            return True

        except Exception as e:
            logger.error(f"Failed to prepare and boot: {e}", exc_info=True)
            return False

    def wait_for_user(self) -> None:
        logger.info("=" * 70)
        logger.info("Manual Testing")
        logger.info("=" * 70)
        logger.info(f"The feeder at address {self.rpi_ip} is ready for testing.")
        logger.info(f"Flag file created: /boot/firmware/{self.flag_filename}")
        logger.info("")
        logger.info("Press Enter when done (or Ctrl+C)...")
        logger.info("=" * 70)

        # Setup signal handler for Ctrl+C
        def signal_handler(signum, frame):
            logger.info("\nReceived interrupt signal")
            self.interrupted = True

        old_handler = signal.signal(signal.SIGINT, signal_handler)

        try:
            input()
        except (KeyboardInterrupt, EOFError):
            self.interrupted = True
        finally:
            # Restore old handler
            signal.signal(signal.SIGINT, old_handler)

        logger.info("User finished testing")

    def cleanup_and_mark_done(self) -> None:
        logger.info("=" * 70)
        logger.info("Cleanup")
        logger.info("=" * 70)

        if self.backend:
            try:
                self.backend.cleanup()
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")

        if self.test_id:
            logger.info("Marking test as complete in database...")
            self.metrics.complete_test(
                self.test_id,
                status="passed",
                error_message="Manual test completed" if not self.interrupted else "Manual test interrupted by user",
            )
            logger.info("✓ Test marked as complete")

    def run(self) -> int:
        try:
            if not self.wait_for_service_idle():
                return 1

            self.test_id = self.mark_test_running()
            if not self.prepare_and_boot():
                logger.error("Failed to prepare and boot system")
                if self.test_id:
                    self.metrics.complete_test(self.test_id, status="failed", error_message="Failed to prepare/boot")
                return 1

            # now the user can test
            self.wait_for_user()

            self.cleanup_and_mark_done()

            logger.info("=" * 70)
            logger.info("Manual test complete!")
            logger.info("=" * 70)
            return 0

        except Exception as e:
            logger.error(f"Manual test failed: {e}", exc_info=True)
            if self.test_id:
                self.metrics.complete_test(self.test_id, status="failed", error_message=str(e))
            return 1


def main() -> int:
    # Load configuration file first (before argparse) to get defaults
    config = load_config()

    parser = argparse.ArgumentParser(
        description="Manual boot testing tool for ADS-B feeder images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test a release image with a usestaging flag
  %(prog)s https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.2.0/adsb-feeder-raspberrypi64.img.xz usestaging

  # Test withhout custom configuration
  %(prog)s --rpi-ip 192.168.1.100 --timeout 15 <image_url>

Note: Configuration is loaded from /etc/adsb-boot-test/config.json (same as the service).
      Command-line arguments override the config file values.
        """,
    )

    # Required arguments
    parser.add_argument("image_url", help="URL to .img.xz image from GitHub releases")
    parser.add_argument(
        "flag_filename",
        nargs="?",
        default=None,
        help="Name of flag file to create in /boot/firmware/ (optional)",
    )

    # Optional configuration (with defaults from config file)
    parser.add_argument(
        "--config",
        default="/etc/adsb-boot-test/config.json",
        help="Configuration file path (default: /etc/adsb-boot-test/config.json)",
    )
    parser.add_argument(
        "--rpi-ip",
        default=config.get("rpi_ip", "192.168.77.190"),
        help=f"Raspberry Pi IP address (default from config: {config.get('rpi_ip', '192.168.77.190')})",
    )
    parser.add_argument(
        "--power-toggle-script",
        default=config.get("power_toggle_script", "/opt/adsb-boot-test/power-toggle-kasa.py"),
        help=f"Path to power toggle script (default from config: {config.get('power_toggle_script', '/opt/adsb-boot-test/power-toggle-kasa.py')})",
    )
    parser.add_argument(
        "--ssh-key",
        default=config.get("ssh_key"),
        help=f"SSH private key for accessing RPi (default from config: {config.get('ssh_key', 'none')})",
    )
    parser.add_argument(
        "--iscsi-server-ip",
        default=config.get("iscsi_server_ip", "192.168.77.252"),
        help=f"iSCSI server IP address (default from config: {config.get('iscsi_server_ip', '192.168.77.252')})",
    )
    parser.add_argument(
        "--serial-console",
        default=config.get("serial_console"),
        help="Serial console device (e.g., /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--serial-baud",
        type=int,
        default=config.get("serial_baud", 115200),
        help=f"Serial baud rate (default: {config.get('serial_baud', 115200)})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=config.get("timeout_minutes", 10),
        help=f"Timeout in minutes (default from config: {config.get('timeout_minutes', 10)})",
    )
    parser.add_argument(
        "--metrics-db",
        default="/var/lib/adsb-boot-test/metrics.db",
        help="Metrics database path (default: /var/lib/adsb-boot-test/metrics.db)",
    )

    args = parser.parse_args()

    # Reload config if a different path was specified
    if args.config != "/etc/adsb-boot-test/config.json":
        config = load_config(args.config)

    # Setup logging
    setup_logging()

    logger.info("=" * 80)
    logger.info("Manual Boot Testing Tool")
    logger.info("=" * 80)
    logger.info(f"Config file: {args.config}")
    logger.info(f"Image URL: {args.image_url}")
    logger.info(f"Flag file: /boot/firmware/{args.flag_filename}")
    logger.info(f"RPi IP: {args.rpi_ip}")
    logger.info(f"Power toggle: {args.power_toggle_script}")
    logger.info("")

    # Create and run manual test
    runner = ManualTestRunner(
        image_url=args.image_url,
        flag_filename=args.flag_filename,
        rpi_ip=args.rpi_ip,
        power_toggle_script=Path(args.power_toggle_script),
        ssh_key=Path(args.ssh_key) if args.ssh_key else None,
        iscsi_server_ip=args.iscsi_server_ip,
        serial_console=args.serial_console,
        serial_baud=args.serial_baud,
        timeout_minutes=args.timeout,
        metrics_db=Path(args.metrics_db),
    )

    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
