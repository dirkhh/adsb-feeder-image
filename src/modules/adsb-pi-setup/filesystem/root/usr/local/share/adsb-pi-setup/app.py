import re
import subprocess
import threading
from os import path, urandom, getenv
from typing import Dict

from flask import Flask, redirect, render_template, request
from uuid import uuid4
from pprint import pprint


class DockerCompose:
    def __init__(self, docker_compose_path: str):
        self.docker_compose_path = docker_compose_path


class Restart:
    def __init__(self):
        self.lock = threading.Lock()

    def restart_systemd(self):
        # if locked, return immediately
        if self.lock.locked():
            return False
        with self.lock:
            subprocess.call("/usr/bin/systemctl restart adsb-docker", shell=True)
            subprocess.call("/usr/bin/systemctl disable adsb-bootstrap", shell=True)
            subprocess.call("/usr/bin/systemctl stop adsb-bootstrap", shell=True)

    @property
    def state(self):
        if self.lock.locked():
            return "restarting"
        return "done"


class NetConfigs:
    def __init__(self):
        self.configs = {
            "adsblol": "adsb,feed.adsb.lol,30004,beast_reduce_plus_out,uuid=${ADSBLOL_UUID};mlat,feed.adsb.lol,31090,39001,uuid=${ADSBLOL_UUID},${MLAT_PRIVACY}",
            "adsbx": "adsb,feed1.adsbexchange.com,30004,beast_reduce_plus_out;mlat,feed.adsbexchange.com,31090,39005,${MLAT_PRIVACY}",
            "theairtraffic": "adsb,feed.theairtraffic.com,30004,beast_reduce_plus_out;mlat,feed.theairtraffic.com,31090,39004,${MLAT_PRIVACY}",
            "planespotters": "adsb,feed.planespotters.net,30004,beast_reduce_plus_out;mlat,mlat.planespotters.net,31090,39003,${MLAT_PRIVACY}",
            "adsbone": "adsb,feed.adsb.one,64004,beast_reduce_plus_out;mlat,feed.adsb.one,64006,39002,${MLAT_PRIVACY}",
            "adsbfi": "adsb,feed.adsb.fi,30004,beast_reduce_plus_out;mlat,feed.adsb.fi,31090,39000,${MLAT_PRIVACY}",
        }

    def get_config(self, key, replacements):
        config = self.configs.get(key)
        if config:
            for var, value in replacements.items():
                config = config.replace(var, value)
            return config
        return None

    def get_keys(self):
        return self.configs.keys()


class EnvFile:
    def __init__(self, env_file_path: str, restart: Restart = None):
        self.env_file_path = env_file_path
        self.restart = restart

    def _setup(self):
        # if file does not exist, create it
        if not path.isfile(self.env_file_path):
            open(self.env_file_path, "w").close()

    @property
    def envs(self):
        self._setup()
        env_values = {}

        with open(self.env_file_path) as f:
            for line in f.readlines():
                if line.strip().startswith("#"):
                    continue
                key, var = line.partition("=")[::2]
                env_values[key.strip()] = var.strip()
        original_env_values = env_values.copy()

        env_values.setdefault("FEEDER_TAR1090_USEROUTEAPI", "1")
        env_values.setdefault("ADSBLOL_UUID", str(uuid4()))
        env_values.setdefault("ULTRAFEEDER_UUID", str(uuid4()))
        env_values.setdefault("MLAT_PRIVACY", "--privacy")
        env_values.setdefault(
            "FEEDER_ULTRAFEEDER_CONFIG",
            NETCONFIGS.get_config(
                "adsblol",
                replacements={
                    "${MLAT_PRIVACY}": env_values.get("MLAT_PRIVACY", "--privacy"),
                    "${ADSBLOL_UUID}": env_values.get("ADSBLOL_UUID", str(uuid4())),
                },
            ),
        )

        print("env_values:")
        pprint(env_values)

        print("DIFF DETECTED!")
        pprint(original_env_values)

        if env_values != original_env_values:
            self.update(env_values)
        return env_values

    def update(self, values: Dict[str, str]):
        self._setup()
        if not path.isfile(self.env_file_path):
            open(self.env_file_path, "w").close()

        with open(self.env_file_path, "r") as ef:
            lines = ef.readlines()

        updated_values = values.copy()
        for idx, line in enumerate(lines):
            for key in values.keys():
                match = re.search(f"(^[^#]*{key}[^#]*=)[^#]*", line)
                if match:
                    lines[idx] = f"{match.group(1)}{values[key]}\n"
                    updated_values.pop(key, None)

        lines.extend(f"{key}={value}\n" for key, value in updated_values.items())

        with open(self.env_file_path, "w") as ef:
            ef.writelines(lines)

    @property
    def metadata(self):
        env_values = self.envs
        metadata = {}

        # Extract the required keys and their values from env_values
        replacements = {
            "${ADSBLOL_UUID}": env_values["ADSBLOL_UUID"],
            "${MLAT_PRIVACY}": env_values["MLAT_PRIVACY"],
        }

        for key in NETCONFIGS.get_keys():
            metadata[key] = (
                "checked"
                if NETCONFIGS.get_config(key, replacements)
                in env_values["FEEDER_ULTRAFEEDER_CONFIG"]
                else ""
            )
        metadata["adv_visible"] = (
            all(
                key in env_values and float(env_values[key]) != 0
                for key in ["FEEDER_LAT", "FEEDER_LONG", "FEEDER_ALT_M"]
            )
            and not self.restart.lock.locked()
        )

        metadata["route"] = (
            "checked" if env_values["FEEDER_TAR1090_USEROUTEAPI"] == "1" else ""
        )
        metadata["privacy"] = (
            "checked" if env_values["MLAT_PRIVACY"] == "--privacy" else ""
        )
        from pprint import pprint

        pprint(metadata)
        return metadata


app = Flask(__name__)
app.secret_key = urandom(16).hex()
RESTART = Restart()
ENV_FILE = EnvFile(
    env_file_path=getenv("ADSB_PI_SETUP_ENVFILE", "/opt/adsb/.env"), restart=RESTART
)
ENV_FILE._setup()
NETCONFIGS = NetConfigs()


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
        restart = RESTART.restart_systemd()
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

    replacements = {
        "${ADSBLOL_UUID}": ENV_FILE.envs.get("ADSBLOL_UUID"),
        "${MLAT_PRIVACY}": ENV_FILE.envs.get("MLAT_PRIVACY"),
    }

    net_configs_list = []
    for key in NETCONFIGS.get_keys():
        if request.form.get(key):
            net_configs_list.append(NETCONFIGS.get_config(key, replacements))
    net = ";".join(net_configs_list) or NETCONFIGS.get_config("adsblol", replacements)

    ENV_FILE.update(
        {
            "FEEDER_TAR1090_USEROUTEAPI": "1" if request.form.get("route") else "0",
            "FEEDER_ULTRAFEEDER_CONFIG": net,
            "MLAT_PRIVACY": "--privacy" if request.form.get("privacy") else "",
        }
    )
    return redirect("/restarting")


@app.route("/", methods=("GET", "POST"))
def setup():
    if request.args.get("success"):
        return redirect("/advanced")
    if RESTART.lock.locked():
        return redirect("/restarting")

    if request.method == "POST":
        lat, lng, alt, form_timezone, mlat_name = (
            request.form[key] for key in ["lat", "lng", "alt", "form_timezone", "mlat_name"]
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
