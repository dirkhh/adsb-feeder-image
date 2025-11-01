#!/usr/bin/env python3
"""
VM Image Testing Script

Tests qcow2 VM images by:
1. Downloading image to local /tmp
2. Transferring to VM server via SCP
3. Decompressing on server
4. Creating VM with virt-install
5. Waiting for IP via DHCP
6. Running Selenium tests
7. Updating metrics database
8. Cleaning up (destroy VM, remove disk)

This script graduates proven code from test_qcow2_vm.py POC into production.
"""

import argparse
import logging
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

# Configure line-buffered output for real-time logging when running as systemd service
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr,attr-defined]
sys.stderr.reconfigure(line_buffering=True)  # type: ignore[union-attr,attr-defined]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def update_metrics_stage(metrics_id: Optional[int], metrics_db: str, stage: str, status: str):
    """Update metrics stage if metrics tracking is enabled."""
    if metrics_id is None:
        return

    try:
        metrics = TestMetrics(db_path=metrics_db)
        metrics.update_stage(metrics_id, stage, status)
    except Exception as e:
        logger.warning(f"Failed to update metrics: {e}")


class VirshRemote:
    """Execute virsh commands on a remote system via SSH."""

    def __init__(self, remote_host: str, ssh_identity: Optional[str] = None):
        """
        Initialize remote virsh connection.

        Args:
            remote_host: Remote host IP/hostname
            ssh_identity: Path to SSH identity file
        """
        self.remote_host = remote_host
        self.ssh_identity = ssh_identity

        # Build SSH options
        ssh_opts = []
        if ssh_identity:
            ssh_opts.extend(["-i", ssh_identity])
        ssh_opts.extend(["-o", "StrictHostKeyChecking=no"])
        ssh_opts.extend(["-o", "UserKnownHostsFile=/dev/null"])
        ssh_opts.extend(["-o", "LogLevel=ERROR"])

        self.ssh_opts = " ".join(ssh_opts) if ssh_opts else ""

    def execute(self, virsh_command: str) -> subprocess.CompletedProcess:
        """
        Execute a virsh command on the remote system.

        Args:
            virsh_command: virsh subcommand (e.g., "list", "dominfo vm-name")

        Returns:
            CompletedProcess with returncode, stdout, stderr
        """
        full_command = f"virsh --connect qemu:///system {virsh_command}"
        return self.ssh_execute(full_command)

    def ssh_execute(self, command: str) -> subprocess.CompletedProcess:
        """
        Execute arbitrary command on remote system via SSH.

        Args:
            command: Command to execute

        Returns:
            CompletedProcess with returncode, stdout, stderr
        """
        ssh_cmd = f"ssh {self.ssh_opts} {self.remote_host} '{command}'"

        result = subprocess.run(
            ssh_cmd,
            shell=True,
            capture_output=True,
            text=True,
        )

        return result


class QCOW2VMTester:
    """Manages VM lifecycle for qcow2 image testing."""

    def __init__(
        self,
        remote: VirshRemote,
        vm_name: str = "adsb-vm-test",
        memory_mb: int = 1024,
        cpus: int = 2,
        bridge: str = "bridge77",
        remote_work_dir: str = "/tmp",
    ):
        """
        Initialize qcow2 VM tester.

        Args:
            remote: VirshRemote instance
            vm_name: Name for the test VM
            memory_mb: RAM in megabytes
            cpus: Number of virtual CPUs
            bridge: Bridge network interface
            remote_work_dir: Working directory on remote server
        """
        self.remote = remote
        self.vm_name = vm_name
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.bridge = bridge
        self.remote_work_dir = remote_work_dir

    def cleanup_existing_vm(self) -> None:
        """Destroy and undefine any existing VM with the same name."""
        logger.info(f"Checking for existing VM: {self.vm_name}")

        # Try to destroy if running
        result = self.remote.execute(f"destroy {self.vm_name}")
        if result.returncode == 0:
            logger.info(f"Destroyed running VM: {self.vm_name}")

        # Try to undefine
        result = self.remote.execute(f"undefine {self.vm_name}")
        if result.returncode == 0:
            logger.info(f"Undefined VM: {self.vm_name}")

    def destroy_vm(self, remove_disk: bool = False, disk_path: Optional[str] = None) -> None:
        """
        Destroy and cleanup VM.

        Args:
            remove_disk: Whether to remove the disk file
            disk_path: Path to disk file on remote (if remove_disk=True)
        """
        logger.info(f"Destroying VM: {self.vm_name}")

        # Destroy (stop) VM
        result = self.remote.execute(f"destroy {self.vm_name}")
        if result.returncode == 0:
            logger.info("✓ VM destroyed")

        # Undefine VM
        result = self.remote.execute(f"undefine {self.vm_name}")
        if result.returncode == 0:
            logger.info("✓ VM undefined")

        # Remove disk if requested
        if remove_disk and disk_path:
            result = self.remote.ssh_execute(f"rm -f {disk_path}")
            if result.returncode == 0:
                logger.info(f"✓ Removed disk: {disk_path}")

    def download_image(self, url: str, local_path: Path) -> bool:
        """
        Download qcow2.xz image from URL.

        Args:
            url: URL to download from
            local_path: Local path to save to

        Returns:
            True if successful
        """
        logger.info(f"Downloading image from: {url}")
        logger.info(f"Saving to: {local_path}")

        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            last_report = 0

            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded > last_report:
                            pct = (downloaded / total_size) * 100
                            logger.info(f"Downloaded: {pct:.1f}% ({downloaded}/{total_size} bytes)")
                            last_report += int(0.05 * total_size)  # Report every 5%

            logger.info(f"✓ Download complete: {local_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            return False

    def transfer_image(self, local_path: Path, remote_path: str) -> bool:
        """
        Transfer image to remote server via SCP.

        Args:
            local_path: Local path to image
            remote_path: Remote path to save to

        Returns:
            True if successful
        """
        logger.info(f"Transferring image to remote server...")
        logger.info(f"Local: {local_path}")
        logger.info(f"Remote: {remote_path}")

        ssh_opts = self.remote.ssh_opts if self.remote.ssh_opts else ""

        ssh_cmd = f"ssh {ssh_opts} {self.remote.remote_host} rm -f {remote_path[:-3]}"

        # Use Popen for real-time output
        process = subprocess.Popen(
            ssh_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output in real-time
        for line in process.stdout:  # type: ignore
            logger.info(line.rstrip())

        returncode = process.wait()

        if returncode != 0:
            logger.error(f"Failed to create delete existing image file (exit code: {returncode})")
            return False

        scp_cmd = f"scp {ssh_opts} {local_path} {self.remote.remote_host}:{remote_path}"

        # Use Popen for real-time output
        process = subprocess.Popen(
            scp_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output in real-time
        for line in process.stdout:  # type: ignore
            logger.info(line.rstrip())

        returncode = process.wait()

        if returncode != 0:
            logger.error(f"Failed to transfer image (exit code: {returncode})")
            return False

        logger.info("✓ Image transferred successfully")
        return True

    def decompress_image(self, compressed_path: str, output_path: str) -> bool:
        """
        Decompress xz image on remote server.

        Args:
            compressed_path: Path to .xz file on remote
            output_path: Path for decompressed .qcow2 file

        Returns:
            True if successful
        """
        logger.info(f"Decompressing image on remote server...")
        logger.info(f"Input: {compressed_path}")
        logger.info(f"Output: {output_path}")

        # Check if already decompressed
        check_result = self.remote.ssh_execute(f"test -f {output_path} && echo exists")
        if check_result.returncode == 0 and "exists" in check_result.stdout:
            logger.info("✓ Decompressed image already exists, skipping")
            return True

        # Decompress using xz
        decompress_cmd = f"xz -d -k -c {compressed_path} > {output_path}"
        result = self.remote.ssh_execute(decompress_cmd)

        if result.returncode != 0:
            logger.error(f"Failed to decompress: {result.stderr}")
            return False

        logger.info("✓ Image decompressed successfully")
        return True

    def create_vm_from_qcow2(self, qcow2_path: str) -> bool:
        """
        Create VM using existing qcow2 image.

        Args:
            qcow2_path: Path to qcow2 file on remote server

        Returns:
            True if successful
        """
        logger.info(f"Creating VM from qcow2 image...")

        # Use virt-install to create VM with existing disk
        virt_install_cmd = [
            "virt-install",
            "--connect qemu:///system",
            f"--name {self.vm_name}",
            f"--memory {self.memory_mb}",
            f"--vcpus {self.cpus}",
            f"--disk path={qcow2_path},format=qcow2,bus=virtio",
            f"--network bridge={self.bridge},model=virtio",
            "--graphics vnc,listen=0.0.0.0",  # Enable VNC for debugging
            "--noautoconsole",
            "--import",  # Important: use existing disk, don't reinstall
            "--osinfo detect=on,name=linux2024",
        ]

        virt_install_str = " ".join(virt_install_cmd)

        # Build SSH command for real-time output
        ssh_opts = self.remote.ssh_opts if self.remote.ssh_opts else ""
        ssh_cmd = f"ssh {ssh_opts} {self.remote.remote_host} {virt_install_str}"

        # Use Popen for real-time output
        process = subprocess.Popen(
            ssh_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output in real-time
        for line in process.stdout:  # type: ignore
            logger.info(line.rstrip())

        returncode = process.wait()

        if returncode != 0:
            logger.error(f"Failed to create VM (exit code: {returncode})")
            return False

        logger.info(f"✓ VM created: {self.vm_name}")
        return True

    def get_vnc_info(self) -> Optional[str]:
        """
        Get VNC connection information.

        Returns:
            VNC display information or None
        """
        result = self.remote.execute(f"vncdisplay {self.vm_name}")
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None

    def get_ip_from_dnsmasq_leases(self, leases_file: str = "/var/lib/misc/dnsmasq.leases") -> Optional[str]:
        """
        Get VM IP address from local dnsmasq leases file.

        Args:
            leases_file: Path to dnsmasq leases file

        Returns:
            IP address or None
        """
        # First get the VM's MAC address
        result = self.remote.execute(f"domiflist {self.vm_name}")
        if result.returncode != 0:
            return None

        # Parse MAC address from output
        mac_match = re.search(
            r"([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})",
            result.stdout,
            re.IGNORECASE,
        )
        if not mac_match:
            logger.debug("Could not find VM MAC address")
            return None

        vm_mac = mac_match.group(1).lower()
        logger.debug(f"VM MAC address: {vm_mac}")

        # Read local dnsmasq leases file
        try:
            with open(leases_file, "r") as f:
                for line in f:
                    # Format: timestamp mac ip hostname client-id
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        lease_mac = parts[1].lower()
                        lease_ip = parts[2]
                        if lease_mac == vm_mac:
                            logger.info(f"✓ Found IP in dnsmasq leases: {lease_ip}")
                            return lease_ip
        except FileNotFoundError:
            logger.warning(f"Leases file not found: {leases_file}")
        except Exception as e:
            logger.warning(f"Error reading leases file: {e}")

        return None

    def get_ip_address(self, max_attempts: int = 30, wait_seconds: int = 2) -> Optional[str]:
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
            # First try dnsmasq leases (works when DHCP is managed locally)
            ip = self.get_ip_from_dnsmasq_leases()
            if ip:
                return ip

            # Fallback: try virsh domifaddr
            result = self.remote.execute(f"domifaddr {self.vm_name} --source lease")
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

    def wait_for_web_server(self, ip: str, port: int = 80, timeout: int = 60) -> bool:
        """
        Wait for web server to be ready.

        Args:
            ip: IP address of VM
            port: Port to check
            timeout: Timeout in seconds

        Returns:
            True if web server is ready
        """
        import socket

        logger.info(f"Waiting for web server at {ip}:{port}...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((ip, port))
                sock.close()

                if result == 0:
                    logger.info(f"✓ Web server is ready")
                    return True

            except Exception:
                pass

            time.sleep(2)

        logger.warning(f"Web server not ready after {timeout}s")
        return False

    def run_selenium_tests(self, ip: str, script_dir: Path) -> bool:
        """
        Run Selenium tests against the VM.

        Args:
            ip: IP address of VM
            script_dir: Directory containing test scripts

        Returns:
            True if tests passed
        """
        logger.info(f"Running Selenium tests against {ip}...")

        # Use the existing run_selenium_test.py script
        selenium_script = script_dir / "run_selenium_test.py"
        if not selenium_script.exists():
            logger.error(f"Selenium test script not found: {selenium_script}")
            return False

        cmd = [
            "sudo",
            "-u",
            "testuser",
            "env",
            f"HOME=/home/testuser",
            f"{script_dir}/venv/bin/python3",
            "-u",  # Unbuffered output
            str(selenium_script),
            ip,  # Positional argument for rpi_ip
            "--timeout",
            "300",
            "--log-level",
            "INFO",
            "--browser",
            "chrome",
            "--headless",
        ]

        # Use Popen for real-time output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output in real-time
        for line in process.stdout:  # type: ignore
            logger.info(line.rstrip())

        returncode = process.wait()

        if returncode == 0:
            logger.info("✓ Selenium tests passed")
            return True
        else:
            logger.error(f"✗ Selenium tests failed (exit code: {returncode})")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test VM qcow2 images")
    parser.add_argument("image_url", help="URL to qcow2.xz image")
    parser.add_argument("--vm-server", required=True, help="VM server IP address")
    parser.add_argument("--vm-ssh-key", required=True, help="SSH key for VM server")
    parser.add_argument("--vm-bridge", default="bridge77", help="Bridge interface (default: bridge77)")
    parser.add_argument("--vm-memory", type=int, default=1024, help="VM memory in MB (default: 1024)")
    parser.add_argument("--vm-cpus", type=int, default=2, help="VM CPUs (default: 2)")
    parser.add_argument("--metrics-id", type=int, help="Metrics database test ID")
    parser.add_argument("--metrics-db", default="/var/lib/adsb-boot-test/metrics.db", help="Metrics database path")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout in minutes (default: 10)")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("VM Image Testing")
    logger.info("=" * 80)
    logger.info(f"Image URL: {args.image_url}")
    logger.info(f"VM Server: {args.vm_server}")
    logger.info(f"Bridge: {args.vm_bridge}")
    logger.info(f"Memory: {args.vm_memory}MB, CPUs: {args.vm_cpus}")
    parsed_url = urllib.parse.urlparse(args.image_url)
    filename = os.path.basename(parsed_url.path)
    expected_image_name = filename.split("-Proxmox")[0]

    # Expand paths
    ssh_key = str(Path(args.vm_ssh_key).expanduser())
    remote_work_dir = "/tmp"
    vm_name = "adsb-vm-test"
    remote_compressed = f"{remote_work_dir}/{vm_name}.qcow2.xz"
    remote_qcow2 = f"{remote_work_dir}/{vm_name}.qcow2"
    local_image = Path(f"/tmp/{vm_name}.qcow2.xz")
    script_dir = Path(__file__).resolve().parent

    # Initialize remote connection
    remote = VirshRemote(args.vm_server, ssh_identity=ssh_key)

    # Initialize tester
    tester = QCOW2VMTester(
        remote=remote,
        vm_name=vm_name,
        memory_mb=args.vm_memory,
        cpus=args.vm_cpus,
        bridge=args.vm_bridge,
        remote_work_dir=remote_work_dir,
    )

    try:
        # Stage 1: Download
        logger.info("Stage 1: Download")
        update_metrics_stage(args.metrics_id, args.metrics_db, "download", "running")

        if not tester.download_image(args.image_url, local_image):
            update_metrics_stage(args.metrics_id, args.metrics_db, "download", "failed")
            sys.exit(1)

        update_metrics_stage(args.metrics_id, args.metrics_db, "download", "passed")

        # Stage 2: VM Setup (transfer + decompress + create)
        logger.info("Stage 2: VM Setup")
        update_metrics_stage(args.metrics_id, args.metrics_db, "boot", "running")  # "boot" = VM setup

        # Cleanup any existing VM
        tester.cleanup_existing_vm()

        # Transfer image
        if not tester.transfer_image(local_image, remote_compressed):
            update_metrics_stage(args.metrics_id, args.metrics_db, "boot", "failed")
            sys.exit(1)

        # Decompress image
        if not tester.decompress_image(remote_compressed, remote_qcow2):
            update_metrics_stage(args.metrics_id, args.metrics_db, "boot", "failed")
            sys.exit(1)

        # Create VM
        if not tester.create_vm_from_qcow2(remote_qcow2):
            update_metrics_stage(args.metrics_id, args.metrics_db, "boot", "failed")
            sys.exit(1)

        # Get VNC info for debugging
        vnc_display = tester.get_vnc_info()
        if vnc_display:
            logger.info(f"VNC Display: {vnc_display}")
            logger.info(f"Connect via: {args.vm_server}{vnc_display}")

        update_metrics_stage(args.metrics_id, args.metrics_db, "boot", "passed")

        # Stage 3: Network (IP discovery)
        logger.info("Stage 3: Network")
        update_metrics_stage(args.metrics_id, args.metrics_db, "network", "running")

        vm_ip = tester.get_ip_address()
        if not vm_ip:
            logger.error("Could not get VM IP address")
            update_metrics_stage(args.metrics_id, args.metrics_db, "network", "failed")
            sys.exit(1)

        logger.info(f"✓ VM IP: {vm_ip}")

        # Update metrics with VM IP (stored in rpi_ip field)
        if args.metrics_id:
            try:
                metrics = TestMetrics(db_path=args.metrics_db)
                conn = metrics._get_connection()
                conn.execute("UPDATE test_runs SET rpi_ip = ? WHERE id = ?", (vm_ip, args.metrics_id))
                conn.commit()
                metrics._close_connection(conn)
            except Exception as e:
                logger.warning(f"Failed to update VM IP in metrics: {e}")

        update_metrics_stage(args.metrics_id, args.metrics_db, "network", "passed")

        # Wait for web server
        if not tester.wait_for_web_server(vm_ip):
            logger.warning("Web server not responding, tests may fail")

        # Wait for first and second boot to complete
        logger.info("Waiting for first boot to finish and ADS-B setup app to start")
        start_time = time.time()
        status_string = ""
        timeout_seconds = args.timeout * 60
        while time.time() - start_time < timeout_seconds:
            status_string = ""
            response: requests.Response = requests.Response()
            try:
                response = requests.get(f"http://{vm_ip}/", timeout=10)
            except Exception:
                status_string += f" HTTP exception - keep waiting"
                response.status_code = 400
            else:
                status_string += f" HTTP response {response.status_code}"
            if response.status_code == 200:
                content = response.text
                # grab the title from the response
                title = content.split("<title>")[1].split("</title>")[0]
                status_string += f" title: {title.strip()}"

                # Look for the footer line with the image name
                if expected_image_name in content:
                    status_string += f" - correct image: {expected_image_name}"
                    logger.info(status_string)
                    break
                elif "boot of ADS-B Feeder System" not in title:
                    status_string += f" - can't find expected image: {expected_image_name}"
                    logger.info(status_string)
                    break
            time.sleep(10)

        if "correct image" not in status_string:
            logger.info("giving up -- tests failed")
            update_metrics_stage(args.metrics_id, args.metrics_db, "browser_test", "failed")
            sys.exit(1)

        # Stage 4: Browser Test
        logger.info("Stage 4: Browser Test")
        update_metrics_stage(args.metrics_id, args.metrics_db, "browser_test", "running")

        if not tester.run_selenium_tests(vm_ip, script_dir):
            update_metrics_stage(args.metrics_id, args.metrics_db, "browser_test", "failed")
            logger.error("Tests failed")
            sys.exit(1)

        update_metrics_stage(args.metrics_id, args.metrics_db, "browser_test", "passed")

        logger.info("=" * 80)
        logger.info("✓ All tests PASSED")
        logger.info("=" * 80)
        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Always cleanup VM
        logger.info("Cleaning up...")
        try:
            tester.destroy_vm(remove_disk=True, disk_path=remote_qcow2)
            # Also remove compressed file
            remote.ssh_execute(f"rm -f {remote_compressed}")
            # Remove local file
            if local_image.exists():
                local_image.unlink()
                logger.info(f"✓ Removed local image: {local_image}")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


if __name__ == "__main__":
    main()
