import re
import shutil
import sys
from os import urandom, path
from flask import Flask, render_template, request, redirect
from utils import RESTART, ENV_FILE
import subprocess

app = Flask(__name__)
app.secret_key = urandom(16).hex()


def print_err(*args):
    print(*args, file=sys.stderr)


@app.route("/propagateTZ")
def get_tz():
    browser_timezone = request.args.get("tz")
    env_values = ENV_FILE.envs
    env_values["FEEDER_TZ"] = browser_timezone
    return render_template(
        "index.html", env_values=env_values, metadata=ENV_FILE.metadata
    )


@app.route("/restarting", methods=(["GET"]))
def restarting():
    return render_template(
        "restarting.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata
    )


@app.route("/restart", methods=(["GET", "POST"]))
def restart():
    if request.method == "POST":
        RESTART.restart_systemd()
        return "restarting" if restart else "already restarting"
    if request.method == "GET":
        return RESTART.state


@app.route("/advanced", methods=("GET", "POST"))
def advanced():
    if request.method == "POST":
        return handle_advanced_post_request()
    env_values = ENV_FILE.envs
    if RESTART.lock.locked():
        return redirect("/restarting")
    return render_template(
        "advanced.html", env_values=env_values, metadata=ENV_FILE.metadata
    )


def handle_advanced_post_request():
    if request.form.get("tar1090") == "go":
        host, port = request.server
        tar1090 = request.url_root.replace(str(port), "8080")
        return redirect(tar1090)

    if request.form.get("expert") == "go":
        return redirect("/expert")

    if request.form.get("aggregators") == "go":
        return redirect("/aggregators")

    print("request_form", request.form)

    ENV_FILE.update(
        {
            "FEEDER_TAR1090_USEROUTEAPI": "1" if request.form.get("route") else "0",
            "MLAT_PRIVACY": "--privacy" if request.form.get("privacy") else "",
        }
    )
    net = ENV_FILE.generate_ultrafeeder_config(request.form)
    ENV_FILE.update({"FEEDER_ULTRAFEEDER_CONFIG": net})
    return redirect("/restarting")


@app.route("/expert", methods=("GET", "POST"))
def expert():
    if request.method == "POST":
        return handle_expert_post_request()
    env_values = ENV_FILE.envs
    if RESTART.lock.locked():
        return redirect("/restarting")
    filecontent = {'have_backup': False}
    if path.exists("/opt/adsb/env-working") and path.exists("/opt/adsb/docker-compose.yml-working"):
        filecontent['have_backup'] = True
    with open("/opt/adsb/.env", "r") as env:
        filecontent['env'] = env.read()
    with open("/opt/adsb/docker-compose.yml") as dc:
        filecontent['dc'] = dc.read()
    return render_template(
        "expert.html", env_values=env_values, metadata=ENV_FILE.metadata, filecontent=filecontent
    )


def handle_expert_post_request():
    if request.form.get("you-asked-for-it") == "you-got-it":
        # well - let's at least try to save the old stuff
        if not path.exists("/opt/adsb/env-working"):
            try:
                shutil.copyfile("/opt/adsb/.env", "/opt/adsb/env-working")
            except shutil.Error as err:
                print(f"copying .env didn't work: {err.args[0]}: {err.args[1]}")
        if not path.exists("/opt/adsb/dc-working"):
            try:
                shutil.copyfile("/opt/adsb/docker-compose.yml", "/opt/adsb/docker-compose.yml-working")
            except shutil.Error as err:
                print(f"copying docker-compose.yml didn't work: {err.args[0]}: {err.args[1]}")
        with open("/opt/adsb/.env", "w") as env:
            env.write(request.form["env"])
        with open("/opt/adsb/docker-compose.yml", "w") as dc:
            dc.write(request.form["dc"])

        RESTART.restart_systemd()
        return redirect("restarting")

    if request.form.get("you-got-it") == "give-it-back":
        # do we have saved old files?
        if path.exists("/opt/adsb/env-working"):
            try:
                shutil.copyfile("/opt/adsb/env-working", "/opt/adsb/.env")
            except shutil.Error as err:
                print(f"copying .env didn't work: {err.args[0]}: {err.args[1]}")
        if path.exists("/opt/adsb/docker-compose.yml-working"):
            try:
                shutil.copyfile("/opt/adsb/docker-compose.yml-working", "/opt/adsb/docker-compose.yml")
            except shutil.Error as err:
                print(f"copying docker-compose.yml didn't work: {err.args[0]}: {err.args[1]}")

        RESTART.restart_systemd()
        return redirect("restarting")

    print("request_form", request.form)
    return redirect("/advanced")


@app.route("/aggregators", methods=("GET", "POST"))
def aggregators():
    if request.method == "POST":
        return handle_aggregators_post_request()
    env_values = ENV_FILE.envs
    if RESTART.lock.locked():
        return redirect("/restarting")
    return render_template(
        "aggregators.html", env_values=env_values, metadata=ENV_FILE.metadata
    )


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


@app.route("/", methods=("GET", "POST"))
def setup():
    if request.args.get("success"):
        return redirect("/advanced")
    if RESTART.lock.locked():
        return redirect("/restarting")

    if request.method == "POST":
        lat, lng, alt, form_timezone, mlat_name = (
            request.form[key]
            for key in ["lat", "lng", "alt", "form_timezone", "mlat_name"]
        )

        if all([lat, lng, alt, form_timezone]):
            ENV_FILE.update(
                {
                    "FEEDER_LAT": lat,
                    "FEEDER_LONG": lng,
                    "FEEDER_ALT_M": alt,
                    "FEEDER_TZ": form_timezone,
                    "MLAT_SITE_NAME": mlat_name,
                }
            )
            return redirect("/restarting")

    return render_template(
        "index.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
