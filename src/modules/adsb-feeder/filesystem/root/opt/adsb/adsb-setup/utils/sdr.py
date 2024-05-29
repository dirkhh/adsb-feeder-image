import io
import re
import subprocess
import sys
from typing import List, Set
from .util import print_err


class SDR:
    def __init__(self, type_: str, address: str):
        self._type = type_
        self._address = address
        self._serial_probed = None
        self.lsusb_output = ""
        # probe serial to popuplate lsusb_output right now
        self._serial

    @property
    def _serial(self) -> str:
        if self._serial_probed:
            return self._serial_probed
        cmdline = f"lsusb -s {self._address} -v"
        try:
            result = subprocess.run(cmdline, shell=True, capture_output=True)
        except subprocess.SubprocessError:
            print_err(f"'lsusb -s {self._address} -v' failed")
            return ""
        output = result.stdout.decode()
        self.lsusb_output = f"lsusb -s {self._address}: {output}"
        # is there a serial number?
        for line in output.splitlines():
            serial_match = re.search(r"iSerial\s+\d+\s+(.*)$", line)
            if serial_match:
                self._serial_probed = serial_match.group(1).strip()
        if not self._serial_probed and self._type == "stratuxv3":
            self._serial_probed = "stratuxv3 w/o serial"
        if not self._serial_probed and self._type == "sdrplay":
            return "SDRplay w/o serial"
        return self._serial_probed

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
        return f"SDR(type: '{self._type}' address: '{self._address}', serial: '{self._serial}')"


class SDRDevices:
    def __init__(self):
        self.sdrs: List[SDR] = []
        self.duplicates: Set[str] = set()
        self.lsusb_output = ""

    def __len__(self):
        return len(self.sdrs)

    def __repr__(self):
        return f"SDRDevices({','.join([s for s in self.sdrs])})"

    def purposes(self):
        return (
            "978serial",
            "1090serial",
            "other-0",
            "other-1",
            "other-2",
            "other-3",
        )

    def get_sdr_info(self):
        try:
            result = subprocess.run("lsusb", shell=True, capture_output=True)
        except subprocess.SubprocessError:
            print("lsusb failed", file=sys.stderr)
            return
        lsusb_text = result.stdout.decode()
        self.lsusb_output = f"lsusb: {lsusb_text}"

        output = lsusb_text.split("\n")
        self.sdrs = []

        def check_pidvid(pv_list=[], sdr_type=None):
            if not sdr_type:
                print_err("WARNING: bad code in check_pidvid")

            for pidvid in pv_list:
                #print_err(f"checking {sdr_type} with pidvid {pidvid}")
                for line in output:
                    address = self._get_address_for_pid_vid(pidvid, line)
                    if address:
                        print_err(f"get_sdr_info() found SDR {pidvid} of type {sdr_type} at {address}")
                        self.sdrs.append(SDR(sdr_type, address))


        check_pidvid(pv_list=["0bda:2838", "0bda:2832"], sdr_type="rtlsdr")
        check_pidvid(pv_list=["0403:7028"], sdr_type="stratuxv3")
        check_pidvid(pv_list=["1d50:60a1"], sdr_type="airspy")

        sdrplay_pv_list = [
                "1df7:2500",
                "1df7:3000",
                "1df7:3010",
                "1df7:3020",
                "1df7:3030",
                "1df7:3050",
                ]

        check_pidvid(pv_list=sdrplay_pv_list, sdr_type="sdrplay")

        found_serials = set()
        self.duplicates = set()
        for sdr in self.sdrs:
            self.lsusb_output += f"\nSDR detected with serial: {sdr._serial}\n"
            self.lsusb_output += sdr.lsusb_output
            if sdr._serial in found_serials:
                self.duplicates.add(sdr._serial)
            else:
                found_serials.add(sdr._serial)

    def _ensure_populated(self):
        self.get_sdr_info()

    def _get_address_for_pid_vid(self, pidvid: str, line: str):
        address = ""
        match = re.search(
            f"Bus ([0-9a-fA-F]+) Device ([0-9a-fA-F]+): ID {pidvid}", line
        )
        if match:
            address = f"{match.group(1)}:{match.group(2)}"
        return address

    @property
    def addresses_per_frequency(self, frequencies: list = [1090, 978]):
        self._ensure_populated()
        # - if we find an airspy, that's for 1090
        # - if we find an stratuxv3, that's for 978
        # - if we find an RTL SDR with serial 1090 or 00001090 - well, that's for 1090 (unless you have an airspy)
        # - if we find an RTL SDR with serial 978 or 00000978 - that's for 978
        # - if we find just one RTL SDR and no airspy, then that RTL SDR is for 1090
        # Make sure one SDR is used per frequency at most...
        ret = {frequency: "" for frequency in frequencies}
        for sdr in self.sdrs:
            if sdr._type == "airspy":
                ret[1090] = sdr._serial
            elif sdr._type == "stratuxv3":
                ret[978] = sdr._serial
            elif sdr._type == "sdrplay":
                ret[1090] = sdr._serial
            elif sdr._type == "rtlsdr":
                if "1090" in sdr._serial:
                    ret[1090] = sdr._serial
                elif "978" in sdr._serial:
                    ret[978] = sdr._serial
        if not ret[1090] and not ret[978] and len(self.sdrs) == 1:
            ret[1090] = self.sdrs[0]._serial
        return ret
