"""VM testing backend using libvirt/KVM."""

import logging
import re
import socket
import time
from pathlib import Path
from typing import Optional

import requests
from boot_test_lib.download import ImageDownloader, ImageInfo
from boot_test_lib.remote import VirshRemote

from .base import HardwareBackend, TestConfig

logger = logging.getLogger(__name__)


class VMLibvirtBackend(HardwareBackend):
    """Test backend for qcow2 VMs via libvirt."""

    def __init__(
        self,
        config: TestConfig,
        vm_server: str,
        vm_ssh_key: Path,
        vm_bridge: str,
        vm_memory_mb: int = 1024,
        vm_cpus: int = 2,
    ):
        """
        Initialize VM libvirt backend.

        Args:
            config: Test configuration
            vm_server: IP/hostname of VM server
            vm_ssh_key: Path to SSH key for VM server
            vm_bridge: Bridge interface name on VM server
            vm_memory_mb: VM memory in MB
            vm_cpus: Number of VM CPUs
        """
        super().__init__(config)
        self.vm_server = vm_server
        self.vm_ssh_key = vm_ssh_key
        self.vm_bridge = vm_bridge
        self.vm_memory_mb = vm_memory_mb
        self.vm_cpus = vm_cpus

        # Initialize remote connection
        self.remote = VirshRemote(vm_server, str(vm_ssh_key))

        # VM details (set during preparation)
        self.vm_name = "adsb-vm-test"
        self.remote_work_dir = "/tmp"
        self.remote_compressed: Optional[str] = None
        self.remote_qcow2: Optional[str] = None
        self.vm_ip: Optional[str] = None
        self.expected_image_name: Optional[str] = None

    def prepare_environment(self) -> None:
        """Download, transfer, and decompress VM image."""
        # Parse image info
        image_info = ImageInfo.from_url(self.config.image_url)
        self.expected_image_name = image_info.expected_name
        logger.info(f"Image type: {image_info.image_type}")
        logger.info(f"Expected name: {image_info.expected_name}")

        # Clean up any existing VM with same name
        self._cleanup_existing_vm()

        # Download image locally
        logger.info("=" * 70)
        logger.info("Stage 1: Download image")
        logger.info("=" * 70)

        downloader = ImageDownloader(cache_dir=Path("/tmp"))
        local_path = downloader.download(image_info)

        # Transfer to VM server
        logger.info("=" * 70)
        logger.info("Stage 2: Transfer to VM server")
        logger.info("=" * 70)

        self.remote_compressed = f"{self.remote_work_dir}/{self.vm_name}.qcow2.xz"
        self.remote_qcow2 = f"{self.remote_work_dir}/{self.vm_name}.qcow2"

        # Remove old files on remote
        self.remote.execute(f"rm -f {self.remote_compressed} {self.remote_qcow2}")

        # Upload using SCP
        if not self.remote.scp_upload(local_path, self.remote_compressed):
            raise RuntimeError("Failed to transfer image to VM server")

        # Decompress on server
        logger.info("=" * 70)
        logger.info("Stage 3: Decompress image on server")
        logger.info("=" * 70)

        self._decompress_remote_image()

        # Create VM
        logger.info("=" * 70)
        logger.info("Stage 4: Create VM")
        logger.info("=" * 70)

        self._create_vm()

    def boot_system(self) -> None:
        """VM is auto-started by virt-install with --import."""
        logger.info(f"VM {self.vm_name} should be running " "(auto-started by virt-install)")

        # Verify VM is running
        result = self.remote.virsh(f"domstate {self.vm_name}")
        if result.returncode == 0:
            state = result.stdout.strip()
            logger.info(f"VM state: {state}")
        else:
            logger.warning("Could not verify VM state")

    def wait_for_network(self) -> str:
        """
        Wait for VM to get IP address and boot to completion.

        Returns:
            VM IP address

        Raises:
            TimeoutError: If IP not obtained within timeout
            RuntimeError: If boot doesn't complete or wrong image
        """
        logger.info("=" * 70)
        logger.info("Stage 5: Wait for system online")
        logger.info("=" * 70)

        # First get IP address
        ip = self._get_ip_address(max_attempts=30, wait_seconds=2)
        if not ip:
            raise TimeoutError("VM did not obtain IP address within timeout")

        self.vm_ip = ip
        logger.info(f"✓ VM IP: {ip}")

        # Wait for boot to complete
        if not self._wait_for_boot_complete(ip):
            raise RuntimeError("Boot did not complete or wrong image running")

        return ip

    def cleanup(self) -> None:
        """Destroy VM and remove disk files."""
        logger.info("=" * 70)
        logger.info("Cleanup: Destroying VM and removing files")
        logger.info("=" * 70)

        # Destroy VM
        result = self.remote.virsh(f"destroy {self.vm_name}")
        if result.returncode == 0:
            logger.info("✓ VM destroyed")

        # Undefine VM
        result = self.remote.virsh(f"undefine {self.vm_name}")
        if result.returncode == 0:
            logger.info("✓ VM undefined")

        # Remove disk files
        if self.remote_qcow2:
            self.remote.execute(f"rm -f {self.remote_qcow2}")
            logger.info(f"✓ Removed: {self.remote_qcow2}")

        if self.remote_compressed:
            self.remote.execute(f"rm -f {self.remote_compressed}")
            logger.info(f"✓ Removed: {self.remote_compressed}")

    def _cleanup_existing_vm(self) -> None:
        """Clean up any existing VM with same name."""
        logger.info(f"Cleaning up any existing VM: {self.vm_name}")

        # Try to destroy if running
        result = self.remote.virsh(f"destroy {self.vm_name}")
        if result.returncode == 0:
            logger.info(f"Destroyed running VM: {self.vm_name}")

        # Try to undefine
        result = self.remote.virsh(f"undefine {self.vm_name}")
        if result.returncode == 0:
            logger.info(f"Undefined VM: {self.vm_name}")

    def _decompress_remote_image(self) -> None:
        """Decompress xz image on remote server."""
        logger.info(f"Decompressing: {self.remote_compressed} " f"-> {self.remote_qcow2}")

        # Check if already decompressed
        check_result = self.remote.execute(f"test -f {self.remote_qcow2} && echo exists")
        if check_result.returncode == 0 and "exists" in check_result.stdout:
            logger.info("✓ Decompressed image already exists, skipping")
            return

        # Decompress using xz (streaming)
        decompress_cmd = f"xz -d -k -c {self.remote_compressed} > {self.remote_qcow2}"
        process = self.remote.execute_streaming(decompress_cmd)

        # Wait for completion
        returncode = process.wait()

        if returncode != 0:
            raise RuntimeError(f"Failed to decompress image (exit code: {returncode})")

        logger.info("✓ Image decompressed successfully")

    def _create_vm(self) -> None:
        """Create VM using virt-install."""
        logger.info(f"Creating VM: {self.vm_name}")

        virt_install_cmd = [
            "virt-install",
            "--connect qemu:///system",
            f"--name {self.vm_name}",
            f"--memory {self.vm_memory_mb}",
            f"--vcpus {self.vm_cpus}",
            f"--disk path={self.remote_qcow2},format=qcow2,bus=virtio",
            f"--network bridge={self.vm_bridge},model=virtio",
            "--graphics vnc,listen=0.0.0.0",
            "--noautoconsole",
            "--import",
            "--osinfo detect=on,name=linux2024",
        ]

        virt_install_str = " ".join(virt_install_cmd)

        # Execute virt-install with real-time output
        process = self.remote.execute_streaming(virt_install_str)

        # Stream output
        if process.stdout:
            for line in process.stdout:
                logger.info(line.rstrip())

        returncode = process.wait()

        if returncode != 0:
            raise RuntimeError(f"Failed to create VM (exit code: {returncode})")

        logger.info(f"✓ VM created and started: {self.vm_name}")

    def _get_ip_address(self, max_attempts: int = 30, wait_seconds: int = 2) -> Optional[str]:
        """
        Get VM IP address via DHCP leases.

        Args:
            max_attempts: Maximum number of attempts
            wait_seconds: Seconds to wait between attempts

        Returns:
            IP address or None
        """
        logger.info("Waiting for VM to get IP address...")

        for attempt in range(max_attempts):
            # Try dnsmasq leases (works when DHCP is managed locally)
            ip = self._get_ip_from_dnsmasq_leases()
            if ip:
                return ip

            # Fallback: try virsh domifaddr
            result = self.remote.virsh(f"domifaddr {self.vm_name} --source lease")
            if result.returncode == 0:
                # Parse output for IP address
                match = re.search(r"ipv4\s+(\d+\.\d+\.\d+\.\d+)/", result.stdout)
                if match:
                    ip = match.group(1)
                    logger.info(f"✓ Found IP address via virsh: {ip}")
                    return ip

            logger.debug(f"Attempt {attempt + 1}/{max_attempts}: No IP yet...")
            time.sleep(wait_seconds)

        logger.warning("Could not determine IP address")
        return None

    def _get_ip_from_dnsmasq_leases(self, leases_file: str = "/var/lib/misc/dnsmasq.leases") -> Optional[str]:
        """Get VM IP from dnsmasq leases file."""
        # Get VM MAC address
        result = self.remote.virsh(f"domiflist {self.vm_name}")
        if result.returncode != 0:
            return None

        # Parse MAC address
        mac_match = re.search(
            r"([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:" r"[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})",
            result.stdout,
            re.IGNORECASE,
        )
        if not mac_match:
            return None

        vm_mac = mac_match.group(1).lower()

        # Read dnsmasq leases file
        try:
            with open(leases_file, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        lease_mac = parts[1].lower()
                        lease_ip = parts[2]
                        if lease_mac == vm_mac:
                            logger.info(f"✓ Found IP in dnsmasq leases: {lease_ip}")
                            return lease_ip
        except FileNotFoundError:
            logger.debug(f"Leases file not found: {leases_file}")
        except Exception as e:
            logger.debug(f"Error reading leases file: {e}")

        return None

    def _wait_for_boot_complete(self, ip: str) -> bool:
        """
        Wait for VM boot to complete and verify correct image.

        Implements dual timeout loop consistent with RPi backend (without restart callbacks).

        Args:
            ip: VM IP address

        Returns:
            True if boot completed with correct image, False otherwise
        """
        logger.info("Waiting for boot to complete and verifying image...")

        outer_start_time = time.time()
        outer_timeout_seconds = self.config.timeout_minutes * 60

        while time.time() - outer_start_time < outer_timeout_seconds:
            # Inner loop: short timeout for individual checks
            inner_loop_count = 0
            max_inner_loops = 10

            while inner_loop_count < max_inner_loops:
                status_string = ""

                try:
                    # Step 1: Check web server
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((ip, 80))
                    sock.close()

                    if result != 0:
                        status_string = "web server down"
                        logger.debug(f"{status_string} - wait 10 seconds")
                        time.sleep(10)
                        inner_loop_count += 1
                        continue

                    status_string = "web server up"

                    # Step 2: Try HTTP request
                    response = requests.get(f"http://{ip}/", timeout=10)
                    status_string += f" HTTP {response.status_code}"

                    if response.status_code == 200:
                        content = response.text

                        # Extract page title
                        if "<title>" in content and "</title>" in content:
                            title = content.split("<title>")[1].split("</title>")[0].strip()
                            status_string += f" | title: {title}"

                            # Detect first or second boot
                            if "First boot of ADS-B Feeder System" in title:
                                logger.info(f"{status_string} | First boot in progress")
                            elif "Second boot of ADS-B Feeder System" in title:
                                logger.info(f"{status_string} | Second boot in progress")

                        # Step 3: Check for expected image name
                        if self.expected_image_name and self.expected_image_name in content:
                            status_string += f" | correct image: {self.expected_image_name}"
                            logger.info(status_string)
                            logger.info(f"✓ Boot complete with correct image: {self.expected_image_name}")
                            return True
                        elif "boot of ADS-B Feeder System" not in content:
                            # Page loaded but not boot page and image not found
                            status_string += f" | can't find expected image: {self.expected_image_name}"
                            logger.warning(status_string)
                            logger.error(f"Wrong image running (expected: {self.expected_image_name})")
                            return False

                        # Still on boot page, keep waiting
                        logger.debug(status_string)

                except requests.exceptions.RequestException as e:
                    status_string += f" | HTTP exception: {e.__class__.__name__}"
                    logger.debug(status_string)
                except Exception as e:
                    logger.debug(f"Error during boot check: {e}")

                time.sleep(10)
                inner_loop_count += 1

        logger.error(f"Boot did not complete within {self.config.timeout_minutes} minutes")
        return False
