import io
import re
import subprocess
import sys
from typing import List


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)



class SDR:
    def __init__(self, type_: str, address: str):
        self._type = type_
        self._address = address
        self._serial_probed = None

    @property
    def _serial(self) -> str:
        if self._serial_probed:
            return self._serial_probed
        cmdline = f"lsusb -s {self._address} -v"
        try:
            result = subprocess.run(cmdline, shell=True, capture_output=True)
        except subprocess.SubprocessError:
            print(f"'lsusb -s {self._address} -v' failed", file=sys.stderr)
        output = result.stdout.decode()
        serial_match = re.search(r"iSerial\s+\d+\s+(.*)", output, flags=re.M)
        if serial_match:
            self._serial_probed = serial_match.group(1).strip()
            return self._serial_probed

        return ""

    @property
    def _json(self):
        return {
            "type": self._type,
            "address": self._address,
            "serial": self._serial,
        }

    # a magic method to compare two objects
    def __eq__(self, other):
        if isinstance(other, SDR):
            return self._json == other._json
        return False

    def __repr__(self):
        return f"SDR(type: {self._type} address: {self._address})"


class SDRDevices:
    def __init__(self):
        self.sdrs: List[SDR] = []

    def __len__(self):
        return len(self.sdrs)

    def __repr__(self):
        return f"SDRDevices({','.join([s for s in self.sdrs])})"

    def get_sdr_info(self):
        try:
            result = subprocess.run("lsusb", shell=True, capture_output=True)
        except subprocess.SubprocessError:
            print("lsusb failed", file=sys.stderr)
        output = io.StringIO(result.stdout.decode())
        for line in output:
            for pidvid in ("1d50:60a1", "0bda:2838", "0bda:2832"):
                address = self._get_address_for_pid_vid(pidvid, line)
                if address:
                    print(f"get_sdr_info() found SDR {pidvid} at {address}")
                    if pidvid == "1d50:60a1":
                        candidate = SDR("airspy", address)
                    else:
                        candidate = SDR("rtlsdr", address)
                    if candidate not in self.sdrs:
                        self.sdrs.append(candidate)

    def _ensure_populated(self):
        self.get_sdr_info()

    def _get_address_for_pid_vid(self, pidvid: str, line: str):
        address = ""
        match = re.search(f"Bus ([0-9a-fA-F]+) Device ([0-9a-fA-F]+): ID {pidvid}", line)
        if match:
            address = f"{match.group(1)}:{match.group(2)}"
        return address

    @property
    def addresses_per_frequency(self, frequencies: list = [1090, 978]):
        self._ensure_populated()
        # they haven't been assigned yet, so let's make some
        # assumptions to get started:
        # - if we find an airspy, that's for 1090
        # - if we find an RTL SDR with serial 1090 - well, that's for 1090 (unless you have an airspy)
        # - if we find an RTL SDR with serial 978 - that's for 978
        # - if we find just one RTL SDR and no airspy, then that RTL SDR is for 1090
        # Make sure one SDR is used per frequency at most...
        ret = {frequency: None for frequency in frequencies}
        for sdr in self.sdrs:
            if sdr._type == "airspy":
                ret[1090] = sdr._serial
            elif sdr._type == "rtlsdr":
                if sdr._serial == "1090":
                    ret[1090] = sdr._serial
                elif sdr._serial == "978":
                    ret[978] = sdr._serial
        if not ret[1090] and len(self.sdrs) == 1:
            ret[1090] = self.sdrs[0]._serial
        return ret
