#!/usr/bin/env python3
"""
Test script for booting and running the feeder image on actual hardware.

This script:
1. Downloads and decompresses a feeder image if needed
2. shuts down and powers off the test system (using a local Kasa smart switch)
2. Copies the fresh image to /srv/iscsi/adsbim.img -- so yes, this assumes that you have a TFTP/iSCSI setup to boot an RPi from
3. Turns on / reboots the test system
4. Waits for the feeder to come online and verifies the correct image is running

Usage:
    python3 test-feeder-image.py <image_url> <rpi_ip> <kasa_ip>
"""

import argparse
import asyncio
import os
import requests
import shutil
import subprocess
import sys
import time
import urllib.parse
from kasa import SmartPlug
from pathlib import Path


def try_ssh_shutdown(rpi_ip: str, user: str = "root", ssh_key: str = "", timeout: int = 10) -> bool:
    """Try to shutdown the system via SSH."""
    ssh_cmd = ["ssh"]

    # Add SSH options
    ssh_cmd.extend(["-o", "ConnectTimeout=" + str(timeout)])
    ssh_cmd.extend(["-o", "StrictHostKeyChecking=no"])

    # Add SSH key if provided
    if ssh_key:
        ssh_cmd.extend(["-i", ssh_key])

    # Add user@host and command
    ssh_cmd.append(f"{user}@{rpi_ip}")
    ssh_cmd.append("shutdown now")

    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout + 5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return False



async def control_kasa_switch_async(kasa_ip: str, turn_on: bool) -> bool:
    """Control a Kasa smart switch."""
    try:
        plug = SmartPlug(kasa_ip)
        await plug.update()

        if turn_on:
            print(f"Turning on Kasa switch at {kasa_ip}...")
            await plug.turn_on()
            print("✓ Kasa switch turned on")
        else:
            print(f"Turning off Kasa switch at {kasa_ip}...")
            await plug.turn_off()
            print("✓ Kasa switch turned off")

        return True

    except Exception as e:
        print(f"✗ Error controlling Kasa switch: {e}")
        return False


def control_kasa_switch(kasa_ip: str, turn_on: bool) -> bool:
    """Control a Kasa smart switch (sync wrapper)."""
    return asyncio.run(control_kasa_switch_async(kasa_ip, turn_on))



def validate_image_filename(filename: str) -> str:
    if not filename.startswith("adsb-im-") or not filename.endswith(".img.xz"):
        raise ValueError(f"Invalid image filename: {filename}. Must start with 'adsb-im-' and end with '.img.xz'")

    # Remove .xz extension to get the expected image name
    expected_image_name = filename[:-3]  # Remove .xz
    return expected_image_name

def download_and_decompress_image(url: str, force_download: bool = False, cache_dir:Path = Path("/tmp")) -> str:
    # Extract filename from URL
    parsed_url = urllib.parse.urlparse(url)
    filename = os.path.basename(parsed_url.path)
    expected_image_name = validate_image_filename(filename)

    cached_compressed = cache_dir / filename
    cached_decompressed = cache_dir / expected_image_name

    if cached_compressed.exists() and not force_download:
        print(f"Using cached compressed image: {cached_compressed}")
        print(f"Cache file size: {cached_compressed.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        cached_compressed.unlink(missing_ok=True)
        print(f"Downloading {filename} to cache...")
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(cached_compressed, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Downloaded {cached_compressed.stat().st_size / 1024 / 1024:.1f} MB")

        # Decompress the file
        with open(cached_decompressed, "wb") as out_file:
            subprocess.run(["xz", "-d", "-c", str(cached_compressed)], stdout=out_file, check=True)
        print(f"Decompressed to {cached_decompressed.stat().st_size / 1024 / 1024:.1f} MB")
    return expected_image_name

def setup_iscsi_image(cached_decompressed: Path) -> None:
    target_path = Path("/srv/iscsi/adsbim.img")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Copying image to {target_path}...")
    shutil.copy(str(cached_decompressed), str(target_path))
    print(f"Image successfully copied to {target_path}")
    print(f"Running setup-tftp-iscsi.sh...")
    subprocess.run(["bash", Path(__file__).parent / "setup-tftp-iscsi.sh", str(target_path)])
    print(f"setup-tftp-iscsi.sh completed")


def wait_for_system_down(rpi_ip: str, timeout_seconds: int = 60) -> bool:
    print(f"Waiting for system at {rpi_ip} to go down (timeout: {timeout_seconds} seconds)...")

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        try:
            result = subprocess.run(["ping", "-c", "1", "-W", "2", rpi_ip],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print(f"\n✓ System at {rpi_ip} is down")
                return True
            print(".", end="", flush=True)
            time.sleep(2)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print(f"\n✓ System at {rpi_ip} is down")
            return True

    print(f"\n⚠ System at {rpi_ip} did not go down within {timeout_seconds} seconds")
    return False


def wait_for_feeder_online(rpi_ip: str, expected_image_name: str, timeout_minutes: int = 5) -> bool:
    """Wait for the feeder to come online and verify the correct image is running."""
    print(f"Waiting for feeder at {rpi_ip} to come online (timeout: {timeout_minutes} minutes)...")

    start_time = time.time()
    timeout_seconds = timeout_minutes * 60

    while time.time() - start_time < timeout_seconds:
        try:
            # Try to fetch the main page
            response = requests.get(f"http://{rpi_ip}/", timeout=10)

            if response.status_code == 200:
                print("Feeder responded! Checking image version...")

                # Look for the footer line with the image name
                content = response.text
                if expected_image_name in content:
                    print(f"✓ SUCCESS: Feeder is running the correct image: {expected_image_name}")
                    return True
                else:
                    print(f"Feeder responded but wrong image. Expected: {expected_image_name}")
                    print("Page content preview:")
                    print(content[:500] + "..." if len(content) > 500 else content)

        except requests.exceptions.RequestException as e:
            print(f"Connection attempt failed: {e}")

        print("Waiting 10 seconds before next attempt...")
        time.sleep(10)

    print(f"✗ FAILURE: Feeder did not come online within {timeout_minutes} minutes")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Test feeder image on actual hardware",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    .venv/bin/python test-feeder-image.py https://example.com/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 192.168.1.200
    .venv/bin/python test-feeder-image.py file:///path/to/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 192.168.1.200
    .venv/bin/python test-feeder-image.py -f https://example.com/adsb-im-raspberrypi64-pi-2-3-4-5-v3.0.6-beta.6.img.xz 192.168.1.100 192.168.1.200
        """,
    )

    parser.add_argument("image_url", help="URL or file path to the .img.xz image file")
    parser.add_argument("rpi_ip", help="IP address of the Raspberry Pi")
    parser.add_argument("kasa_ip", help="IP address of the Kasa smart switch")
    parser.add_argument("--force-download", action="store_true", help="Force re-download even if cached files exist")
    parser.add_argument("--force-off", action="store_true", help="Force shutdown and turn off power")
    parser.add_argument("--user", default="root", help="SSH user (default: root)")
    parser.add_argument("--ssh-key", help="Path to SSH private key")
    parser.add_argument("--shutdown-timeout", type=int, default=10, help="SSH connection timeout in seconds (default: 10)")
    parser.add_argument("--timeout", type=int, default=5, help="Timeout in minutes (default: 5)")

    args = parser.parse_args()

    try:
        script_dir = Path(__file__).parent.parent.parent
        cache_dir = script_dir / "test-images"
        expected_image_name = download_and_decompress_image(args.image_url, args.force_download, cache_dir)
        cached_image_path = cache_dir / expected_image_name

        if not args.force_off:
            try_ssh_shutdown(args.rpi_ip, args.user, args.ssh_key, args.shutdown_timeout)
            wait_for_system_down(args.rpi_ip, args.shutdown_timeout)

        control_kasa_switch(args.kasa_ip, False)
        setup_iscsi_image(cached_image_path)
        control_kasa_switch(args.kasa_ip, True)
        success = wait_for_feeder_online(args.rpi_ip, expected_image_name, args.timeout)

        if success:
            print("\n🎉 Test completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Test failed!")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
