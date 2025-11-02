#!/usr/bin/env python3
"""
Feeder Image Testing Script - Refactored Version

Tests RPi feeder images using the RPiISCSIBackend hardware abstraction.
This script is now a thin wrapper around the shared backend implementation.
"""

import argparse
import logging
import sys
from pathlib import Path

from boot_test_lib.logging_utils import setup_logging
from boot_test_lib.metrics_utils import complete_test, update_stage
from hardware_backends.base import TestConfig
from hardware_backends.rpi_iscsi import RPiISCSIBackend

logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test RPi feeder images")
    parser.add_argument("image_url", help="URL to .img.xz image")
    parser.add_argument("rpi_ip", help="Raspberry Pi IP address")
    parser.add_argument("power_toggle_script", help="Path to power toggle script")
    parser.add_argument("--ssh-key", help="SSH public key to install in image")
    parser.add_argument("--serial-console", help="Serial console device (e.g., /dev/ttyUSB0)")
    parser.add_argument("--serial-baud", type=int, default=115200, help="Serial baud rate (default: 115200)")
    parser.add_argument("--metrics-id", type=int, help="Metrics database test ID")
    parser.add_argument("--metrics-db", default="/var/lib/adsb-boot-test/metrics.db", help="Metrics database path")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout in minutes (default: 10)")
    parser.add_argument("--keep-on-failure", action="store_true", help="Don't power off RPi on test failure (for debugging)")

    args = parser.parse_args()

    # Setup logging
    setup_logging()

    logger.info("=" * 80)
    logger.info("Feeder Image Testing (Refactored)")
    logger.info("=" * 80)
    logger.info(f"Image URL: {args.image_url}")
    logger.info(f"RPi IP: {args.rpi_ip}")
    logger.info(f"Power toggle: {args.power_toggle_script}")

    # Create test configuration
    config = TestConfig(
        image_url=args.image_url,
        metrics_id=args.metrics_id,
        metrics_db=Path(args.metrics_db),
        timeout_minutes=args.timeout,
        ssh_key=Path(args.ssh_key) if args.ssh_key else None,
    )

    # Create RPi backend
    backend = RPiISCSIBackend(
        config=config,
        rpi_ip=args.rpi_ip,
        power_toggle_script=Path(args.power_toggle_script),
        serial_console=args.serial_console,
        serial_baud=args.serial_baud,
    )

    success = False

    try:
        # Stage 1-2: Download and setup iSCSI
        update_stage(config.metrics_id, config.metrics_db, "download", "running")
        backend.prepare_environment()
        update_stage(config.metrics_id, config.metrics_db, "download", "passed")

        # Stage 3: Boot system
        update_stage(config.metrics_id, config.metrics_db, "boot", "running")
        backend.boot_system()
        update_stage(config.metrics_id, config.metrics_db, "boot", "passed")

        # Stage 4: Wait for network
        update_stage(config.metrics_id, config.metrics_db, "network", "running")
        rpi_ip = backend.wait_for_network()
        update_stage(config.metrics_id, config.metrics_db, "network", "passed")

        # Stage 5: Browser tests
        logger.info("=" * 70)
        logger.info("Stage 5: Browser tests")
        logger.info("=" * 70)

        update_stage(config.metrics_id, config.metrics_db, "browser_test", "running")
        success = backend.run_browser_tests(rpi_ip)

        if success:
            logger.info("✓ All tests passed!")
            update_stage(config.metrics_id, config.metrics_db, "browser_test", "passed")
            complete_test(config.metrics_id, config.metrics_db, "passed")
        else:
            logger.error("✗ Tests failed")
            update_stage(config.metrics_id, config.metrics_db, "browser_test", "failed")
            complete_test(config.metrics_id, config.metrics_db, "failed", "Browser tests failed")

    except Exception as e:
        logger.error(f"Test failed with exception: {e}", exc_info=True)
        complete_test(config.metrics_id, config.metrics_db, "failed", str(e))
        success = False

    finally:
        # Cleanup (but skip if test failed and --keep-on-failure is set)
        if success or not args.keep_on_failure:
            try:
                backend.cleanup()
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")
        else:
            logger.warning("Skipping cleanup due to test failure (--keep-on-failure)")
            logger.info(f"System is still running at {rpi_ip} for debugging")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
