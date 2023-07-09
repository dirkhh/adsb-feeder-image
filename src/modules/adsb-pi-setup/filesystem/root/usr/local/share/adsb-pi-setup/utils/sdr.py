import io
import re
import subprocess
import sys


class SDR:
    def __init__(self, type_: str, address: str):
        self._type = type_
        self._address = address

    @property
    def _serial(self):
        try:
            result = subprocess.run(
                f"lsusb -s {self._address} -v", shell=True, capture_output=True
            )
        except subprocess.SubprocessError:
            print(f"'lsusb -s {self._address} -v' failed", file=sys.stderr)
        output = result.stdout.decode()
        serial_match = re.search(r"iSerial\s+\d+\s+(.*)", output, flags=re.M)
        if serial_match:
            return serial_match.group(1).strip().rstrip("0")

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
                # If it already exists, don't add it again
                candidate = SDR("rtlsdr", address)
                if candidate not in self.sdrs:
                    self.sdrs.append(candidate)
            airspy_match = re.search(
                "Bus ([0-9a-fA-F]+) Device ([0-9a-fA-F]+): ID 1d50:60a1", line
            )
            if airspy_match:
                address = f"{airspy_match.group(1)}:{airspy_match.group(2)}"
                print(f"get_sdr_info() found Airspy at {address}", file=sys.stderr)
                candidate = SDR("airspy", address)
                if candidate not in self.sdrs:
                    self.sdrs.append(candidate)

    def _ensure_populated(self):
        self.get_sdr_info()

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
                ret[1090] = sdr
            elif sdr._type == "rtlsdr":
                if sdr._serial == "1090":
                    ret[1090] = sdr
                elif sdr._serial == "978":
                    ret[978] = sdr
                elif not ret[1090]:
                    ret[1090] = sdr
        return ret
