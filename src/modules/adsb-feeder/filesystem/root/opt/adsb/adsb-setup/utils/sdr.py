import io
import re
import subprocess
import sys
import time
from threading import Lock
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
        if self._type == "airspy" and self._serial_probed:
            split = self._serial_probed.split(":")
            if len(split) == 2 and len(split[1]) == 16:
                self._serial_probed = split[1]

        if not self._serial_probed:
            if self._type == "stratuxv3":
                self._serial_probed = "stratuxv3 w/o serial"
            if self._type == "modesbeast":
                self._serial_probed = "Mode-S Beast w/o serial"
            if self._type == "sdrplay":
                self._serial_probed = "SDRplay w/o serial"
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
        self.last_probe = 0
        self.last_debug_out = ""
        self.lock = Lock()

    def __len__(self):
        return len(self.sdrs)

    def __repr__(self):
        return f"SDRDevices({','.join([s for s in self.sdrs])})"

    def purposes(self):
        p = (
            "1090serial",
            "978serial",
            "1090_2serial",
            "acarsserial",
            "acars2serial",
            "vdl2serial",
            "hfdlserial",
            "aisserial",
        )
        for i in range(16):
            p += (f"other-{i}",)
        return p

    def get_sdr_info(self):
        self.debug_out = "get_sdr_info() found:\n"
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
                # print_err(f"checking {sdr_type} with pidvid {pidvid}")
                for line in output:
                    address = self._get_address_for_pid_vid(pidvid, line)
                    if address:
                        new_sdr = SDR(sdr_type, address)
                        self.sdrs.append(new_sdr)
                        self.debug_out += f"sdr_info: type: {sdr_type} serial: {new_sdr._serial} address: {address} pidvid: {pidvid}\n"

        # list from rtl-sdr drivers
        # lots of these are likely not gonna work / work well but it's still better
        # for them to be selectable by the user at least so they can see if it works or not
        rtlsdr_pv_list = [
            "0bda:2832",  # Generic RTL2832U
            "0bda:2838",  # Generic RTL2832U OEM
            "0413:6680",  # DigitalNow Quad DVB-T PCI-E card
            "0413:6f0f",  # Leadtek WinFast DTV Dongle mini D
            "0458:707f",  # Genius TVGo DVB-T03 USB dongle (Ver. B)
            "0ccd:00a9",  # Terratec Cinergy T Stick Black (rev 1)
            "0ccd:00b3",  # Terratec NOXON DAB/DAB+ USB dongle (rev 1)
            "0ccd:00b4",  # Terratec Deutschlandradio DAB Stick
            "0ccd:00b5",  # Terratec NOXON DAB Stick - Radio Energy
            "0ccd:00b7",  # Terratec Media Broadcast DAB Stick
            "0ccd:00b8",  # Terratec BR DAB Stick
            "0ccd:00b9",  # Terratec WDR DAB Stick
            "0ccd:00c0",  # Terratec MuellerVerlag DAB Stick
            "0ccd:00c6",  # Terratec Fraunhofer DAB Stick
            "0ccd:00d3",  # Terratec Cinergy T Stick RC (Rev.3)
            "0ccd:00d7",  # Terratec T Stick PLUS
            "0ccd:00e0",  # Terratec NOXON DAB/DAB+ USB dongle (rev 2)
            "1554:5020",  # PixelView PV-DT235U(RN)
            "15f4:0131",  # Astrometa DVB-T/DVB-T2
            "15f4:0133",  # HanfTek DAB+FM+DVB-T
            "185b:0620",  # Compro Videomate U620F
            "185b:0650",  # Compro Videomate U650F
            "185b:0680",  # Compro Videomate U680F
            "1b80:d393",  # GIGABYTE GT-U7300
            "1b80:d394",  # DIKOM USB-DVBT HD
            "1b80:d395",  # Peak 102569AGPK
            "1b80:d397",  # KWorld KW-UB450-T USB DVB-T Pico TV
            "1b80:d398",  # Zaapa ZT-MINDVBZP
            "1b80:d39d",  # SVEON STV20 DVB-T USB & FM
            "1b80:d3a4",  # Twintech UT-40
            "1b80:d3a8",  # ASUS U3100MINI_PLUS_V2
            "1b80:d3af",  # SVEON STV27 DVB-T USB & FM
            "1b80:d3b0",  # SVEON STV21 DVB-T USB & FM
            "1d19:1101",  # Dexatek DK DVB-T Dongle (Logilink VG0002A)
            "1d19:1102",  # Dexatek DK DVB-T Dongle (MSI DigiVox mini II V3.0)
            "1d19:1103",  # Dexatek Technology Ltd. DK 5217 DVB-T Dongle
            "1d19:1104",  # MSI DigiVox Micro HD
            "1f4d:a803",  # Sweex DVB-T USB
            "1f4d:b803",  # GTek T803
            "1f4d:c803",  # Lifeview LV5TDeluxe
            "1f4d:d286",  # MyGica TD312
            "1f4d:d803",  # PROlectrix DV107669
        ]

        check_pidvid(pv_list=rtlsdr_pv_list, sdr_type="rtlsdr")
        check_pidvid(pv_list=["0403:7028"], sdr_type="stratuxv3")
        check_pidvid(pv_list=["1d50:60a1"], sdr_type="airspy")
        check_pidvid(pv_list=["0403:6001"], sdr_type="modesbeast")

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

        if len(self.sdrs) == 0:
            self.debug_out = "get_sdr_info() could not find any SDRs"

        if self.last_debug_out != self.debug_out:
            self.last_debug_out = self.debug_out
            print_err(self.debug_out.rstrip("\n"))

    def get_sdr_by_serial(self, serial: str):
        self._ensure_populated()
        for sdr in self.sdrs:
            if sdr._serial == serial:
                return sdr

    def _ensure_populated(self):
        with self.lock:
            if time.time() - self.last_probe < 1:
                return
            self.last_probe = time.time()
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
        # - if we find an airspy, that's for 1090
        # - if we find an stratuxv3, that's for 978
        # - if we find an RTL SDR with serial 1090 or 00001090 - well, that's for 1090 (unless you have an airspy)
        # - if we find an RTL SDR with serial 978 or 00000978 - that's for 978 (if you have more than one SDR)
        # - if we find just one RTL SDR and no airspy, then that RTL SDR is for 1090
        # Make sure one SDR is used per frequency at most...
        ret = {frequency: "" for frequency in frequencies}
        for sdr in self.sdrs:
            if sdr._type == "airspy":
                ret[1090] = sdr._serial
            if sdr._type == "modesbeast":
                ret[1090] = sdr._serial
            elif sdr._type == "stratuxv3":
                ret[978] = sdr._serial
            elif sdr._type == "sdrplay":
                ret[1090] = sdr._serial
            elif sdr._type == "rtlsdr":
                if "1090" in sdr._serial:
                    ret[1090] = sdr._serial
                elif "978" in sdr._serial and len(self.sdrs) > 1:
                    ret[978] = sdr._serial
        if not ret[1090] and not ret[978] and len(self.sdrs) == 1:
            ret[1090] = self.sdrs[0]._serial
        return ret
