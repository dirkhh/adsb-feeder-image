import copy
import filecmp
import io
import json
import os
import os.path
import pathlib
import pickle
import platform
import re
import requests
import secrets
import signal
import shutil
import string
import subprocess
import threading
from uuid import uuid4
import sys
import zipfile
from base64 import b64encode
from datetime import datetime
from os import urandom
from time import sleep
from typing import Dict, List
from zlib import compress

from utils.config import (
    read_values_from_config_json,
    read_values_from_env_file,
    write_values_to_config_json,
    write_values_to_env_file,
)

if not os.path.exists("/opt/adsb/config/config.json"):
    print_err(
        "No config.json found, this should have been created before starting adsb-setup"
    )
    values = read_values_from_env_file()
    write_values_to_config_json(values)

# nofmt: on
# isort: off
from flask import (
    Flask,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    Response,
    send_file,
    url_for,
)


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
    stack_info,
    generic_get_json,
    is_true,
    verbose,
)

# nofmt: off
# isort: on

from werkzeug.utils import secure_filename


class AdsbIm:
    def __init__(self):
        print_err("starting AdsbIm.__init__", level=4)
        self.app = Flask(__name__)
        self.app.secret_key = urandom(16).hex()

        @self.app.context_processor
        def env_functions():
            def get_value(tags):
                e = self._d.env_by_tags(tags)
                return e.value if e else ""

            def list_value_by_tags(tags, idx):
                e = self._d.env_by_tags(tags)
                return e.list_get(idx) if e else ""

            return {
                "is_enabled": lambda tag: self._d.is_enabled(tag),
                "list_is_enabled": lambda tag, idx: self._d.list_is_enabled(
                    tag, idx=idx
                ),
                "env_value_by_tag": lambda tag: get_value([tag]),  # single tag
                "env_value_by_tags": lambda tags: get_value(tags),  # list of tags
                "list_value_by_tag": lambda tag, idx: list_value_by_tags([tag], idx),
                "list_value_by_tags": lambda tag, idx: list_value_by_tags(tag, idx),
                "env_values": self._d.envs,
            }

        self._routemanager = RouteManager(self.app)
        self._d = Data()
        self._system = System(data=self._d)
        self._sdrdevices = SDRDevices()
        for i in range(0, self._d.env_by_tags("num_micro_sites").value + 1):
            self._d.ultrafeeder.append(UltrafeederConfig(data=self._d, micro=i))

        self._agg_status_instances = dict()
        self._next_url_from_director = ""

        # Ensure secure_image is set the new way if before the update it was set only as env variable
        if self._d.is_enabled("secure_image"):
            self.set_secure_image()
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
            ["adsblol", "adsb.lol", "https://adsb.lol/", ["https://api.adsb.lol/0/me"]],
            ["flyitaly", "Fly Italy ADSB", "https://mappa.flyitalyadsb.com/", ["https://my.flyitalyadsb.com/am_i_feeding"]],
            ["avdelphi", "AVDelphi", "https://www.avdelphi.com/coverage.html", [""]],
            ["planespotters", "Planespotters", "https://radar.planespotters.net/", ["https://www.planespotters.net/feed/status"]],
            ["tat", "TheAirTraffic", "https://globe.theairtraffic.com/", ["https://theairtraffic.com/feed/myip/"]],
            # on "pause" for a while... ["flyovr", "FLYOVR.io", "https://globe.flyovr.io/", ""],
            ["radarplane", "RadarPlane", "https://radarplane.com/", ["https://radarplane.com/feed"]],
            ["adsbfi", "adsb.fi", "https://globe.adsb.fi/", ["https://api.adsb.fi/v1/myip"]],
            ["adsbx", "ADSBExchange", "https://globe.adsbexchange.com/", ["https://www.adsbexchange.com/myip/"]],
            ["hpradar", "HPRadar", "https://skylink.hpradar.com/", [""]],
            ["alive", "airplanes.live", "https://globe.airplanes.live/", ["https://airplanes.live/myfeed/"]],
            ["flightradar", "flightradar24", "https://www.flightradar24.com/", ["/fr24-monitor.jsonSTG2IDX"]],
            ["planewatch", "Plane.watch", "https:/plane.watch/desktop.html", [""]],
            ["flightaware", "FlightAware", "https://www.flightaware.com/live/map", ["/fa-status.jsonSTG2IDX"]],
            ["radarbox", "RadarBox", "https://www.radarbox.com/coverage-map", ["https://www.radarbox.com/stations/<FEEDER_RADARBOX_SN>"]],
            ["planefinder", "PlaneFinder", "https://planefinder.net/", ["/planefinder-statSTG2IDX"]],
            ["adsbhub", "ADSBHub", "https://www.adsbhub.org/coverage.php", [""]],
            ["opensky", "OpenSky", "https://opensky-network.org/network/explorer", ["https://opensky-network.org/receiver-profile?s=<FEEDER_OPENSKY_SERIAL>"]],
            ["radarvirtuel", "RadarVirtuel", "https://www.radarvirtuel.com/", [""]],
            ["1090uk", "1090MHz UK", "https://1090mhz.uk", ["https://www.1090mhz.uk/mystatus.php?key=<FEEDER_1090UK_API_KEY>"]],
        ]
        self.microfeeder_setting_tags = (
            "site_name", "lat", "lng", "alt", "tz", "mf_version",
            "adsblol_uuid", "ultrafeeder_uuid", "mlat_privacy", "route_api",
            "uat978", "heywhatsthat", "heywhatsthat_id",
            "flightradar--key", "flightradar_uat--key", "flightradar--is_enabled",
            "planewatch--key", "planewatch--is_enabled",
            "flightaware--key", "flightaware--is_enabled",
            "radarbox--key", "radarbox--is_enabled",
            "planefinder--key", "planefinder--is_enabled",
            "adsbhub--key", "adsbhub--is_enabled",
            "opensky--user", "opensky--key", "opensky--is_enabled",
            "radarvirtuel--key", "radarvirtuel--is_enabled",
            "planewatch--key", "planewatch--is_enabled",
            "1090uk--key", "1090uk--is_enabled",
            "adsblol--is_enabled",
            "flyitaly--is_enabled",
            "adsbx--is_enabled", "adsbxfeederid",
            "tat--is_enabled",
            "planespotters--is_enabled",
            "adsbfi--is_enabled",
            "avdelphi--is_enabled",
            "radarplane--is_enabled",
            "hpradar--is_enabled",
            "alive--is_enabled",
            "uat978--is_enabled", "978url", "uatport", "978piaware",
            "piamapport", "piastatport", "frport", "pfport"
        )

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
        self.app.add_url_rule("/visualization", "visualization", self.visualization, methods=["GET", "POST"])
        self.app.add_url_rule("/expert", "expert", self.expert, methods=["GET", "POST"])
        self.app.add_url_rule("/aggregators", "aggregators", self.aggregators, methods=["GET", "POST"])
        self.app.add_url_rule("/", "director", self.director, methods=["GET", "POST"])
        self.app.add_url_rule("/index", "index", self.index)
        self.app.add_url_rule("/info", "info", self.info)
        self.app.add_url_rule("/support", "support", self.support, methods=["GET", "POST"])
        self.app.add_url_rule("/setup", "setup", self.setup, methods=["GET", "POST"])
        self.app.add_url_rule("/stage2", "stage2", self.stage2, methods=["GET", "POST"])
        self.app.add_url_rule("/update", "update", self.update, methods=["POST"])
        self.app.add_url_rule("/sdplay_license", "sdrplay_license", self.sdrplay_license, methods=["GET", "POST"])
        self.app.add_url_rule("/api/sdr_info", "sdr_info", self.sdr_info)
        self.app.add_url_rule("/api/base_info", "base_info", self.base_info)
        self.app.add_url_rule("/api/micro_settings", "micro_settings", self.micro_settings)
        self.app.add_url_rule("/api/check_remote_feeder/<ip>", "check_remote_feeder", self.check_remote_feeder)
        self.app.add_url_rule(f"/api/status/<agg>", "beast", self.agg_status)
        self.app.add_url_rule(f"/api/status/<agg>/<idx>", "beast", self.agg_status)
        # fmt: on
        self.update_boardname()
        self.update_version()

        # finally, try to make sure that we have all the pieces that we need and recreate what's missing
        for i in range(self._d.env_by_tags("num_micro_sites").value + 1):
            if not self._d.env_by_tags("adsblol_uuid").list_get(i):
                self._d.env_by_tags("adsblol_uuid").list_set(i, str(uuid4()))
            if not self._d.env_by_tags("ultrafeeder_uuid").list_get(i):
                self._d.env_by_tags("ultrafeeder_uuid").list_set(i, str(uuid4()))
            create_stage2_yml_files(i, self._d.env_by_tags("mf_ip").list_get(i))

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
            "cv": self._d.env_by_tags("base_version").value,
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

    def write_envfile(self):
        write_values_to_env_file(self._d.envs_for_envfile)

    def setup_ultrafeeder_args(self):
        # set all of the ultrafeeder config data up
        for i in range(1 + self._d.env_by_tags("num_micro_sites").value):
            print_err(f"ultrafeeder_config {i}", level=2)
            if i >= len(self._d.ultrafeeder):
                self._d.ultrafeeder.append(UltrafeederConfig(data=self._d, micro=i))
            self._d.env_by_tags("ultrafeeder_config").list_set(
                i, self._d.ultrafeeder[i].generate()
            )

    def setup_app_ports(self):
        in_json = read_values_from_config_json()
        if "AF_WEBPORT" not in in_json.keys():
            # ok, we don't have them explicitly set, so let's set them up
            # with the app defaults
            self._d.env_by_tags("webport").value = 1099
            self._d.env_by_tags("tar1090port").value = 1090
            self._d.env_by_tags("uatport").value = 1091
            self._d.env_by_tags("piamapport").value = 1092
            self._d.env_by_tags("piastatport").value = 1093
            self._d.env_by_tags("dazzleport").value = 1094

    def run(self, no_server=False):
        self._routemanager.add_proxy_routes(self.proxy_routes)
        debug = os.environ.get("ADSBIM_DEBUG") is not None
        self._debug_cleanup()
        self.write_envfile()
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
            # v1.3.4 ended up not installing the correct port definitions - if that's
            # the case, then insert them into the settings
            self.setup_app_ports()

        # if all the user wanted is to make sure the housekeeping tasks are completed,
        # don't start the flask app and exit instead
        if no_server:
            self.setup_ultrafeeder_args()
            self.write_envfile()
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
            self.write_envfile()
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
        adsb_path = self._d.config_path
        if include_graphs:
            rrd_file = adsb_path / "ultrafeeder/graphs1090/rrd/localhost.tar.gz"
            # the rrd file will be updated via move after collectd is done writing it out
            # so killing collectd and waiting for the mtime to change is enough
            prev_time = os.stat(rrd_file).st_mtime
            try:
                subprocess.call(
                    "docker exec ultrafeeder pkill collectd", timeout=5.0, shell=True
                )
            except:
                print_err(
                    "failed to kill collectd - just using the localhost.tar.gz that's already there"
                )
                pass
            else:
                count = 0
                while True:
                    # because of the way the file gets updated, it will briefly not exist
                    # when the new copy is moved in place, which will make os.stat unhappy;
                    # either way, we give up after 30 seconds
                    try:
                        latest_timestamp = os.stat(rrd_file).st_mtime
                    except:
                        sleep(0.5)
                        continue
                    if latest_timestamp != prev_time:
                        break
                    sleep(1)
                    count += 1
                    if count > 30:
                        break
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

        site_name = self._d.env_by_tags("site_name").list_get(0)
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

            self.write_envfile()

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
            if env._value == None or (type(env._value) == list and not env.list_get(0)):
                print_err(f"base_is_configured: {env} isn't set up yet")
                return False
        return True

    def at_least_one_aggregator(self) -> bool:
        # this only checks for a micro feeder or integrated feeder, not for stage2
        if self._d.ultrafeeder[0].enabled_aggregators:
            return True

        # of course, maybe they picked just one or more proprietary aggregators and that's all they want...
        for submit_key in self._other_aggregators.keys():
            key = submit_key.replace("--submit", "")
            if self._d.list_is_enabled(key, idx=0):
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
        used_serials = {
            self._d.env_by_tags(f).value for f in self._sdrdevices.purposes()
        }
        for f in [978, 1090]:
            if not serials[f] and serial_guess[f] not in used_serials:
                serials[f] = serial_guess[f]

        print_err(f"sdr_info->frequencies: {str(serials)}")
        jsonString = json.dumps(
            {
                "sdrdevices": [sdr._json for sdr in self._sdrdevices.sdrs],
                "frequencies": serials,
                "duplicates": ", ".join(self._sdrdevices.duplicates),
                "lsusb_output": self._sdrdevices.lsusb_output,
            },
            indent=2,
        )
        return Response(jsonString, mimetype="application/json")

    def base_info(self):
        listener = request.remote_addr
        stage2_listeners = self._d.env_by_tags("stage2_listeners").value
        print_err(f"access to base_info from {listener}")
        if not listener in stage2_listeners:
            idx = len(stage2_listeners)
            self._d.env_by_tags("stage2_listeners").list_set(idx, listener)
        response = make_response(
            json.dumps(
                {
                    "name": self._d.env_by_tags("site_name").list_get(0),
                    "lat": self._d.env_by_tags("lat").list_get(0),
                    "lng": self._d.env_by_tags("lng").list_get(0),
                    "alt": self._d.env_by_tags("alt").list_get(0),
                    "tz": self._d.env_by_tags("tz").list_get(0),
                    "version": self._d.env_by_tags("base_version").value,
                }
            )
        )
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def micro_settings(self):
        microsettings = {}
        for e in self._d._env:
            for t in self.microfeeder_setting_tags:
                tags = t.split("--")
                if all(t in e.tags for t in tags):
                    if type(e._value) == list:
                        microsettings[t] = e.list_get(0)
                    else:
                        microsettings[t] = e._value
        # fix up the version
        microsettings["mf_version"] = self._d.env_by_tags("base_version").value
        response = make_response(json.dumps(microsettings))
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def agg_status(self, agg, idx=0):
        # print_err(f'agg_status(agg={agg}, idx={idx})')
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

        status = self._agg_status_instances.get(f"{agg}-{idx}")
        if status is None:
            status = self._agg_status_instances[f"{agg}-{idx}"] = AggStatus(
                agg, idx, self._d, request.host_url.rstrip("/ ")
            )

        if agg == "adsbx":
            return json.dumps(
                {
                    "beast": status.beast,
                    "mlat": status.mlat,
                    "adsbxfeederid": self._d.env_by_tags("adsbxfeederid").list_get(idx),
                }
            )
        return json.dumps({"beast": status.beast, "mlat": status.mlat})

    @check_restart_lock
    def advanced(self):
        if request.method == "POST":
            return self.update()
        if self._d.is_enabled("stage2"):
            return self.visualization()
        return render_template("advanced.html")

    def visualization(self):
        if request.method == "POST":
            return self.update()

        # is this a stage2 site and you are looking at an individual micro feeder,
        # or is this a regular feeder?
        # m=0 indicates we are looking at an integrated/micro feeder or at the stage 2 local aggregator
        # m>0 indicates we are looking at a micro-proxy
        if self._d.is_enabled("stage2"):
            try:
                m = int(request.args.get("m"))
            except:
                m = 0
            site = self._d.env_by_tags("site_name").list_get(m)
            print_err(
                "setting up visualization on a stage 2 system for site {site} (m={m})"
            )
        else:
            site = ""
            m = 0
        return render_template("visualization.html", site=site, m=m)

    def set_channel(self, channel: str):
        with open(self._d.data_path / "update-channel", "w") as update_channel:
            print(channel, file=update_channel)

    def extract_channel(self) -> str:
        channel = self._d.env_by_tags("base_version").value
        if channel:
            match = re.search(r"\((.*?)\)", channel)
            if match:
                channel = match.group(1)
        if channel in ["stable", "beta", "main"]:
            channel = ""
        if not channel.startswith("origin/"):
            channel = f"origin/{channel}"
        return channel

    def clear_range_outline(self, idx=0):
        # is the file where we expect it?
        globe_history = "globe_history" if idx == 0 else f"globe_history_{idx}"
        rangedirs = (
            self._d.config_path
            / "ultrafeeder"
            / globe_history
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

    def get_base_info(self, n, do_import=False):
        ip = self._d.env_by_tags("mf_ip").list_get(n)
        print_err(f"getting info from {ip} with do_import={do_import}")
        # try:
        if do_import:
            micro_settings, status = generic_get_json(
                f"http://{ip}/api/micro_settings", None
            )
            print_err(f"micro_settings API on {ip}: {status}, {micro_settings}")
            if status == 200 and micro_settings != None:
                for key, value in micro_settings.items():
                    tags = key.split("--")
                    print_err(f"setting env for {tags} to {value}", level=4)
                    e = self._d.env_by_tags(tags)
                    if e:
                        e.list_set(n, value)
                return True
        # we fall through here if we can't get the micro settings
        base_info, status = generic_get_json(f"http://{ip}/api/base_info", None)
        if status == 200 and base_info != None:
            print_err(f"got {base_info} for {ip}")
            self._d.env_by_tags("site_name").list_set(n, base_info["name"])
            self._d.env_by_tags("lat").list_set(n, base_info["lat"])
            self._d.env_by_tags("lng").list_set(n, base_info["lng"])
            self._d.env_by_tags("alt").list_set(n, base_info["alt"])
            self._d.env_by_tags("tz").list_set(n, base_info["tz"])
            self._d.env_by_tags("mf_version").list_set(n, base_info["version"])
            return True
        #    except:
        #        pass
        print_err(f"failed to get base_info from micro feeder {n}")
        return False

    def check_remote_feeder(self, ip):
        url = f"http://{ip}/api/base_info"
        print_err(f"checking remote feeder {url}")
        try:
            response = requests.get(url, timeout=5.0)
            print_err(f"response code: {response.status_code}")
            json_dict = response.json()
            print_err(f"json_dict: {type(json_dict)} {json_dict}")
        except:
            print_err(f"failed to check base_info from remote feeder {ip}")
        else:
            if response.status_code == 200:
                # yay, this is an adsb.im feeder
                # is it new enough to have the setting transfer?
                url = f"http://{ip}/api/micro_settings"
                print_err(f"checking remote feeder {url}")
                try:
                    response = requests.get(url, timeout=5.0)
                except:
                    print_err(f"failed to check micro_settings from remote feeder {ip}")
                    json_dict["micro_settings"] = False
                else:
                    if response.status_code == 200:
                        # ok, we have a recent adsb.im version
                        json_dict["micro_settings"] = True
                    else:
                        json_dict["micro_settings"] = False
            # now return the json_dict which will give the caller all the relevant data
            # including whether this is a v2 or not
            return make_response(json.dumps(json_dict), 200)
        # ok, it's not a recent adsb.im version, it could still be a feeder
        # the show-only argument basically just makes sure that the readsb doesn't create
        # hundreds or thousands of lines of output
        uf = self._d.env_by_tags(["ultrafeeder", "container"]).value
        print_err(
            f"running: 'docker run --rm --entrypoint /usr/local/bin/readsb {uf} --net-connector {ip},30005,beast_in --net-only --show-only=123456'"
        )
        try:
            response = subprocess.run(
                f"docker run --rm --entrypoint /usr/local/bin/readsb {uf} --net-connector {ip},30005,beast_in --net-only --show-only=123456",
                shell=True,
                timeout=5.0,
                capture_output=True,
            )
            output = response.stderr.decode("utf-8")
        except subprocess.TimeoutExpired as e:
            # no worries, that' very much expected behavior
            output = e.stderr.decode("utf-8")
        except:
            print_err(
                "failed to use readsb in ultrafeeder container to check on remote feeder status"
            )
            return make_response(json.dumps({"status": "fail"}), 200)
        if not re.search("Beast TCP input: Connection established", output):
            print_err(f"can't connect to beast_output on remote feeder: {output}")
            return make_response(json.dumps({"status": "fail"}), 200)
        return make_response(json.dumps({"status": "ok"}), 200)

    def import_graphs_and_history_from_remote(self, ip):
        print_err(f"importing graphs and history from {ip}")
        # first make sure that there isn't any old data that needs to be moved
        # out of the way
        if pathlib.Path(self._d.config_path / "ultrafeeder" / ip).exists():
            now = datetime.now().replace(microsecond=0).isoformat().replace(":", "-")
            shutil.move(
                self._d.config_path / "ultrafeeder" / ip,
                self._d.config_path / "ultrafeeder" / f"{ip}-{now}",
            )
        url = f"http://{ip}/backupexecutefull"
        with requests.get(url, stream=True) as response, zipfile.ZipFile(
            io.BytesIO(response.content)
        ) as zf:
            zf.extractall(path=self._d.config_path / "ultrafeeder" / ip)
        # deal with the duplicate "ultrafeeder in the path"
        shutil.move(
            self._d.config_path / "ultrafeeder" / ip / "ultrafeeder" / "globe_history",
            self._d.config_path / "ultrafeeder" / ip / "globe_history",
        )
        shutil.move(
            self._d.config_path / "ultrafeeder" / ip / "ultrafeeder" / "graphs1090",
            self._d.config_path / "ultrafeeder" / ip / "graphs1090",
        )
        print_err(f"done importing graphs and history from {ip}")

    def setup_new_micro_site(
        self, ip, uat, is_adsbim, do_import=False, do_restore=False
    ):
        if ip in self._d.env_by_tags("mf_ip").value:
            print_err(f"IP address {ip} already listed as a micro site")
            return False
        print_err(
            f"setting up a new micro site at {ip} do_import={do_import} do_restore={do_restore}"
        )
        n = self._d.env_by_tags("num_micro_sites").value
        # store the IP address so that get_base_info works
        self._d.env_by_tags("mf_ip").list_set(n + 1, ip)
        if not is_adsbim:
            # well that's unfortunate
            # we might get asked to create a UI for this at some point. Not today, though
            print_err(f"Micro feeder at {ip} is not an adsb.im feeder")
            n += 1
            self._d.env_by_tags("num_micro_sites").value = n
            self._d.env_by_tags("site_name").list_set(n, ip)
            self._d.env_by_tags("lat").list_set(n, "")
            self._d.env_by_tags("lng").list_set(n, "")
            self._d.env_by_tags("alt").list_set(n, "")
            self._d.env_by_tags("tz").list_set(n, "UTC")
            self._d.env_by_tags("mf_version").list_set(n, "not an adsb.im feeder")
            self._d.env_by_tags(["uat978", "is_enabled"]).list_set(n, uat)
            if uat:
                # always get UAT from the readsb uat_replay
                self._d.env_by_tags("replay978").list_set(
                    n, "--net-uat-replay-port 30978"
                )
                self._d.env_by_tags("978host").list_set(n, f"ultrafeeder_{n}")
                self._d.env_by_tags("978piaware").list_set(n, "relay")
            return True

        # now let's see if we can get the data from the micro feeder
        if self.get_base_info(n + 1, do_import=do_import):
            print_err(
                f"added new micro site {self._d.env_by_tags('site_name').value[n + 1]} at {ip}"
            )
            n += 1
            self._d.env_by_tags("num_micro_sites").value = n
            create_stage2_yml_files(n, ip)
            if do_restore:
                print_err(f"attempting to restore graphs and history from {ip}")
                self.import_graphs_and_history_from_remote(ip)
        else:
            # oh well, remove the IP address
            self._d.env_by_tags("mf_ip").list_remove()
            return False

        self._d.env_by_tags(["uat978", "is_enabled"]).list_set(n, uat)
        if uat:
            # always get UAT from the readsb uat_replay
            self._d.env_by_tags("replay978").list_set(n, "--net-uat-replay-port 30978")
            self._d.env_by_tags("978host").list_set(n, f"ultrafeeder_{n}")
            self._d.env_by_tags("978piaware").list_set(n, "relay")
        return True

    def remove_micro_site(self, num):
        # carefully shift everything down
        print_err(f"removing micro site {num}")
        for t in self.microfeeder_setting_tags + ("mf_ip",):
            tags = t.split("--")
            e = self._d.env_by_tags(tags)
            if e:
                print_err(
                    f"shifting {e.name} down and deleting last element {e._value}"
                )
                for i in range(num, self._d.env_by_tags("num_micro_sites").value):
                    e.list_set(i, e.list_get(i + 1))
                if len(e._value) > self._d.env_by_tags("num_micro_sites").value:
                    e.list_remove()
            else:
                print_err(f"couldn't find env for {tags}")
        self._d.env_by_tags("num_micro_sites").value -= 1
        # finally, recreate the stage2 yml files for those feeders that shifted down
        # the index is used to pick the correct environment variables, the IP address
        # is used to distinguish the globe history and graphs for each micro feeder
        for i in range(num, self._d.env_by_tags("num_micro_sites").value):
            create_stage2_yml_files(i, self._d.env_by_tags("mf_ip").list_get(i))

    @check_restart_lock
    def update(self):
        description = """
            This is the one endpoint that handles all the updates coming in from the UI.
            It walks through the form data and figures out what to do about the information provided.
        """
        # let's try and figure out where we came from:
        referer = request.headers.get("referer")
        match = re.match(r"\?m=(\d*)$", referer)
        if match:
            sitenum = int(match.group(1))
            if sitenum >= 0 and sitenum < self._d.env_by_tags("num_micro_sites").value:
                # this is a request coming from a micro site
                site = self._d.env_by_tags("site_name").list_get(sitenum)
            else:
                print_err(
                    f"invalid micro site number {sitenum} (num_micro_sites={self._d.env_by_tags('num_micro_sites').value})"
                )
                sitenum = 0
                site = ""
        else:
            site = ""
            sitenum = 0
            target = "integrated feeder / stage2 main page"
        print_err(f"handling input from {referer} and site {site}")
        # in the HTML, every input field needs to have a name that is concatenated by "--"
        # and that matches the tags of one Env
        purposes = self._sdrdevices.purposes()
        form: Dict = request.form
        seen_go = False
        next_url = None
        allow_insecure = not self.check_secure_image()
        for key, value in form.items():
            print_err(f"handling {key} -> {value} (allow insecure is {allow_insecure})")
            # this seems like cheating... let's capture all of the submit buttons
            if value == "go" or value.startswith("go-"):
                seen_go = True
            if value == "go" or value.startswith("go-") or value == "wait":
                if key == "showmap" and value.startswith("go-"):
                    idx = value[3:]
                    try:
                        idx = int(idx)
                    except:
                        idx = 0
                    port = 8090 + idx if idx > 0 else 8080
                    self._next_url_from_director = (
                        f"http://{request.host.split(':')[0]}:{port}/"
                    )
                    print_err(
                        f"after applying changes, go to map at {self._next_url_from_director}"
                    )
                if key == "clear_range":
                    self.clear_range_outline(sitenum)
                    continue
                if key == "sdrplay_license_accept":
                    self._d.env_by_tags("sdrplay_license_accepted").value = True
                if key == "sdrplay_license_reject":
                    self._d.env_by_tags("sdrplay_license_accepted").value = False
                if (
                    key == "add_micro"
                    or key == "add_other"
                    or key.startswith("import_micro")
                ):
                    # user has clicked Add micro feeder on Stage 2 page
                    # grab the IP that we know the user has provided
                    ip = form.get("add_micro_feeder_ip")
                    uat = form.get("micro_uat")
                    is_adsbim = key != "add_other"
                    do_import = key.startswith("import_micro")
                    do_restore = key == "import_micro_full"
                    if self.setup_new_micro_site(
                        ip,
                        uat=is_true(uat),
                        is_adsbim=is_adsbim,
                        do_import=do_import,
                        do_restore=do_restore,
                    ):
                        continue
                    next_url = url_for("stage2")
                    continue
                if key.startswith("remove_micro_"):
                    # user has clicked Remove micro feeder on Stage 2 page
                    # grab the micro feeder number that we know the user has provided
                    num = int(key[len("remove_micro_") :])
                    self.remove_micro_site(num)
                    continue
                if key == "set_stage2_data":
                    # just grab the new data and go back
                    next_url = url_for("stage2")
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
                    self.write_envfile()
                    # almost certainly overkill, but...
                    self._system.restart_containers()
                    return render_template("/waitandredirect.html")
                if key == "secure_image":
                    self.set_secure_image()
                if key.startswith("update_feeder_aps"):
                    channel = key.rsplit("_", 1)[-1]
                    if channel == "branch":
                        channel = self.extract_channel()
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
            if value == "stay" or value.startswith("stay-"):
                if allow_insecure and key == "rpw":
                    print_err("updating the root password")
                    self.set_rpw()
                    continue
                if key in self._other_aggregators:
                    l_sitenum = 0
                    if value.startswith("stay-"):
                        try:
                            l_sitenum = int(value[5:])
                            l_site = self._d.env_by_tags("site_name").list_get(
                                l_sitenum
                            )
                            if not l_site:
                                l_sitenum = 0
                        except:
                            print_err(f"failed to parse value keyword {value}")
                            l_sitenum = 0
                        print_err(
                            f"found other aggregator {key} for site {l_site} sitenum {l_sitenum}"
                        )
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
                    print_err(
                        f"got aggregator object {aggregator_object} -- activating for sitenum {l_sitenum}"
                    )
                    try:
                        is_successful = aggregator_object._activate(
                            aggregator_argument, l_sitenum
                        )
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
                # deal with the micro feeder and stage2 initial setup
                if key == "aggregators" and value == "micro":
                    self._d.env_by_tags(["tar1090_ac_db"]).value = False
                    self._d.env_by_tags(["mlathub_disable"]).value = True
                    self._d.env_by_tags("aggregators_chosen").value = True
                    # disable all the aggregators in micro mode
                    for ev in self._d._env:
                        if "is_enabled" in ev.tags:
                            if (
                                "other_aggregator" in ev.tags
                                or "ultrafeeder" in ev.tags
                            ):
                                ev.list_set(0, False)
                else:
                    self._d.env_by_tags(["tar1090_ac_db"]).value = True
                    self._d.env_by_tags(["mlathub_disable"]).value = False
                if key == "aggregators" and value == "stage2":
                    self._d.env_by_tags("stage2").value = True
                    self._d.env_by_tags("site_name").list_set(0, form.get("site_name"))
                # finally, painfully ensure that we remove explicitly asigned SDRs from other asignments
                # this relies on the web page to ensure that each SDR is only asigned on purpose
                # the key in quesiton will be explicitely set and does not need clearing
                # empty string means no SDRs assigned to that purpose
                if key in purposes and value != "":
                    for clear_key in purposes:
                        if (
                            clear_key != key
                            and value == self._d.env_by_tags(clear_key).value
                        ):
                            print_err(f"clearing: {str(clear_key)} old value: {value}")
                            self._d.env_by_tags(clear_key).value = ""
                # when dealing with micro feeder aggregators, we need to keep the site number
                # in mind
                tags = key.split("--")
                if sitenum > 0 and "is_enabled" in tags:
                    print_err(f"setting up stage2 micro site number {sitenum}: {key}")
                    self._d.env_by_tags("aggregators_chosen").value = True
                    self._d.env_by_tags(tags).list_set(sitenum, is_true(value))
                else:
                    if type(e._value) == list:
                        e.list_set(sitenum, value)
                    else:
                        e.value = value
                if key == "site_name":
                    self._d.env_by_tags("site_name").list_set(sitenum, value)
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
            self._d.env_by_tags(["uat978", "is_enabled"]).list_set(sitenum, True)
            self._d.env_by_tags("978url").list_set(
                sitenum, "http://dump978/skyaware978"
            )
            self._d.env_by_tags("978host").list_set(sitenum, "dump978")
            self._d.env_by_tags("978piaware").list_set(sitenum, "relay")
        else:
            self._d.env_by_tags(["uat978", "is_enabled"]).list_set(sitenum, False)
            self._d.env_by_tags("978url").list_set(sitenum, "")
            self._d.env_by_tags("978host").list_set(sitenum, "")
            self._d.env_by_tags("978piaware").list_set(sitenum, "")

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
        self._d.env_by_tags("readsb_device_type").value = "rtlsdr" if rtlsdr else ""

        if verbose & 1:
            print_err(f"in the end we have")
            print_err(f"1090serial {env1090.value}")
            print_err(f"978serial {env978.value}")
            print_err(
                f"airspy container is {self._d.is_enabled(['airspy', 'is_enabled'])}"
            )
            print_err(
                f"SDRplay container is {self._d.is_enabled(['sdrplay', 'is_enabled'])}"
            )
            print_err(
                f"dump978 container {self._d.list_is_enabled(['uat978', 'is_enabled'], sitenum)}"
            )

        # set all of the ultrafeeder config data up
        self.setup_ultrafeeder_args()

        # finally, check if this has given us enough configuration info to
        # start the containers
        agg_chosen_env = self._d.env_by_tags("aggregators_chosen")
        if self.base_is_configured() or self._d.is_enabled("stage2"):
            self._d.env_by_tags(["base_config", "is_enabled"]).value = True
            if self.at_least_one_aggregator():
                agg_chosen_env.value = True

        # write all this out to the .env file so that a docker-compose run will find it
        self.write_envfile()

        # if the button simply updated some field, stay on the same page
        if not seen_go:
            print_err("no go button, so stay on the same page", level=2)
            return redirect(request.url)

        # where do we go from here?
        if next_url:  # we figured it out above
            return redirect(next_url)
        if self._d.is_enabled("base_config"):
            print_err("base config is completed", level=2)
            if agg_chosen_env.value == True:
                print_err("base config is completed", level=2)
                if self._d.is_enabled("sdrplay") and not self._d.is_enabled(
                    "sdrplay_license_accepted"
                ):
                    return redirect(url_for("sdrplay_license"))
                return redirect(url_for("restarting"))
            if self._d.env_by_tags("aggregators").value == "stage2":
                return redirect(url_for("stage2"))
            if self._d.env_by_tags("aggregators").value != "micro":
                return redirect(url_for("aggregators"))
        print_err("base config not completed", level=2)
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
        # if we are on a branch that's neither stable nor beta, pass the value to the template
        # so that a third update button will be shown
        return render_template(
            "expert.html",
            rpw=self.rpw,
            channel=self.extract_channel(),
        )

    @check_restart_lock
    def sdrplay_license(self):
        if request.method == "POST":
            return self.update()
        return render_template("sdrplay_license.html")

    @check_restart_lock
    def aggregators(self):
        if request.method == "POST":
            return self.update()

        def uf_enabled(tag, m=0):
            # stack_info(f"tags are {type(tag)} {tag}")
            if type(tag) == str:
                tag = [tag]
            if type(tag) != list:
                print_err(f"PROBLEM::: tag is {type(tag)}")
            return (
                "checked"
                if self._d.list_is_enabled(["ultrafeeder"] + tag, idx=m)
                else ""
            )

        def others_enabled(tag, m=0):
            # stack_info(f"tags are {type(tag)} {tag}")
            if type(tag) == str:
                tag = [tag]
            if type(tag) != list:
                print_err(f"PROBLEM::: tag is {type(tag)}")
            return (
                "checked"
                if self._d.list_is_enabled(["other_aggregator"] + tag, idx=m)
                else ""
            )

        # is this a stage2 site and you are looking at an individual micro feeder,
        # or is this a regular feeder? If we have a query argument m that is a non-negative
        # number, then yes it is
        if self._d.is_enabled("stage2"):
            print_err("setting up aggregators on a stage 2 system")
            try:
                m = int(request.args.get("m"))
            except:
                m = 1
            if m == 0:  # do not set up aggregators for the aggregated feed
                if self._d.env_by_tags("num_micro_sites").value == "0":
                    # things aren't set up yet, bail out to the stage 2 setup
                    return redirect(url_for("stage2"))
                m = 1
            site = self._d.env_by_tags("site_name").list_get(m)
            print_err(f"setting up aggregators for site {site} (m={m})")
        else:
            site = ""
            m = 0
        return render_template(
            "aggregators.html",
            uf_enabled=uf_enabled,
            others_enabled=others_enabled,
            site=site,
            m=str(m),
        )

    @check_restart_lock
    def director(self):
        # figure out where to go:
        if request.method == "POST":
            return self.update()
        if not self._d.is_enabled("base_config"):
            return self.setup()
        # if we already figured out where to go next, let's just do that
        if self._next_url_from_director:
            url = self._next_url_from_director
            self._next_url_from_director = ""
            if re.match(r"^http://\d+\.\d+\.\d+\.\d+:\d+$", url):
                # this looks like it could be a forward to a tar1090 map
                # give it a few moments until this page is ready
                # but don't risk hanging out here forever
                testurl = url + "/data/receiver.json"
                for i in range(5):
                    sleep(1.0)
                    try:
                        response = requests.get(testurl, timeout=2.0)
                        if response.status_code == 200:
                            break
                    except:
                        pass
            return redirect(url)
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
            self._d.env_by_tags(["mf_ip"]).list_set(0, ip)
        try:
            result = subprocess.run(
                "ip route get 1 | head -1  | cut -d' ' -f7",
                shell=True,
                capture_output=True,
                timeout=2.0,
            ).stdout
        except:
            result = ""
        else:
            result = result.decode().strip()
        if result:
            local_address = result
        else:
            local_address = request.host.split(":")[0]

        if self._d.env_by_tags("tailscale_name").value:
            try:
                result = subprocess.run(
                    "tailscale ip -4 2>/dev/null",
                    shell=True,
                    capture_output=True,
                    timeout=2.0,
                ).stdout
            except:
                result = ""
            else:
                result = result.decode().strip()
            tailscale_address = result
        else:
            tailscale_address = ""
        zt_network = self._d.env_by_tags("zerotierid").value
        if zt_network:
            try:
                result = subprocess.run(
                    f"zerotier-cli get {zt_network} ip4 2>/dev/null",
                    shell=True,
                    capture_output=True,
                    timeout=2.0,
                ).stdout
            except:
                result = ""
            else:
                result = result.decode().strip()
            zerotier_address = result
        else:
            zerotier_address = ""
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
        aggregators = copy.deepcopy(self.all_aggregators)
        url_start = request.host_url.rstrip("/ ")
        for idx in range(len(aggregators)):
            status_link_list = aggregators[idx][3]
            template_link = status_link_list[0]
            final_link = template_link
            for i in range(self._d.env_by_tags("num_micro_sites").value + 1):
                if template_link.startswith("/"):
                    final_link = url_start + template_link.replace(
                        "STG2IDX", "" if i == 0 else f"_{i}"
                    )
                else:
                    match = re.search("<([^>]*)>", template_link)
                    if match:
                        final_link = template_link.replace(
                            match.group(0), self._d.env(match.group(1)).list_get(i)
                        )
                if i == 0:
                    status_link_list[0] = final_link
                else:
                    status_link_list.append(final_link)
        print_err(f"final aggregator structure: {aggregators}")
        return render_template(
            "index.html",
            aggregators=aggregators,
            local_address=local_address,
            tailscale_address=tailscale_address,
            zerotier_address=zerotier_address,
        )

    @check_restart_lock
    def setup(self):
        if request.method == "POST" and request.form.get("submit") == "go":
            return self.update()
        # is this a stage2 feeder?
        if self._d.is_enabled("stage2"):
            return render_template("stage2.html")
        # make sure DNS works
        self.update_dns_state()
        return render_template("setup.html")

    @check_restart_lock
    def stage2(self):
        if request.method == "POST":
            return self.update()
        # update the info from the micro feeders
        for i in range(self._d.env_by_tags("num_micro_sites").value):
            self.get_base_info(i + 1)  # micro proxies start at 1
        return render_template("stage2.html")

    def support(self):
        url = ""
        print_err(f"support request, {request.form}")
        if request.method == "POST":
            if request.form.get("upload") == "stay":
                print_err("trying to upload the logs")
                try:
                    result = subprocess.run(
                        "bash /opt/adsb/log-sanitizer.sh | curl -F 'sprunge=<-' http://sprunge.us",
                        shell=True,
                        capture_output=True,
                    )
                except:
                    print_err("failed to upload logs")
                else:
                    url = result.stdout.decode("utf-8").strip()
                    print_err(f"uploaded logs to {url}")
        return render_template("support.html", url=url)

    def info(self):
        board = self._d.env_by_tags("board_name").value
        base = self._d.env_by_tags("image_name").value
        current = self._d.env_by_tags("base_version").value
        ufargs = self._d.env_by_tags("ultrafeeder_extra_args").value
        envvars = self._d.env_by_tags("ultrafeeder_extra_env").value
        sdrs = (
            [f"{sdr}" for sdr in self._sdrdevices.sdrs]
            if len(self._sdrdevices.sdrs) > 0
            else ["none"]
        )
        try:
            cmdline = "df -h | grep -v overlay"
            result = subprocess.run(
                cmdline, shell=True, capture_output=True, timeout=2.0
            )
        except:
            result = "failed to run 'df -h | grep -v overlay'"
        storage = result.stdout.decode("utf-8")
        try:
            cmdline = "free -h"
            result = subprocess.run(
                cmdline, shell=True, capture_output=True, timeout=2.0
            )
        except:
            result = "failed to run 'free -h'"
        memory = result.stdout.decode("utf-8")
        containers = [
            self._d.env_by_tags(["container", container]).value
            for container in self._d.tag_for_name.values()
            if self._d.is_enabled(container) or container == "ultrafeeder"
        ]
        return render_template(
            "info.html",
            board=board,
            memory=memory,
            storage=storage,
            base=base,
            current=current,
            containers=containers,
            sdrs=sdrs,
            ufargs=ufargs,
            envvars=envvars,
        )


def create_stage2_yml_from_template(stage2_yml_name, n, ip, template_file):
    if n:
        with open(template_file, "r") as stage2_yml_template:
            with open(stage2_yml_name, "w") as stage2_yml:
                stage2_yml.write(
                    stage2_yml_template.read()
                    .replace("STAGE2NUM", f"{n}")
                    .replace("STAGE2IP", ip)
                )
    else:
        print_err(f"could not find micro feedernumber in {stage2_yml_name}")


def create_stage2_yml_files(n, ip):
    if not n:
        return
    for yml_file, template in [
        [f"stage2_micro_site_{n}.yml", "stage2.yml"],
        [f"1090uk_{n}.yml", "1090uk_stage2_template.yml"],
        [f"ah_{n}.yml", "ah_stage2_template.yml"],
        [f"fa_{n}.yml", "fa_stage2_template.yml"],
        [f"fr24_{n}.yml", "fr24_stage2_template.yml"],
        [f"os_{n}.yml", "os_stage2_template.yml"],
        [f"pf_{n}.yml", "pf_stage2_template.yml"],
        [f"pw_{n}.yml", "pw_stage2_template.yml"],
        [f"rb_{n}.yml", "rb_stage2_template.yml"],
        [f"rv_{n}.yml", "rv_stage2_template.yml"],
    ]:
        create_stage2_yml_from_template(
            f"/opt/adsb/config/{yml_file}", n, ip, f"/opt/adsb/config/{template}"
        )


if __name__ == "__main__":
    # setup the config folder if that hasn't happened yet
    # this is designed for two scenarios:
    # (a) /opt/adsb/config is a subdirectory of /opt/adsb (that gets created if necessary)
    #     and the config files are moved to reside there
    # (b) prior to starting this app, /opt/adsb/config is created as a symlink to the
    #     OS designated config dir (e.g., /mnt/dietpi_userdata/adsb-feeder) and the config
    #     files are moved to that place instead

    adsb_dir = pathlib.Path("/opt/adsb")
    config_dir = pathlib.Path("/opt/adsb/config")

    if not config_dir.exists():
        config_dir.mkdir()
        env_file = adsb_dir / ".env"
        if env_file.exists():
            env_file.rename(config_dir / ".env")

    for config_file in adsb_dir.glob("*.yml"):
        if config_file.exists():
            new_file = config_dir / config_file.name
            config_file.rename(new_file)
            print_err(f"moved {config_file} to {new_file}")

    if not pathlib.Path(config_dir / ".env").exists():
        # I don't understand how that could happen
        shutil.copyfile(adsb_dir / "docker.image.versions", config_dir / ".env")

    no_server = len(sys.argv) > 1 and sys.argv[1] == "--update-config"

    AdsbIm().run(no_server=no_server)
