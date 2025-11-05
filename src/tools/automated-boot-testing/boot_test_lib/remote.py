"""SSH and SCP utilities for remote operations."""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class SSHRemote:
    """Execute commands on a remote system via SSH."""

    def __init__(self, remote_host: str, ssh_identity: Optional[str] = None, user: str = "root"):
        """
        Initialize remote SSH connection.

        Args:
            remote_host: Remote host IP/hostname
            ssh_identity: Path to SSH identity file
            user: SSH user (default: root)
        """
        self.remote_host = remote_host
        self.ssh_identity = ssh_identity
        self.user = user

        # Build SSH options list
        ssh_opts: List[str] = []
        if ssh_identity:
            ssh_opts.extend(["-i", ssh_identity])
        ssh_opts.extend(["-o", "StrictHostKeyChecking=no"])
        ssh_opts.extend(["-o", "UserKnownHostsFile=/dev/null"])
        ssh_opts.extend(["-o", "LogLevel=ERROR"])

        self.ssh_opts_list = ssh_opts
        self.ssh_opts = " ".join(ssh_opts) if ssh_opts else ""

    def execute(self, command: str, check: bool = False) -> subprocess.CompletedProcess:
        """
        Execute command on remote system via SSH.

        Args:
            command: Command to execute on remote system
            check: If True, raise CalledProcessError on non-zero exit

        Returns:
            CompletedProcess with returncode, stdout, stderr
        """
        full_cmd = ["ssh"] + self.ssh_opts_list + [f"{self.user}@{self.remote_host}", command]

        result = subprocess.run(full_cmd, capture_output=True, text=True, check=check)
        return result

    def execute_streaming(self, command: str) -> subprocess.Popen:
        """
        Execute command with real-time output streaming.

        Args:
            command: Command to execute

        Returns:
            Popen process with stdout/stderr merged
        """
        full_cmd = ["ssh"] + self.ssh_opts_list + [f"{self.user}@{self.remote_host}", command]

        process = subprocess.Popen(
            full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )  # Line buffered

        return process

    def scp_upload(self, local_path: Path, remote_path: str, show_progress: bool = True) -> bool:
        """
        Upload file to remote system via SCP.

        Args:
            local_path: Local file path
            remote_path: Remote destination path
            show_progress: Show transfer progress

        Returns:
            True if successful
        """
        scp_cmd = ["scp"]

        # Add SSH identity if specified
        if self.ssh_identity:
            scp_cmd.extend(["-i", self.ssh_identity])

        # Add SSH options
        scp_cmd.extend(["-o", "StrictHostKeyChecking=no"])
        scp_cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
        scp_cmd.extend(["-o", "LogLevel=ERROR"])

        # Add source and destination
        scp_cmd.append(str(local_path))
        scp_cmd.append(f"{self.user}@{self.remote_host}:{remote_path}")

        logger.info(f"Uploading {local_path} to {self.remote_host}:{remote_path}")

        # Use Popen for real-time output
        process = subprocess.Popen(
            scp_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )  # Line buffered

        # Stream output in real-time
        if process.stdout:
            for line in process.stdout:
                if show_progress:
                    logger.info(line.rstrip())

        returncode = process.wait()

        if returncode == 0:
            logger.info("✓ Upload complete")
            return True
        else:
            logger.error(f"Upload failed with exit code {returncode}")
            return False


class VirshRemote(SSHRemote):
    """Execute virsh commands on a remote system via SSH."""

    def __init__(self, remote_host: str, ssh_identity: Optional[str] = None):
        """
        Initialize remote virsh connection.

        Args:
            remote_host: Remote host IP/hostname
            ssh_identity: Path to SSH identity file
        """
        user = "root"
        if "@" in remote_host:
            user, remote_host = remote_host.split("@")
        super().__init__(remote_host, ssh_identity, user=user)

    def virsh(self, virsh_command: str, check: bool = False) -> subprocess.CompletedProcess:
        """
        Execute a virsh command on the remote system.

        Args:
            virsh_command: virsh subcommand (e.g., "list", "dominfo vm-name")
            check: If True, raise CalledProcessError on non-zero exit

        Returns:
            CompletedProcess with returncode, stdout, stderr
        """
        full_command = f"virsh --connect qemu:///system {virsh_command}"
        return self.execute(full_command, check=check)
