"""Raspberry Pi testing backend using iSCSI boot."""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests
from boot_test_lib.disk_space_utils import handle_space_error, is_likely_space_error
from boot_test_lib.download import ImageDownloader, ImageInfo
from serial_console_reader import SerialConsoleReader  # type: ignore

from .base import HardwareBackend, TestConfig

logger = logging.getLogger(__name__)


class RPiISCSIBackend(HardwareBackend):
    """Test backend for Raspberry Pi with iSCSI network boot."""

    def __init__(
        self,
        config: TestConfig,
        rpi_ip: str,
        power_toggle_script: Path,
        serial_console: Optional[str] = None,
        serial_baud: int = 115200,
        iscsi_server_ip: str = "192.168.77.252",
    ):
        """
        Initialize RPi iSCSI backend.

        Args:
            config: Test configuration
            rpi_ip: IP address of Raspberry Pi
            power_toggle_script: Path to power toggle script
            serial_console: Optional serial console device path
            serial_baud: Serial baud rate
            iscsi_server_ip: iSCSI server IP address (default: 192.168.77.252)
        """
        super().__init__(config)
        self.rpi_ip = rpi_ip
        self.power_toggle_script = power_toggle_script
        self.serial_console = serial_console
        self.serial_baud = serial_baud
        self.iscsi_server_ip = iscsi_server_ip

        self.expected_image_name: Optional[str] = None
        self.serial_reader: Optional[SerialConsoleReader] = None
        self.serial_log_dir = Path("/opt/adsb-boot-test/serial-logs")
        self.flag_filename: Optional[str] = None  # Optional flag file to create in /boot/firmware/

    def prepare_environment(self) -> None:
        """Download image and setup iSCSI."""
        # Start serial console monitoring if device is provided
        if self.serial_console:
            self._start_serial_console()

        # Parse image info
        image_info = ImageInfo.from_url(self.config.image_url)
        self.expected_image_name = image_info.expected_name

        logger.info(f"Image type: {image_info.image_type}")
        logger.info(f"Expected name: {self.expected_image_name}")

        # Download and decompress image
        logger.info("=" * 70)
        logger.info("Stage 1: Download and decompress image")
        logger.info("=" * 70)

        downloader = ImageDownloader(cache_dir=Path("/tmp"))
        self.local_compressed = downloader.download(image_info)

        # Decompress locally
        self.local_decompressed = self.local_compressed.with_suffix("")  # Remove .xz
        if not self.local_decompressed.exists():
            logger.info(f"Decompressing to {self.local_decompressed}")
            try:
                subprocess.run(["xz", "-d", "-k", str(self.local_compressed)], check=True)
                logger.info(f"Decompressed to {self.local_decompressed.stat().st_size / 1024 / 1024:.1f} MB")
            except Exception as e:
                if is_likely_space_error(e):
                    handle_space_error(Path("/tmp"), "decompression")
                raise
        else:
            logger.info(f"Using cached decompressed image: {self.local_decompressed}")

        # Setup iSCSI image
        logger.info("=" * 70)
        logger.info("Stage 2: Setup iSCSI image")
        logger.info("=" * 70)

        self._setup_iscsi_image(self.local_decompressed)

    def boot_system(self) -> None:
        """Power cycle Raspberry Pi."""
        logger.info("=" * 70)
        logger.info("Stage 3: Power cycle Raspberry Pi")
        logger.info("=" * 70)

        # Shutdown gracefully if possible
        self._try_ssh_shutdown()

        # Wait for system to go down
        self._wait_for_system_down()

        # Power cycle
        logger.info("Powering off...")
        self._power_toggle(turn_on=False)
        time.sleep(10)

        logger.info("Powering on...")
        self._power_toggle(turn_on=True)
        time.sleep(60)  # Give time to boot and initialize iSCSI

    def wait_for_network(self) -> str:
        """
        Wait for RPi to boot and verify correct image is running.

        Returns:
            RPi IP address

        Raises:
            RuntimeError: If system doesn't come online or wrong image
        """
        logger.info("=" * 70)
        logger.info("Stage 4: Wait for system online")
        logger.info("=" * 70)

        success = self._wait_for_feeder_online()

        if not success:
            raise RuntimeError("System did not come online or wrong image is running")

        return self.rpi_ip

    def cleanup(self) -> None:
        """Save the setup log (if able) and power off Raspberry Pi and cleanup serial reader."""
        logger.info("=" * 70)
        logger.info("Save setup log")
        logger.info("=" * 70)
        # Copy setup log from RPi
        self._copy_setup_log()

        logger.info("=" * 70)
        logger.info("Cleanup: Powering off Raspberry Pi")
        logger.info("=" * 70)

        # Save and stop serial reader if running
        if self.serial_reader and self.serial_reader.is_running():
            try:
                self._save_serial_log()
                self.serial_reader.stop()
                logger.info("✓ Serial console reader stopped")
            except Exception as e:
                logger.warning(f"Failed to stop serial reader: {e}")

        # Power off
        try:
            self._power_toggle(turn_on=False)
            logger.info("✓ Raspberry Pi powered off")
        except Exception as e:
            logger.warning(f"Failed to power off: {e}")

        # create a space optimized copy of the files so we can restart this particular image later
        # - if there is no previous directory under /srv/history/ then create a backup using
        #   cp -al /srv/tftp /srv/history/<self.config.metrics_id>/tftp
        # - if there is one or more previous directory under /srv/history/ create a new backup
        #   rsync -a --link-dest=/srv/history/<newest exist. backup>/tftp /tftp/<self.config.metrics_id>/history/2/tftp/
        # finally, create a hardlink to the image file in use under /srv/iscsi/ in that backup directory as well
        # that way we'll be able to get back to this state quite easily in the future
        try:
            history_dir = Path("/srv/history")
            backup_dir = history_dir / str(self.config.metrics_id)
            tftp_source = Path("/srv/tftp")

            # Create history directory if it doesn't exist
            history_dir.mkdir(parents=True, exist_ok=True)
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Find all existing backups in /srv/history/ (excluding the current one)
            existing_backups = sorted(
                [d for d in history_dir.iterdir() if d.is_dir() and d != backup_dir],
                key=lambda p: p.stat().st_mtime,
            )

            tftp_backup_dest = backup_dir / "tftp"

            if not existing_backups:
                # No previous backups exist, use cp -al for hardlink copy
                logger.info(f"Creating first backup using hardlinks: {tftp_backup_dest}")
                subprocess.run(
                    ["cp", "-al", str(tftp_source), str(tftp_backup_dest)],
                    check=True,
                )
                logger.info("✓ First backup created with hardlinks")
            else:
                # Previous backups exist, use rsync with --link-dest
                newest_backup = existing_backups[-1]
                link_dest = newest_backup / "tftp"
                logger.info(f"Creating incremental backup with hardlinks from: {newest_backup}")
                subprocess.run(
                    [
                        "rsync",
                        "-a",
                        f"--link-dest={link_dest}",
                        f"{tftp_source}/",
                        f"{tftp_backup_dest}/",
                    ],
                    check=True,
                )
                logger.info(f"✓ Incremental backup created (linked to {newest_backup})")

            # Create hardlink to the iSCSI image file in the backup directory
            if hasattr(self, "local_decompressed") and self.local_decompressed:
                iscsi_image_path = Path("/srv/iscsi") / self.local_decompressed.name
                if iscsi_image_path.exists():
                    image_backup_dest = backup_dir / iscsi_image_path.name
                    logger.info(f"Creating hardlink to iSCSI image: {image_backup_dest}")
                    if image_backup_dest.exists():
                        image_backup_dest.unlink()
                    os.link(iscsi_image_path, image_backup_dest)
                    logger.info("✓ iSCSI image hardlink created")
                else:
                    logger.warning(f"iSCSI image not found at: {iscsi_image_path}")

            logger.info(f"✓ Backup completed: {backup_dir}")
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")

        # Clean up temp files
        if hasattr(self, "local_decompressed") and self.local_decompressed and self.local_decompressed.exists():
            try:
                self.local_decompressed.unlink()
                logger.info(f"✓ Removed temp file: {self.local_decompressed}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file: {e}")

        if hasattr(self, "local_compressed") and self.local_compressed and self.local_compressed.exists():
            try:
                self.local_compressed.unlink()
                logger.info(f"✓ Removed temp file: {self.local_compressed}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file: {e}")

    def _setup_iscsi_image(self, decompressed_image: Path) -> None:
        """
        Setup iSCSI image using setup-tftp-iscsi.sh script.

        Args:
            decompressed_image: Path to decompressed image file.
                Can be in /tmp/ (initial setup from clean image) or /srv/iscsi/ (restart using working image).
        """
        # Resolve to absolute paths to handle any symlinks
        source_path = decompressed_image.resolve()
        target_path = (Path("/srv/iscsi") / decompressed_image.name).resolve()

        logger.info(f"iSCSI setup: source={source_path}, target={target_path}")

        # Derive SSH public key path from private key path
        # The script expects the PUBLIC key, not the private key
        ssh_public_key = ""
        if self.config.ssh_key:
            # Assume public key is at private_key.pub (e.g., id_rsa -> id_rsa.pub)
            ssh_public_key_path = self.config.ssh_key.with_suffix(self.config.ssh_key.suffix + ".pub")
            if ssh_public_key_path.exists():
                ssh_public_key = str(ssh_public_key_path)
                logger.info(f"Using SSH public key: {ssh_public_key}")
            else:
                logger.warning(f"SSH key provided but public key not found at: {ssh_public_key_path}")

        # Build command
        script_path = Path(__file__).parent.parent / "setup-tftp-iscsi.sh"
        cmd = [
            "stdbuf",
            "-oL",
            "bash",
            str(script_path),
            str(source_path),
            str(target_path),
        ]
        if ssh_public_key:
            cmd.append(ssh_public_key)
        else:
            cmd.append("")  # Empty string for ssh_public_key if not provided

        # Add iscsi_server_ip as the 4th argument
        cmd.append(self.iscsi_server_ip)

        # Add flag_filename as the 5th argument (optional)
        if hasattr(self, "flag_filename") and self.flag_filename:
            cmd.append(self.flag_filename)
            logger.info(f"Flag file will be created: /boot/firmware/{self.flag_filename}")
        else:
            cmd.append("")  # Empty string if no flag file

        logger.info(f"Running: {' '.join(cmd)}")

        # Run with real-time output
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

        if process.stdout:
            for line in process.stdout:
                logger.info(line.rstrip())

        returncode = process.wait()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)

        logger.info("✓ iSCSI setup complete")

        # Wait for tgt to fully initialize and expose the backing store
        # The tgt service needs time to parse config and create LUNs
        logger.info("Waiting for iSCSI target to fully initialize...")
        time.sleep(3)

        # Verify iSCSI target is properly configured (with retries)
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Verification attempt {attempt}/{max_attempts}")
            if self._verify_iscsi_target(target_path):
                break

            if attempt < max_attempts:
                logger.warning("Verification failed, waiting 2 seconds before retry...")
                time.sleep(2)
        else:
            raise RuntimeError("iSCSI target verification failed after all retries - disk LUN not exposed")

    def _verify_iscsi_target(self, expected_image_path: Path) -> bool:
        """
        Verify iSCSI target is properly configured with backing store.

        Args:
            expected_image_path: Path to the image file that should be exposed

        Returns:
            True if target is properly configured, False otherwise
        """
        logger.info("Verifying iSCSI target configuration...")

        try:
            result = subprocess.run(
                ["tgtadm", "--lld", "iscsi", "--op", "show", "--mode", "target"],
                capture_output=True,
                text=True,
                check=True,
            )

            # Check for backing store
            if str(expected_image_path) in result.stdout:
                logger.info(f"✓ iSCSI backing store verified: {expected_image_path}")

                # Check for LUN 1 (the actual disk)
                # LUN 0 is always the controller, LUN 1 should be the disk
                if "LUN: 1" in result.stdout and "Type: disk" in result.stdout:
                    logger.info("✓ iSCSI LUN 1 (disk) is exposed")
                    return True
                else:
                    logger.error("✗ iSCSI LUN 1 (disk) is NOT exposed!")
                    logger.error("This will cause boot to fail with '/dev/sda2 does not exist'")
                    logger.error("Target output:")
                    logger.error(result.stdout)
                    return False
            else:
                logger.error(f"✗ Backing store not found in iSCSI target: {expected_image_path}")
                logger.error("Target output:")
                logger.error(result.stdout)
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to query iSCSI target: {e}")
            if e.stderr:
                logger.error(f"Error output: {e.stderr}")
            return False

    def _try_ssh_shutdown(self) -> None:
        """Try to shutdown via SSH (graceful)."""
        ssh_key = str(self.config.ssh_key) if self.config.ssh_key else ""

        ssh_cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no"]
        if ssh_key:
            ssh_cmd.extend(["-i", ssh_key])
        ssh_cmd.extend([f"root@{self.rpi_ip}", "shutdown now"])

        try:
            subprocess.run(ssh_cmd, capture_output=True, timeout=15)
            logger.info("Sent shutdown command via SSH")
        except Exception as e:
            logger.warning(f"SSH shutdown failed: {e}")

    def _wait_for_system_down(self, timeout_seconds: int = 60) -> bool:
        """Wait for system to go down."""
        logger.info(f"Waiting for {self.rpi_ip} to go down...")

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            result = subprocess.run(["ping", "-c", "1", "-W", "2", self.rpi_ip], capture_output=True)
            if result.returncode != 0:
                logger.info("✓ System is down")
                return True
            time.sleep(2)

        logger.warning(f"System did not go down within {timeout_seconds}s")
        return False

    def _power_toggle(self, turn_on: bool) -> bool:
        """Toggle power using configured script."""
        cmd = [str(self.power_toggle_script), "on" if turn_on else "off"]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            action = "on" if turn_on else "off"
            logger.info(f"✓ Power toggled {action}")
            return True
        else:
            logger.error(f"Power toggle failed: {result.stderr}")
            return False

    def _wait_for_feeder_online(self) -> bool:
        """
        Wait for feeder to come online and verify correct image.

        Implements dual timeout loop with restart callback on hang detection.
        Uses grace period after restarts to avoid false positives from stale serial data.
        """
        logger.info(f"Waiting for feeder at {self.rpi_ip} to come online...")

        # Shutdown hang patterns for serial console detection
        shutdown_hang_patterns = [
            "Failed to send WATCHDOG",
            "Syncing filesystems and block devices - timed out, issuing SIGKILL",
            "rejecting I/O to offline device",
            "Failed to execute shutdown binary",
            "Transport endpoint is not connected",
            "Job networking.service/stop running",
            "I/O error, dev sda",  # iSCSI root filesystem errors during reboot
        ]

        outer_start_time = time.time()
        outer_timeout_seconds = self.config.timeout_minutes * 60
        grace_period_until = time.time() + 90  # 90s grace after start/restart
        ping_down_since = None  # Track when continuous ping down started
        seen_first_boot = False

        while time.time() - outer_start_time < outer_timeout_seconds:
            # Inner loop: 10 iterations of 10-second checks
            for inner_count in range(10):
                try:
                    # Step 1: Check ping
                    result = subprocess.run(["ping", "-c", "1", "-W", "2", self.rpi_ip], capture_output=True)
                    if result.returncode != 0:
                        # Ping is down
                        if ping_down_since is None:
                            ping_down_since = time.time()
                        ping_down_duration = time.time() - ping_down_since

                        logger.info(f"ping down ({ping_down_duration:.0f}s)")

                        # Check for hangs only after grace period
                        if time.time() > grace_period_until:
                            # Check for successful reboot completion (iSCSI boot needs restart)
                            # When system reaches reboot.target and ping is down, it has cleanly shut down
                            # and is waiting for iSCSI to come back - we need to sync boot files immediately
                            if self.serial_reader and seen_first_boot:
                                if self.serial_reader.search_recent("Reached target reboot.target", 5):
                                    logger.info("System reached reboot.target and ping is down")
                                    self._show_serial_context()
                                    logger.info("Syncing boot files and restarting...")
                                    try:
                                        self._restart_after_hang()
                                    except Exception as e:
                                        logger.error(f"Restart failed: {e}", exc_info=True)
                                        return False
                                    # Reset timers
                                    outer_start_time = time.time()
                                    grace_period_until = time.time() + 90
                                    ping_down_since = None
                                    seen_first_boot = False
                                    break

                            # Check for shutdown hang patterns in serial console
                            if self.serial_reader:
                                import re

                                pattern = "|".join(re.escape(p) for p in shutdown_hang_patterns)
                                if self.serial_reader.search_recent(pattern, max_lines=15, regex=True):
                                    logger.warning("Detected shutdown hang in serial console")
                                    self._show_serial_context()
                                    logger.warning("Triggering restart...")
                                    try:
                                        self._restart_after_hang()
                                    except Exception as e:
                                        logger.error(f"Restart failed: {e}", exc_info=True)
                                        return False
                                    # Reset timers
                                    outer_start_time = time.time()
                                    grace_period_until = time.time() + 90
                                    ping_down_since = None
                                    seen_first_boot = False
                                    break

                            # Check for iSCSI driver failure (initramfs prompt)
                            if self.serial_reader and self.serial_reader.search_recent(
                                "Enter 'help' for a list of built-in commands.", 15
                            ):
                                logger.error("iSCSI driver not found in initramfs")
                                self._show_serial_context()
                                logger.warning("Triggering restart with image rebuild...")
                                try:
                                    self._restart_with_rebuild()
                                except Exception as e:
                                    logger.error(f"Restart with rebuild failed: {e}", exc_info=True)
                                    return False
                                # Reset timers
                                outer_start_time = time.time()
                                grace_period_until = time.time() + 90
                                ping_down_since = None
                                seen_first_boot = False
                                break

                            # Check for ping down timeout (after first boot, during reboot)
                            if seen_first_boot and ping_down_duration > 120:
                                logger.warning(f"Ping down for {ping_down_duration:.0f}s after first boot")
                                self._show_serial_context()
                                logger.warning("Triggering restart...")
                                try:
                                    self._restart_after_hang()
                                except Exception as e:
                                    logger.error(f"Restart failed: {e}", exc_info=True)
                                    return False
                                # Reset timers
                                outer_start_time = time.time()
                                grace_period_until = time.time() + 90
                                ping_down_since = None
                                seen_first_boot = False
                                break
                        else:
                            grace_remaining = grace_period_until - time.time()
                            logger.info(f"  (grace period: {grace_remaining:.0f}s remaining)")

                        self._show_serial_context()
                        time.sleep(10)
                        continue

                    # Ping is up - reset ping down timer
                    ping_down_since = None

                    # Step 2: Check web server and get HTTP response
                    response = requests.get(f"http://{self.rpi_ip}/", timeout=10)

                    if response.status_code != 200:
                        logger.info(f"ping up | HTTP {response.status_code}")
                        time.sleep(10)
                        continue

                    # Got HTTP 200
                    content = response.text

                    # Extract page title
                    title = ""
                    if "<title>" in content and "</title>" in content:
                        title = content.split("<title>")[1].split("</title>")[0].strip()

                    # Detect first or second boot
                    if "First boot of ADS-B Feeder System" in title:
                        logger.info("ping up | HTTP 200 | First boot in progress")
                        seen_first_boot = True
                        time.sleep(10)
                        continue
                    elif "Second boot of ADS-B Feeder System" in title:
                        logger.info("ping up | HTTP 200 | Second boot in progress")
                        time.sleep(10)
                        continue

                    # Check for expected image name
                    if self.expected_image_name and self.expected_image_name in content:
                        logger.info(f"ping up | HTTP 200 | correct image: {self.expected_image_name}")
                        logger.info(f"✓ Correct image running: {self.expected_image_name}")
                        return True

                    # Page loaded but expected image not found and not boot page
                    if "boot of ADS-B Feeder System" not in content:
                        logger.error(f"Wrong image running (expected: {self.expected_image_name})")
                        return False

                    # Still waiting
                    logger.debug(f"ping up | HTTP 200 | title: {title}")

                except requests.exceptions.RequestException as e:
                    logger.info(f"HTTP exception: {e.__class__.__name__}")
                except Exception as e:
                    logger.error(f"Error during network check: {e}", exc_info=True)

                time.sleep(10)

        logger.error(f"System did not come online within {self.config.timeout_minutes} minutes")
        return False

    def _show_serial_context(self, num_lines: int = 3) -> None:
        """Show the last N lines from serial console for debugging."""
        if not self.serial_reader or not self.serial_reader.is_running():
            return

        try:
            recent_lines = self.serial_reader.get_recent(num_lines)
            if recent_lines:
                logger.info(f"  Serial console (last {len(recent_lines)} lines):")
                for line in recent_lines:
                    logger.info(f"    {line}")
        except Exception as e:
            logger.debug(f"  (Could not read serial console: {e})")

    def _restart_after_hang(self) -> None:
        """
        Restart system after detecting a hang during shutdown/reboot.

        Re-runs iSCSI setup on the CURRENT WORKING IMAGE in /srv/iscsi/ to sync
        boot kernel and modules. This does NOT rebuild from the compressed original,
        allowing installations to continue progressing.
        """
        logger.info("Restarting system after hang detection...")

        # Power cycle
        logger.info("Powering off...")
        self._power_toggle(turn_on=False)
        time.sleep(10)

        # Re-setup iSCSI using CURRENT WORKING IMAGE (not the clean cached one)
        # This syncs boot kernel from root filesystem to ensure modules match
        logger.info("Re-running iSCSI setup to sync boot kernel from current working image...")
        if self.expected_image_name:
            working_image = Path("/srv/iscsi") / self.expected_image_name
            if working_image.exists():
                logger.info(f"Using current working image: {working_image}")
                self._setup_iscsi_image(working_image)
            else:
                logger.error(f"Could not find working image: {working_image}")
                raise RuntimeError(f"Working image not found: {working_image}")

        # Power on
        logger.info("Powering on...")
        self._power_toggle(turn_on=True)
        time.sleep(60)

    def _restart_with_rebuild(self) -> None:
        """
        Restart system after rebuilding image from compressed original.

        Used when iSCSI driver is missing from initramfs.
        """
        logger.info("Rebuilding image from compressed original...")

        # Power cycle
        logger.info("Powering off...")
        self._power_toggle(turn_on=False)
        time.sleep(10)

        # Rebuild image from compressed original
        if self.expected_image_name:
            cache_dir = Path("/tmp")
            compressed_image = cache_dir / f"{self.expected_image_name}.xz"
            decompressed_image = cache_dir / self.expected_image_name

            if compressed_image.exists():
                # Remove old decompressed image
                decompressed_image.unlink(missing_ok=True)

                # Decompress fresh copy
                logger.info(f"Decompressing fresh image from {compressed_image}")
                subprocess.run(["xz", "-d", "-k", str(compressed_image)], check=True)
                logger.info(f"Decompressed to {decompressed_image.stat().st_size / 1024 / 1024:.1f} MB")

                # Setup iSCSI
                self._setup_iscsi_image(decompressed_image)
            else:
                logger.error(f"Could not find compressed image: {compressed_image}")
                logger.error("Cannot rebuild image")
                raise RuntimeError("Cannot rebuild image - compressed file not found")

        # Power on
        logger.info("Powering on...")
        self._power_toggle(turn_on=True)
        time.sleep(60)

    def _start_serial_console(self) -> None:
        """Start serial console monitoring."""
        if not self.serial_console:
            return

        # Create log directory if it doesn't exist
        self.serial_log_dir.mkdir(parents=True, exist_ok=True)

        # Generate real-time log filename
        if self.config.metrics_id:
            realtime_log_file = str(self.serial_log_dir / f"serial-console-test-{self.config.metrics_id}.log")
            log_prefix = f"serial-{self.config.metrics_id}"
        else:
            import time as time_module

            timestamp = int(time_module.time())
            realtime_log_file = str(self.serial_log_dir / f"serial-console-{timestamp}.log")
            log_prefix = "serial"

        logger.info(f"Starting serial console monitoring: {self.serial_console}")
        logger.info(f"Serial log file: {realtime_log_file}")

        try:
            self.serial_reader = SerialConsoleReader(
                device_path=self.serial_console,
                baud_rate=self.serial_baud,
                log_prefix=log_prefix,
                realtime_log_file=realtime_log_file,
            )

            if self.serial_reader.start():
                logger.info(f"✓ Serial console monitoring enabled: {self.serial_console}")
                logger.info(f"✓ Real-time serial logging to: {realtime_log_file}")
            else:
                logger.warning("⚠️  Serial console monitoring failed to start")
                self.serial_reader = None
        except Exception as e:
            logger.error(f"Failed to start serial console reader: {e}")
            self.serial_reader = None

    def _save_serial_log(self) -> None:
        """Save serial console log to file."""
        if not self.serial_reader or not self.serial_reader.is_running():
            logger.debug("No serial reader running, skipping log save")
            return

        try:
            # Create logs directory if needed
            self.serial_log_dir.mkdir(parents=True, exist_ok=True)

            # Generate log filename
            if self.config.metrics_id:
                log_file = self.serial_log_dir / f"serial-console-test-{self.config.metrics_id}.log"
            else:
                import time as time_module

                timestamp = int(time_module.time())
                log_file = self.serial_log_dir / f"serial-console-{timestamp}.log"

            # Note: The real-time log file already exists from SerialConsoleReader
            # We just need to ensure the buffer is also saved
            buffer_size = self.serial_reader.get_buffer_size()
            logger.info(f"Serial console captured {buffer_size} lines")
            logger.info(f"Serial console log available at: {log_file}")

        except Exception as e:
            logger.warning(f"Error reporting serial log info: {e}")

    def _copy_setup_log(self) -> None:
        """Copy the adsb-feeder-image.log from RPi to local server."""
        try:
            # Create logs directory if needed
            setup_log_dir = Path("/opt/adsb-boot-test/setup-logs")
            setup_log_dir.mkdir(parents=True, exist_ok=True)

            # Generate log filename
            if self.config.metrics_id:
                local_log_file = setup_log_dir / f"adsb-feeder-image-{self.config.metrics_id}.log"
            else:
                timestamp = int(time.time())
                local_log_file = setup_log_dir / f"adsb-feeder-image-{timestamp}.log"

            # Build ssh command to cat the file and redirect to local file
            # This avoids scp/sftp-server requirement and known_hosts issues
            ssh_key = str(self.config.ssh_key) if self.config.ssh_key else ""
            ssh_cmd = [
                "ssh",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
            ]
            if ssh_key:
                ssh_cmd.extend(["-i", ssh_key])
            ssh_cmd.extend([f"root@{self.rpi_ip}", "cat /run/adsb-feeder-image.log"])

            logger.info(f"Copying setup log from RPi to {local_log_file}...")
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                # Write the output to the local file
                local_log_file.write_text(result.stdout)
                logger.info(f"✓ Setup log copied to: {local_log_file}")
            else:
                logger.warning(f"Failed to copy setup log: {result.stderr}")

        except subprocess.TimeoutExpired:
            logger.warning("Setup log copy timed out")
        except Exception as e:
            logger.warning(f"Failed to copy setup log: {e}")
