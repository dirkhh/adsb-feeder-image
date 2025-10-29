#!/usr/bin/env python3
"""
UniFi PoE Port Power Toggle via SSH

Controls PoE power on a specific port of a UniFi switch via direct SSH commands.
Much faster than Controller API (5-10s vs 30+s).

Reads configuration from /etc/adsb-boot-test/config.json

Configuration required in config.json:
  "unifi_ssh_address": "192.168.1.10"           # Switch IP/hostname
  "unifi_ssh_username": "admin"                 # SSH username
  "unifi_ssh_keypath": "/path/to/key"           # Path to private key (no passphrase)
  "unifi_port_number": 16                       # Port number (1-based)

Exit codes:
  0 - Success
  1 - Failure (connection error, invalid config, etc.)
"""

import json
import os
import subprocess
import sys
import time
from typing import Optional


class UniFiSSHController:
    """Controls UniFi switch PoE ports via SSH commands"""

    def __init__(self, address: str, username: str, keypath: str, port_number: int):
        """
        Initialize SSH controller.

        Args:
            address: IP or hostname of the switch
            username: SSH username
            keypath: Path to SSH private key file (no passphrase)
            port_number: Port number to control (1-based)
        """
        self.address = address
        self.username = username
        self.keypath = keypath
        self.port_number = port_number

    def toggle_port(self, turn_on: bool) -> bool:
        """
        Toggle port power and verify state change.

        Args:
            turn_on: True to enable PoE, False to disable

        Returns:
            True if port reached desired state, False otherwise
        """
        expected_state = "On" if turn_on else "Off"

        # Pre-check: Query current state first
        print(f"Checking current state of port {self.port_number}...")
        success, output = self._run_ssh_command(f"swctrl poe show id {self.port_number}")

        if success:
            current_state = self._parse_poe_status(output)
            if current_state == expected_state:
                print(f"✓ Port {self.port_number} is already {expected_state}")
                return True
            print(f"Current state: {current_state}, target state: {expected_state}")
        else:
            print(f"Warning: Could not check current state, proceeding with toggle...")

        # Send toggle command
        action = "Enabling" if turn_on else "Disabling"
        poe_mode = "auto" if turn_on else "off"
        print(f"{action} PoE on port {self.port_number}...")

        success, output = self._run_ssh_command(f"swctrl poe set {poe_mode} id {self.port_number}")
        if not success:
            print(f"ERROR: Failed to send toggle command: {output}", file=sys.stderr)
            return False

        # Wait and verify state change
        return self._verify_state_change(expected_state)

    def _run_ssh_command(self, command: str, retry: bool = True) -> tuple[bool, str]:
        """
        Execute SSH command on the UniFi switch.

        Args:
            command: The swctrl command to run
            retry: If True and command fails, wait 2s and retry once

        Returns:
            (success: bool, output: str)
            - success: True if command executed (exit code 0), False otherwise
            - output: stdout from the command (or stderr on failure)
        """
        ssh_cmd = [
            "ssh",
            "-i",
            self.keypath,
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=5",
            f"{self.username}@{self.address}",
            command,
        ]

        for attempt in range(2 if retry else 1):
            try:
                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=7,
                    check=False,
                )

                if result.returncode == 0:
                    return (True, result.stdout)

                # First attempt failed, retry if enabled
                if retry and attempt == 0:
                    print(f"SSH command failed (attempt {attempt + 1}), retrying in 2s...")
                    time.sleep(2)
                    continue

                return (False, result.stderr or result.stdout)

            except subprocess.TimeoutExpired:
                if retry and attempt == 0:
                    print(f"SSH command timed out (attempt {attempt + 1}), retrying in 2s...")
                    time.sleep(2)
                    continue
                return (False, "SSH command timed out")

            except FileNotFoundError:
                return (False, "SSH binary not found. Is OpenSSH installed?")

            except Exception as e:
                return (False, f"Unexpected error: {e}")

        return (False, "All retry attempts failed")

    def _verify_state_change(self, expected_state: str, max_wait_seconds: int = 15) -> bool:
        """
        Poll port status until PoE power matches expected state.

        Args:
            expected_state: Either "On" or "Off"
            max_wait_seconds: Maximum time to wait (default 15)

        Returns:
            True if state matches expected_state within timeout, False otherwise
        """
        # Initial wait for hardware to process command
        print(f"Waiting for PoE state to change...")
        time.sleep(2)

        poll_interval = 2
        elapsed = 2
        first_check = True

        while elapsed <= max_wait_seconds:
            success, output = self._run_ssh_command(f"swctrl poe show id {self.port_number}", retry=False)

            if not success:
                print(f"Warning: Could not query port status: {output}")
                time.sleep(poll_interval)
                elapsed += poll_interval
                continue

            current_state = self._parse_poe_status(output)

            if first_check:
                print(f"Current PoE state: {current_state}, waiting for: {expected_state}")
                first_check = False

            if current_state == expected_state:
                status = "enabled" if expected_state == "On" else "disabled"
                print(f"✓ PoE {status} on port {self.port_number} (verified after {elapsed}s)")
                return True

            time.sleep(poll_interval)
            elapsed += poll_interval

        print(
            f"ERROR: PoE state did not change to '{expected_state}' after {max_wait_seconds}s",
            file=sys.stderr,
        )
        return False

    def _parse_poe_status(self, output: str) -> Optional[str]:
        """
        Parse 'swctrl poe show id <port>' output to extract PoE power state.

        Expected output format:
        Port  OpMode      HpMode    PwrLimit   Class   PoEPwr  PwrGood  Power(W)  ...
        ----  ------  ------------  --------  -------  ------  -------  --------  ...
          16    Auto       Unknown        -1  Class 4      On     Good      5.35  ...

        Args:
            output: Raw output from swctrl poe show command

        Returns:
            "On" or "Off" if parsed successfully, None if parsing failed
        """
        try:
            lines = output.strip().split("\n")
            if len(lines) < 3:
                return None

            # Find header line and PoEPwr column index
            header_line = None
            for i, line in enumerate(lines):
                if "PoEPwr" in line:
                    header_line = line
                    break

            if not header_line:
                return None

            # Split header to find column index
            headers = header_line.split()
            try:
                poe_pwr_index = headers.index("PoEPwr")
            except ValueError:
                return None

            # Find data line (starts with whitespace + digits)
            data_line = None
            for line in lines:
                stripped = line.strip()
                if stripped and stripped[0].isdigit():
                    data_line = line
                    break

            if not data_line:
                return None

            # Extract value at PoEPwr column
            data_line = data_line.replace("Class ", "Class")
            values = data_line.split()
            if len(values) <= poe_pwr_index:
                return None

            poe_value = values[poe_pwr_index]
            if poe_value in ("On", "Off"):
                return poe_value

            return None

        except Exception as e:
            print(f"Warning: Failed to parse PoE status: {e}", file=sys.stderr)
            return None


def load_config(config_path: str = "/etc/adsb-boot-test/config.json") -> dict:
    """Load configuration from file"""
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in config file: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point"""
    if len(sys.argv) != 2 or sys.argv[1] not in ["on", "off"]:
        print("Usage: power-toggle-unifi.py <on|off>", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]
    turn_on = action == "on"

    # Load config
    config = load_config()

    # Get UniFi SSH settings from config
    required_fields = [
        "unifi_ssh_address",
        "unifi_ssh_username",
        "unifi_ssh_keypath",
        "unifi_port_number",
    ]

    missing = [field for field in required_fields if field not in config]
    if missing:
        print(f"ERROR: Missing required config fields: {', '.join(missing)}", file=sys.stderr)
        print("\nRequired UniFi SSH configuration:", file=sys.stderr)
        print('  "unifi_ssh_address": "192.168.1.10"', file=sys.stderr)
        print('  "unifi_ssh_username": "admin"', file=sys.stderr)
        print('  "unifi_ssh_keypath": "/etc/adsb-boot-test/unifi_key"', file=sys.stderr)
        print('  "unifi_port_number": 16', file=sys.stderr)
        sys.exit(1)

    # Validate keypath exists
    keypath = config["unifi_ssh_keypath"]
    if not os.path.isfile(keypath):
        print(f"ERROR: SSH key not found: {keypath}", file=sys.stderr)
        sys.exit(1)

    # Validate port number is integer >= 1
    try:
        port_number = int(config["unifi_port_number"])
        if port_number < 1:
            print(f"ERROR: Port number must be >= 1, got: {port_number}", file=sys.stderr)
            sys.exit(1)
    except (ValueError, TypeError):
        print(
            f"ERROR: Port number must be an integer, got: {config['unifi_port_number']}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Create controller and toggle port
    controller = UniFiSSHController(
        address=config["unifi_ssh_address"],
        username=config["unifi_ssh_username"],
        keypath=keypath,
        port_number=port_number,
    )

    success = controller.toggle_port(turn_on)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
