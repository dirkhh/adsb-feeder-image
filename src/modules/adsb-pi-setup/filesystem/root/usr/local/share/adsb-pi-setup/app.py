import filecmp
import io
import json
import os.path
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile
from os import path, urandom
from typing import Dict, List, Tuple

from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from utils import (
    Constants,
    System,
    RouteManager,
    SDRDevices,
    check_restart_lock,
)
from utils import (
    ADSBHub,
    FlightAware,
    FlightRadar24,
    OpenSky,
    PlaneFinder,
    PlaneWatch,
    RadarBox24,
    RadarVirtuel,
)
from werkzeug.utils import secure_filename


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class AdsbIm:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = urandom(16).hex()

        self._routemanager = RouteManager(self.app)
        self._constants = Constants()

        self._system = System(constants=self._constants)
        self._sdrdevices = SDRDevices()

        self._other_aggregators = {
            "adsb_hub": ADSBHub(self._system),
            "flightaware": FlightAware(self._system),
            "flightradar24": FlightRadar24(self._system),
            "opensky": OpenSky(self._system),
            "planefinder": PlaneFinder(self._system),
            "planewatch": PlaneWatch(self._system),
            "radarbox24": RadarBox24(self._system),
            "radarvirtuel": RadarVirtuel(self._system),
        }

        self.proxy_routes = self._constants.proxy_routes
        self.app.add_url_rule("/propagateTZ", "propagateTZ", self.get_tz)
        self.app.add_url_rule("/restarting", "restarting", self.restarting)
        self.app.add_url_rule(
            "/restart", "restart", self.restart, methods=["GET", "POST"]
        )
        self.app.add_url_rule("/backup", "backup", self.backup)
        self.app.add_url_rule("/backupexecute", "backupexecute", self.backup_execute)
        self.app.add_url_rule(
            "/restore", "restore", self.restore, methods=["GET", "POST"]
        )
        self.app.add_url_rule("/executerestore", "executerestore", self.executerestore)
        self.app.add_url_rule(
            "/advanced", "advanced", self.advanced, methods=["GET", "POST"]
        )
        self.app.add_url_rule(
            "/aggregators", "aggregators", self.aggregators, methods=["GET", "POST"]
        )
        self.app.add_url_rule("/", "director", self.director)
        self.app.add_url_rule("/index", "index", self.index)
        self.app.add_url_rule("/setup", "setup", self.setup, methods=["GET", "POST"])
        self.app.add_url_rule("/api/sdr_info", "sdr_info", self.sdr_info)

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
        self._constants.env("FEEDER_tZ").value = browser_timezone
        # Set it as datetimectl too
        try:
            subprocess.run(
                f"timedatectl set-timezone {browser_timezone}", shell=True, check=True
            )
        except subprocess.SubprocessError:
            print_err("failed to set up timezone")
        return render_template(
            "setup.html",
            env_values=self._constants.envs,
        )

    def restarting(self):
        return render_template(
            "restarting.html",
            env_values=self._constants.envs,
        )

    def restart(self):
        if request.method == "POST":
            resp = self._system._restart.restart_systemd()
            return "restarting" if resp else "already restarting"
        if request.method == "GET":
            return self._system._restart.state

    def backup(self):
        return render_template(
            "/backup.html",
            env_values=self._constants.envs,
        )

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
            return render_template(
                "/restore.html",
                env_values=self._constants.envs,
            )

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
            # metadata = self._envfile.metadata
            # metadata["changed"] = changed
            # metadata["unchanged"] = unchanged
            # ^ WTF is this for? FIXME
            return render_template("/restoreexecute.html")  # , metadata=metadata)
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

    def sdr_info(self):
        return {
            # FIXME
            "sdrdevices": [sdr._json for sdr in self._sdrdevices.sdrs],
            "frequencies": self._sdrdevices.addresses_per_frequency,
        }

    # @app.route("/advanced", methods=("GET", "POST"))
    @check_restart_lock
    def advanced(self):
        if request.method == "POST":
            return self.handle_advanced_post_request()

        # just in case things have changed (the user plugged in a new device for example)
        return render_template(
            "advanced.html",
            env_values=self._constants.envs,
        )

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

    def handle_advanced_post_request(self):
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
            return self.handle_aggregators_post_request()
        return render_template(
            "aggregators.html",
            env_values=env_values,
        )

    # @app.route("/")

    def director(self):
        # figure out where to go:
        if self._constants.env_by_tags(["base_config", "finished"]).value != "1":
            return self.setup()

        # If we have more than one SDR, or one of them is an airspy,
        # we need to go to advanced
        if len(self._sdrdevices) > 1 or any(
            [sdr._type == "airspy" for sdr in self._sdrdevices.sdrs]
        ):
            return self.advanced()
        return self.index()

    # @app.route("/index")
    def index(self):
        return render_template("index.html", env_values=self._constants.envs)

    @check_restart_lock
    def setup(self):
        if request.method != "POST" and request.form.get("submit") != "go":
            return render_template(
                "setup.html",
                env_values=self._constants.envs,
            )

        # For each item in the form, try getting an env object with the matching frontend_name
        envs = {
            env.frontend_name: env
            for env in self._constants.envs.values()
            if env.frontend_name in request.form
        }

        # Now we have a dict of env objects, we can update them all at once. How beautiful.
        for env in envs.values():
            env.value = request.form.get(env.frontend_name)

        # FIXME finish me

    # FIXME tear me up into my own class please.

    def handle_aggregators_post_request(self):
        print_err(request.form)
        if request.form.get("tar1090") == "go":
            self.update_env()
            self._restart.restart_systemd()
            return redirect("/restarting")
        for key, value in [
            ["get-fr24-sharing-key", self._other_aggregators["flightradar24"]],
            ["get-pw-api-key", self._other_aggregators["planewatch"]],
            ["get-fa-api-key", self._other_aggregators["flightaware"]],
            ["get-rb-sharing-key", self._other_aggregators["radarbox24"]],
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
