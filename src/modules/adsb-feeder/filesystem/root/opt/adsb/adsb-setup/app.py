import filecmp
import json
import os
import os.path
import pathlib
import pickle
import platform
import re
import secrets
import signal
import shutil
import string
import subprocess
import threading
import sys
import zipfile
import tempfile
from base64 import b64encode
from datetime import datetime
from os import urandom
from time import sleep
from typing import Dict, List
from zlib import compress

from utils.config import (
    read_values_from_env_file,
    write_values_to_config_json,
    write_values_to_env_file,
)

if not os.path.exists("/opt/adsb/config/config.json"):
    # this must be either a first run after an install,
    # or the first run after an upgrade from a version that didn't use the config.json
    values = read_values_from_env_file()
    write_values_to_config_json(values)

# nofmt: on
# isort: off
from flask import Flask, flash, redirect, render_template, request, send_file, url_for


from utils import (
    ADSBHub,
    Background,
    Data,
    Env,
    FlightAware,
    FlightRadar24,
    OpenSky,
    PlaneFinder,
    PlaneWatch,
    RadarBox,
    RadarVirtuel,
    Uk1090,
    RouteManager,
    SDRDevices,
    AggStatus,
    ImStatus,
    System,
    check_restart_lock,
    UltrafeederConfig,
    cleanup_str,
    print_err,
)

# nofmt: off
# isort: on

from werkzeug.utils import secure_filename


class AdsbIm:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = urandom(16).hex()

        @self.app.context_processor
        def env_functions():
            def get_value(tags):
                e = self._d.env_by_tags(tags)
                return e.value if e else ""

            return {
                "is_enabled": lambda tag: self._d.is_enabled(tag),
                "env_value_by_tag": lambda tag: get_value([tag]),  # single tag
                "env_value_by_tags": lambda tags: get_value(tags),  # list of tags
                "env_values": self._d.envs,
            }

        self._routemanager = RouteManager(self.app)
        self._d = Data()
        self._system = System(data=self._d)
        self._sdrdevices = SDRDevices()
        self._ultrafeeder = UltrafeederConfig(data=self._d)

        self._agg_status_instances = dict()

        # Ensure secure_image is set the new way if before the update it was set only as env variable
        if self._d.is_enabled("secure_image"):
            self.set_secure_image()

        # update Env ultrafeeder to have value self._ultrafeed.generate()
        self._d.env_by_tags("ultrafeeder_config")._value_call = (
            self._ultrafeeder.generate
        )
        self._d.env_by_tags("pack")._value_call = self.pack_im
        self._other_aggregators = {
            "adsbhub--submit": ADSBHub(self._system),
            "flightaware--submit": FlightAware(self._system),
            "flightradar--submit": FlightRadar24(self._system),
            "opensky--submit": OpenSky(self._system),
            "planefinder--submit": PlaneFinder(self._system),
            "planewatch--submit": PlaneWatch(self._system),
            "radarbox--submit": RadarBox(self._system),
            "radarvirtuel--submit": RadarVirtuel(self._system),
            "1090uk--submit": Uk1090(self._system),
        }
        # fmt: off
        self.all_aggregators = [
            # tag, name, map link, status link
            ["adsblol", "adsb.lol", "https://adsb.lol/", "https://api.adsb.lol/0/me"],
            ["flyitaly", "Fly Italy ADSB", "https://mappa.flyitalyadsb.com/", "https://my.flyitalyadsb.com/am_i_feeding"],
            ["avdelphi", "AVDelphi", "https://www.avdelphi.com/coverage.html", ""],
            ["planespotters", "Planespotters", "https://radar.planespotters.net/", "https://www.planespotters.net/feed/status"],
            ["tat", "TheAirTraffic", "https://globe.theairtraffic.com/", "https://theairtraffic.com/feed/myip/"],
            # on "pause" for a while... ["flyovr", "FLYOVR.io", "https://globe.flyovr.io/", ""],
            ["radarplane", "RadarPlane", "https://radarplane.com/", "https://radarplane.com/feed"],
            ["adsbfi", "adsb.fi", "https://globe.adsb.fi/", "https://api.adsb.fi/v1/myip"],
            ["adsbx", "ADSBExchange", "https://globe.adsbexchange.com/", "https://www.adsbexchange.com/myip/"],
            ["hpradar", "HPRadar", "https://skylink.hpradar.com/", ""],
            ["alive", "airplanes.live", "https://globe.airplanes.live/", "https://airplanes.live/myfeed/"],
            ["flightradar", "flightradar24", "https://www.flightradar24.com/", "/fr24-monitor.json"],
            ["planewatch", "Plane.watch", "https:/plane.watch/desktop.html", ""],
            ["flightaware", "FlightAware", "https://www.flightaware.com/live/map", "/fa-status"],
            ["radarbox", "RadarBox", "https://www.radarbox.com/coverage-map", "https://www.radarbox.com/stations/<FEEDER_RADARBOX_SN>"],
            ["planefinder", "PlaneFinder", "https://planefinder.net/", "/planefinder-stat"],
            ["adsbhub", "ADSBHub", "https://www.adsbhub.org/coverage.php", ""],
            ["opensky", "OpenSky", "https://opensky-network.org/network/explorer", "https://opensky-network.org/receiver-profile?s=<FEEDER_OPENSKY_SERIAL>"],
            ["radarvirtuel", "RadarVirtuel", "https://www.radarvirtuel.com/", ""],
            ["1090uk", "1090MHz UK", "https://1090mhz.uk", "https://www.1090mhz.uk/mystatus.php?key=<FEEDER_1090UK_API_KEY>"],
        ]
        self.proxy_routes = self._d.proxy_routes
        self.app.add_url_rule("/propagateTZ", "propagateTZ", self.get_tz)
        self.app.add_url_rule("/restarting", "restarting", self.restarting)
        self.app.add_url_rule("/restart", "restart", self.restart, methods=["GET", "POST"])
        self.app.add_url_rule("/running", "running", self.running)
        self.app.add_url_rule("/backup", "backup", self.backup)
        self.app.add_url_rule("/backupexecutefull", "backupexecutefull", self.backup_execute_full)
        self.app.add_url_rule("/backupexecutegraphs", "backupexecutegraphs", self.backup_execute_graphs)
        self.app.add_url_rule("/backupexecuteconfig", "backupexecuteconfig", self.backup_execute_config)
        self.app.add_url_rule("/restore", "restore", self.restore, methods=["GET", "POST"])
        self.app.add_url_rule("/executerestore", "executerestore", self.executerestore, methods=["GET", "POST"])
        self.app.add_url_rule("/advanced", "advanced", self.advanced, methods=["GET", "POST"])
        self.app.add_url_rule("/expert", "expert", self.expert, methods=["GET", "POST"])
        self.app.add_url_rule("/aggregators", "aggregators", self.aggregators, methods=["GET", "POST"])
        self.app.add_url_rule("/", "director", self.director, methods=["GET", "POST"])
        self.app.add_url_rule("/index", "index", self.index)
        self.app.add_url_rule("/setup", "setup", self.setup, methods=["GET", "POST"])
        self.app.add_url_rule("/update", "update", self.update, methods=["POST"])
        self.app.add_url_rule("/sdplay_license", "sdrplay_license", self.sdrplay_license, methods=["GET", "POST"])
        self.app.add_url_rule("/api/sdr_info", "sdr_info", self.sdr_info)
        self.app.add_url_rule("/api/base_info", "base_info", self.base_info)
        self.app.add_url_rule(f"/api/status/<agg>", "beast", self.agg_status)
        # fmt: on
        self.update_boardname()
        self.update_version()

    def update_boardname(self):
        board = ""
        if pathlib.Path("/sys/firmware/devicetree/base/model").exists():
            # that's some kind of SBC most likely
            with open("/sys/firmware/devicetree/base/model", "r") as model:
                board = cleanup_str(model.read().strip())
        else:
            # are we virtualized?
            try:
                output = subprocess.run(
                    "systemd-detect-virt",
                    timeout=2.0,
                    shell=True,
                    capture_output=True,
                )
            except subprocess.SubprocessError:
                pass  # whatever
            else:
                virt = output.stdout.decode().strip()
                if virt and virt != "none":
                    board = f"Virtualized {platform.machine()} environment under {virt}"
                else:
                    board = f"Native on {platform.machine()} system"
        if board == "":
            board = f"Unknown {platform.machine()} system"
        if board == "Firefly roc-rk3328-cc":
            board = f"Libre Computer Renegade ({board})"
        elif board == "Libre Computer AML-S905X-CC":
            board = "Libre Computer Le Potato (AML-S905X-CC)"
        self._d.env_by_tags("board_name").value = board

    def update_version(self):
        conf_version = self._d.env_by_tags("base_version").value
        if pathlib.Path(self._d.version_file).exists():
            with open(self._d.version_file, "r") as f:
                file_version = f.read().strip()
        else:
            file_version = ""
        if file_version:
            if file_version != conf_version:
                print_err(
                    f"found version '{conf_version}' in memory, but '{file_version}' on disk, updating to {file_version}"
                )
                self._d.env_by_tags("base_version").value = file_version
        else:
            if conf_version:
                print_err(f"no version found on disk, using {conf_version}")
                with open(self._d.version_file, "w") as f:
                    f.write(conf_version)
            else:
                print_err("no version found on disk or in memory, using v0.0.0")
                self._d.env_by_tags("base_version").value = "v0.0.0"

    def pack_im(self) -> str:
        image = {
            "in": self._d.env_by_tags("image_name").value,
            "bn": self._d.env_by_tags("board_name").value,
            "bv": self._d.env_by_tags("base_version").value,
            "cv": self._d.env_by_tags("container_version").value,
        }
        return b64encode(compress(pickle.dumps(image))).decode("utf-8")

    def check_secure_image(self):
        return self._d.secure_image_path.exists()

    def set_secure_image(self):
        # set legacy env variable as well for webinterface
        self._d.env_by_tags("secure_image").value = True
        if not self.check_secure_image():
            self._d.secure_image_path.touch(exist_ok=True)
            print_err("secure_image has been set")

    def update_dns_state(self):
        dns_state = self._system.check_dns()
        self._d.env_by_tags("dns_state").value = dns_state
        if not dns_state:
            print_err("we appear to have lost DNS")

    def run(self, no_server=False):
        self._routemanager.add_proxy_routes(self.proxy_routes)
        debug = os.environ.get("ADSBIM_DEBUG") is not None
        self._debug_cleanup()
        write_values_to_env_file(self._d.envs)
        self.update_dns_state()
        # in no_server mode we want to exit right after the housekeeping, so no
        # point in running this in the background
        if not no_server:
            self._dns_watch = Background(3600, self.update_dns_state)
        # prepare for app use (vs ADS-B Feeder Image use)
        # newer images will include a flag file that indicates that this is indeed
        # a full image - but in case of upgrades from older version, this heuristic
        # should be sufficient to guess if this is an image or an app
        os_flag_file = self._d.data_path / "os.adsb.feeder.image"
        if not os_flag_file.exists():
            # so this could be a pre-0.15 image, or it could indeed be the app
            app_flag_file = adsb_dir / "app.adsb.feeder.image"
            if not app_flag_file.exists():
                # there should be no app without the app flag file, so assume that
                # this is an older image that was upgraded and hence didn't get the
                # os flag file at install time
                open(os_flag_file, "w").close()

        if not os_flag_file.exists():
            # we are running as an app under DietPi or some other OS
            self._d.is_feeder_image = False
            with open(
                self._d.data_path / "adsb-setup/templates/expert.html", "r+"
            ) as expert_file:
                expert_html = expert_file.read()
                expert_file.seek(0)
                expert_file.write(
                    re.sub(
                        "FULL_IMAGE_ONLY_START.*? FULL_IMAGE_ONLY_END",
                        "",
                        expert_html,
                        flags=re.DOTALL,
                    )
                )
                expert_file.truncate()

        # if all the user wanted is to make sure the housekeeping tasks are completed,
        # don't start the flask app and exit instead
        if no_server:
            signal.raise_signal(signal.SIGTERM)
            return

        self.app.run(
            host="0.0.0.0",
            port=int(self._d.env_by_tags("webport").value),
            debug=debug,
        )

    def _debug_cleanup(self):
        """
        This is a debug function to clean up the docker-starting.lock file
        """
        # rm /opt/adsb/docker-starting.lock
        try:
            os.remove(self._d.data_path / "docker-starting.lock")
        except FileNotFoundError:
            pass

    def get_tz(self):
        browser_timezone = request.args.get("tz")
        # Some basic check that it looks something like Europe/Rome
        if not re.match(r"^[A-Z][a-z]+/[A-Z][a-z]+$", browser_timezone):
            return "invalid"
        # Add to .env
        self._d.env("FEEDER_TZ").value = browser_timezone
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

    def running(self):
        if self._system.docker_restarting():
            return "containers restarting", 202
        return "OK"

    def backup(self):
        return render_template("/backup.html")

    def backup_execute_config(self):
        return self.create_backup_zip()

    def backup_execute_graphs(self):
        return self.create_backup_zip(include_graphs=True)

    def backup_execute_full(self):
        return self.create_backup_zip(include_graphs=True, include_heatmap=True)

    def create_backup_zip(self, include_graphs=False, include_heatmap=False):
        adsb_path = pathlib.Path("/opt/adsb/config")
        fdOut, fdIn = os.pipe()
        pipeOut = os.fdopen(fdOut, "rb")
        pipeIn = os.fdopen(fdIn, "wb")

        def zip2fobj(fobj, include_graphs, include_heatmap):
            try:
                with fobj as file, zipfile.ZipFile(file, mode="w") as backup_zip:
                    backup_zip.write(adsb_path / "config.json", arcname="config.json")
                    if include_graphs:
                        graphs_path = pathlib.Path(
                            adsb_path / "ultrafeeder/graphs1090/rrd/localhost.tar.gz"
                        )
                        backup_zip.write(
                            graphs_path, arcname=graphs_path.relative_to(adsb_path)
                        )
                    if include_heatmap:
                        uf_path = pathlib.Path(adsb_path / "ultrafeeder/globe_history")
                        if uf_path.is_dir():
                            for f in uf_path.rglob("*"):
                                backup_zip.write(f, arcname=f.relative_to(adsb_path))
            except BrokenPipeError:
                print_err(f"warning: backup download aborted mid-stream")

        thread = threading.Thread(
            target=zip2fobj,
            kwargs={
                "fobj": pipeIn,
                "include_graphs": include_graphs,
                "include_heatmap": include_heatmap,
            },
        )
        thread.start()

        site_name = self._d.env_by_tags("mlat_name").value
        now = datetime.now().replace(microsecond=0).isoformat().replace(":", "-")
        download_name = f"adsb-feeder-config-{site_name}-{now}.zip"
        return send_file(
            pipeOut,
            mimetype="application/zip",
            as_attachment=True,
            download_name=download_name,
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
                restore_path = pathlib.Path("/opt/adsb/config/restore")
                # clean up the restore path when saving a fresh zipfile
                shutil.rmtree(restore_path, ignore_errors=True)
                restore_path.mkdir(mode=0o644, exist_ok=True)
                file.save(restore_path / filename)
                print_err(f"saved restore file to {restore_path / filename}")
                return redirect(url_for("executerestore", zipfile=filename))
            else:
                flash("Please only submit ADS-B Feeder Image backup files")
                return redirect(request.url)
        else:
            return render_template("/restore.html")

    def executerestore(self):
        if request.method == "GET":
            # the user has uploaded a zip file and we need to take a look.
            # be very careful with the content of this zip file...
            print_err("zip file uploaded, looking at the content")
            filename = request.args["zipfile"]
            adsb_path = pathlib.Path("/opt/adsb/config")
            restore_path = adsb_path / "restore"
            restore_path.mkdir(mode=0o755, exist_ok=True)
            restored_files: List[str] = []
            with zipfile.ZipFile(restore_path / filename, "r") as restore_zip:
                for name in restore_zip.namelist():
                    print_err(f"found file {name} in archive")
                    # remove files with a name that results in a path that doesn't start with our decompress path
                    if not str(
                        os.path.normpath(os.path.join(restore_path, name))
                    ).startswith(str(restore_path)):
                        print_err(f"restore skipped for path breakout name: {name}")
                        continue
                    # only accept the .env file and config.json and files for ultrafeeder
                    if (
                        name != ".env"
                        and name != "config.json"
                        and not name.startswith("ultrafeeder/")
                    ):
                        continue
                    restore_zip.extract(name, restore_path)
                    restored_files.append(name)
            # now check which ones are different from the installed versions
            changed: List[str] = []
            unchanged: List[str] = []
            saw_globe_history = False
            saw_graphs = False
            for name in restored_files:
                if name.startswith("ultrafeeder/globe_history/"):
                    saw_globe_history = True
                elif name.startswith("ultrafeeder/graphs1090/"):
                    saw_graphs = True
                elif os.path.isfile(adsb_path / name):
                    if filecmp.cmp(adsb_path / name, restore_path / name):
                        print_err(f"{name} is unchanged")
                        unchanged.append(name)
                    else:
                        print_err(f"{name} is different from current version")
                        changed.append(name)
            if saw_globe_history:
                changed.append("ultrafeeder/globe_history/")
            if saw_graphs:
                changed.append("ultrafeeder/graphs1090/")
            print_err(f"offering the usr to restore the changed files: {changed}")
            return render_template(
                "/restoreexecute.html", changed=changed, unchanged=unchanged
            )
        else:
            # they have selected the files to restore
            print_err("restoring the files the user selected")
            adsb_path = pathlib.Path("/opt/adsb/config")
            (adsb_path / "ultrafeeder").mkdir(mode=0o755, exist_ok=True)
            restore_path = adsb_path / "restore"
            restore_path.mkdir(mode=0o755, exist_ok=True)
            try:
                subprocess.call(
                    "/opt/adsb/docker-compose-adsb down -t 20", timeout=40.0, shell=True
                )
            except subprocess.TimeoutExpired:
                print_err("timeout expired stopping docker... trying to continue...")
            for name, value in request.form.items():
                if value == "1":
                    print_err(f"restoring {name}")
                    dest = adsb_path / name
                    if dest.is_file():
                        shutil.move(dest, adsb_path / (name + ".dist"))
                    elif dest.is_dir():
                        shutil.rmtree(dest, ignore_errors=True)

                    shutil.move(restore_path / name, dest)

                    if name == ".env":
                        if "config.json" in request.form.keys():
                            # if we are restoring the config.json file, we don't need to restore the .env
                            # this should never happen, but better safe than sorry
                            continue
                        # so this is a backup from an older system, let's try to make this work
                        # read them in, replace the ones that match a norestore tag with the current value
                        # and then write this all back out as config.json
                        values = read_values_from_env_file()
                        for e in self._d._env:
                            if "norestore" in e.tags:
                                # this overwrites the value in the file we just restored with the current value of the running image,
                                # iow it doesn't restore that value from the backup
                                values[e.name] = e.value
                        write_values_to_config_json(values)

            # clean up the restore path
            restore_path = pathlib.Path("/opt/adsb/config/restore")
            shutil.rmtree(restore_path, ignore_errors=True)

            # now that everything has been moved into place we need to read all the values from config.json
            # of course we do not want to pull values marked as norestore
            print_err("finished restoring files, syncing the configuration")

            for e in self._d._env:
                e._reconcile(e._value, pull=("norestore" not in e.tags))
                print_err(
                    f"{'wrote out' if 'norestore' in e.tags else 'read in'} {e.name}: {e.value}"
                )

            # finally make sure that a couple of the key settings are up to date
            self.update_boardname()
            self.update_version()

            # make sure we are connected to the right Zerotier network
            zt_network = self._d.env_by_tags("zerotierid").value
            if (
                zt_network and len(zt_network) == 16
            ):  # that's the length of a valid network id
                try:
                    subprocess.call(
                        f"zerotier_cli join {zt_network}", timeout=30.0, shell=True
                    )
                except subprocess.TimeoutExpired:
                    print_err(
                        "timeout expired joining Zerotier network... trying to continue..."
                    )

            # let's make sure we write out the updated ultrafeeder config
            write_values_to_env_file(self._d.envs)

            try:
                subprocess.call(
                    "/opt/adsb/docker-compose-start", timeout=180.0, shell=True
                )
            except subprocess.TimeoutExpired:
                print_err("timeout expired re-starting docker... trying to continue...")
            return redirect(url_for("director"))

    def base_is_configured(self):
        base_config: set[Env] = {env for env in self._d._env if env.is_mandatory}
        for env in base_config:
            if env.value == None:
                print_err(f"base_is_configured: {env} isn't set up yet")
                return False
        return True

    def at_least_one_aggregator(self) -> bool:
        if self._ultrafeeder.enabled_aggregators:
            return True

        # of course, maybe they picked just one or more proprietary aggregators and that's all they want...
        for submit_key in self._other_aggregators.keys():
            key = submit_key.replace("--submit", "")
            if self._d.is_enabled(key):
                print_err(f"no semi-anonymous aggregator, but enabled {key}")
                return True

        return False

    def sdr_info(self):
        # get our guess for the right SDR to frequency mapping
        # and then update with the actual settings
        serial_guess: Dict[str, str] = self._sdrdevices.addresses_per_frequency
        print_err(f"serial guess: {serial_guess}")
        serials: Dict[str, str] = {
            f: self._d.env_by_tags(f"{f}serial").value for f in [978, 1090]
        }
        for f in [978, 1090]:
            if not serials[f] and serial_guess[f] not in serials.values():
                serials[f] = serial_guess[f]

        return json.dumps(
            {
                "sdrdevices": [sdr._json for sdr in self._sdrdevices.sdrs],
                "frequencies": serials,
                "duplicates": ", ".join(self._sdrdevices.duplicates),
            }
        )

    def base_info(self):
        return json.dumps(
            {
                "name": self._d.env_by_tags("mlat_name").value,
                "lat": self._d.env_by_tags("lat").value,
                "lng": self._d.env_by_tags("lng").value,
                "alt": self._d.env_by_tags("alt").value,
                "tz": self._d.env_by_tags("form_timezone").value,
                "version": self._d.env_by_tags("base_version").value,
            }
        )

    def agg_status(self, agg):
        if agg == "im":
            im_json, status = ImStatus(self._d).check()
            if status == 200:
                return json.dumps(im_json)
            else:
                print_err(f"adsb.im returned {status}")
                return {
                    "latest_tag": "unknown",
                    "latest_commit": "",
                    "advice": "there was an error obtaining the latest version information",
                }

        status = self._agg_status_instances.get(agg)
        if status is None:
            status = self._agg_status_instances[agg] = AggStatus(
                agg, self._d, request.host_url.rstrip("/ ")
            )

        if agg == "adsbx":
            return json.dumps(
                {
                    "beast": status.beast,
                    "mlat": status.mlat,
                    "adsbxfeederid": self._d.env_by_tags("adsbxfeederid").value,
                }
            )
        return json.dumps({"beast": status.beast, "mlat": status.mlat})

    @check_restart_lock
    def advanced(self):
        if request.method == "POST":
            return self.update()

        # just in case things have changed (the user plugged in a new device for example)
        self._sdrdevices._ensure_populated()
        # embed lsusb output in the page
        try:
            lsusb = subprocess.run(
                "lsusb", shell=True, check=True, capture_output=True
            ).stdout.decode()
        except:
            lsusb = "lsusb failed"

        return render_template("advanced.html", lsusb=lsusb)

    def set_channel(self, channel: str):
        with open(self._d.data_path / "update-channel", "w") as update_channel:
            print(channel, file=update_channel)

    def clear_range_outline(self):
        # is the file where we expect it?
        rangedirs = (
            self._d.config_path
            / "ultrafeeder"
            / "globe_history"
            / "internal_state"
            / "rangeDirs.gz"
        )
        if not rangedirs.exists() and rangedirs.is_file():
            print_err(f"can't seem to find the range outline file {rangedirs}")
            return

        # try to stop the Ultrafeeder container, then remove the range outline, then restart everything
        try:
            subprocess.call(
                "/opt/adsb/docker-compose-adsb down ultrafeeder",
                timeout=40.0,
                shell=True,
            )
        except subprocess.TimeoutExpired:
            print_err(
                "timeout expired stopping ultrafeeder... trying to continue anyway..."
            )
        rangedirs.unlink(missing_ok=True)
        try:
            subprocess.call("/opt/adsb/docker-compose-start", timeout=180.0, shell=True)
        except subprocess.TimeoutExpired:
            print_err("timeout expired re-starting docker... trying to continue...")
        print_err("removed the range outline")

    def set_rpw(self):
        try:
            subprocess.call(f"echo 'root:{self.rpw}' | chpasswd", shell=True)
        except:
            print_err("failed to overwrite root password")
        if os.path.exists("/etc/ssh/sshd_config"):
            try:
                subprocess.call(
                    "sed -i 's/^\(PermitRootLogin.*\)/# \\1/' /etc/ssh/sshd_config &&"
                    "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && "
                    "systemctl restart sshd",
                    shell=True,
                )
            except:
                print_err("failed to allow root ssh login")

    def update(self):
        description = """
            This is the one endpoint that handles all the updates coming in from the UI.
            It walks through the form data and figures out what to do about the information provided.
        """
        # in the HTML, every input field needs to have a name that is concatenated by "--"
        # and that matches the tags of one Env
        purposes = (
            "978serial",
            "1090serial",
            "other-0",
            "other-1",
            "other-2",
            "other-3",
        )
        form: Dict = request.form
        seen_go = False
        allow_insecure = not self.check_secure_image()
        for key, value in form.items():
            print_err(f"handling {key} -> {value} (allow insecure is {allow_insecure})")
            # this seems like cheating... let's capture all of the submit buttons
            if value == "go":
                seen_go = True
            if value == "go" or value == "wait":
                if key == "sdrplay_license_accept":
                    self._d.env_by_tags("sdrplay_license_accepted").value = True
                if key == "sdrplay_license_reject":
                    self._d.env_by_tags("sdrplay_license_accepted").value = False
                if key == "aggregators":
                    # user has clicked Submit on Aggregator page
                    self._d.env_by_tags("aggregators_chosen").value = True
                if allow_insecure and key == "shutdown":
                    # do shutdown
                    self._system.halt()
                    return render_template("/waitandredirect.html")
                if allow_insecure and key == "reboot":
                    # initiate reboot
                    self._system.reboot()
                    return render_template("/waitandredirect.html")
                if key == "restart_containers":
                    # almost certainly overkill, but...
                    self._system.restart_containers()
                    return render_template("/waitandredirect.html")
                if key == "secure_image":
                    self.set_secure_image()
                if key == "update":
                    # this needs a lot more checking and safety, but for now, just go
                    cmdline = "/opt/adsb/docker-update-adsb-im"
                    subprocess.run(cmdline, timeout=600.0, shell=True)
                if key == "update_feeder_aps_beta" or key == "update_feeder_aps_stable":
                    channel = "stable" if key == "update_feeder_aps_stable" else "beta"
                    self.set_channel(channel)
                    print_err(f"updating feeder to {channel} channel")
                    # start this in the background so it doesn't prevent showing the waiting screen
                    cmdline = "systemctl start adsb-feeder-update.service &"
                    subprocess.run(cmdline, timeout=5.0, shell=True)
                    return render_template("/waitandredirect.html")
                if key == "resetgain":
                    # tell the ultrafeeder container to restart the autogain processing
                    cmdline = (
                        "docker exec ultrafeeder /usr/local/bin/autogain1090 reset"
                    )
                    try:
                        subprocess.run(cmdline, timeout=5.0, shell=True)
                    except:
                        print_err("Error running Ultrafeeder autogain reset")
                if key == "resetuatgain":
                    # tell the dump978 container to restart the autogain processing
                    cmdline = "docker exec dump978 /usr/local/bin/autogain978 reset"
                    try:
                        subprocess.run(cmdline, timeout=5.0, shell=True)
                    except:
                        print_err("Error running UAT autogain reset")
                if key == "nightly_update" or key == "zerotier":
                    # this will be handled through the separate key/value pairs
                    pass
                if allow_insecure and key == "tailscale":
                    # grab extra arguments if given
                    ts_args = form.get("tailscale_extras", "")
                    if ts_args:
                        # right now we really only want to allow the login server arg
                        ts_cli_switch, ts_cli_value = ts_args.split("=")
                        if ts_cli_switch != "--login-server":
                            print_err(
                                "at this point we only allow the --login-server argument; "
                                "please let us know at the Zulip support link why you need "
                                f"this to support {ts_cli_switch}"
                            )
                            continue
                        print_err(f"login server arg is {ts_cli_value}")
                        match = re.match(
                            r"^https?://[-a-zA-Z0-9._\+~=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?::[0-9]{1,5})?(?:[-a-zA-Z0-9()_\+.~/=]*)$",
                            ts_cli_value,
                        )
                        if not match:
                            print_err(
                                f"the login server URL didn't make sense {ts_cli_value}"
                            )
                            continue
                    print_err(f"starting tailscale (args='{ts_args}')")
                    try:
                        subprocess.run(
                            "/usr/bin/systemctl enable --now tailscaled",
                            shell=True,
                            timeout=20.0,
                        )
                        result = subprocess.run(
                            f"/usr/bin/tailscale up {ts_args} --accept-dns=false 2> /tmp/out &",
                            shell=True,
                            capture_output=False,
                            timeout=30.0,
                        )
                    except:
                        # this really needs a user visible error...
                        print_err("exception trying to set up tailscale - giving up")
                        continue
                    while True:
                        sleep(1.0)
                        with open("/tmp/out") as out:
                            output = out.read()
                        # standard tailscale result
                        match = re.search(r"(https://login\.tailscale.*)", output)
                        if match:
                            break
                        # when using a login-server
                        match = re.search(r"(https://.*/register/nodekey.*)", output)
                        if match:
                            break

                    login_link = match.group(1)
                    print_err(f"found login link {login_link}")
                    self._d.env_by_tags("tailscale_ll").value = login_link
                    return redirect(url_for("expert"))
                # tailscale handling uses 'continue' to avoid deep nesting - don't add other keys
                # here at the end - instead insert them before tailscale
                continue
            if value == "stay":
                if key == "clear_range":
                    self.clear_range_outline()
                    continue
                if allow_insecure and key == "rpw":
                    print_err("updating the root password")
                    self.set_rpw()
                    continue
                if key in self._other_aggregators:
                    is_successful = False
                    base = key.replace("--submit", "")
                    aggregator_argument = form.get(f"{base}--key", None)
                    if base == "flightradar":
                        uat_arg = form.get(f"{base}_uat--key", None)
                        aggregator_argument += f"::{uat_arg}"
                    if base == "opensky":
                        user = form.get(f"{base}--user", None)
                        aggregator_argument += f"::{user}"
                    aggregator_object = self._other_aggregators[key]
                    try:
                        is_successful = aggregator_object._activate(aggregator_argument)
                    except Exception as e:
                        print_err(f"error activating {key}: {e}")
                    if not is_successful:
                        print_err(f"did not successfully enable {base}")

                continue
            # now handle other form input
            e = self._d.env_by_tags(key.split("--"))
            if e:
                if allow_insecure and key == "ssh_pub":
                    ssh_dir = pathlib.Path("/root/.ssh")
                    ssh_dir.mkdir(mode=0o700, exist_ok=True)
                    with open(ssh_dir / "authorized_keys", "a+") as authorized_keys:
                        authorized_keys.write(f"{value}\n")
                    self._d.env_by_tags("ssh_configured").value = True
                if allow_insecure and key == "zerotierid":
                    try:
                        subprocess.call(
                            "/usr/bin/systemctl enable --now zerotier-one", shell=True
                        )
                        sleep(5.0)  # this gives the service enough time to get ready
                        subprocess.call(
                            f"/usr/sbin/zerotier-cli join {value}", shell=True
                        )
                    except:
                        print_err("exception trying to set up zerorier - giving up")
                if key in {"lat", "lng", "alt"}:
                    # remove letters, spaces, degree symbols
                    value = str(float(re.sub("[a-zA-Z° ]", "", value)))
                if key == "alt":
                    # remove decimals as well
                    value = str(int(float(value)))
                if key == "gain":
                    self._d.env_by_tags(["gain_airspy"]).value = (
                        "auto" if value == "autogain" else value
                    )
                # deal with the micro feeder setup
                if key == "aggregators" and value == "micro":
                    self._d.env_by_tags(["tar1090_ac_db"]).value = False
                    self._d.env_by_tags(["mlathub_disable"]).value = True
                    self._d.env_by_tags("aggregators_chosen").value = True
                else:
                    self._d.env_by_tags(["tar1090_ac_db"]).value = True
                    self._d.env_by_tags(["mlathub_disable"]).value = False
                # finally, painfully ensure that we remove explicitly asigned SDRs from other asignments
                # this relies on the web page to ensure that each SDR is only asigned on purpose
                if key in purposes:
                    for clear_key in purposes:
                        if value == self._d.env_by_tags(clear_key).value:
                            self._d.env_by_tags(clear_key).value = ""

                e.value = value
        # done handling the input data
        # what implied settings do we have (and could we simplify them?)
        # first grab the SDRs plugged in and check if we have one identified for UAT
        self._sdrdevices._ensure_populated()
        env978 = self._d.env_by_tags("978serial")
        env1090 = self._d.env_by_tags("1090serial")
        if env978.value != "" and not any(
            [sdr._serial == env978.value for sdr in self._sdrdevices.sdrs]
        ):
            env978.value = ""
        if env1090.value != "" and not any(
            [sdr._serial == env1090.value for sdr in self._sdrdevices.sdrs]
        ):
            env1090.value = ""
        auto_assignment = self._sdrdevices.addresses_per_frequency
        # if we have an actual asignment, that overrides the auto-assignment,
        # delete the auto-assignment
        for frequency in [978, 1090]:
            if any(
                auto_assignment[frequency] == self._d.env_by_tags(purpose).value
                for purpose in purposes
            ):
                auto_assignment[frequency] = ""
        if not env1090.value and auto_assignment[1090]:
            env1090.value = auto_assignment[1090]
        if not env978.value and auto_assignment[978]:
            env978.value = auto_assignment[978]
        if env978.value:
            self._d.env_by_tags(["uat978", "is_enabled"]).value = True
            self._d.env_by_tags("978url").value = "http://dump978/skyaware978"
            self._d.env_by_tags("978host").value = "dump978"
            self._d.env_by_tags("978piaware").value = "relay"
        else:
            self._d.env_by_tags(["uat978", "is_enabled"]).value = False
            self._d.env_by_tags("978url").value = ""
            self._d.env_by_tags("978host").value = ""
            self._d.env_by_tags("978piaware").value = ""

        # next check for airspy devices
        airspy = any([sdr._type == "airspy" for sdr in self._sdrdevices.sdrs])
        self._d.env_by_tags(["airspy", "is_enabled"]).value = airspy

        # SDRplay devices
        sdrplay = any([sdr._type == "sdrplay" for sdr in self._sdrdevices.sdrs])
        self._d.env_by_tags(["sdrplay", "is_enabled"]).value = sdrplay

        # next - if we have exactly one SDR and it hasn't been assigned to anything, use it for 1090
        if (
            len(self._sdrdevices.sdrs) == 1
            and not airspy
            and not any(self._d.env_by_tags(p).value for p in purposes)
        ):
            env1090.value = self._sdrdevices.sdrs[0]._serial

        rtlsdr = any(
            sdr._type == "rtlsdr" and sdr._serial == env1090.value
            for sdr in self._sdrdevices.sdrs
        )
        if not rtlsdr:
            env1090.value = ""
        self._d.env_by_tags("rtlsdr").value = "rtlsdr" if rtlsdr else ""

        print_err(f"in the end we have")
        print_err(f"1090serial {env1090.value}")
        print_err(f"978serial {env978.value}")
        print_err(
            f"airspy container is {self._d.env_by_tags(['airspy', 'is_enabled']).value}"
        )
        print_err(
            f"dump978 container {self._d.env_by_tags(['uat978', 'is_enabled']).value}"
        )
        # finally, set a flag to indicate whether this is a stage 2 configuration or whether it has actual SDRs attached
        self._d.env_by_tags(["stage2", "is_enabled"]).value = (
            not env1090.value and not env978.value
        )

        # let's make sure we write out the updated ultrafeeder config
        write_values_to_env_file(self._d.envs)

        # if the button simply updated some field, stay on the same page
        if not seen_go:
            return redirect(request.url)

        # finally, check if this has given us enough configuration info to
        # start the containers
        if self.base_is_configured():
            self._d.env_by_tags(["base_config"]).value = True
            agg_chosen_env = self._d.env_by_tags("aggregators_chosen")
            if self.at_least_one_aggregator() or agg_chosen_env.value == True:
                agg_chosen_env.value = True
                if self._d.is_enabled("sdrplay") and not self._d.is_enabled(
                    "sdrplay_license_accepted"
                ):
                    return redirect(url_for("sdrplay_license"))
                return redirect(url_for("restarting"))
            return redirect(url_for("aggregators"))
        return redirect(url_for("director"))

    @check_restart_lock
    def expert(self):
        if request.method == "POST":
            return self.update()
        if self._d.is_feeder_image:
            # is tailscale set up?
            try:
                result = subprocess.run(
                    "pgrep tailscaled >/dev/null 2>/dev/null && tailscale status --json 2>/dev/null",
                    shell=True,
                    check=True,
                    capture_output=True,
                )
            except:
                # a non-zero return value means tailscale isn't configured
                self._d.env_by_tags("tailscale_name").value = ""
            else:
                ts_status = json.loads(result.stdout.decode())
                if ts_status.get("BackendState") == "Running" and ts_status.get("Self"):
                    tailscale_name = ts_status.get("Self").get("HostName")
                    print_err(f"configured as {tailscale_name} on tailscale")
                    self._d.env_by_tags("tailscale_name").value = tailscale_name
                    self._d.env_by_tags("tailscale_ll").value = ""
                else:
                    self._d.env_by_tags("tailscale_name").value = ""
        # create a potential new root password in case the user wants to change it
        alphabet = string.ascii_letters + string.digits
        self.rpw = "".join(secrets.choice(alphabet) for i in range(12))
        return render_template("expert.html", rpw=self.rpw)

    @check_restart_lock
    def sdrplay_license(self):
        if request.method == "POST":
            return self.update()
        return render_template("sdrplay_license.html")

    @check_restart_lock
    def aggregators(self):
        if request.method == "POST":
            return self.update()

        def uf_enabled(*tags):
            return "checked" if self._d.is_enabled("ultrafeeder", *tags) else ""

        def others_enabled(*tags):
            return "checked" if self._d.is_enabled("other_aggregator", *tags) else ""

        return render_template(
            "aggregators.html",
            uf_enabled=uf_enabled,
            others_enabled=others_enabled,
        )

    @check_restart_lock
    def director(self):
        # figure out where to go:
        if request.method == "POST":
            return self.update()
        if not self._d.is_enabled("base_config"):
            return self.setup()

        # If we have more than one SDR, or one of them is an airspy,
        # we need to go to advanced - unless we have at least one of the serials set up
        # for 978 or 1090 reporting
        self._sdrdevices._ensure_populated()

        # do we have duplicate SDR serials?
        if len(self._sdrdevices.duplicates) > 0:
            return self.advanced()

        # check that "something" is configured as input
        if (
            len(self._sdrdevices) > 1
            or any([sdr._type == "airspy" for sdr in self._sdrdevices.sdrs])
        ) and not (
            self._d.env_by_tags("1090serial").value
            or self._d.env_by_tags("978serial").value
            or self._d.is_enabled("airspy")
        ):
            return self.advanced()

        # if the user chose to individually pick aggregators but hasn't done so,
        # they need to go to the aggregator page
        if self.at_least_one_aggregator() or self._d.env_by_tags("aggregators_chosen"):
            return self.index()
        return self.aggregators()

    @check_restart_lock
    def index(self):
        # make sure DNS works
        self.update_dns_state()
        ip, status = self._system.check_ip()
        if status == 200:
            self._d.env_by_tags(["feeder_ip"]).value = ip
        local_address = request.host.split(":")[0]

        # next check if there were under-voltage events (this is likely only relevant on an RPi)
        self._d.env_by_tags("under_voltage").value = False
        board = self._d.env_by_tags("board_name").value
        if board and board.startswith("Raspberry"):
            try:
                # yes, the except / else is a bit unintuitive, but that seemed the easiest way to do this;
                # if we don't find the text (the good case) we get an exception
                # ... on my kernels the message seems to be "Undervoltage", but on the web I find references to "under-voltage"
                subprocess.check_call(
                    "dmesg | grep -iE under.?voltage",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                pass
            else:
                self._d.env_by_tags("under_voltage").value = True

        # now let's check for disk space
        self._d.env_by_tags("low_disk").value = (
            shutil.disk_usage("/").free < 1024 * 1024 * 1024
        )

        # if we get to show the feeder homepage, the user should have everything figured out
        # and we can remove the pre-installed ssh-keys and password
        if os.path.exists("/opt/adsb/adsb.im.passwd.and.keys"):
            print_err("removing pre-installed ssh-keys, overwriting root password")
            authkeys = "/root/.ssh/authorized_keys"
            shutil.copyfile(authkeys, authkeys + ".bak")
            with open("/root/.ssh/adsb.im.installkey", "r") as installkey_file:
                installkey = installkey_file.read().strip()
            with open(authkeys + ".bak", "r") as org_authfile:
                with open(authkeys, "w") as new_authfile:
                    for line in org_authfile.readlines():
                        if "adsb.im" not in line and installkey not in line:
                            new_authfile.write(line)
            # now overwrite the root password with something random
            alphabet = string.ascii_letters + string.digits + string.punctuation
            self.rpw = "".join(secrets.choice(alphabet) for i in range(12))
            self.set_rpw()
            os.remove("/opt/adsb/adsb.im.passwd.and.keys")
        aggregators = self.all_aggregators
        for idx in range(len(aggregators)):
            if aggregators[idx][3]:
                if aggregators[idx][3][0] == "/":
                    aggregators[idx][3] = (
                        request.host_url.rstrip("/ ") + aggregators[idx][3]
                    )
                match = re.search("<([^>]*)>", aggregators[idx][3])
                if match:
                    # print_err(
                    #    f"found {match.group(0)} - replace with {self._d.env(match.group(1)).value}"
                    # )
                    aggregators[idx][3] = aggregators[idx][3].replace(
                        match.group(0), self._d.env(match.group(1)).value
                    )
        return render_template(
            "index.html", aggregators=aggregators, local_address=local_address
        )

    @check_restart_lock
    def setup(self):
        if request.method == "POST" and request.form.get("submit") == "go":
            return self.update()

        # make sure DNS works
        self.update_dns_state()
        return render_template("setup.html")


if __name__ == "__main__":
    # setup the config folder if that hasn't happened yet
    # this is designed for two scenarios:
    # (a) /opt/adsb/config is a subdirectory of /opt/adsb (that gets created if necessary)
    #     and the config files are moved to reside there
    # (b) prior to starting this app, /opt/adsb/config is created as a symlink to the
    #     OS designated config dir (e.g., /mnt/dietpi_userdata/adsb-feeder) and the config
    #     files are moved to that place instead
    config_files = {
        ".env",
        "1090uk.yml",
        "ah.yml",
        "airspy.yml",
        "docker-compose.yml",
        "dozzle.yml",
        "fa.yml",
        "fr24.yml",
        "os.yml",
        "pf.yml",
        "pw.yml",
        "rb.yml",
        "rv.yml",
        "sdrplay.yml",
        "uat978.yml",
    }
    adsb_dir = pathlib.Path("/opt/adsb")
    config_dir = pathlib.Path("/opt/adsb/config")
    if not config_dir.exists():
        config_dir.mkdir()
        env_file = adsb_dir / ".env"
        if env_file.exists():
            env_file.rename(config_dir / ".env")
    for file_name in config_files:
        config_file = pathlib.Path(adsb_dir / file_name)
        if config_file.exists():
            new_file = pathlib.Path(config_dir / file_name)
            config_file.rename(new_file)
            print_err(f"moved {config_file} to {new_file}")
    if not pathlib.Path(config_dir / ".env").exists():
        # I don't understand how that could happen
        shutil.copyfile(adsb_dir / "docker.image.versions", config_dir / ".env")

    no_server = len(sys.argv) > 1 and sys.argv[1] == "--update-config"

    AdsbIm().run(no_server=no_server)
