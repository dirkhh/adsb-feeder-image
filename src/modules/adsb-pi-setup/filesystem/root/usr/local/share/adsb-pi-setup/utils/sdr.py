import io
import re
import subprocess
import sys
from functools import lru_cache


class SDR:
    def __init__(self, type_: str, address: str):
        self.type = type_
        self.address = address
        self.serial = self.get_serial(address)

    @staticmethod
    @lru_cache(maxsize=32)
    def get_serial(address: str):
        try:
            result = subprocess.run(
                f"lsusb -s {address} -v", shell=True, capture_output=True
            )
        except subprocess.SubprocessError:
            print(f"'lsusb -s {address} -v' failed", file=sys.stderr)
        output = result.stdout.decode()
        serial_match = re.search(r"iSerial\s+\d+\s+(.*)", output, flags=re.M)
        if serial_match:
            return serial_match.group(1)
        return ""


class SDRDevices:
    def __init__(self):
        self.sdrs = []

    def __len__(self):
        return len(self.sdrs)

    def get_sdr_info(self):
        try:
            result = subprocess.run("lsusb", shell=True, capture_output=True)
        except subprocess.SubprocessError:
            print("lsusb failed", file=sys.stderr)
        output = io.StringIO(result.stdout.decode())
        for line in output:
            rtl_sdr_match = re.search(
                "Bus ([0-9a-fA-F]+) Device ([0-9a-fA-F]+): ID 0bda:2838", line
            )
            if rtl_sdr_match:
                address = f"{rtl_sdr_match.group(1)}:{rtl_sdr_match.group(2)}"
                print(f"get_sdr_info() found RTL SDR at {address}", file=sys.stderr)
                self.sdrs.append(SDR("rtlsdr", address))
            airspy_match = re.search(
                "Bus ([0-9a-fA-F]+) Device ([0-9a-fA-F]+): ID 1d50:60a1", line
            )
            if airspy_match:
                address = f"{airspy_match.group(1)}:{airspy_match.group(2)}"
                print(f"get_sdr_info() found Airspy at {address}", file=sys.stderr)
                self.sdrs.append(SDR("airspy", address))
