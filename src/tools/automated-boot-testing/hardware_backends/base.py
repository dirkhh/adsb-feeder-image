"""Abstract base class for hardware test backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TestConfig:
    """Common configuration for all test backends."""

    image_url: str
    metrics_id: Optional[int]
    metrics_db: Path
    timeout_minutes: int
    ssh_key: Optional[Path] = None


class HardwareBackend(ABC):
    """Abstract base for hardware testing backends."""

    def __init__(self, config: TestConfig):
        """
        Initialize hardware backend.

        Args:
            config: Test configuration
        """
        self.config = config

    @abstractmethod
    def prepare_environment(self) -> None:
        """
        Download image and prepare hardware/VM.

        This should handle:
        - Downloading the image
        - Any required file transfers
        - Hardware-specific preparation

        Raises:
            Exception: On preparation failure
        """
        pass

    @abstractmethod
    def boot_system(self) -> None:
        """
        Boot the system (power on RPi or start VM).

        Raises:
            Exception: On boot failure
        """
        pass

    @abstractmethod
    def wait_for_network(self) -> str:
        """
        Wait for system to get IP address and be network-ready.

        Returns:
            IP address of the booted system

        Raises:
            TimeoutError: If system doesn't become ready in time
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """
        Clean up resources (destroy VM, power off RPi, remove temp files).

        This should be safe to call multiple times and handle cleanup
        even if earlier stages failed.
        """
        pass

    def run_browser_tests(self, target_ip: str) -> bool:
        """
        Run Selenium browser tests against the target system.

        SECURITY: Runs browser as 'testuser' (non-root) for security.
        Browsers should never run as root due to their large attack surface.

        Args:
            target_ip: IP address of system to test

        Returns:
            True if tests passed, False otherwise
        """
        import logging
        import pwd
        import subprocess

        logger = logging.getLogger(__name__)

        # Ensure testuser exists
        try:
            pwd.getpwnam("testuser")
            logger.info("✓ testuser exists")
        except KeyError:
            logger.warning("testuser does not exist - creating it")
            try:
                subprocess.run(
                    [
                        "useradd",
                        "-r",
                        "-m",
                        "-s",
                        "/bin/bash",
                        "-c",
                        "User for running browser tests",
                        "testuser",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logger.info("✓ testuser created")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to create testuser: {e.stderr}")
                return False

        # Run selenium tests as testuser using venv Python
        script_path = Path(__file__).parent.parent / "run-selenium-as-testuser.py"

        # Find the venv Python - check common locations
        venv_python = None
        possible_venv_paths = [
            Path("/opt/adsb-boot-test/venv/bin/python3"),
            Path(__file__).parent.parent / "venv" / "bin" / "python3",
        ]

        for venv_path in possible_venv_paths:
            if venv_path.exists():
                venv_python = venv_path
                break

        if not venv_python:
            logger.error("Could not find venv Python - selenium tests require virtual environment")
            return False

        try:
            logger.info(f"Running browser tests as testuser against {target_ip}")
            logger.info(f"Using venv Python: {venv_python}")

            result = subprocess.run(
                [
                    "sudo",
                    "-u",
                    "testuser",
                    str(venv_python),
                    str(script_path),
                    target_ip,
                    "--timeout",
                    str(self.config.timeout_minutes * 60),
                ],
                capture_output=False,  # Let output go directly to console/journalctl
                check=False,
            )

            return result.returncode == 0

        except Exception as e:
            logger.error(f"Browser tests failed: {e}", exc_info=True)
            return False
