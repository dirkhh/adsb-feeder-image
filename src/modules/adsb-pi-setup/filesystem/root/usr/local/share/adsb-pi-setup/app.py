import filecmp
import io
import json
from operator import is_
import os.path
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile
from functools import partial
from os import path, urandom
from typing import Dict, List, Tuple

from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from utils import (
    ADSBHub,
    Constants,
    Env,
    FlightAware,
    FlightRadar24,
    OpenSky,
    PlaneFinder,
    PlaneWatch,
    RadarBox,
    RadarVirtuel,
    RouteManager,
    SDRDevices,
    System,
    check_restart_lock,
    UltrafeederConfig,
)
from werkzeug.utils import secure_filename


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class AdsbIm:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = urandom(16).hex()

        @self.app.context_processor
        def env_functions():
            return {
                "is_enabled": lambda tag: self._constants.is_enabled(tag),
                "env_value_by_tag": lambda tag: self._constants.env_by_tags([tag]).value,  # this one takes a single tag
                "env_value_by_tags": lambda tags: self._constants.env_by_tags(tags).value, # this one takes a list of tags
                "env_values": self._constants.envs,
            }

        self._routemanager = RouteManager(self.app)
        self._constants = Constants()

        self._system = System(constants=self._constants)
        self._sdrdevices = SDRDevices()
        self._ultrafeeder = UltrafeederConfig(constants=self._constants)

        # update Env ultrafeeder to have value self._ultrafeed.generate()
        self._constants.env_by_tags("ultrafeeder_config")._value_call = self._ultrafeeder.generate

        self._other_aggregators = {
            "adsb_hub": ADSBHub(self._system),
            "flightaware": FlightAware(self._system),
            "flightradar24": FlightRadar24(self._system),
            "opensky": OpenSky(self._system),
            "planefinder": PlaneFinder(self._system),
            "planewatch": PlaneWatch(self._system),
            "radarbox": RadarBox(self._system),
            "radarvirtuel": RadarVirtuel(self._system),
        }
        # fmt: off
        self.proxy_routes = self._constants.proxy_routes
        self.app.add_url_rule("/propagateTZ", "propagateTZ", self.get_tz)
        self.app.add_url_rule("/restarting", "restarting", self.restarting)
        self.app.add_url_rule("/restart", "restart", self.restart, methods=["GET", "POST"])
        self.app.add_url_rule("/backup", "backup", self.backup)
        self.app.add_url_rule("/backupexecute", "backupexecute", self.backup_execute)
        self.app.add_url_rule("/restore", "restore", self.restore, methods=["GET", "POST"])
        self.app.add_url_rule("/executerestore", "executerestore", self.executerestore)
        self.app.add_url_rule("/advanced", "advanced", self.advanced, methods=["GET", "POST"])
        self.app.add_url_rule("/expert", "expert", self.expert, methods=["GET", "POST"])
        self.app.add_url_rule("/aggregators", "aggregators", self.aggregators, methods=["GET", "POST"])
        self.app.add_url_rule("/", "director", self.director)
        self.app.add_url_rule("/index", "index", self.index)
        self.app.add_url_rule("/setup", "setup", self.setup, methods=["GET", "POST"])
        self.app.add_url_rule("/update", "update", self.update, methods=["POST"])
        self.app.add_url_rule("/api/sdr_info", "sdr_info", self.sdr_info)
        # fmt: on

    def run(self):
        self._routemanager.add_proxy_routes(self.proxy_routes)
        debug = os.environ.get("ADSBIM_DEBUG") is not None
        self._debug_cleanup()
        self.app.run(host="0.0.0.0", port=80, debug=debug)

    def _debug_cleanup(self):
        """
        This is a debug function to clean up the docker-starting.lock file
        """
        # rm /opt/adsb/docker-starting.lock
        try:
            os.remove("/opt/adsb/docker-starting.lock")
        except FileNotFoundError:
            pass

    def get_tz(self):
        browser_timezone = request.args.get("tz")
        # Some basic check that it looks something like Europe/Rome
        if not re.match(r"^[A-Z][a-z]+/[A-Z][a-z]+$", browser_timezone):
            return "invalid"
        # Add to .env
        self._constants.env("FEEDER_TZ").value = browser_timezone
        # Set it as datetimectl too
        try:
            subprocess.run(
                f"timedatectl set-timezone {browser_timezone}", shell=True, check=True
            )
        except subprocess.SubprocessError:
            print_err("failed to set up timezone")

        return render_template("setup.html")

    def restarting(self):
        return render_template("restarting.html")

    def restart(self):
        if request.method == "POST":
            resp = self._system._restart.restart_systemd()
            return "restarting" if resp else "already restarting"
        if request.method == "GET":
            return self._system._restart.state

    def backup(self):
        return render_template("/backup.html")

    def backup_execute(self):
        data = self._system.backup()
        return send_file(
            data,
            mimetype="application/zip",
            as_attachment=True,
            download_name="adsb-feeder-config.zip",
        )

    def restore(self):
        if request.method == "POST":
            # check if the post request has the file part
            if "file" not in request.files:
                flash("No file submitted")
                return redirect(request.url)
            file = request.files["file"]
            # If the user does not select a file, the browser submits an
            # empty file without a filename.
            if file.filename == "":
                flash("No file selected")
                return redirect(request.url)
            if file.filename.endswith(".zip"):
                filename = secure_filename(file.filename)
                restore_path = pathlib.Path("/opt/adsb/restore")
                restore_path.mkdir(mode=0o644, exist_ok=True)
                file.save(restore_path / filename)
                print_err(f"saved restore file to {restore_path / filename}")
                return redirect(url_for("executerestore", zipfile=filename))
            else:
                flash("Please only submit ADSB Feeder Image backup files")
                return redirect(request.url)
        else:
            return render_template("/restore.html")

    def executerestore(self):
        if request.method == "GET":
            # the user has uploaded a zip file and we need to take a look.
            # be very careful with the content of this zip file...
            filename = request.args["zipfile"]
            adsb_path = pathlib.Path("/opt/adsb")
            restore_path = pathlib.Path("/opt/adsb/restore")
            restored_files: List[str] = []
            with zipfile.ZipFile(restore_path / filename, "r") as restore_zip:
                for name in restore_zip.namelist():
                    print_err(f"found file {name} in archive")
                    # only accept the .env file and simple .yml filenames
                    if (
                        name != ".env"
                        and not name.startswith("ultrafeeder/")
                        and (not name.endswith(".yml") or name != secure_filename(name))
                    ):
                        continue
                    restore_zip.extract(name, restore_path)
                    restored_files.append(name)
            # now check which ones are different from the installed versions
            changed: List[str] = []
            unchanged: List[str] = []
            for name in restored_files:
                if not name.startswith("ultrafeeder/") and os.path.isfile(
                    adsb_path / name
                ):
                    if filecmp.cmp(adsb_path / name, restore_path / name):
                        print_err(f"{name} is unchanged")
                        unchanged.append(name)
                    else:
                        print_err(f"{name} is different from current version")
                        changed.append(name)
                elif name == "ultrafeeder/":
                    changed.append("ultrafeeder")
            return render_template("/restoreexecute.html")
        else:
            # they have selected the files to restore
            restore_path = pathlib.Path("/opt/adsb/restore")
            adsb_path = pathlib.Path("/opt/adsb")
            for name in request.form.keys():
                print_err(f"restoring {name}")
                shutil.move(adsb_path / name, restore_path / (name + ".dist"))
                shutil.move(restore_path / name, adsb_path / name)
            return redirect(
                "/advanced"
            )  # that's a good place from where the user can continue

    def base_is_configured(self):
        base_config: set[Env] = {
            env for env in self._constants._env if env.is_mandatory
        }
        for env in base_config:
            if env.value == None:
                print_err(f"base_is_configured: {env} isn't set up yet")
                return False
        return True

    def sdr_info(self):
        self._sdrdevices._ensure_populated()
        # get our guess for the right SDR to frequency mapping
        # and then update with the actual settings
        frequencies: Dict[str, str] = self._sdrdevices.addresses_per_frequency
        for freq in [1090, 978]:
            setting = self._constants.env_by_tags(str(freq))
            if setting and setting.value != "":
                frequencies[freq] = setting.value
        return json.dumps(
            {
                "sdrdevices": [sdr._json for sdr in self._sdrdevices.sdrs],
                "frequencies": frequencies,
            }
        )

    @check_restart_lock
    def advanced(self):
        if request.method == "POST":
            return self.update()

        # just in case things have changed (the user plugged in a new device for example)
        self._sdrdevices._ensure_populated()
        return render_template("advanced.html")

    """ -- poor man's multi line comment
    def handle_advanced_post_request(self):
        print_err("request_form", request.form)
        if request.form.get("submit") == "go":
            advanced_settings = {
                "FEEDER_TAR1090_USEROUTEAPI": "1" if request.form.get("route") else "0",
                "MLAT_PRIVACY": "--privacy" if request.form.get("privacy") else "",
                "HEYWHATSTHAT": "1" if request.form.get("heywhatsthat") else "",
                "FEEDER_HEYWHATSTHAT_ID": request.form.get(
                    "FEEDER_HEYWHATSTHAT_ID", default=""
                ),
                "FEEDER_ENABLE_BIASTEE": "true" if request.form.get("biast") else "",
            }
        serial1090: str = request.form.get("1090", default="")
        serial978: str = request.form.get("978", default="")
        print_err(f"received serial1090 of {serial1090} and serial978 of {serial978}")
        if serial1090:
            if not serial1090.startswith(("AIRSPY", "airspy")):
                advanced_settings["FEEDER_1090"] = serial1090
            else:
                advanced_settings["FEEDER_1090"] = "airspy"
            advanced_settings.update(setup_airspy_or_rtl())
        if serial978:
            advanced_settings["FEEDER_978"] = serial978
            advanced_settings["FEEDER_ENABLE_UAT978"] = "yes"
            advanced_settings["FEEDER_URL_978"] = "http://dump978/skyaware978"
            advanced_settings["FEEDER_UAT978_HOST"] = "dump978"
            advanced_settings["FEEDER_PIAWARE_UAT978"] = "relay"

        num = get_sdr_info()["num"]
        advanced_settings["NUM_SDRS"] = num
        advanced_settings["SDR_MANUALLY_ASSIGNED"] = "1"
        # now we need to update the ENV_FILE so that the ultrafeeder configuration below is correct
        ENV_FILE.update(advanced_settings)
        envs = ENV_FILE.envs
        print_err(f"after the update, FEEDER_1090 is {envs.get('FEEDER_1090')} and FEEDER_978 is {envs.get('FEEDER_978')}")
        net = ENV_FILE.generate_ultrafeeder_config(request.form)
        ENV_FILE.update({
            "FEEDER_ULTRAFEEDER_CONFIG": net,
            "UF": "1"
        })
        print_err(f"calculated ultrafeeder config of {net}")
        return redirect("/restarting")
    """

    def update(self):
        description = """
            This is the one endpoint that handles all the updates coming in from the UI.
            It walks through the form data and figures out what to do about the information provided.
        """
        # in the HTML, every input field needs to have a name that is concatenated by "--"
        # and that matches the tags of one Env
        form: Dict = request.form
        allow_insecure = self._constants.is_enabled("secure_image")
        for key, value in form.items():
            # this seems like cheating... let's capture all of the submit buttons
            if value == "go":
                if key == "shutdown":
                    # do shutdown
                    self._system.halt()
                    return "System halted"  # that return statement is of course a joke
                if key == "reboot":
                    # initiate reboot
                    self._system.reboot()
                    return "System rebooting, please refresh in about a minute"
                if key == "secure_image":
                    self._constants.env_by_tags("secure_image").value = True
                    self.secure_image()
                if key == "update":
                    # this needs a lot more checking and safety, but for now, just go
                    cmdline = "/usr/bin/docker-update-adsb-im"
                    subprocess.run(cmdline, timeout=600.0, shell=True)
                if key == "update_feeder_aps":
                    cmdline = "/usr/bin/feeder-update"
                    subprocess.run(cmdline, timeout=600.0, shell=True)
                if key == "nightly_update" or key == "zerotier":
                    # this will be handled through the separate key/value pairs
                    pass
                continue
            e = self._constants.env_by_tags(key.split("--"))
            print_err(f"key {key} value {value} env {e}")
            if e:
                if allow_insecure and key == "ssh_pub":
                    ssh_dir = pathlib.Path("/root/.ssh")
                    ssh_dir.mkdir(mode=0o700, exist_ok=True)
                    with open(ssh_dir / "authorized_keys", "a+") as authorized_keys:
                        authorized_keys.write(
                            f"{self._constants.env_by_tags('ssh_pub')}\n"
                        )
                    self._constants.env_by_tags("ssh_configured").value = True
                e.value = value
        # done handling the input data
        # let's make sure we write out the updated ultrafeeder config
        self._constants.update_env()

        # finally, check if this has given us enouch configuration info to
        # start the containers
        if self.base_is_configured():
            self._constants.env_by_tags(["base_config"]).value = True
            return redirect(url_for("restarting"))
        return redirect(url_for("director"))

    # FIXME tear me up into my own class please.

    def handle_advanced_post_request(self):
        # FIXME: this needs to move into /update
        # Refactoring the above function to use the new self._constants._env objects.

        # Get the submit=go out of the way to avoid indenting hard
        if request.form.get("submit") != "go":
            return redirect("/")

        # For each item in the form, try getting an env object with the matching frontend_name
        envs = {
            env.frontend_name: env
            for env in self._constants.envs.values()
            if env.frontend_name in request.form
        }

        # Now we have a dict of env objects, we can update them all at once. How beautiful.
        for env in envs.values():
            env.value = request.form.get(env.frontend_name)
        # FIXME the rest of the function got lost in the refactoring

    @check_restart_lock
    def expert(self):
        if request.method == "POST":
            return self.update()

        return render_template("expert.html")

    def secure_image(self):
        output: str = ""
        try:
            result = subprocess.run(
                "/usr/bin/secure-image", shell=True, capture_output=True
            )
        except subprocess.TimeoutError as exc:
            output = exc.stdout.decode()
        else:
            output = result.stdout.decode()
        print_err(f"secure_image: {output}")

    @check_restart_lock
    def aggregators(self):
        if request.method == "POST":
            return self.update()

        def uf_enabled(*tags):
            return "checked" if self._constants.is_enabled("ultrafeeder", *tags) else ""
        def others_enabled(*tags):
            return "checked" if self._constants.is_enabled("other_aggregators", *tags) else ""

        return render_template(
            "aggregators.html",
            uf_enabled=uf_enabled,
            others_enabled=others_enabled,
        )

    # @app.route("/")

    def director(self):
        # figure out where to go:
        if not self._constants.is_enabled("base_config"):
            return self.setup()

        # If we have more than one SDR, or one of them is an airspy,
        # we need to go to advanced - unless we have at least one of the serials set up
        # for 978 or 1090 reporting
        self._sdrdevices._ensure_populated()
        if ((len(self._sdrdevices) > 1 or any([sdr._type == "airspy" for sdr in self._sdrdevices.sdrs]))
            and not (self._constants.env_by_tags("1090").value or self._constants.env_by_tags("978").value)):
            return self.advanced()

        # if the user chose to individually pick aggregators but hasn't done so,
        # they need to go to the aggregator page
        if not self._ultrafeeder.enabled_aggregators:
            return self.aggregators()

        return self.index()

    # @app.route("/index")
    def index(self):
        return render_template("index.html")

    @check_restart_lock
    def setup(self):
        if request.method == "POST" and request.form.get("submit") == "go":
            return self.update()
        return render_template("setup.html")

    def handle_aggregators_post_request(self):
        # FIXME -- this needs to move into /update
        print_err(request.form)
        if request.form.get("tar1090") == "go":
            self.update_env()
            self._restart.restart_systemd()
            return redirect("/restarting")
        for key, value in [
            ["get-fr24-sharing-key", self._other_aggregators["flightradar24"]],
            ["get-pw-api-key", self._other_aggregators["planewatch"]],
            ["get-fa-api-key", self._other_aggregators["flightaware"]],
            ["get-rb-sharing-key", self._other_aggregators["radarbox"]],
            ["get-pf-sharecode", self._other_aggregators["planefinder"]],
            ["get-ah-station-key", self._other_aggregators["adsb_hub"]],
            ["get-os-info", self._other_aggregators["opensky"]],
            ["get-rv-feeder-key", self._other_aggregators["radarvirtuel"]],
        ]:
            if request.form.get(key) == "go":
                is_successful = False
                try:
                    is_successful = value._activate()
                except Exception as e:
                    print_err(f"error activating {key}: {e}")
                if is_successful:
                    return redirect("/restarting")
        else:
            # how did we get here???
            return "something went wrong"


if __name__ == "__main__":
    AdsbIm().run()
