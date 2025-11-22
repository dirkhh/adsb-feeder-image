#!/usr/bin/env python3
"""
Historical Image Restore Tool

A text UI tool for restoring and booting previously tested images from /srv/history/.
Uses the metrics database as a locking mechanism to prevent conflicts with the automated
testing service.

Usage:
    restore-image.py [--config CONFIG_FILE]

Example:
    restore-image.py
    restore-image.py --config /etc/adsb-boot-test/config.json
"""

import argparse
import curses
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from metrics import TestMetrics

logger = logging.getLogger(__name__)


class HistoricalImage:
    """Represents a historical test image backup."""

    def __init__(self, path: Path, metrics_id: int):
        self.path = path
        self.metrics_id = metrics_id
        self.tftp_dir = path / "tftp"

        # Find the image file (should be a .img file in the directory)
        self.image_file: Optional[Path] = None
        for file in path.iterdir():
            if file.is_file() and file.suffix == ".img":
                self.image_file = file
                break

        # Get metadata from metrics database
        self.timestamp: Optional[datetime] = None
        self.image_url: Optional[str] = None
        self.status: Optional[str] = None
        self.trigger_source: Optional[str] = None

    def __str__(self) -> str:
        """Return a string representation of the image."""
        parts = [f"HistoricalImage(id={self.metrics_id}"]

        if self.image_file:
            parts.append(f", image={self.image_file.name}")

        if self.timestamp:
            parts.append(f", date={self.timestamp.strftime('%Y-%m-%d %H:%M')}")

        if self.status:
            parts.append(f", status={self.status}")

        parts.append(f", valid={self.is_valid()})")

        return "".join(parts)

    def is_valid(self) -> bool:
        """Check if this backup has all required components."""
        return self.tftp_dir.exists() and self.image_file is not None and self.image_file.exists()

    def get_display_name(self) -> str:
        """Get a human-readable display name."""
        if self.image_file:
            name = self.image_file.name
        else:
            name = "Unknown"

        if self.timestamp:
            date_str = self.timestamp.strftime("%Y-%m-%d %H:%M")
        else:
            date_str = "Unknown date"

        return f"{name} ({date_str})"

    def get_size_mb(self) -> float:
        """Get approximate size in MB (just the image file)."""
        if self.image_file and self.image_file.exists():
            return self.image_file.stat().st_size / 1024 / 1024
        return 0.0


class ImageRestoreTool:
    """Interactive tool for restoring historical images."""

    def __init__(self, config_path: str = "/etc/adsb-boot-test/config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self.metrics = TestMetrics(db_path="/var/lib/adsb-boot-test/metrics.db")
        self.history_dir = Path("/srv/history")
        self.current_test_id: Optional[int] = None

    def _load_config(self) -> Dict:
        """Load configuration from file."""
        config_path = Path(self.config_path)

        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}")
            logger.warning("Using default configuration")
            return {
                "rpi_ip": "192.168.77.190",
                "power_toggle_script": "/opt/adsb-boot-test/power-toggle-kasa.py",
                "ssh_key": "/etc/adsb-boot-test/ssh_key",
                "iscsi_server_ip": "192.168.77.252",
            }

        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)

    def discover_images(self) -> List[HistoricalImage]:
        """Discover all historical images in /srv/history/."""
        if not self.history_dir.exists():
            logger.warning(f"History directory not found: {self.history_dir}")
            return []

        images = []
        for entry in self.history_dir.iterdir():
            logger.info(f"looking at entry {entry}")
            if not entry.is_dir():
                continue

            try:
                metrics_id = int(entry.name)
            except ValueError:
                logger.debug(f"Skipping non-numeric directory: {entry.name}")
                continue

            image = HistoricalImage(entry, metrics_id)
            logger.info(f"got image {image}")

            # Get metadata from database
            test_data = self.metrics.get_test(metrics_id)
            if test_data:
                # Parse started_at timestamp
                started_at = test_data.get("started_at")
                if started_at:
                    try:
                        image.timestamp = datetime.fromisoformat(started_at)
                    except (ValueError, TypeError):
                        pass
                image.image_url = test_data.get("image_url")
                image.status = test_data.get("status")
                image.trigger_source = test_data.get("trigger_source")

            if image.is_valid():
                images.append(image)
            else:
                logger.debug(f"Skipping invalid backup: {entry}")

        # Sort by timestamp (newest first)
        images.sort(key=lambda img: img.timestamp or datetime.min, reverse=True)
        return images

    def check_service_idle(self) -> bool:
        """Check if the automated testing service is idle."""
        running_tests = self.metrics.get_tests_by_status("running")
        queued_tests = self.metrics.get_queued_tests()

        return len(running_tests) == 0 and len(queued_tests) == 0

    def wait_for_service_idle(self, stdscr) -> bool:
        """Wait for service to become idle, with visual feedback."""
        max_wait_seconds = 300  # 5 minutes
        start_time = time.time()
        poll_interval = 5

        while time.time() - start_time < max_wait_seconds:
            if self.check_service_idle():
                return True

            running_tests = self.metrics.get_tests_by_status("running")
            queued_tests = self.metrics.get_queued_tests()

            elapsed = int(time.time() - start_time)
            stdscr.clear()
            stdscr.addstr(0, 0, "Waiting for automated testing service to become idle...")
            stdscr.addstr(2, 0, f"Running tests: {len(running_tests)}")
            stdscr.addstr(3, 0, f"Queued tests: {len(queued_tests)}")
            stdscr.addstr(5, 0, f"Waiting... ({elapsed}s / {max_wait_seconds}s)")
            stdscr.addstr(7, 0, "Press 'q' to cancel")
            stdscr.refresh()

            # Check for user cancel
            stdscr.timeout(poll_interval * 1000)
            key = stdscr.getch()
            if key == ord("q") or key == ord("Q"):
                return False

        return False

    def mark_test_running(self, image: HistoricalImage) -> int:
        """Create a test entry to prevent service interference."""
        test_id = self.metrics.start_test(
            image_url=image.image_url or "restored-from-history",
            triggered_by="manual",
            trigger_source=f"restore-image.py (metrics_id={image.metrics_id})",
            rpi_ip=self.config.get("rpi_ip", ""),
        )
        self.metrics.update_test_status(test_id, "running")
        return test_id

    def restore_and_boot(self, image: HistoricalImage, stdscr) -> bool:
        """Restore TFTP/iSCSI and boot the system."""
        if not image.is_valid():
            logger.error(f"not a valid image {image}")
            return False
        assert image.image_file is not None
        try:
            stdscr.clear()
            stdscr.addstr(0, 0, "Restoring image...")
            stdscr.refresh()

            # Copy TFTP directory
            tftp_dest = Path("/srv/tftp")
            logger.info(f"Restoring TFTP from {image.tftp_dir} to {tftp_dest}")
            stdscr.addstr(2, 0, f"Copying TFTP files...")
            stdscr.refresh()

            # Remove existing TFTP directory
            if tftp_dest.exists():
                subprocess.run(["rm", "-rf", str(tftp_dest)], check=True)

            # Copy with hardlinks for efficiency
            subprocess.run(["cp", "-al", str(image.tftp_dir), str(tftp_dest)], check=True)

            # Setup iSCSI target
            stdscr.addstr(3, 0, f"Setting up iSCSI target...")
            stdscr.refresh()

            iscsi_dest = Path("/srv/iscsi") / image.image_file.name

            # Remove existing iSCSI image if present
            if iscsi_dest.exists():
                subprocess.run(["rm", "-f", str(iscsi_dest)], check=True)

            # Create hardlink to the historical image
            os.link(image.image_file, iscsi_dest)

            # Configure iSCSI target using tgtadm
            logger.info(f"Configuring iSCSI target with {iscsi_dest}")
            self._setup_iscsi_target(iscsi_dest)

            stdscr.addstr(4, 0, f"✓ Image restored")
            stdscr.addstr(6, 0, f"Powering on Raspberry Pi...")
            stdscr.refresh()

            # Power on
            self._power_toggle(turn_on=True)

            stdscr.addstr(7, 0, f"✓ Raspberry Pi powered on")
            stdscr.addstr(9, 0, f"System is booting...")
            stdscr.addstr(10, 0, f"IP: {self.config.get('rpi_ip', 'unknown')}")
            stdscr.refresh()

            return True

        except Exception as e:
            logger.error(f"Failed to restore and boot: {e}", exc_info=True)
            stdscr.addstr(12, 0, f"ERROR: {str(e)}")
            stdscr.refresh()
            time.sleep(3)
            return False

    def _setup_iscsi_target(self, image_path: Path) -> None:
        """Setup iSCSI target using tgtadm."""
        # Must match the target name in setup-tftp-iscsi.sh
        target_name = "iqn.2025-10.im.adsb:adsbim-test.root"

        logger.info("Setting up iSCSI target...")

        # Delete existing target if present
        try:
            result = subprocess.run(
                ["tgtadm", "--lld", "iscsi", "--op", "delete", "--mode", "target", "--tid", "1"],
                capture_output=True,
                text=True,
            )
            logger.info(f"Deleted existing target (if any): rc={result.returncode}")
        except Exception as e:
            logger.warning(f"Could not delete existing target: {e}")

        # Create new target
        logger.info(f"Creating target: {target_name}")
        result = subprocess.run(
            ["tgtadm", "--lld", "iscsi", "--op", "new", "--mode", "target", "--tid", "1", "-T", target_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"Failed to create target: {result.stderr}")
            raise RuntimeError(f"Failed to create iSCSI target: {result.stderr}")

        # Add backing store (LUN 1)
        logger.info(f"Adding backing store: {image_path}")
        result = subprocess.run(
            [
                "tgtadm",
                "--lld",
                "iscsi",
                "--op",
                "new",
                "--mode",
                "logicalunit",
                "--tid",
                "1",
                "--lun",
                "1",
                "-b",
                str(image_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"Failed to add backing store: {result.stderr}")
            raise RuntimeError(f"Failed to add backing store: {result.stderr}")

        # Bind to all interfaces
        logger.info("Binding to all interfaces")
        result = subprocess.run(
            ["tgtadm", "--lld", "iscsi", "--op", "bind", "--mode", "target", "--tid", "1", "-I", "ALL"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"Failed to bind target: {result.stderr}")
            raise RuntimeError(f"Failed to bind target: {result.stderr}")

        # Verify the target is configured
        logger.info("Verifying iSCSI target configuration...")
        result = subprocess.run(
            ["tgtadm", "--lld", "iscsi", "--op", "show", "--mode", "target"],
            capture_output=True,
            text=True,
        )
        logger.info(f"Target status:\n{result.stdout}")

        if target_name not in result.stdout:
            raise RuntimeError(f"Target {target_name} not found after creation")

        if "LUN: 1" not in result.stdout or str(image_path) not in result.stdout:
            raise RuntimeError(f"Backing store not properly configured")

        logger.info(f"✓ iSCSI target configured: {target_name}")

    def _power_toggle(self, turn_on: bool) -> None:
        """Toggle power using configured script."""
        script = self.config.get("power_toggle_script", "/opt/adsb-boot-test/power-toggle-kasa.py")
        cmd = [script, "on" if turn_on else "off"]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Power toggle failed: {result.stderr}")

    def _ssh_shutdown(self) -> None:
        """Shutdown via SSH."""
        rpi_ip = self.config.get("rpi_ip", "")
        ssh_key = self.config.get("ssh_key", "")

        ssh_cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no"]
        if ssh_key:
            ssh_cmd.extend(["-i", ssh_key])
        ssh_cmd.extend([f"root@{rpi_ip}", "shutdown now"])

        try:
            subprocess.run(ssh_cmd, capture_output=True, timeout=15)
            logger.info("Shutdown command sent via SSH")
        except Exception as e:
            logger.warning(f"SSH shutdown failed: {e}")

    def shutdown_and_cleanup(self, stdscr) -> None:
        """Shutdown system and cleanup."""
        try:
            stdscr.clear()
            stdscr.addstr(0, 0, "Shutting down...")
            stdscr.refresh()

            # Send SSH shutdown
            stdscr.addstr(2, 0, "Sending shutdown command via SSH...")
            stdscr.refresh()
            self._ssh_shutdown()

            # Wait a bit
            time.sleep(5)

            # Power off
            stdscr.addstr(3, 0, "Powering off...")
            stdscr.refresh()
            self._power_toggle(turn_on=False)

            stdscr.addstr(5, 0, "✓ System powered off")
            stdscr.refresh()

        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            stdscr.addstr(7, 0, f"ERROR: {str(e)}")
            stdscr.refresh()
            time.sleep(2)

    def run_ui(self, stdscr) -> int:
        """Run the interactive UI."""
        curses.curs_set(0)  # Hide cursor
        stdscr.keypad(True)

        # Discover images
        stdscr.addstr(0, 0, "Discovering historical images...")
        stdscr.refresh()

        images = self.discover_images()

        if not images:
            stdscr.clear()
            stdscr.addstr(0, 0, "No historical images found in /srv/history/")
            stdscr.addstr(2, 0, "Press any key to exit")
            stdscr.refresh()
            stdscr.getch()
            return 1

        # Image selection UI
        current_idx = 0
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Header
            stdscr.addstr(0, 0, "Historical Image Restore Tool", curses.A_BOLD)
            stdscr.addstr(1, 0, "=" * min(50, width - 1))
            stdscr.addstr(2, 0, f"Found {len(images)} historical images")
            stdscr.addstr(3, 0, "Use ↑/↓ to select, Enter to restore, 'q' to quit")
            stdscr.addstr(4, 0, "-" * min(50, width - 1))

            # Image list
            start_row = 6
            visible_rows = height - start_row - 3

            # Calculate scroll offset
            if current_idx < visible_rows // 2:
                offset = 0
            elif current_idx >= len(images) - visible_rows // 2:
                offset = max(0, len(images) - visible_rows)
            else:
                offset = current_idx - visible_rows // 2

            for i in range(offset, min(offset + visible_rows, len(images))):
                img = images[i]
                row = start_row + (i - offset)

                # Format display line
                status_icon = "✓" if img.status == "passed" else "✗" if img.status == "failed" else "?"
                size_mb = img.get_size_mb()
                line = f"{status_icon} [{img.metrics_id:4d}] {img.get_display_name()[:width-30]} ({size_mb:.0f}MB)"

                if i == current_idx:
                    stdscr.addstr(row, 0, line, curses.A_REVERSE)
                else:
                    stdscr.addstr(row, 0, line)

            # Show selected image details
            detail_row = height - 2
            if current_idx < len(images):
                img = images[current_idx]
                details = f"URL: {img.image_url or 'N/A'}"[: width - 1]
                stdscr.addstr(detail_row, 0, details)

            stdscr.refresh()

            # Handle input
            key = stdscr.getch()

            if key == ord("q") or key == ord("Q"):
                return 0
            elif key == curses.KEY_UP and current_idx > 0:
                current_idx -= 1
            elif key == curses.KEY_DOWN and current_idx < len(images) - 1:
                current_idx += 1
            elif key == ord("\n") or key == curses.KEY_ENTER or key == 10 or key == 13:
                # User selected an image
                selected_image = images[current_idx]

                # Check if service is idle
                if not self.check_service_idle():
                    stdscr.clear()
                    stdscr.addstr(0, 0, "Automated testing service is busy!")
                    stdscr.addstr(1, 0, "Waiting for it to become idle...")
                    stdscr.refresh()

                    if not self.wait_for_service_idle(stdscr):
                        stdscr.clear()
                        stdscr.addstr(0, 0, "Cancelled or timeout waiting for service")
                        stdscr.addstr(1, 0, "Press any key to continue")
                        stdscr.refresh()
                        stdscr.getch()
                        continue

                # Mark test as running
                self.current_test_id = self.mark_test_running(selected_image)

                # Restore and boot
                if not self.restore_and_boot(selected_image, stdscr):
                    # Cleanup on failure
                    if self.current_test_id:
                        self.metrics.complete_test(self.current_test_id, status="failed", error_message="Restore failed")
                    stdscr.addstr(height - 1, 0, "Press any key to continue")
                    stdscr.refresh()
                    stdscr.getch()
                    continue

                # Wait for user confirmation
                stdscr.addstr(12, 0, "=" * min(50, width - 1))
                stdscr.addstr(13, 0, "Press Enter when done testing (system will shutdown)")
                stdscr.refresh()

                while True:
                    key = stdscr.getch()
                    if key == ord("\n") or key == curses.KEY_ENTER or key == 10 or key == 13:
                        break

                # Shutdown
                self.shutdown_and_cleanup(stdscr)

                # Mark test as complete
                if self.current_test_id:
                    self.metrics.complete_test(
                        self.current_test_id,
                        status="passed",
                        error_message="Manual restore session completed",
                    )

                stdscr.addstr(height - 1, 0, "Press any key to continue")
                stdscr.refresh()
                stdscr.getch()

        return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive tool for restoring historical test images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        default="/etc/adsb-boot-test/config.json",
        help="Configuration file path (default: /etc/adsb-boot-test/config.json)",
    )

    args = parser.parse_args()

    # Setup logging to file (not stdout) to avoid interfering with curses UI
    log_dir = Path("/opt/adsb-boot-test/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "restore-image.log"

    # Configure logging to file only
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
        ],
    )

    logger.info("=" * 80)
    logger.info("Restore Image Tool Starting")
    logger.info("=" * 80)

    # Create tool instance
    tool = ImageRestoreTool(config_path=args.config)

    # Run UI
    try:
        return curses.wrapper(tool.run_ui)
    except KeyboardInterrupt:
        logger.info("Cancelled by user")
        print("\nCancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
        print(f"See {log_file} for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
