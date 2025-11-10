#!/usr/bin/env python3
"""
Selenium test runner wrapper - runs tests as testuser for security.

This script is invoked by the main test script via sudo -u testuser.
It runs the selenium tests in an isolated user context to avoid running
browsers as root.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from selenium_framework.config import SeleniumConfig  # noqa: E402
from selenium_framework.test_runner import SeleniumTestRunner  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    """Run selenium tests as testuser."""
    parser = argparse.ArgumentParser(description="Run selenium tests as non-root user")
    parser.add_argument("target_ip", help="IP address of system to test")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds (default: 600)")
    parser.add_argument(
        "--browser",
        choices=["chrome", "firefox"],
        default="firefox",
        help="Browser to use for testing (default: firefox)",
    )
    args = parser.parse_args()

    logger.info(f"Running browser tests against {args.target_ip}")
    logger.info(f"Running as user: {Path.home().owner() if hasattr(Path.home(), 'owner') else 'unknown'}")

    try:
        # Create test configuration
        config = SeleniumConfig(rpi_ip=args.target_ip, browser=args.browser, headless=True, timeout=args.timeout)

        # Run tests using context manager
        with SeleniumTestRunner(config) as runner:
            success = runner.run_basic_setup_test()

            if success:
                success = runner.run_authentication_test()

        if success:
            logger.info("✓ Tests passed")
            return 0
        else:
            logger.error("✗ Tests failed")
            return 1

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
