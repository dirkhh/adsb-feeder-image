#!/usr/bin/env python3
"""
VM Image Testing Script - Refactored Version

Tests qcow2 VM images using the VMLibvirtBackend hardware abstraction.
This script is now a thin wrapper around the shared backend implementation.
"""

import argparse
import logging
import sys
from pathlib import Path

from boot_test_lib.logging_utils import setup_logging
from boot_test_lib.metrics_utils import complete_test, update_stage
from hardware_backends.base import TestConfig
from hardware_backends.vm_libvirt import VMLibvirtBackend

logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test qcow2 VM images")
    parser.add_argument("image_url", help="URL to qcow2.xz image")
    parser.add_argument("--vm-server", required=True, help="VM server IP address")
    parser.add_argument("--vm-ssh-key", required=True, help="SSH key for VM server")
    parser.add_argument("--vm-bridge", default="bridge77", help="Bridge interface (default: bridge77)")
    parser.add_argument("--vm-memory", type=int, default=1024, help="VM memory in MB (default: 1024)")
    parser.add_argument("--vm-cpus", type=int, default=2, help="VM CPUs (default: 2)")
    parser.add_argument("--metrics-id", type=int, help="Metrics database test ID")
    parser.add_argument("--metrics-db", default="/var/lib/adsb-boot-test/metrics.db", help="Metrics database path")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout in minutes (default: 10)")
    parser.add_argument("--keep-on-failure", action="store_true", help="Don't cleanup VM on test failure (for debugging)")

    args = parser.parse_args()

    # Setup logging
    setup_logging()

    logger.info("=" * 80)
    logger.info("VM Image Testing (Refactored)")
    logger.info("=" * 80)
    logger.info(f"Image URL: {args.image_url}")
    logger.info(f"VM Server: {args.vm_server}")
    logger.info(f"Bridge: {args.vm_bridge}")
    logger.info(f"Memory: {args.vm_memory}MB, CPUs: {args.vm_cpus}")

    # Create test configuration
    config = TestConfig(
        image_url=args.image_url,
        metrics_id=args.metrics_id,
        metrics_db=Path(args.metrics_db),
        timeout_minutes=args.timeout,
    )

    # Create VM backend
    backend = VMLibvirtBackend(
        config=config,
        vm_server=args.vm_server,
        vm_ssh_key=Path(args.vm_ssh_key),
        vm_bridge=args.vm_bridge,
        vm_memory_mb=args.vm_memory,
        vm_cpus=args.vm_cpus,
    )

    vm_ip: str = ""
    success = False

    try:
        # Stage 1-4: Download, transfer, decompress, create VM
        update_stage(config.metrics_id, config.metrics_db, "download", "running")
        backend.prepare_environment()
        update_stage(config.metrics_id, config.metrics_db, "download", "passed")

        # Stage 5: Boot (already done by virt-install)
        update_stage(config.metrics_id, config.metrics_db, "boot", "running")
        backend.boot_system()
        update_stage(config.metrics_id, config.metrics_db, "boot", "passed")

        # Stage 6: Wait for network
        update_stage(config.metrics_id, config.metrics_db, "network", "running")
        vm_ip = backend.wait_for_network()
        update_stage(config.metrics_id, config.metrics_db, "network", "passed")

        # Stage 7: Browser tests
        logger.info("=" * 70)
        logger.info("Stage 7: Browser tests")
        logger.info("=" * 70)

        update_stage(config.metrics_id, config.metrics_db, "browser_test", "running")
        success = backend.run_browser_tests(vm_ip)

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
        # Cleanup VM (but skip if test failed and --keep-on-failure is set)
        if success or not args.keep_on_failure:
            try:
                backend.cleanup()
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")
        else:
            logger.warning("Skipping cleanup due to test failure (--keep-on-failure)")
            if hasattr(backend, "vm_ip") and backend.vm_ip:
                logger.info(f"VM is still running at {backend.vm_ip} for debugging")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
