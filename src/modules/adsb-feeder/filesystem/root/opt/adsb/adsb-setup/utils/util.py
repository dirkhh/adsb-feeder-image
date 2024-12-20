import hashlib
import inspect
import itertools
import math
import os
import pathlib
import re
import secrets
import requests
import sys
import time
import subprocess
import tempfile
import traceback

verbose = (
    0 if not os.path.exists("/opt/adsb/config/verbose") else int(open("/opt/adsb/config/verbose", "r").read().strip())
)

# create a board unique but otherwise random / anonymous ID
idhash = hashlib.md5(pathlib.Path("/etc/machine-id").read_text().encode()).hexdigest()


def stack_info(msg=""):
    framenr = 0
    for frame, filename, line_num, func, source_code, source_index in inspect.stack():
        if framenr == 0:
            framenr += 1
            continue
        print_err(f" .. [{framenr}] {filename}:{line_num}: in {func}()")
        if framenr == 1:
            fname = func
        framenr += 1
        if func.startswith("dispatch_request"):
            break
    if msg:
        print_err(f" == {fname}: {msg}")


# let's do this just once, not at every call
_clean_control_chars = "".join(map(chr, itertools.chain(range(0x00, 0x20), range(0x7F, 0xA0))))
_clean_control_char_re = re.compile("[%s]" % re.escape(_clean_control_chars))


def cleanup_str(s):
    return _clean_control_char_re.sub("", s)


def print_err(*args, **kwargs):
    level = int(kwargs.pop("level", 0))
    if level > 0 and int(verbose) & int(level) == 0:
        return
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".{0:03.0f}Z".format(
        math.modf(time.time())[0] * 1000
    )
    print(*((timestamp,) + args), file=sys.stderr, **kwargs)


# this is based on https://www.regular-expressions.info/email.html
def is_email(text: str):
    return re.match(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)


# extend the truthy concept to exclude all non-empty string except a few specific ones ([Tt]rue, [Oo]n, 1)
def is_true(value):
    if type(value) == str:
        return value.lower() in ["true", "on", "1"]
    return bool(value)


def make_int(value):
    try:
        return int(value)
    except:
        stack_info(f"ERROR: make_int({value}) - returning 0")
        return 0


def generic_get_json(url: str, data=None, timeout=5.0):
    requests.packages.urllib3.util.connection.HAS_IPV6 = False
    if "host.docker.internal" in url:
        url = url.replace("host.docker.internal", "localhost")
    # use image specific but random value for user agent to distinguish
    # between requests from the same IP but different feeders
    agent = f"ADS-B Image-{idhash[:8]}"
    status = -1
    try:
        response = requests.request(
            method="GET" if data == None else "POST",
            url=url,
            timeout=timeout,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": agent,
            },
        )
        json_response = response.json()
    except (
        requests.HTTPError,
        requests.ConnectionError,
        requests.Timeout,
        requests.RequestException,
    ) as err:
        print_err(f"checking {url} failed: {err}")
        status = err.errno
    except:
        # for some reason this didn't work
        print_err("checking {url} failed: reason unknown")
    else:
        return json_response, response.status_code
    return None, status


def create_fake_info():
    # instead of trying to figure out if we need this and creating it only in that case,
    # let's just make sure the fake files are there and move on
    os.makedirs("/opt/adsb/rb/thermal_zone0", exist_ok=True)
    cpuinfo = pathlib.Path("/opt/adsb/rb/cpuinfo")
    # when docker tries to mount this file without it existing, it creates a directory
    # in case that has happened, remove it
    if cpuinfo.is_dir():
        try:
            cpuinfo.rmdir()
        except:
            pass
    if not cpuinfo.exists():
        with open("/proc/cpuinfo", "r") as ci_in, open(cpuinfo, "w") as ci_out:
            for line in ci_in:
                if not line.startswith("Serial"):
                    ci_out.write(line)
            random_hex_string = secrets.token_hex(8)
            ci_out.write(f"Serial\t\t: {random_hex_string}\n")
    if not pathlib.Path("/opt/adsb/rb/thermal_zone0/temp").exists():
        with open("/opt/adsb/rb/thermal_zone0/temp", "w") as fake_temp:
            fake_temp.write("12345\n")
    return not pathlib.Path("/sys/class/thermal/thermal_zone0/temp").exists()


def mf_get_ip_and_triplet(ip):
    # mf_ip for microproxies can either be an IP or a triplet of ip,port,protocol
    split = ip.split(",")
    if len(split) != 1:
        # the function was passed a triplet, set the ip to the first part
        triplet = ip
        ip = split[0]
    else:
        # the fucntion was passed an IP, port 30005 and protocol beast_in are implied
        # unless we are a stage2 getting data from a nanofeeder on localhost
        if ip == "local":
            # container to container connections we do directly, use nanofeeder
            triplet = f"nanofeeder,30005,beast_in"
            # this ip is used to talk to the python running on the host, use host.docker.internal
            ip = "host.docker.internal"
        else:
            triplet = f"{ip},30005,beast_in"

    return (ip, triplet)


def run_shell_captured(command="", timeout=1800):
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            check=True,
            timeout=timeout,
        )
    except subprocess.SubprocessError as e:
        # something went wrong
        output = ""
        if e.stdout:
            output += e.stdout.decode()
        if e.stderr:
            output += e.stderr.decode()
        return (False, output)

    output = result.stdout.decode()
    return (True, output)


def string2file(path=None, string=None, verbose=False):
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
        with os.fdopen(fd, "w") as file:
            file.write(string)
        os.rename(tmp, path)
    except:
        print_err(traceback.format_exc())
        print_err(f'error writing "{string}" to {path}')
    else:
        if verbose:
            print_err(f'wrote "{string}" to {path}')


def get_plain_url(plain_url):
    requests.packages.urllib3.util.connection.HAS_IPV6 = False
    status = -1
    try:
        response = requests.get(
                plain_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/117.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    },
                )
    except (
            requests.HTTPError,
            requests.ConnectionError,
            requests.Timeout,
            requests.RequestException,
            ) as err:
        print_err(f"checking {plain_url} failed: {err}")
        status = err.errno
    except:
        print_err("checking {plain_url} failed: {traceback.format_exc()}")
    else:
        return response.text, response.status_code
    return None, status
