import hashlib
import inspect
import itertools
import math
import os
import pathlib
import re
import secrets
import subprocess
import sys
import tempfile
import time
import traceback

import requests
from flask import flash

# Import paths after they might be configured
try:
    from .paths import FAKE_CPUINFO_DIR, FAKE_THERMAL_TEMP_FILE, FAKE_THERMAL_ZONE_DIR, MACHINE_ID_FILE, VERBOSE_FILE
except ImportError:
    # Fallback for when paths module is not available
    import os as _os

    _ADSB_BASE_DIR = pathlib.Path(_os.environ.get("ADSB_BASE_DIR", "/opt/adsb"))
    VERBOSE_FILE = _ADSB_BASE_DIR / "config" / "verbose"
    MACHINE_ID_FILE = pathlib.Path("/etc/machine-id")
    FAKE_CPUINFO_DIR = _ADSB_BASE_DIR / "rb"
    FAKE_THERMAL_ZONE_DIR = FAKE_CPUINFO_DIR / "thermal_zone0"
    FAKE_THERMAL_TEMP_FILE = FAKE_THERMAL_ZONE_DIR / "temp"

verbose = 0 if not VERBOSE_FILE.exists() else int(VERBOSE_FILE.read_text().strip())

# create a board unique but otherwise random / anonymous ID
idhash = hashlib.md5(MACHINE_ID_FILE.read_text().encode()).hexdigest()


def stack_info(msg=""):
    framenr = 0
    fname = ""
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
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".{0:03.0f}Z".format(math.modf(time.time())[0] * 1000)
    print(*((timestamp,) + args), file=sys.stderr, **kwargs)


def report_issue(msg):
    print_err(msg, level=1)
    try:
        flash(msg)
    except Exception:
        print_err(traceback.format_exc())


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
    except Exception:
        stack_info(f"ERROR: make_int({value}) - returning 0")
        return 0


def generic_get_json(url: str, data=None, timeout=5.0):
    requests.packages.urllib3.util.connection.HAS_IPV6 = False  # type: ignore[attr-defined]
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
        status = err.errno if err.errno else -1
    except Exception:
        # for some reason this didn't work
        print_err("checking {url} failed: reason unknown")
    else:
        return json_response, response.status_code
    return None, status


def create_fake_info(indices):
    # instead of trying to figure out if we need this and creating it only in that case,
    # let's just make sure the fake files are there and move on
    os.makedirs(FAKE_THERMAL_ZONE_DIR, exist_ok=True)

    for idx in indices:
        # Validate idx to prevent path traversal attacks
        if idx is not None:
            # idx must be an integer
            if not isinstance(idx, int):
                raise ValueError(f"Index must be an integer or None, got {type(idx).__name__}: {idx}")
            # idx must be in safe range (0-99)
            if idx < 0 or idx > 99:
                raise ValueError(f"Index must be in range 0-99, got {idx}")

        suffix = f"_{idx}" if idx else ""
        cpuinfo = FAKE_CPUINFO_DIR / f"cpuinfo{suffix}"

        # Verify path stays within FAKE_CPUINFO_DIR to prevent path traversal
        # resolve() makes the path absolute and resolves any '..' components
        resolved_cpuinfo = cpuinfo.resolve()
        resolved_base = FAKE_CPUINFO_DIR.resolve()

        # Check if the resolved path is within the base directory
        try:
            resolved_cpuinfo.relative_to(resolved_base)
        except ValueError:
            raise ValueError(f"Path traversal detected: {cpuinfo} resolves to {resolved_cpuinfo}, outside {resolved_base}")

        # when docker tries to mount this file without it existing, it creates a directory
        # in case that has happened, remove it
        if cpuinfo.is_dir():
            try:
                cpuinfo.rmdir()
            except Exception:
                pass
        if not cpuinfo.exists():
            with open("/proc/cpuinfo", "r") as ci_in, open(cpuinfo, "w") as ci_out:
                for line in ci_in:
                    if not line.startswith("Serial"):
                        ci_out.write(line)
                random_hex_string = secrets.token_hex(8)
                ci_out.write(f"Serial\t\t: {random_hex_string}\n")

    if not FAKE_THERMAL_TEMP_FILE.exists():
        with open(FAKE_THERMAL_TEMP_FILE, "w") as fake_temp:
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
        elif ip == "local2":
            # container to container connections we do directly, use nanofeeder
            triplet = f"nanofeeder_2,30005,beast_in"
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
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        # something went wrong
        output = ""
        if e.stdout:
            output += e.stdout.decode()
        if e.stderr:
            output += e.stderr.decode()
        return (False, output)
    except Exception as e:
        # catch any other unexpected exceptions
        print_err(f"run_shell_captured: unexpected exception {e}")
        return (False, str(e))

    output = result.stdout.decode()
    return (True, output)


def string2file(path: str = "", string: str = "", verbose: bool = False):
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
        with os.fdopen(fd, "w") as file:
            file.write(string)
        os.rename(tmp, path)
    except Exception as e:
        # print_err(traceback.format_exc())
        print_err(f'error writing "{string}" to {path} ({type(e).__name__})')
    else:
        if verbose:
            print_err(f'wrote "{string}" to {path}')


def get_plain_url(plain_url, method="GET", data=None):
    requests.packages.urllib3.util.connection.HAS_IPV6 = False  # type: ignore[attr-defined]
    status = -1
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/117.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    method = method.upper()
    if data is not None:
        # sending plain text for custom bodies
        headers["Content-Type"] = "text/plain; charset=utf-8"
    try:
        response = requests.request(method=method, url=plain_url, headers=headers, data=data)
    except (
        requests.HTTPError,
        requests.ConnectionError,
        requests.Timeout,
        requests.RequestException,
    ) as err:
        print_err(f"checking {plain_url} failed: {err}")
        status = err.errno if err.errno else -1
    except Exception:
        print_err("checking {plain_url} failed: {traceback.format_exc()}")
    else:
        return response.text, response.status_code
    return None, status
