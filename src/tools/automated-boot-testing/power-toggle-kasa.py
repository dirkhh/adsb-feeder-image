#!/usr/bin/env python3
"""
Kasa Smart Plug Power Toggle

Turns a TP-Link Kasa smart plug on or off.
Reads configuration from /etc/adsb-boot-test/config.json

Exit codes:
  0 - Success
  1 - Failure (connection error, invalid config, etc.)
"""

import asyncio
import json
import sys

from kasa import SmartPlug


async def control_kasa_async(ip: str, turn_on: bool) -> bool:
    """Control Kasa smart plug (async)"""
    try:
        plug = SmartPlug(ip)
        await plug.update()

        if turn_on:
            print(f"Turning on Kasa switch at {ip}...")
            await plug.turn_on()
            print("✓ Kasa switch turned ON")
        else:
            print(f"Turning off Kasa switch at {ip}...")
            await plug.turn_off()
            print("✓ Kasa switch turned OFF")

        return True
    except Exception as e:
        print(f"ERROR: Failed to control Kasa switch at {ip}: {e}", file=sys.stderr)
        return False


def control_kasa(ip: str, turn_on: bool) -> bool:
    """Control Kasa smart plug (sync wrapper)"""
    return asyncio.run(control_kasa_async(ip, turn_on))


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
        print("Usage: power-toggle-kasa.py <on|off>", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]
    turn_on = action == "on"

    # Load config
    config = load_config()

    # Get Kasa IP from config
    kasa_ip = config.get("kasa_ip")
    if not kasa_ip:
        print("ERROR: 'kasa_ip' not found in config.json", file=sys.stderr)
        sys.exit(1)

    # Control the switch
    success = control_kasa(kasa_ip, turn_on)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
