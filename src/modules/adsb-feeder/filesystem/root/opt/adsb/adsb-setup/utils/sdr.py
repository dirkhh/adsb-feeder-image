import io
import re
import subprocess
import sys
import time
from threading import Lock
from typing import Dict, List, Set, Tuple
from .util import print_err


class SDR:
    def __init__(self, type_: str, address: str, data):
        self._d = data
        self._type = type_
        self._address = address
        self._serial_probed = None
        self.lsusb_output = ""
        # probe serial to popuplate lsusb_output right now
        self._serial
        # store the settings for the SDR in its own dict
        self.purpose = ""
        self.gain = ""
        self.biastee = False

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
        if "airspy" in self._type and self._serial_probed:
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
        if self._type == "sdrplay" and self._d.is_enabled("sdrplay_ignore_serial"):
            self._serial_probed = "SDRplay w/o serial"
        return self._serial_probed

    @property
    def _json(self):
        return {
            "type": self._type,
            "address": self._address,
            "serial": self._serial,
            "purpose": self.purpose,
            "gain": self.gain,
            "biastee": self.biastee,
        }

    # a magic method to compare two objects
    def __eq__(self, other):
        if isinstance(other, SDR):
            return self._json == other._json
        return False

    def __repr__(self):
        return f"SDR(type: '{self._type}' address: '{self._address}', serial: '{self._serial}', purpose: '{self.purpose}', gain: '{self.gain}', biastee: {self.biastee})"


class SDRDevices:
    def __init__(self, assignment_function, data):
        self._d = data
        self.assignment_function = assignment_function
        # these are the SDRs that we keep re-populating from lsusb
        self.sdrs: List[SDR] = []
        # this is the dict that contains the data of what we are doing with the SDRs, accessed by serial number
        self.sdr_settings: dict[str, SDR] = {}
        self.null_sdr: SDR = SDR("unknown", "unknown", self._d)
        self.duplicates: Set[str] = set()
        self.lsusb_output = ""
        self.last_probe = 0
        self.last_debug_out = ""
        self.lock = Lock()

    def __len__(self):
        return len(self.sdrs)

    def __repr__(self):
        return f"SDRDevices({', '.join([s.__repr__() for s in self.sdrs])})"

    def purposes(self):
        p = (
            "1090",
            "978",
            "1090_2",
            "acars",
            "acars_2",
            "vdl2",
            "hfdl",
            "ais",
            "sonde",
        )
        for i in range(16):
            p += (f"other-{i}",)
        return p

    def purpose_env(self, purpose: str):
        purpose_env = purpose
        if not purpose_env.startswith("other-"):
            purpose_env += "serial"
        return purpose_env

    def ensure_populated(self):
        with self.lock:
            if time.time() - self.last_probe < 10:
                return
            self.last_probe = time.time()
            self._get_sdr_info()

    # don't use this directly call ensure_populated instead
    def _get_sdr_info(self):
        self.debug_out = "_get_sdr_info() found:\n"
        try:
            result = subprocess.run("lsusb", shell=True, capture_output=True)
        except subprocess.SubprocessError:
            print("lsusb failed", file=sys.stderr)
            return
        lsusb_text = result.stdout.decode()
        self.lsusb_output = f"lsusb: {lsusb_text}"

        output = lsusb_text.split("\n")
        self.sdrs = []
        self.sdr_settings = {}
        found_serials = set()
        self.duplicates = set()

        def check_pidvid(pv_list=[], sdr_type=None):
            if not sdr_type:
                print_err("WARNING: bad code in check_pidvid")
                return

            for pidvid in pv_list:
                # print_err(f"checking {sdr_type} with pidvid {pidvid}")
                for line in output:
                    address = self._get_address_for_pid_vid(pidvid, line)
                    if address:
                        new_sdr = SDR(sdr_type, address, self._d)
                        if new_sdr._serial in self.sdr_settings:
                            self.duplicates.add(new_sdr._serial)
                        else:
                            # add this SDR to the settings dict
                            self.sdr_settings[new_sdr._serial] = new_sdr
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
        check_pidvid(pv_list=["03eb:800c"], sdr_type="airspyhf")
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

        for sdr in self.sdrs:
            self.lsusb_output += f"\nSDR detected with serial: {sdr._serial}\n"
            self.lsusb_output += sdr.lsusb_output
            # we should have detected all of the duplicates already, but just in case, we make sure
            if sdr._serial in found_serials:
                self.duplicates.add(sdr._serial)
            else:
                found_serials.add(sdr._serial)

        if len(self.sdrs) == 0:
            self.debug_out = "get_sdr_info() could not find any SDRs"

        if self.last_debug_out != self.debug_out:
            self.last_debug_out = self.debug_out
            print_err(self.debug_out.rstrip("\n"))

        # we store the purpose specific information differently because that's how the
        # yml files can get access to the correct data based on adsb/uat/ais/etc
        #
        # so we need to collect this data and store it in the SDR objects
        assignments: Dict[str, Tuple[str, str, bool]] = self.assignment_function()
        for purpose in assignments.keys():
            serial, gain, biastee = assignments[purpose]
            sdr = self.sdr_settings.get(serial)
            if sdr:
                sdr.purpose = purpose
                sdr.gain = gain
                sdr.biastee = biastee

    def get_sdr_by_serial(self, serial: str):
        self.ensure_populated()
        for sdr in self.sdrs:
            if sdr._serial == serial:
                print_err(f"found SDR for serial: {serial}: id: {id(sdr)} sdr: {sdr}")
                return sdr
        return self.null_sdr

    def _get_address_for_pid_vid(self, pidvid: str, line: str):
        address = ""
        match = re.search(f"Bus ([0-9a-fA-F]+) Device ([0-9a-fA-F]+): ID {pidvid}", line)
        if match:
            address = f"{match.group(1)}:{match.group(2)}"
        return address

    @property
    def addresses_per_frequency(self, frequencies: list[str] = ["1090", "978"]) -> dict[str, str]:
        self.ensure_populated()
        # - if we find an airspy, that's for 1090
        # - if we find an stratuxv3, that's for 978
        # - if we find an RTL SDR with serial 1090 or 00001090 - well, that's for 1090 (unless you have an airspy)
        # - if we find an RTL SDR with serial 978 or 00000978 - that's for 978 (if you have more than one SDR)
        # - if we find just one RTL SDR and no airspy, then that RTL SDR is for 1090
        # Make sure one SDR is used per frequency at most...
        ret = {frequency: "" for frequency in frequencies}

        if not self._d.is_enabled("is_adsb_feeder"):
            # currently no logic for non ads-b setups, don't give any suggestions
            return ret

        for sdr in self.sdrs:
            if sdr._type == "airspy":
                ret["1090"] = sdr._serial
            if sdr._type == "modesbeast":
                ret["1090"] = sdr._serial
            elif sdr._type == "stratuxv3":
                ret["978"] = sdr._serial
            elif sdr._type == "sdrplay":
                ret["1090"] = sdr._serial
            elif sdr._type == "rtlsdr":
                if "1090" in sdr._serial:
                    ret["1090"] = sdr._serial
                elif "978" in sdr._serial and len(self.sdrs) > 1:
                    ret["978"] = sdr._serial
        if not ret["1090"] and not ret["978"] and len(self.sdrs) == 1:
            ret["1090"] = self.sdrs[0]._serial
        return ret

    # currently not all containers support biastee
    # and of course there are many SDRs that don't support it, either, but that's not something we can detect
    def sdr_field_mapping(self, field: str, purpose: str, sdr_type: str):
        mapping = {
            "gain": {
                "1090": "1090gain",
                "1090_2": "1090_2gain",
                "978": "978gain",
                "acars": "acarsgain",
                "acars_2": "acars_2gain",
                "vdl2": "vdl2gain",
                "hfdl": "hfdlgain",
                "ais": "aisgain",
                "sonde": "sondegain",
            },
            # note -- the UI has to know where we don't support biastee
            "biastee": {
                "1090": "1090biastee",
                "1090_2": "1090_2biastee",
                "978": "978biastee",
                "acars": "acarsbiastee",
                "acars_2": "acars2biastee",
                "vdl2": "vdl2biastee",
                "hfdl": "",
                "ais": "aisbiastee",
                "sonde": "sondebiastee",
            },
        }
        if purpose.startswith("other"):
            return ""
        else:
            return mapping[field][purpose]

    def set_sdr_data(self, sdr: SDR, sdr_data):
        sdr.purpose = sdr_data["purpose"]
        sdr.gain = sdr_data["gain"]
        sdr.biastee = sdr_data["biastee"]
        return (
            self.sdr_field_mapping("gain", sdr.purpose, sdr._type),
            self.sdr_field_mapping("biastee", sdr.purpose, sdr._type),
        )

    def change_sdr_serial(self, oldserial: str, newserial: str):
        self.ensure_populated()
        rtlsdrs = [s for s in self.sdrs if s._type == "rtlsdr"]
        if len(rtlsdrs) != 1:
            print_err(f"there must be exactly one rtlsdr, but we found {len(rtlsdrs)}")
            return "[ERROR] there must be exactly one rtlsdr"
        sdr = rtlsdrs[0]
        if sdr._serial != oldserial:
            print_err(f"found rtlsdr serial {sdr._serial} but expected {oldserial}")
            return f"[ERROR] did not find RTLSDR with serial {oldserial}"
        try:
            result = subprocess.run(
                "rtl_eeprom -d 0", shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
        except subprocess.SubprocessError:
            print_err("rtl_eeprom -d 0 failed")
            return f"[ERROR] rtl_eeprom -d 0 failed"
        rtl_eeprom_text = result.stdout
        if "usb_claim_interface error" in rtl_eeprom_text:
            print_err("usb_claim_interface error in rtl_eeprom output")
            return f"[ERROR] the SDR is in use, did you stop all containers?"
        match = re.search(r"Serial number:\s*(\w+)", rtl_eeprom_text)
        if not match:
            print_err(f"could not find serial number in rtl_eeprom output '{rtl_eeprom_text}'")
            return f"[ERROR] could not find serial number in rtl_eeprom output"
        if match.group(1) != oldserial:
            print_err(f"rtl_eeprom found serial number {match.group(1)} but expected {oldserial}")
            return f"[ERROR] rtl_eeprom found serial number {match.group(1)} but expected {oldserial}"
        # ok, this looks all good. fingers crossed
        try:
            result = subprocess.run(
                f"echo 'y' | rtl_eeprom -d 0 -s {newserial}",
                shell=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except subprocess.SubprocessError:
            print_err(f"rtl_eeprom -d 0 -s {newserial} failed")
            return f"[ERROR] rtl_eeprom -d 0 -s {newserial} failed"
        print_err(f"rtl_eeprom -d 0 -s {newserial} output: {result.stdout}")

        # because we are paranoid, let's check
        try:
            result = subprocess.run(
                "rtl_eeprom -d 0", shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
        except subprocess.SubprocessError:
            print_err("verify success: rtl_eeprom -d 0 failed")
            return f"[ERROR] verify success: rtl_eeprom -d 0 failed"
        rtl_eeprom_text = result.stdout
        match = re.search(r"Serial number:\s*(\w+)", rtl_eeprom_text)
        if not match:
            print_err("verify success: could not find serial number in rtl_eeprom output")
            return f"[ERROR] verify successs: could not find serial number in rtl_eeprom output"
        if match.group(1) != newserial:
            print_err(f"verify success: rtl_eepromfound serial number {match.group(1)} but expected {newserial}")
            return f"[ERROR] verify success: rtl_eeprom found serial number {match.group(1)} but expected {newserial}"
        return "[OK] success"
