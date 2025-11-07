#!/usr/bin/env python3
"""
Selenium test runner - designed to run as non-root user (testuser).
This script is invoked by test-feeder-image.py via sudo -u testuser.

Refactored to use Page Object Model and proper separation of concerns.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add the script directory to Python path so selenium_framework can be imported
script_dir = Path(__file__).resolve().parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from selenium_framework.config import SeleniumConfig  # noqa: E402
from selenium_framework.test_runner import SeleniumTestRunner  # noqa: E402

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def main() -> int:
    """
    Main entry point for selenium tests.

    Returns:
        0 on success, 1 on failure
    """
    parser = argparse.ArgumentParser(description="Run Selenium tests as non-root user")
    parser.add_argument("rpi_ip", help="IP address of the Raspberry Pi")
    parser.add_argument("--timeout", type=int, default=90, help="Timeout in seconds (default: 90)")
    parser.add_argument(
        "--browser",
        choices=["chrome", "firefox"],
        default="firefox",
        help="Browser to use for testing (default: firefox)",
    )
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode (default: True)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run browser with GUI")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")

    args = parser.parse_args()

    # Apply requested log level
    try:
        log_level = getattr(logging, args.log_level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
    except Exception:
        logging.getLogger().setLevel(logging.INFO)

    # Create test configuration
    config = SeleniumConfig(rpi_ip=args.rpi_ip, browser=args.browser, headless=args.headless, timeout=args.timeout)

    # Run tests
    try:
        with SeleniumTestRunner(config) as runner:
            success = runner.run_basic_setup_test()
            return 0 if success else 1
    except Exception as e:
        logging.exception(f"Test runner failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
