import inspect
import itertools
import math
import re
import requests
import sys
import time


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
_clean_control_chars = "".join(
    map(chr, itertools.chain(range(0x00, 0x20), range(0x7F, 0xA0)))
)
_clean_control_char_re = re.compile("[%s]" % re.escape(_clean_control_chars))


def cleanup_str(s):
    return _clean_control_char_re.sub("", s)


def print_err(*args, **kwargs):
    timestamp = time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.gmtime()
    ) + ".{0:03.0f}Z".format(math.modf(time.time())[0] * 1000)
    print(*((timestamp,) + args), file=sys.stderr, **kwargs)


# this is based on https://www.regular-expressions.info/email.html
def is_email(text: str):
    return re.match(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)


# extend the truthy concept to exclude all non-empty string except a few specific ones ([Tt]rue, [Oo]n, 1)
def is_true(value):
    if type(value) == str:
        return any({value.lower() == "true", value.lower == "on", value == "1"})
    return bool(value)


def generic_get_json(url: str, data):
    requests.packages.urllib3.util.connection.HAS_IPV6 = False
    status = -1
    try:
        response = requests.request(
            method="GET" if data == None else "POST",
            url=url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ADS-B Image",
            },
        )
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
        return response.json(), response.status_code
    return None, status
