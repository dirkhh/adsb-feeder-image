#!/usr/bin/env python3
"""
UniFi PoE Port Power Toggle

Controls PoE power on a specific port of a UniFi switch via the UniFi Controller API.
Reads configuration from /etc/adsb-test-service/config.json

Configuration required in config.json:
  "unifi_controller": "192.168.1.1"     # Controller IP/hostname
  "unifi_username": "admin"             # Controller username
  "unifi_password": "password"          # Controller password
  "unifi_site": "default"               # Site name (usually "default")
  "unifi_switch_mac": "aa:bb:cc:dd:ee:ff"  # MAC of the switch
  "unifi_port_idx": 5                   # Port number (1-based, e.g., 5 = port 5)

Exit codes:
  0 - Success
  1 - Failure (connection error, invalid config, etc.)
"""

import json
import sys
import time
import urllib3
import requests

try:
    from pyunifi.controller import Controller
except ImportError:
    print("ERROR: pyunifi not installed", file=sys.stderr)
    print("Install with: pip install pyunifi", file=sys.stderr)
    sys.exit(1)

# Disable SSL warnings for self-signed certs (UniFi uses self-signed by default)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def control_unifi_port(
    controller_ip: str,
    username: str,
    password: str,
    site: str,
    switch_mac: str,
    port_idx: int,
    turn_on: bool,
) -> bool:
    """
    Control PoE power on a UniFi switch port.

    Args:
        controller_ip: IP or hostname of UniFi controller
        username: Controller username
        password: Controller password
        site: Site name (usually "default")
        switch_mac: MAC address of the switch
        port_idx: Port number (1-based)
        turn_on: True to enable PoE, False to disable

    Returns:
        True on success, False on failure
    """
    try:
        print(f"Connecting to UniFi controller at {controller_ip}...")

        # Connect to controller
        # Default UniFi port is 8443 (HTTPS)
        controller = Controller(
            host=controller_ip,
            username=username,
            password=password,
            port=8443,
            site_id=site,
            ssl_verify=False,  # UniFi uses self-signed certs
        )

        # Normalize MAC address format (UniFi expects lowercase with colons)
        switch_mac = switch_mac.lower().replace("-", ":")

        # Ensure port_idx is an integer (1-based port number)
        port_idx = int(port_idx)

        action = "Enabling" if turn_on else "Disabling"
        print(f"{action} PoE on switch {switch_mac} port {port_idx}...")

        # Workaround for pyunifi bug: use raw API calls instead of broken methods
        # Get the device by MAC address
        devices = controller.get_aps()  # get_aps() returns all devices including switches
        device = None
        for d in devices:
            if d.get("mac", "").lower() == switch_mac:
                device = d
                break

        if not device:
            print(f"ERROR: Switch with MAC {switch_mac} not found")
            return False

        device_id = device["_id"]
        print(f"Found device ID: {device_id}")

        # Get current port overrides
        current_overrides = device.get("port_overrides", [])

        # Find if this port already has an override
        # NOTE: UniFi API uses 1-based port indexing, NOT 0-based!
        override_found = False
        new_overrides = []

        for override in current_overrides:
            if override.get("port_idx") == port_idx:
                # Update existing override - keep all existing fields
                override["poe_mode"] = "auto" if turn_on else "off"
                override_found = True
            new_overrides.append(override)

        # If no override exists for this port, create one
        if not override_found:
            # Need to include required fields - copy structure from existing override if available
            new_override = {
                "port_idx": port_idx,  # 1-based, not 0-based!
                "poe_mode": "auto" if turn_on else "off"
            }
            # If there are existing overrides, copy the structure/fields from one as template
            if current_overrides:
                template = current_overrides[0]
                for key in template.keys():
                    if key not in new_override and key not in ["port_idx", "poe_mode"]:
                        # Copy other fields that might be required
                        new_override[key] = template[key]
            new_overrides.append(new_override)

        # Update the device with new port overrides
        # Construct the API URL and make a PUT request directly
        # pyunifi's _run_command doesn't support PUT, so we use requests directly
        api_url = f"https://{controller_ip}:8443/api/s/{site}/rest/device/{device_id}"
        payload = {"port_overrides": new_overrides}

        # Use the controller's session which already has auth cookies
        response = controller.session.put(
            api_url,
            json=payload,
            verify=False  # Skip SSL verification for self-signed certs
        )

        if response.status_code != 200:
            print(f"ERROR: API request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False

        # Wait for the actual PoE state to change (can take 5-10 seconds)
        print(f"Waiting for PoE state to actually change on port {port_idx}...")
        expected_mode = "auto" if turn_on else "off"
        max_wait_seconds = 30
        poll_interval = 1
        elapsed = 0

        while elapsed < max_wait_seconds:
            # Re-fetch the device to get current port_table status
            devices = controller.get_aps()
            device = None
            for d in devices:
                if d.get("mac", "").lower() == switch_mac:
                    device = d
                    break

            if not device:
                print(f"ERROR: Could not re-fetch device status")
                return False

            # Check port_table for actual PoE status
            # port_table uses 1-based indexing in the array (port 1 = index 0)
            port_table = device.get("port_table", [])
            if port_idx - 1 < len(port_table):
                port_status = port_table[port_idx - 1]
                actual_poe_mode = port_status.get("poe_mode", "unknown")

                # Check if the actual mode matches what we requested
                if actual_poe_mode == expected_mode:
                    status = "enabled" if turn_on else "disabled"
                    print(f"✓ PoE {status} on port {port_idx} (verified after {elapsed}s)")
                    return True

                # For debugging: show what we're waiting for
                if elapsed == 0:
                    print(f"Current PoE mode: {actual_poe_mode}, waiting for: {expected_mode}")

            time.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout - state didn't change in time
        print(f"WARNING: PoE state change timed out after {max_wait_seconds}s")
        print(f"Configuration was updated, but actual port state may not have changed yet")
        return True  # Return success since the API call worked, even if state didn't change yet

    except Exception as e:
        print(f"ERROR: Failed to control UniFi switch: {e}", file=sys.stderr)
        return False


def load_config(config_path: str = "/etc/adsb-test-service/config.json") -> dict:
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

    # Get UniFi settings from config
    required_fields = [
        "unifi_controller",
        "unifi_username",
        "unifi_password",
        "unifi_site",
        "unifi_switch_mac",
        "unifi_port_idx",
    ]

    missing = [field for field in required_fields if field not in config]
    if missing:
        print(f"ERROR: Missing required config fields: {', '.join(missing)}", file=sys.stderr)
        print("\nRequired UniFi configuration:", file=sys.stderr)
        print('  "unifi_controller": "192.168.1.1"', file=sys.stderr)
        print('  "unifi_username": "admin"', file=sys.stderr)
        print('  "unifi_password": "password"', file=sys.stderr)
        print('  "unifi_site": "default"', file=sys.stderr)
        print('  "unifi_switch_mac": "aa:bb:cc:dd:ee:ff"', file=sys.stderr)
        print('  "unifi_port_idx": 5', file=sys.stderr)
        sys.exit(1)

    # Control the port
    success = control_unifi_port(
        controller_ip=config["unifi_controller"],
        username=config["unifi_username"],
        password=config["unifi_password"],
        site=config["unifi_site"],
        switch_mac=config["unifi_switch_mac"],
        port_idx=config["unifi_port_idx"],
        turn_on=turn_on,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
