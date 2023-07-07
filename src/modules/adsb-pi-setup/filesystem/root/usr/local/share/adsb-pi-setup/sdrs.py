import subprocess
import re
import io
from utils import ENV_FILE, print_err


def map_sdrs():
    env_values = ENV_FILE.envs
    sdrs = get_sdr_info()
    mapping = {}
    if env_values.get("SDR_MANUALLY_ASSIGNED") != "1":
        # they haven't been assigned yet, so let's make some
        # assumptions to get started:
        # - if we find an airspy, that's for 1090
        # - if we find an RTL SDR with serial 1090 - well, that's for 1090 (unless you have an airspy)
        # - if we find an RTL SDR with serial 978 - that's for 978
        # - if we find just one RTL SDR and no airspy, then that RTL SDR is for 1090
        have_airspy = any([sdr["type"] == "airspy" for sdr in sdrs["sdrs"]])
        have_1090 = any([sdr["type"] == "rtlsdr" and sdr["serial"] == "1090" for sdr in sdrs["sdrs"]])
        have_978 = any([sdr["type"] == "rtlsdr" and sdr["serial"] == "978" for sdr in sdrs["sdrs"]])
        if have_airspy:
            mapping["FEEDER_1090"] = "airspy"
        elif have_1090:
            mapping["FEEDER_1090"] = "1090"
        if have_978:
            mapping["FEEDER_978"] = "978"
        if sdrs["num"] == 1 and not (mapping.get("FEEDER_978") or mapping.get("FEEDER_1090")):
            sdr = sdrs["sdrs"][0]
            mapping["FEEDER_1090"] = sdr["serial"]
    else:
        mapping["FEEDER_1090"] = env_values.get("FEEDER_1090")
        mapping["FEEDER_978"] = env_values.get("FEEDER_978")
    return mapping


def get_sdr_info():
    sdrs = {"num": 0, "sdrs": []}
    try:
        result = subprocess.run("lsusb", shell=True, capture_output=True)
    except subprocess.SubprocessError:
        print_err("lsusb failed")
    output = io.StringIO(result.stdout.decode())
    for line in output:
        rtl_sdr_match = re.search("Bus ([0-9a-fA-F]+) Device ([0-9a-fA-F]+): ID 0bda:2838", line)
        if rtl_sdr_match:
            address = f"{rtl_sdr_match.group(1)}:{rtl_sdr_match.group(2)}"
            print_err(f"get_sdr_info() found RTL SDR at {address}")
            sdrs["num"] += 1
            sdrs["sdrs"].append({"type": "rtlsdr", "address": address, "serial": get_serial(address)})
        airspy_match = re.search("Bus ([0-9a-fA-F]+) Device ([0-9a-fA-F]+): ID 1d50:60a1", line)
        if airspy_match:
            address = f"{airspy_match.group(1)}:{airspy_match.group(2)}"
            print_err(f"get_sdr_info() found Airspy at {address}")
            sdrs["num"] += 1
            sdrs["sdrs"].append({"type": "airspy", "address": address, "serial": get_serial(address)})
    return sdrs


def get_serial(address: str) -> str:
    try:
        result = subprocess.run(f"lsusb -s {address} -v", shell=True, capture_output=True)
    except subprocess.SubprocessError:
        print_err(f"'lsusb -s {address} -v' failed")
    output = result.stdout.decode()
    serial_match = re.search(r"iSerial\s+\d+\s+(.*)", output, flags=re.M)
    if serial_match:
        return serial_match.group(1)
    return ""

