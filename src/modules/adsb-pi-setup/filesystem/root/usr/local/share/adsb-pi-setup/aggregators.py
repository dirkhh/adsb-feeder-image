import re
import subprocess
import sys
from flask import request, redirect
from utils import RESTART, ENV_FILE


def print_err(*args):
    print(*args, file=sys.stderr)


def handle_aggregators_post_request():
    if request.form.get("tar1090") == "go":
        host, port = request.server
        tar1090 = request.url_root.replace(str(port), "8080")
        return redirect(tar1090)
    if request.form.get("get-fr24-sharing-key") == "go":
        return fr24_setup()
    elif request.form.get("get-pw-api-key") == "go":
        return pw_setup()
    elif request.form.get("get-fa-api-key") == "go":
        return fa_setup()
    elif request.form.get("get-rb-sharing-key") == "go":
        return rb_setup()
    elif request.form.get("get-pf-sharecode") == "go":
        return pf_setup()
    elif request.form.get("get-ah-station-key") == "go":
        return ah_setup()
    elif request.form.get("get-os-info") == "go":
        return os_setup()
    elif request.form.get("get_rv_feeder_key") == "go":
        return rv_setup()
    else:
        # how did we get here???
        return "something went wrong"


def fr24_setup():
    sharing_key = request.form.get("FEEDER_FR24_SHARING_KEY")
    print_err(f"form.get of sharing key results in {sharing_key}")
    if not sharing_key:
        print_err("no sharing key - reload")
        return redirect("/aggegators")  # basically just a page reload
    if re.match(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', sharing_key):
        # that's an email address, so we are looking to get a sharing key
        print_err("got email address, going to request a sharing key")
        return request_fr24_sharing_key()
    if re.match("[0-9a-zA-Z]*", sharing_key):
        # that might be a valid key
        print_err(f"{sharing_key} looks like a valid sharing key")
        ENV_FILE.update({"FEEDER_FR24_SHARING_KEY": sharing_key, "FR24": "1"})
    else:
        # hmm, that's weird. we need some error return, I guess
        print_err(f"we got a text that's neither email address nor sharing key: {sharing_key}")
        return "that's not a valid sharing key"
    # we have a sharing key, let's just enable the container
    RESTART.restart_systemd()
    return redirect("/aggregators")


def pw_setup():
    api_key = request.form.get("FEEDER_PLANEWATCH_API_KEY")
    if not api_key:
        print_err("no api key - reload")
        print_err(request.form)
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the sharing key looks about right - reg exp
    ENV_FILE.update({"FEEDER_PLANEWATCH_API_KEY": api_key, "PW": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def fa_setup():
    feeder_id = request.form.get("FEEDER_PIAWARE_FEEDER_ID")
    if not feeder_id:
        print_err("no feeder ID - reload")
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_PIAWARE_FEEDER_ID": feeder_id, "FA": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def rb_setup():
    sharing_key = request.form.get("FEEDER_RADARBOX_SHARING_KEY")
    if not sharing_key:
        print_err("no sharing key - reload")
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_RADARBOX_SHARING_KEY": sharing_key, "RB": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def pf_setup():
    sharecode = request.form.get("FEEDER_PLANEFINDER_SHARECODE")
    if not sharecode:
        print_err("no sharecode - reload")
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_PLANEFINDER_SHARECODE": sharecode, "PF": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def ah_setup():
    station_key = request.form.get("FEEDER_ADSBHUB_STATION_KEY")
    if not station_key:
        print_err("no station key - reload")
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_ADSBHUB_STATION_KEY": station_key, "AH": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def os_setup():
    username = request.form.get("FEEDER_OPENSKY_USERNAME")
    serial = request.form.get("FEEDER_OPENSKY_SERIAL")
    if not username or not serial:
        print_err("no username or serial - reload")
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_OPENSKY_USERNAME": username,
                     "FEEDER_OPENSKY_SERIAL": serial,
                     "AH": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def rv_setup():
    feeder_key = request.form.get("FEEDER_RV_FEEDER_KEY")
    if not feeder_key:
        print_err("no feeder key - reload")
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_RV_FEEDER_KEY": feeder_key, "RV": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def request_fr24_sharing_key():
    if not request.form.get("FEEDER_FR24_SHARING_KEY"):
        return redirect("/aggregators")
    # create the docker command line to request a sharing key from FR24
    env_values = ENV_FILE.envs
    lat = float(env_values["FEEDER_LAT"])
    lng = float(env_values["FEEDER_LONG"])
    alt = int(int(env_values["FEEDER_ALT_M"]) / 0.308)
    email = request.form.get("FEEDER_FR24_SHARING_KEY")
    cmdline = f"docker run --rm -i -e FEEDER_LAT=\"{lat}\" -e FEEDER_LONG=\"{lng}\" -e FEEDER_ALT_FT=\"{alt}\" " \
        f"-e FR24_EMAIL=\"{email}\" --entrypoint /scripts/signup.sh ghcr.io/sdr-enthusiasts/docker-flightradar24"
    result = subprocess.run(cmdline, timeout=60.0, shell=True, capture_output=True)
    # need to catch timeout error
    sharing_key_match = re.search("Your sharing key \\(([a-zA-Z0-9]*)\\) has been", str(result.stdout))
    if sharing_key_match:
        sharing_key = sharing_key_match.group(1)
        ENV_FILE.update({"FEEDER_FR24_SHARING_KEY": sharing_key, "FR24": "1"})
        RESTART.restart_systemd()
    return redirect("/aggregators")
    #    return "placeholder for waiting page"
