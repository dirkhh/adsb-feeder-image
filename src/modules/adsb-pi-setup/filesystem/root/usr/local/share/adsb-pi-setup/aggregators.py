import re
import subprocess
from flask import request, redirect
from utils import RESTART, ENV_FILE, print_err


def handle_aggregators_post_request():
    print_err(request.form)
    if request.form.get("tar1090") == "go":
        update_env()
        RESTART.restart_systemd()
        return redirect("/restarting")
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
    elif request.form.get("get-rv-feeder-key") == "go":
        return rv_setup()
    else:
        # how did we get here???
        return "something went wrong"


def update_env():
    checkboxes = ["FR24", "PW", "FA", "RB", "PF", "AH", "OS", "RV"]
    env_updates = {}
    for box in checkboxes:
        env_updates[box] = "1" if request.form.get(box) == "on" else "0"
    net = ENV_FILE.generate_ultrafeeder_config(request.form)
    env_updates["FEEDER_ULTRAFEEDER_CONFIG"] = net
    env_updates["UF"] = "1" if net else "0"
    # we should also check that there are the right keys given...
    ENV_FILE.update(env_updates)


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
    print_err(f"form.get of api key results in {api_key}")
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
    print_err(f"form.get of feeder id results in {feeder_id}")
    if not feeder_id:
        print_err("no feeder ID - request one")
        return request_fa_feeder_id()
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_PIAWARE_FEEDER_ID": feeder_id, "FA": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def rb_setup():
    sharing_key = request.form.get("FEEDER_RADARBOX_SHARING_KEY")
    print_err(f"form.get of sharing key results in {sharing_key}")
    if not sharing_key:
        print_err("no sharing key - request one")
        return request_rb_feeder_id()
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_RADARBOX_SHARING_KEY": sharing_key, "RB": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def pf_setup():
    sharecode = request.form.get("FEEDER_PLANEFINDER_SHARECODE")
    print_err(f"form.get of sharecode results in {sharecode}")
    if not sharecode:
        print_err("no sharecode - reload")
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_PLANEFINDER_SHARECODE": sharecode, "PF": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def ah_setup():
    station_key = request.form.get("FEEDER_ADSBHUB_STATION_KEY")
    print_err(f"form.get of station key results in {station_key}")
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
    print_err(f"form.get of username results in {username}")
    print_err(f"form.get of serial results in {serial}")
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
    print_err(f"form.get of feeder key results in {feeder_key}")
    if not feeder_key:
        print_err("no feeder key - reload")
        return redirect("/aggregators")  # basically just a page reload - needs some error instead
    # here we should check if the feeder id looks about right - reg exp
    ENV_FILE.update({"FEEDER_RV_FEEDER_KEY": feeder_key, "RV": "1"})
    RESTART.restart_systemd()
    return redirect("/aggregators")


def download_docker_container(container: str) -> bool:
    cmdline = f"docker pull {container}"
    try:
        result = subprocess.run(cmdline, timeout=180.0, shell=True)
    except subprocess.TimeoutExpired:
        return False
    return True


def docker_run_with_timeout(arguments: str, timeout: float) -> str:
    cmdline = f"docker run --name temp_container {arguments}"
    try:
        result = subprocess.run(cmdline, timeout=timeout, shell=True, capture_output=True)
    except subprocess.TimeoutExpired as exc:
        # for several of these containers "timeout" is actually the expected behavior;
        # they don't stop on their own. So just grab the output and kill the container
        output = str(exc.stdout)
        try:
            result = subprocess.run("docker rm -f temp_container", timeout=10.0, shell=True, capture_output=True)
        except subprocess.TimeoutExpired:
            print_err(f"failed to remove the temp container {str(result.stdout)} / {str(result.stderr)}")
    else:
        output = str(result.stdout)
    return output


def request_fr24_sharing_key():
    env_values = ENV_FILE.envs
    lat = float(env_values["FEEDER_LAT"])
    lng = float(env_values["FEEDER_LONG"])
    alt = int(int(env_values["FEEDER_ALT_M"]) / 0.308)
    email = request.form.get("FEEDER_FR24_SHARING_KEY")
    container_name = env_values["FR24_CONTAINER"]
    if download_docker_container(container_name):
        cmdline = f"--rm -i -e FEEDER_LAT=\"{lat}\" -e FEEDER_LONG=\"{lng}\" -e FEEDER_ALT_FT=\"{alt}\" " \
                  f"-e FR24_EMAIL=\"{email}\" --entrypoint /scripts/signup.sh {container_name}"
        output = docker_run_with_timeout(cmdline, 45.0)
        sharing_key_match = re.search("Your sharing key \\(([a-zA-Z0-9]*)\\) has been", output)
        if sharing_key_match:
            sharing_key = sharing_key_match.group(1)
            ENV_FILE.update({"FEEDER_FR24_SHARING_KEY": sharing_key, "FR24": "1"})
            RESTART.restart_systemd()
        else:
            print_err(f"couldn't find a sharing key in the container output: {output}")
    else:
        print_err("failed to download the FR24 docker image")
    return redirect("/aggregators")


def request_fa_feeder_id():
    container_name = ENV_FILE.envs['FA_CONTAINER']
    if download_docker_container(container_name):
        cmdline = f"--rm {container_name}"
        output = docker_run_with_timeout(cmdline, 45.0)
        feeder_id_match = re.search(" feeder ID is ([-a-zA-Z0-9]*)", output)
        if feeder_id_match:
            feeder_id = feeder_id_match.group(1)
            ENV_FILE.update({"FEEDER_PIAWARE_FEEDER_ID": feeder_id, "FA": "1"})
            RESTART.restart_systemd()
        else:
            print_err(f"couldn't find a feeder ID in the container output: {output}")
    else:
        print_err("failed to download the piaware docker image")
    return redirect("/aggregators")


def request_rb_feeder_id():
    env_values = ENV_FILE.envs
    lat = float(env_values["FEEDER_LAT"])
    lng = float(env_values["FEEDER_LONG"])
    alt = int(env_values["FEEDER_ALT_M"])
    container_name = env_values["RB_CONTAINER"]
    if download_docker_container(container_name):
        cmdline = f"--rm -i --network adsb_default -e BEASTHOST=ultrafeeder -e LAT=${lat} " \
                  f"-e LONG=${lng} -e ALT=${alt} {container_name}"
        output = docker_run_with_timeout(cmdline, 45.0)
        sharing_key_match = re.search("Your new key is ([a-zA-Z0-9]*)", output)
        if sharing_key_match:
            sharing_key = sharing_key_match.group(1)
            ENV_FILE.update({"FEEDER_RADARBOX_SHARING_KEY": sharing_key, "RB": "1"})
            RESTART.restart_systemd()
        else:
            print_err(f"couldn't find a sharing key in the container output: {output}")
    else:
        print_err("failed to download the radarbox docker image")
    return redirect("/aggregators")
