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
import shlex
import requests
import secrets
import signal
import shutil
import string
import subprocess
import threading
import time
import tempfile
from uuid import uuid4
import sys
import zipfile
from base64 import b64encode
from datetime import datetime
from os import urandom
from time import sleep
from typing import Dict, List
from zlib import compress
from copy import deepcopy

from utils.config import (
    config_lock,
    read_values_from_config_json,
    read_values_from_env_file,
    write_values_to_config_json,
    write_values_to_env_file,
)
from utils.util import create_fake_info, make_int, print_err, mf_get_ip_and_triplet

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
    run_shell_captured,
    stack_info,
    generic_get_json,
    is_true,
    verbose,
)

# nofmt: off
# isort: on

from werkzeug.utils import secure_filename

from flask.logging import logging as flask_logging


# don't log static assets
class NoStatic(flask_logging.Filter):
    def filter(record):
        msg = record.getMessage()
        if "GET /static/" in msg:
            return False
        if not (verbose & 8) and "GET /api/" in msg:
            return False

        return True


flask_logging.getLogger("werkzeug").addFilter(NoStatic)


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
                "list_is_enabled": lambda tag, idx: self._d.list_is_enabled(tag, idx=idx),
                "env_value_by_tag": lambda tag: get_value([tag]),  # single tag
                "env_value_by_tags": lambda tags: get_value(tags),  # list of tags
                "list_value_by_tag": lambda tag, idx: list_value_by_tags([tag], idx),
                "list_value_by_tags": lambda tag, idx: list_value_by_tags(tag, idx),
                "env_values": self._d.envs,
            }

        self._routemanager = RouteManager(self.app)
        self._d = Data()
        self._system = System(data=self._d)

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
            with open(self._d.data_path / "adsb-setup/templates/systemmgmt.html", "r+") as systemmgmt_file:
                systemmgmt_html = systemmgmt_file.read()
                systemmgmt_file.seek(0)
                systemmgmt_file.write(
                    re.sub(
                        "FULL_IMAGE_ONLY_START.*? FULL_IMAGE_ONLY_END",
                        "",
                        systemmgmt_html,
                        flags=re.DOTALL,
                    )
                )
                systemmgmt_file.truncate()
            # v1.3.4 ended up not installing the correct port definitions - if that's
            # the case, then insert them into the settings
            self.setup_app_ports()

        self._sdrdevices = SDRDevices()
        for i in [0] + self.micro_indices():
            self._d.ultrafeeder.append(UltrafeederConfig(data=self._d, micro=i))

        self._current_site_name = None
        self._agg_status_instances = dict()
        self._next_url_from_director = ""
        self._last_stage2_contact = ""
        self._last_stage2_contact_time = 0

        self._last_base_info = dict()

        self._multi_outline_bg = None

        # no one should share a CPU serial with RadarBox, so always create fake cpuinfo;
        # also identify if we would use the thermal hack for RB and Ultrafeeder
        self._d.env_by_tags("rbthermalhack").value = "/sys/class/thermal" if create_fake_info() else ""

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
            ["radarplane", "RadarPlane", "https://radarplane.com/", ["https://radarplane.com/feed"]],
            ["adsbfi", "adsb.fi", "https://globe.adsb.fi/", ["https://api.adsb.fi/v1/myip"]],
            ["adsbx", "ADSBExchange", "https://globe.adsbexchange.com/", ["https://www.adsbexchange.com/myip/"]],
            ["hpradar", "HPRadar", "https://skylink.hpradar.com/", [""]],
            ["alive", "airplanes.live", "https://globe.airplanes.live/", ["https://airplanes.live/myfeed/"]],
            ["flightradar", "flightradar24", "https://www.flightradar24.com/", ["/fr24STG2IDX"]],
            ["planewatch", "Plane.watch", "https:/plane.watch/desktop.html", [""]],
            ["flightaware", "FlightAware", "https://www.flightaware.com/live/map", ["/fa-statusSTG2IDX/"]],
            ["radarbox", "RadarBox", "https://www.radarbox.com/coverage-map", ["https://www.radarbox.com/stations/<FEEDER_RADARBOX_SN>"]],
            ["planefinder", "PlaneFinder", "https://planefinder.net/", ["/planefinder-statSTG2IDX"]],
            ["adsbhub", "ADSBHub", "https://www.adsbhub.org/coverage.php", [""]],
            ["opensky", "OpenSky", "https://opensky-network.org/network/explorer", ["https://opensky-network.org/receiver-profile?s=<FEEDER_OPENSKY_SERIAL>"]],
            ["radarvirtuel", "RadarVirtuel", "https://www.radarvirtuel.com/", [""]],
            ["1090uk", "1090MHz UK", "https://1090mhz.uk", ["https://www.1090mhz.uk/mystatus.php?key=<FEEDER_1090UK_API_KEY>"]],
        ]
        self.last_aggregator_debug_print = None
        self.microfeeder_setting_tags = (
            "site_name", "lat", "lon", "alt", "tz", "mf_version",
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
            "uat978--is_enabled",
        )

        self._routemanager.add_proxy_routes(self._d.proxy_routes)
        self.app.add_url_rule("/hotspot_test", "hotspot_test", self.hotspot_test)
        self.app.add_url_rule("/restarting", "restarting", self.restarting)
        self.app.add_url_rule("/restart", "restart", self.restart, methods=["GET", "POST"])
        self.app.add_url_rule("/waiting", "waiting", self.waiting)
        self.app.add_url_rule("/stream-log", "stream_log", self.stream_log)
        self.app.add_url_rule("/running", "running", self.running)
        self.app.add_url_rule("/backup", "backup", self.backup)
        self.app.add_url_rule("/backupexecutefull", "backupexecutefull", self.backup_execute_full)
        self.app.add_url_rule("/backupexecutegraphs", "backupexecutegraphs", self.backup_execute_graphs)
        self.app.add_url_rule("/backupexecuteconfig", "backupexecuteconfig", self.backup_execute_config)
        self.app.add_url_rule("/restore", "restore", self.restore, methods=["GET", "POST"])
        self.app.add_url_rule("/executerestore", "executerestore", self.executerestore, methods=["GET", "POST"])
        self.app.add_url_rule("/sdr_setup", "sdr_setup", self.sdr_setup, methods=["GET", "POST"])
        self.app.add_url_rule("/visualization", "visualization", self.visualization, methods=["GET", "POST"])
        self.app.add_url_rule("/expert", "expert", self.expert, methods=["GET", "POST"])
        self.app.add_url_rule("/systemmgmt", "systemmgmt", self.systemmgmt, methods=["GET", "POST"])
        self.app.add_url_rule("/aggregators", "aggregators", self.aggregators, methods=["GET", "POST"])
        self.app.add_url_rule("/", "director", self.director, methods=["GET", "POST"])
        self.app.add_url_rule("/index", "index", self.index)
        self.app.add_url_rule("/info", "info", self.info)
        self.app.add_url_rule("/support", "support", self.support, methods=["GET", "POST"])
        self.app.add_url_rule("/setup", "setup", self.setup, methods=["GET", "POST"])
        self.app.add_url_rule("/stage2", "stage2", self.stage2, methods=["GET", "POST"])
        self.app.add_url_rule("/update", "update", self.update, methods=["POST"])
        self.app.add_url_rule("/sdplay_license", "sdrplay_license", self.sdrplay_license, methods=["GET", "POST"])
        self.app.add_url_rule("/api/ip_info", "ip_info", self.ip_info)
        self.app.add_url_rule("/api/sdr_info", "sdr_info", self.sdr_info)
        self.app.add_url_rule("/api/base_info", "base_info", self.base_info)
        self.app.add_url_rule("/api/stage2_info", "stage2_info", self.stage2_info)
        self.app.add_url_rule("/api/stage2_stats", "stage2_stats", self.stage2_stats)
        self.app.add_url_rule("/api/micro_settings", "micro_settings", self.micro_settings)
        self.app.add_url_rule("/api/check_remote_feeder/<ip>", "check_remote_feeder", self.check_remote_feeder)
        self.app.add_url_rule(f"/api/status/<agg>", "beast", self.agg_status)
        self.app.add_url_rule(f"/api/status/<agg>/<idx>", "beast", self.agg_status)
        self.app.add_url_rule("/api/stage2_connection", "stage2_connection", self.stage2_connection)
        self.app.add_url_rule("/api/get_temperatures.json", "temperatures", self.temperatures)
        # fmt: on
        self.update_boardname()
        self.update_version()
        self.update_meminfo()
        self.update_journal_state()

        # now all the envs are loaded and reconciled with the data on file - which means we should
        # actually write out the potentially updated values (e.g. when plain values were converted
        # to lists)
        with config_lock:
            write_values_to_config_json(self._d.envs, reason="Startup")

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
                    prod = ""
                    manufacturer = ""
                    try:
                        prod = subprocess.run(
                            "dmidecode -s system-product-name",
                            shell=True,
                            capture_output=True,
                            text=True,
                        )
                        manufacturer = subprocess.run(
                            "dmidecode -s system-manufacturer",
                            shell=True,
                            capture_output=True,
                            text=True,
                        )
                    except:
                        pass
                    if prod or manufacturer:
                        board = f"Native on {manufacturer.stdout.strip()} {prod.stdout.strip()} {platform.machine()} system"
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

    def update_meminfo(self):
        self._memtotal = 0
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        self._memtotal = make_int(line.split()[1])
                        break
        except:
            pass

    def update_journal_state(self):
        # with no config setting or an 'auto' setting, the journal is persistent IFF /var/log/journal exists
        self._persistent_journal = pathlib.Path("/var/log/journal").exists()
        # read journald.conf line by line and check if we override the default
        try:
            result = subprocess.run(
                "systemd-analyze cat-config systemd/journald.conf", shell=True, capture_output=True, timeout=2.0
            )
            config = result.stdout.decode("utf-8")
        except:
            config = "Storage=auto"
        for line in config:
            if line.startswith("Storage=volatile"):
                self._persistent_journal = False
                break

    def pack_im(self) -> str:
        image = {
            "in": self._d.env_by_tags("image_name").value,
            "bn": self._d.env_by_tags("board_name").value,
            "bv": self._d.env_by_tags("base_version").value,
            "cv": self._d.settings,
        }
        if self._d.env_by_tags("initial_version").value == "":
            if pathlib.Path("/opt/adsb/initial_install").exists():
                pathlib.Path("/opt/adsb/initial_install").unlink()
                image["iv"] = "1"
            self._d.env_by_tags("initial_version").value == self._d.env_by_tags("base_version").value
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
        def update_dns():
            dns_state = self._system.check_dns()
            self._d.env_by_tags("dns_state").value = dns_state
            if not dns_state:
                print_err("we appear to have lost DNS")

        threading.Thread(target=update_dns).start()

    def write_envfile(self):
        write_values_to_env_file(self._d.envs_for_envfile)

    def setup_ultrafeeder_args(self):
        # set all of the ultrafeeder config data up
        for i in [0] + self.micro_indices():
            print_err(f"ultrafeeder_config {i}", level=2)
            if i >= len(self._d.ultrafeeder):
                self._d.ultrafeeder.append(UltrafeederConfig(data=self._d, micro=i))
            self._d.env_by_tags("ultrafeeder_config").list_set(i, self._d.ultrafeeder[i].generate())

    def setup_app_ports(self):
        if not self._d.is_enabled("app_init_done"):
            # ok, we don't have them explicitly set, so let's set them up
            # with the app defaults
            self._d.env_by_tags("webport").value = 1099
            self._d.env_by_tags("tar1090port").value = 1090
            self._d.env_by_tags("uatport").value = 1091
            self._d.env_by_tags("piamapport").value = 1092
            self._d.env_by_tags("piastatport").value = 1093
            self._d.env_by_tags("dazzleport").value = 1094

            self._d.env_by_tags("app_init_done").value = True

    def onlyAlphaNumDash(self, name):
        new_name = "".join(c for c in name if c.isalnum() or c == "-")
        new_name = new_name.strip("-")[:63]
        return new_name

    def set_hostname(self, site_name: str):
        os_flag_file = self._d.data_path / "os.adsb.feeder.image"
        if not os_flag_file.exists() or not site_name:
            return
        # create a valid hostname from the site name and set it up as mDNS alias
        # initially we only allowed alpha-numeric characters, but after fixing an
        # error in the service file, we now can allow dash (or hyphen) as well.
        host_name = self.onlyAlphaNumDash(site_name)

        def start_mdns():
            subprocess.run(["/usr/bin/bash", "/opt/adsb/scripts/mdns-alias-setup.sh", f"{host_name}"])
            subprocess.run(["/usr/bin/hostnamectl", "hostname", f"{host_name}"])

        if not host_name or self._current_site_name == site_name:
            return

        self._current_site_name = site_name
        # print_err(f"set_hostname {site_name} {self._current_site_name}")

        thread = threading.Thread(target=start_mdns)
        thread.start()

    def run(self, no_server=False):
        debug = os.environ.get("ADSBIM_DEBUG") is not None

        # hopefully very temporary hack to deal with a broken container that
        # doesn't run on Raspberry Pi 5 boards
        board = self._d.env_by_tags("board_name").value
        if board.startswith("Raspberry Pi 5"):
            self._d.env_by_tags(["container", "planefinder"]).value = (
                "ghcr.io/sdr-enthusiasts/docker-planefinder:5.0.161_arm64"
            )

        self.handle_implied_settings()
        self.write_envfile()

        # if all the user wanted is to make sure the housekeeping tasks are completed,
        # don't start the flask app and exit instead
        if no_server:
            signal.raise_signal(signal.SIGTERM)
            return

        # if using gpsd, try to update the location
        if self._d.is_enabled("use_gpsd"):
            self.get_lat_lon_alt()

        self._every_minute = Background(60, self.every_minute)
        # every_minute stuff is required to initialize some values, run it synchronously
        self.every_minute()

        if self._d.is_enabled("stage2"):
            # let's make sure we tell the micro feeders every ten minutes that
            # the stage2 is around, looking at them
            threading.Thread(target=self.stage2_checks).start()
            self._stage2_checks = Background(600, self.stage2_checks)

        self.app.run(
            host="0.0.0.0",
            port=int(self._d.env_by_tags("webport").value),
            debug=debug,
        )

    def set_tz(self, timezone):
        # Set it as datetimectl too
        try:
            print_err(f"calling timedatectl set-timezone {timezone}")
            subprocess.run(["timedatectl", "set-timezone", f"{timezone}"], check=True)
            # Add to .env only if timedatectl has succeeded
            self._d.env("FEEDER_TZ").list_set(0, timezone)
        except subprocess.SubprocessError:
            print_err(f"failed to set up timezone ({timezone}), defaulting to UTC")
            timezone = "UTC"
            print_err(f"calling timedatectl set-timezone {timezone}")
            subprocess.run(["timedatectl", "set-timezone", f"{timezone}"])
            self._d.env("FEEDER_TZ").list_set(0, timezone)

    def push_multi_outline(self) -> None:
        if not self._d.is_enabled("stage2"):
            return

        def push_mo():
            subprocess.run(
                ["bash", "/opt/adsb/push_multioutline.sh", f"{self._d.env_by_tags('num_micro_sites').value}"]
            )

        thread = threading.Thread(
            target=push_mo,
        )
        thread.start()

    def stage2_checks(self):
        for i in self.micro_indices():
            if self._d.env_by_tags("mf_version").list_get(i) != "not an adsb.im feeder":
                self.get_base_info(i)

    def hotspot_test(self):
        return render_template("hotspot.html", version="123", comment="comment", ssids=list(range(20)))

    def restarting(self):
        return render_template("restarting.html")

    def restart(self):
        self._system._restart.wait_restart_done(timeout=5)
        return self._system._restart.state

    def running(self):
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

        def graphs1090_writeback(uf_path, microIndex):
            # the rrd file will be updated via move after collectd is done writing it out
            # so killing collectd and waiting for the mtime to change is enough

            rrd_file = uf_path / "graphs1090/rrd/localhost.tar.gz"

            def timeSinceWrite(rrd_file):
                # because of the way the file gets updated, it will briefly not exist
                # when the new copy is moved in place, which will make os.stat unhappy
                try:
                    return time.time() - os.stat(rrd_file).st_mtime
                except:
                    return time.time() - 0  # fallback to long time since last write

            context = f"graphs1090 writeback {microIndex}"

            t = timeSinceWrite(rrd_file)
            if t < 120:
                print_err(f"{context}: not needed, timeSinceWrite: {round(t)}s")
                return

            print_err(f"{context}: requesting")
            try:
                if microIndex == 0:
                    uf_container = "ultrafeeder"
                else:
                    uf_container = f"uf_{microIndex}"
                subprocess.call(
                    f"docker exec {uf_container} pkill collectd",
                    timeout=5.0,
                    shell=True,
                )
            except:
                print_err("failed to kill collectd - just using the localhost.tar.gz that's already there")
                pass
            else:
                count = 0
                increment = 0.1
                # give up after 30 seconds
                while count < 30:
                    count += increment
                    sleep(increment)
                    if timeSinceWrite(rrd_file) < 120:
                        print_err(f"{context}: success")
                        break

        fdOut, fdIn = os.pipe()
        pipeOut = os.fdopen(fdOut, "rb")
        pipeIn = os.fdopen(fdIn, "wb")

        def zip2fobj(fobj, include_graphs, include_heatmap):
            try:
                with fobj as file, zipfile.ZipFile(file, mode="w") as backup_zip:
                    backup_zip.write(adsb_path / "config.json", arcname="config.json")

                    for microIndex in [0] + self.micro_indices():
                        if microIndex == 0:
                            uf_path = adsb_path / "ultrafeeder"
                        else:
                            uf_path = adsb_path / "ultrafeeder" / self._d.env_by_tags("mf_ip").list_get(microIndex)

                        gh_path = uf_path / "globe_history"
                        if include_heatmap and gh_path.is_dir():
                            for subpath in gh_path.iterdir():
                                pstring = str(subpath)
                                if subpath.name == "internal_state":
                                    continue
                                if subpath.name == "tar1090-update":
                                    continue

                                print_err(f"add: {pstring}")
                                for f in subpath.rglob("*"):
                                    backup_zip.write(f, arcname=f.relative_to(adsb_path))

                        # do graphs after heatmap data as this can pause a couple seconds in graphs1090_writeback
                        # due to buffers, the download won't be recognized by the browsers until some data is added to the zipfile
                        if include_graphs:
                            graphs1090_writeback(uf_path, microIndex)
                            graphs_path = uf_path / "graphs1090/rrd/localhost.tar.gz"
                            backup_zip.write(graphs_path, arcname=graphs_path.relative_to(adsb_path))

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
        if self._d.is_enabled("stage2"):
            site_name = f"stage2-{site_name}"
        now = datetime.now().replace(microsecond=0).isoformat().replace(":", "-")
        download_name = f"adsb-feeder-config-{site_name}-{now}.backup"
        try:
            return send_file(
                pipeOut,
                mimetype="application/zip",
                as_attachment=True,
                download_name=download_name,
            )
        except TypeError:
            return send_file(
                pipeOut,
                mimetype="application/zip",
                as_attachment=True,
                attachment_filename=download_name,
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
            if file.filename.endswith(".zip") or file.filename.endswith(".backup"):
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
            return self.restore_get(request)
        if request.method == "POST":
            form = deepcopy(request.form)

            def do_restore_post():
                self.restore_post(form)

            self._system._restart.bg_run(func=do_restore_post)
            return render_template("/restarting.html")

    def restore_get(self, request):
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
                if not str(os.path.normpath(os.path.join(restore_path, name))).startswith(str(restore_path)):
                    print_err(f"restore skipped for path breakout name: {name}")
                    continue
                # only accept the .env file and config.json and files for ultrafeeder
                if name != ".env" and name != "config.json" and not name.startswith("ultrafeeder/"):
                    continue
                restore_zip.extract(name, restore_path)
                restored_files.append(name)
        # now check which ones are different from the installed versions
        changed: List[str] = []
        unchanged: List[str] = []
        saw_globe_history = False
        saw_graphs = False
        uf_paths = set()
        for name in restored_files:
            if name.startswith("ultrafeeder/"):
                parts = name.split("/")
                if len(parts) < 3:
                    continue
                uf_paths.add(parts[0] + "/" + parts[1] + "/")
            elif os.path.isfile(adsb_path / name):
                if filecmp.cmp(adsb_path / name, restore_path / name):
                    print_err(f"{name} is unchanged")
                    unchanged.append(name)
                else:
                    print_err(f"{name} is different from current version")
                    changed.append(name)

        changed += list(uf_paths)

        print_err(f"offering the usr to restore the changed files: {changed}")
        return render_template("/restoreexecute.html", changed=changed, unchanged=unchanged)

    def restore_post(self, form):
        # they have selected the files to restore
        print_err("restoring the files the user selected")
        adsb_path = pathlib.Path("/opt/adsb/config")
        (adsb_path / "ultrafeeder").mkdir(mode=0o755, exist_ok=True)
        restore_path = adsb_path / "restore"
        restore_path.mkdir(mode=0o755, exist_ok=True)
        try:
            subprocess.call("/opt/adsb/docker-compose-adsb down -t 20", timeout=40.0, shell=True)
        except subprocess.TimeoutExpired:
            print_err("timeout expired stopping docker... trying to continue...")
        for name, value in form.items():
            if value == "1":
                print_err(f"restoring {name}")
                dest = adsb_path / name
                if dest.is_file():
                    shutil.move(dest, adsb_path / (name + ".dist"))
                elif dest.is_dir():
                    shutil.rmtree(dest, ignore_errors=True)

                if name != "config.json" and name != ".env":
                    shutil.move(restore_path / name, dest)
                    continue

                with config_lock:
                    shutil.move(restore_path / name, dest)

                    if name == ".env":
                        if "config.json" in form.keys():
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
                        write_values_to_config_json(values, reason="execute_restore from .env")

        # clean up the restore path
        restore_path = pathlib.Path("/opt/adsb/config/restore")
        shutil.rmtree(restore_path, ignore_errors=True)

        # now that everything has been moved into place we need to read all the values from config.json
        # of course we do not want to pull values marked as norestore
        print_err("finished restoring files, syncing the configuration")

        for e in self._d._env:
            e._reconcile(e._value, pull=("norestore" not in e.tags))
            print_err(f"{'wrote out' if 'norestore' in e.tags else 'read in'} {e.name}: {e.value}")

        # finally make sure that a couple of the key settings are up to date
        self.update_boardname()
        self.update_version()

        self.set_tz(self._d.env("FEEDER_TZ").list_get(0))

        # make sure we are connected to the right Zerotier network
        zt_network = self._d.env_by_tags("zerotierid").value
        if zt_network and len(zt_network) == 16:  # that's the length of a valid network id
            try:
                subprocess.call(
                    ["zerotier-cli", "join", f"{zt_network}"],
                    timeout=30.0,
                )
            except subprocess.TimeoutExpired:
                print_err("timeout expired joining Zerotier network... trying to continue...")

        self.handle_implied_settings()
        self.write_envfile()

        try:
            subprocess.call("/opt/adsb/docker-compose-start", timeout=180.0, shell=True)
        except subprocess.TimeoutExpired:
            print_err("timeout expired re-starting docker... trying to continue...")

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

    def ip_info(self):
        ip, status = self._system.check_ip()
        if status == 200:
            self._d.env_by_tags(["feeder_ip"]).value = ip
            self._d.env_by_tags(["mf_ip"]).list_set(0, ip)
        jsonString = json.dumps(
            {
                "feeder_ip": ip,
            },
            indent=2,
        )
        return Response(jsonString, mimetype="application/json")

    def sdr_info(self):
        # get our guess for the right SDR to frequency mapping
        # and then update with the actual settings
        serial_guess: Dict[str, str] = self._sdrdevices.addresses_per_frequency
        print_err(f"serial guess: {serial_guess}")
        serials: Dict[str, str] = {f: self._d.env_by_tags(f"{f}serial").value for f in [978, 1090]}
        used_serials = {self._d.env_by_tags(f).value for f in self._sdrdevices.purposes()}
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

    def stage2_info(self):
        if not self._d.is_enabled("stage2"):
            print_err("/api/stage2_info called but stage2 is not enabled")
            return self.base_info()
        # for a stage2 we return the base info for each of the micro feeders
        info_array = []
        for i in self.micro_indices():
            uat_capable = False
            if self._d.env_by_tags("mf_version").list_get(i) != "not an adsb.im feeder":
                self.get_base_info(i)
                uat_capable = self._d.env_by_tags("978url").list_get(i) != ""

            info_array.append(
                {
                    "mf_ip": self._d.env_by_tags("mf_ip").list_get(i),
                    "mf_version": self._d.env_by_tags("mf_version").list_get(i),
                    "lat": self._d.env_by_tags("lat").list_get(i),
                    "lon": self._d.env_by_tags("lon").list_get(i),
                    "alt": self._d.env_by_tags("alt").list_get(i),
                    "uat_capable": uat_capable,
                    "brofm_capable": (
                        self._d.list_is_enabled("mf_brofm_capable", idx=i)
                        or self._d.list_is_enabled("mf_brofm", idx=i)
                    ),
                    "brofm_enabled": self._d.list_is_enabled("mf_brofm", idx=i),
                }
            )
        return Response(json.dumps(info_array), mimetype="application/json")

    def get_lat_lon_alt(self):
        # get lat, lon, alt of an integrated or micro feeder either from gps data
        # or from the env variables
        lat = self._d.env_by_tags("lat").list_get(0)
        lon = self._d.env_by_tags("lon").list_get(0)
        alt = self._d.env_by_tags("alt").list_get(0)
        gps_json = pathlib.Path("/run/adsb-feeder-ultrafeeder/readsb/gpsd.json")
        if self._d.is_enabled("use_gpsd") and gps_json.exists():
            with gps_json.open() as f:
                gps = json.load(f)
                if "lat" in gps and "lon" in gps:
                    lat = gps["lat"]
                    lon = gps["lon"]
                    # normalize to no more than 5 digits after the decimal point for lat/lon
                    lat = f"{float(lat):.5f}"
                    lon = f"{float(lon):.5f}"
                    self._d.env_by_tags("lat").list_set(0, lat)
                    self._d.env_by_tags("lon").list_set(0, lon)
                if "alt" in gps:
                    alt = gps["alt"]
                    # normalize to whole meters for alt
                    alt = f"{float(alt):.0f}"
                    self._d.env_by_tags("alt").list_set(0, alt)
        return lat, lon, alt

    def base_info(self):
        listener = request.remote_addr
        tm = int(time.time())
        print_err(f"access to base_info from {listener}", level=8)
        self._last_stage2_contact = listener
        self._last_stage2_contact_time = tm
        lat, lon, alt = self.get_lat_lon_alt()
        rtlsdr_at_port = 0
        if self._d.env_by_tags("readsb_device_type").value == "rtlsdr":
            if self._d.is_enabled("stage2_nano"):
                rtlsdr_at_port = self._d.env_by_tags("nanotar1090portadjusted").value
            else:
                rtlsdr_at_port = self._d.env_by_tags("tar1090port").value
        response = make_response(
            json.dumps(
                {
                    "name": self._d.env_by_tags("site_name").list_get(0),
                    "lat": lat,
                    "lng": lon,  # include both spellings for backwards compatibility
                    "lon": lon,
                    "alt": alt,
                    "tz": self._d.env_by_tags("tz").list_get(0),
                    "version": self._d.env_by_tags("base_version").value,
                    "airspy_at_port": (self._d.env_by_tags("airspyport").value if self._d.is_enabled("airspy") else 0),
                    "rtlsdr_at_port": rtlsdr_at_port,
                    "dump978_at_port": (
                        self._d.env_by_tags("uatport").value if self._d.list_is_enabled(["uat978"], 0) else 0
                    ),
                    "brofm_capable": (self._d.env_by_tags("aggregator_choice").value in ["micro", "nano"]),
                }
            )
        )
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def stage2_stats(self):
        ret = []
        if self._d.is_enabled("stage2"):
            for i in [0] + self.micro_indices():
                ip = self._d.env_by_tags("mf_ip").list_get(i)
                ip, triplet = mf_get_ip_and_triplet(ip)
                suffix = f"uf_{i}" if i != 0 else "ultrafeeder"
                try:
                    with open(f"/run/adsb-feeder-{suffix}/readsb/stats.prom") as f:
                        pct = 0
                        secs = 0
                        found = 0
                        for line in f:
                            if "position_count_total" in line:
                                pps = int(int(line.split()[1]) / 60)
                                found |= 1
                            if "readsb_messages_valid" in line:
                                mps = int(int(line.split()[1]) / 60)
                                found |= 4
                            if ip in line:
                                secs = int(line.split()[1])
                                found |= 2
                            if found == 7:
                                break
                        ret.append({"pps": pps, "mps": mps, "secs": secs})
                except:
                    ret.append({"pps": 0, "mps": 0, "secs": 0})
        return Response(json.dumps(ret), mimetype="application/json")

    def stage2_connection(self):
        if not self._d.env_by_tags("aggregator_choice").value in ["micro", "nano"] or self._last_stage2_contact == "":
            return Response(json.dumps({"stage2_connected": "never"}), mimetype="application/json")
        now = int(time.time())
        last = self._last_stage2_contact_time
        since = now - last
        hrs, min = divmod(since // 60, 60)
        if hrs > 0:
            time_since = "more than an hour"
        elif min > 15:
            time_since = f"{min} minutes"
        else:
            time_since = "recent"
        return Response(
            json.dumps(
                {
                    "stage2_connected": time_since,
                    "address": self._last_stage2_contact,
                }
            ),
            mimetype="application/json",
        )

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
        # ensure forward/backward compatibility with lng/lon change
        microsettings["lng"] = microsettings["lon"]
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
                agg,
                idx,
                self._d,
                f"http://127.0.0.1:{self._d.env_by_tags('webport').value}",
            )

        res = (
            {
                "beast": status.beast,
                "mlat": status.mlat,
            }
        )

        if agg == "adsbx":
            res["adsbxfeederid"] = self._d.env_by_tags("adsbxfeederid").list_get(idx)
        elif agg == "adsblol":
            res["adsblollink"] = self._d.env_by_tags("adsblol_link").list_get(idx),
        elif agg == "alive":
            res["alivemaplink"] = self._d.env_by_tags("alivemaplink").list_get(idx),

        return json.dumps(res)

    @check_restart_lock
    def sdr_setup(self):
        if request.method == "POST":
            return self.update()
        return render_template("sdr_setup.html")

    def visualization(self):
        if request.method == "POST":
            return self.update()

        # is this a stage2 site and you are looking at an individual micro feeder,
        # or is this a regular feeder?
        # m=0 indicates we are looking at an integrated/micro feeder or at the stage 2 local aggregator
        # m>0 indicates we are looking at a micro-proxy
        if self._d.is_enabled("stage2"):
            if request.args.get("m"):
                m = make_int(request.args.get("m"))
            else:
                m = 0
            site = self._d.env_by_tags("site_name").list_get(m)
            print_err("setting up visualization on a stage 2 system for site {site} (m={m})")
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
        if idx == 0:
            globe_history = "globe_history"
        else:
            globe_history = f"{self._d.env_by_tags('mf_ip').list_get(idx)}/globe_history"

        rangedirs = self._d.config_path / "ultrafeeder" / globe_history / "internal_state" / "rangeDirs.gz"
        if not rangedirs.exists() and rangedirs.is_file():
            print_err(f"can't seem to find the range outline file {rangedirs}")
            return

        # try to stop the Ultrafeeder container, then remove the range outline, then restart everything
        container = "ultrafeeder" if idx == 0 else f"uf_{idx}"
        try:
            subprocess.call(
                f"/opt/adsb/docker-compose-adsb down {container}",
                timeout=40.0,
                shell=True,
            )
        except subprocess.TimeoutExpired:
            print_err("timeout expired stopping ultrafeeder... trying to continue anyway...")
        rangedirs.unlink(missing_ok=True)
        print_err(f"removed the range outline at path {rangedirs}")
        try:
            subprocess.call("/opt/adsb/docker-compose-start", timeout=180.0, shell=True)
        except subprocess.TimeoutExpired:
            print_err("timeout expired re-starting docker... trying to continue...")

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

    def unique_site_name(self, name, idx=-1):
        # make sure that a site name is unique - if the idx is given that's
        # the current value and excluded from the check
        existing_names = self._d.env_by_tags("site_name")
        names = [existing_names.list_get(n) for n in range(0, len(existing_names.value)) if n != idx]
        while name in names:
            name += "_"
        return name

    def get_base_info(self, n, do_import=False):
        ip = self._d.env_by_tags("mf_ip").list_get(n)
        port = self._d.env_by_tags("mf_port").list_get(n)
        if not port:
            port = "80"
        ip, triplet = mf_get_ip_and_triplet(ip)

        print_err(f"getting info from {ip}:{port} with do_import={do_import}", level=8)
        timeout = 2.0
        # try:
        if do_import:
            micro_settings, status = generic_get_json(f"http://{ip}:{port}/api/micro_settings", timeout=timeout)
            print_err(f"micro_settings API on {ip}:{port}: {status}, {micro_settings}")
            if status != 200 or micro_settings == None:
                # maybe we're running on 1099?
                port = "1099"
                micro_settings, status = generic_get_json(f"http://{ip}:{port}/api/micro_settings", timeout=timeout)
                print_err(f"micro_settings API on {ip}:{port}: {status}, {micro_settings}")

            if status == 200 and micro_settings != None:
                for key, value in micro_settings.items():
                    # when getting values from a microfeeder older than v2.1.3
                    if key == "lng":
                        key = "lon"
                    if key not in self.microfeeder_setting_tags:
                        continue
                    tags = key.split("--")
                    print_err(f"setting env for {tags} to {value}", level=4)
                    e = self._d.env_by_tags(tags)
                    if e:
                        e.list_set(n, value)

        base_info, status = generic_get_json(f"http://{ip}:{port}/api/base_info", timeout=timeout)
        if (status != 200 or base_info == None) and port == "80":
            # maybe we're running on 1099?
            port = "1099"
            base_info, status = generic_get_json(f"http://{ip}:{port}/api/base_info", timeout=timeout)
        if status == 200 and base_info != None:

            base_info_string = json.dumps(base_info)

            if self._last_base_info.get(ip) != base_info_string:
                self._last_base_info[ip] = base_info_string
                print_err(f"got {base_info} for {ip}")

            if do_import or not self._d.env_by_tags("site_name").list_get(n):
                # only accept the remote name if this is our initial import
                # after that the user may have overwritten it
                self._d.env_by_tags("site_name").list_set(n, self.unique_site_name(base_info["name"], n))
            self._d.env_by_tags("lat").list_set(n, base_info["lat"])
            # deal with backwards compatibility
            lon = base_info.get("lon", None)
            if lon is None:
                lon = base_info.get("lng", "")
            self._d.env_by_tags("lon").list_set(n, lon)
            self._d.env_by_tags("alt").list_set(n, base_info["alt"])
            self._d.env_by_tags("tz").list_set(n, base_info["tz"])
            self._d.env_by_tags("mf_version").list_set(n, base_info["version"])
            self._d.env_by_tags("mf_port").list_set(n, port)

            aap = base_info.get("airspy_at_port")
            rap = base_info.get("rtlsdr_at_port")
            dap = base_info.get("dump978_at_port")
            airspyurl = ""
            rtlsdrurl = ""
            dump978url = ""

            if aap and aap != 0:
                airspyurl = f"http://{ip}:{aap}"
            if rap and rap != 0:
                rtlsdrurl = f"http://{ip}:{rap}"
            if dap and dap != 0:
                dump978url = f"http://{ip}:{dap}/skyaware978"

            self._d.env_by_tags("airspyurl").list_set(n, airspyurl)
            self._d.env_by_tags("rtlsdrurl").list_set(n, rtlsdrurl)
            self._d.env_by_tags("978url").list_set(n, dump978url)

            self._d.env_by_tags("mf_brofm_capable").list_set(n, bool(base_info.get("brofm_capable")))

            return True
        #    except:
        #        pass
        print_err(f"failed to get base_info from micro feeder {n}")
        return False

    def check_remote_feeder(self, ip):
        print_err(f"check_remote_feeder({ip})")
        ip, triplet = mf_get_ip_and_triplet(ip)
        json_dict = {}
        for port in ["80", "1099"]:
            url = f"http://{ip}:{port}/api/base_info"
            print_err(f"checking remote feeder {url}")
            try:
                response = requests.get(url, timeout=5.0)
                print_err(f"response code: {response.status_code}")
                json_dict = response.json()
                print_err(f"json_dict: {type(json_dict)} {json_dict}")
            except:
                print_err(f"failed to check base_info from remote feeder {ip}:{port}")
            else:
                if response.status_code == 200:
                    # yay, this is an adsb.im feeder
                    # is it new enough to have the setting transfer?
                    url = f"http://{ip}:{port}/api/micro_settings"
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
                    # does it support beast reduce optimized for mlat (brofm)?
                    json_dict["brofm_capable"] = bool(json_dict.get("brofm_capable"))

                # now return the json_dict which will give the caller all the relevant data
                # including whether this is a v2 or not
                return make_response(json.dumps(json_dict), 200)

        # ok, it's not a recent adsb.im version, it could still be a feeder
        uf = self._d.env_by_tags(["ultrafeeder", "container"]).value
        cmd = [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/usr/local/bin/readsb",
            f"{uf}",
            "--net",
            "--net-connector",
            f"{triplet}",
            "--quiet",
            "--auto-exit=2",
        ]
        print_err(f"running: {cmd}")
        try:
            response = subprocess.run(
                cmd,
                timeout=30.0,
                capture_output=True,
            )
            output = response.stderr.decode("utf-8")
        except:
            print_err("failed to use readsb in ultrafeeder container to check on remote feeder status")
            return make_response(json.dumps({"status": "fail"}), 200)
        if not re.search("input: Connection established", output):
            print_err(f"can't connect to beast_output on remote feeder: {output}")
            return make_response(json.dumps({"status": "fail"}), 200)
        return make_response(json.dumps({"status": "ok"}), 200)

    def import_graphs_and_history_from_remote(self, ip, port):
        print_err(f"importing graphs and history from {ip}")
        # first make sure that there isn't any old data that needs to be moved
        # out of the way
        if pathlib.Path(self._d.config_path / "ultrafeeder" / ip).exists():
            now = datetime.now().replace(microsecond=0).isoformat().replace(":", "-")
            shutil.move(
                self._d.config_path / "ultrafeeder" / ip,
                self._d.config_path / "ultrafeeder" / f"{ip}-{now}",
            )

        url = f"http://{ip}:{port}/backupexecutefull"
        # make tmpfile
        fd, tmpfile = tempfile.mkstemp(dir=self._d.config_path / "ultrafeeder")
        os.close(fd)

        # stream writing to a file with requests library is a pain so just use curl
        try:
            subprocess.run(
                ["curl", "-o", f"{tmpfile}", f"{url}"],
                check=True,
            )

            with zipfile.ZipFile(tmpfile) as zf:
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
        except:
            print_err(f"ERROR when importing graphs and history from {ip}")
        finally:
            os.remove(tmpfile)

    def setup_new_micro_site(
        self,
        key,
        uat,
        is_adsbim,
        brofm,
        do_import=False,
        do_restore=False,
        micro_data={},
    ):
        # the key here can be a readsb net connector triplet in the form ip,port,protocol
        # usually it's just the ip
        if key in {self._d.env_by_tags("mf_ip").list_get(i) for i in self.micro_indices()}:
            print_err(f"IP address {key} already listed as a micro site")
            return (False, f"IP address {key} already listed as a micro site")
        print_err(f"setting up a new micro site at {key} do_import={do_import} do_restore={do_restore}")
        n = self._d.env_by_tags("num_micro_sites").value

        # store the IP address so that get_base_info works
        # and assume port is 80 (get_base_info will fix that if it's wrong)
        self._d.env_by_tags("mf_ip").list_set(n + 1, key)
        self._d.env_by_tags("mf_port").list_set(n + 1, "80")
        self._d.env_by_tags("mf_brofm").list_set(n + 1, brofm)

        if not is_adsbim:
            # well that's unfortunate
            # we might get asked to create a UI for this at some point. Not today, though
            print_err(f"Micro feeder at {key} is not an adsb.im feeder")
            n += 1
            self._d.env_by_tags("num_micro_sites").value = n
            self._d.env_by_tags("site_name").list_set(n, self.unique_site_name(micro_data.get("micro_site_name", "")))
            self._d.env_by_tags("lat").list_set(n, micro_data.get("micro_lat", ""))
            self._d.env_by_tags("lon").list_set(n, micro_data.get("micro_lon", ""))
            self._d.env_by_tags("alt").list_set(n, micro_data.get("micro_alt", ""))
            self._d.env_by_tags("tz").list_set(n, "UTC")
            self._d.env_by_tags("mf_version").list_set(n, "not an adsb.im feeder")
            self._d.env_by_tags(["uat978", "is_enabled"]).list_set(n, uat)
            return (True, "")

        # now let's see if we can get the data from the micro feeder
        if self.get_base_info(n + 1, do_import=do_import):
            print_err(f"added new micro site {self._d.env_by_tags('site_name').list_get(n + 1)} at {key}")
            n += 1
            self._d.env_by_tags("num_micro_sites").value = n
            if do_restore:
                port = self._d.env_by_tags("mf_port").list_get(n)
                print_err(f"attempting to restore graphs and history from {key}:{port}")
                self.import_graphs_and_history_from_remote(key, port)
        else:
            # oh well, remove the IP address
            self._d.env_by_tags("mf_ip").list_remove()
            return (False, "unable to get base info from micro feeder")

        self._d.env_by_tags(["uat978", "is_enabled"]).list_set(n, uat)
        return (True, "")

    def remove_micro_site(self, num):
        # carefully shift everything down
        print_err(f"removing micro site {num}")
        for t in self.microfeeder_setting_tags + (
            "mf_ip",
            "airspyurl",
            "1090signalurl",
            "978url",
            "978piaware",
            "replay978",
            "978host",
            "mf_brofm",
            "mf_brofm_capable",
            "ultrafeeder_config",
            "rb978host",
            "airspyurl",
            "rtlsdrurl",
            "978url",
        ):
            tags = t.split("--")
            e = self._d.env_by_tags(tags)
            if e and type(e._value) == list:
                print_err(f"shifting {e.name} down and deleting last element {e._value}")
                for i in range(num, self._d.env_by_tags("num_micro_sites").value):
                    e.list_set(i, e.list_get(i + 1))
                while len(e._value) > self._d.env_by_tags("num_micro_sites").value:
                    e.list_remove()
            else:
                print_err(f"couldn't find env list for {tags}")
        self._d.env_by_tags("num_micro_sites").value -= 1

    def edit_micro_site(self, num, site_name, ip, uat, brofm):
        print_err(
            f"editing micro site {num} from {self._d.env_by_tags('site_name').list_get(num)} at {self._d.env_by_tags('mf_ip').list_get(num)} to {site_name} at {ip}"
        )
        old_ip = self._d.env_by_tags("mf_ip").list_get(num)
        if old_ip != ip:
            if any([s in ip for s in ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "..", "$"]]):
                print_err(f"found suspicious characters in IP address {ip} - let's not use this in a command")
            else:
                data_dir = pathlib.Path("/opt/adsb/config/ultrafeeder")
                if (data_dir / f"{old_ip}").exists() and (data_dir / f"{old_ip}").is_dir():
                    # ok, as one would hope, there's an Ultrafeeder directory for the old IP
                    if (data_dir / f"{ip}").exists():
                        print_err(f"can't move micro feeder data directory to {data_dir/ip} - it's already in use")
                        return (
                            False,
                            f"can't move micro feeder data directory to {data_dir/ip} - it's already in use",
                        )
                    try:
                        subprocess.run(
                            f"/opt/adsb/docker-compose-adsb down uf_{num} -t 20",
                            shell=True,
                        )
                    except:
                        print_err(f"failed to stop micro feeder {num}")
                        return (False, f"failed to stop micro feeder {num}")
                    print_err(f"moving micro feeder data directory from {data_dir/old_ip} to {data_dir/ip}")
                    try:
                        os.rename(data_dir / f"{old_ip}", data_dir / f"{ip}")
                    except:
                        print_err(
                            f"failed to move micro feeder data directory from {data_dir/old_ip} to {data_dir/ip}"
                        )
                        return (
                            False,
                            f"failed to move micro feeder data directory from {data_dir/old_ip} to {data_dir/ip}",
                        )
                # ok, this seems to have worked, let's update the environment variable IP
                self._d.env_by_tags("mf_ip").list_set(num, ip)

        if site_name != self._d.env_by_tags("site_name").list_get(num):
            print_err(f"update site name from {self._d.env_by_tags('site_name').list_get(num)} to {site_name}")
            self._d.env_by_tags("site_name").list_set(num, self.unique_site_name(site_name))
        if uat != self._d.env_by_tags("uat978").list_get(num):
            print_err(f"update uat978 from {self._d.env_by_tags('uat978').list_get(num)} to {uat}")
            self._d.env_by_tags("uat978").list_set(num, uat)
            self.setup_or_disable_uat(num)

        self._d.env_by_tags("mf_brofm").list_set(num, brofm)
        return (True, "")

    def setRtlGain(self):
        def tryWriteFile(path, string):
            try:
                with open(path, "w") as file:
                    file.write(string)
            except:
                print_err(f'error writing "{string}" to {path}')

        if self._d.is_enabled("stage2_nano"):
            gaindir = pathlib.Path("/opt/adsb/config/nanofeeder/globe_history/autogain")
        else:
            gaindir = pathlib.Path("/opt/adsb/config/ultrafeeder/globe_history/autogain")
        try:
            gaindir.mkdir(exist_ok=True, parents=True)
        except:
            pass
        gain = self._d.env_by_tags(["gain"]).value

        # autogain is configured via the container env vars to be always enabled
        # so we can change gain on the fly without changing env vars
        # for manual gain the autogain script in the container can be asked to do nothing
        # by touching the suspend file
        if gain == "autogain":
            (gaindir / "suspend").unlink(missing_ok=True)
        else:
            (gaindir / "suspend").touch(exist_ok=True)

            # this file sets the gain on readsb start
            tryWriteFile(gaindir / "gain", f"{gain}\n")

            # this adjusts the gain while readsb is running
            tryWriteFile("/run/adsb-feeder-ultrafeeder/readsb/setGain", f"{gain}\n")

    def setup_or_disable_uat(self, sitenum):
        if sitenum and self._d.list_is_enabled(["uat978"], sitenum):
            # always get UAT from the readsb uat_replay
            self._d.env_by_tags("replay978").list_set(sitenum, "--net-uat-replay-port 30978")
            self._d.env_by_tags("978host").list_set(sitenum, f"uf_{sitenum}")
            self._d.env_by_tags("rb978host").list_set(sitenum, self._d.env_by_tags("mf_ip").list_get(sitenum))
            self._d.env_by_tags("978piaware").list_set(sitenum, "relay")
        else:
            self._d.env_by_tags("replay978").list_set(sitenum, "")
            self._d.env_by_tags("978host").list_set(sitenum, "")
            self._d.env_by_tags("rb978host").list_set(sitenum, "")
            self._d.env_by_tags("978piaware").list_set(sitenum, "")

    def handle_implied_settings(self):
        if self._d.env_by_tags("aggregator_choice").value in ["micro", "nano"]:
            ac_db = False
            self._d.env_by_tags(["mlathub_disable"]).value = True
        else:
            ac_db = True
            self._d.env_by_tags(["mlathub_disable"]).value = False

        if self._memtotal < 900000:
            ac_db = False
            # save 100 MB of memory for low memory setups

        self._d.env_by_tags(["tar1090_ac_db"]).value = ac_db

        # make sure the avahi alias service runs on an adsb.im image
        self.set_hostname(self._d.env_by_tags("site_name").list_get(0))

        stage2_nano = False

        if self._d.is_enabled("stage2") and (
            self._d.env_by_tags("1090serial").value or self._d.env_by_tags("978serial").value
        ):
            # this is special - the user has declared this a stage2 feeder, yet
            # appears to be setting up an SDR - let's force this to be treated as
            # nanofeeder

            self._d.env_by_tags("stage2_nano").value = True
            self._d.env_by_tags("nano_beast_port").value = "30035"
            self._d.env_by_tags("nano_beastreduce_port").value = "30036"
        else:
            self._d.env_by_tags("stage2_nano").value = False
            self._d.env_by_tags("nano_beast_port").value = "30005"
            self._d.env_by_tags("nano_beastreduce_port").value = "30006"

        for sitenum in [0] + self.micro_indices():

            # make sure use_route_api is populated with the default:
            self._d.env_by_tags("route_api").list_get(sitenum)

            # make sure the uuids are populated:
            if not self._d.env_by_tags("adsblol_uuid").list_get(sitenum):
                self._d.env_by_tags("adsblol_uuid").list_set(sitenum, str(uuid4()))
            if not self._d.env_by_tags("ultrafeeder_uuid").list_get(sitenum):
                self._d.env_by_tags("ultrafeeder_uuid").list_set(sitenum, str(uuid4()))

            for agg in [submit_key.replace("--submit", "") for submit_key in self._other_aggregators.keys()]:
                if self._d.env_by_tags([agg, "is_enabled"]).list_get(sitenum):
                    # disable other aggregators for the combined data of stage2
                    if sitenum == 0 and self._d.is_enabled("stage2"):
                        self._d.env_by_tags([agg, "is_enabled"]).list_set(sitenum, False)
                    # disable other aggregators if their key isn't set
                    if self._d.env_by_tags([agg, "key"]).list_get(sitenum) == "":
                        print_err(f"empty key, disabling: agg: {agg}, sitenum: {sitenum}")
                        self._d.env_by_tags([agg, "is_enabled"]).list_set(sitenum, False)

        # explicitely enable mlathub unless disabled
        self._d.env_by_tags(["mlathub_enable"]).value = not self._d.env_by_tags(["mlathub_disable"]).value

        if self._d.env_by_tags("aggregator_choice").value in ["micro", "nano"]:
            self._d.env_by_tags("beast-reduce-optimize-for-mlat").value = True
        else:
            self._d.env_by_tags("beast-reduce-optimize-for-mlat").value = False

        if self._d.env_by_tags("tar1090_image_config_link").value != "":
            self._d.env_by_tags("tar1090_image_config_link").value = (
                f"http://HOSTNAME:{self._d.env_by_tags('webport').value}/"
            )

        if self._d.is_enabled("stage2"):
            # for stage2 tar1090port is used for the webproxy
            # move the exposed port for the combined ultrafeeder to 8078 to avoid a port conflict
            self._d.env_by_tags("tar1090portadjusted").value = 8078
            # similarly, move the exposed port for a local nanofeeder to 8076 to avoid another port conflict
            self._d.env_by_tags("nanotar1090portadjusted").value = 8076

            # set unlimited range for the stage2 tar1090
            self._d.env_by_tags("max_range").list_set(0, 0)

            for sitenum in [0] + self.micro_indices():
                self.setup_or_disable_uat(sitenum)

        else:
            self._d.env_by_tags("tar1090portadjusted").value = self._d.env_by_tags("tar1090port").value
            self._d.env_by_tags("nanotar1090portadjusted").value = self._d.env_by_tags("tar1090port").value

            # for regular feeders or micro feeders a max range of 300nm seem reasonable
            self._d.env_by_tags("max_range").list_set(0, 300)

        # make all the smart choices for plugged in SDRs - unless we are a stage2 that hasn't explicitly requested SDR support
        if not self._d.is_enabled("stage2") or self._d.is_enabled("stage2_nano"):
            # first grab the SDRs plugged in and check if we have one identified for UAT
            self._sdrdevices._ensure_populated()
            env978 = self._d.env_by_tags("978serial")
            env1090 = self._d.env_by_tags("1090serial")
            if env978.value != "" and not any([sdr._serial == env978.value for sdr in self._sdrdevices.sdrs]):
                env978.value = ""
            if env1090.value != "" and not any([sdr._serial == env1090.value for sdr in self._sdrdevices.sdrs]):
                env1090.value = ""
            auto_assignment = self._sdrdevices.addresses_per_frequency

            purposes = self._sdrdevices.purposes()

            # if we have an actual asignment, that overrides the auto-assignment,
            # delete the auto-assignment
            for frequency in [978, 1090]:
                if any(auto_assignment[frequency] == self._d.env_by_tags(purpose).value for purpose in purposes):
                    auto_assignment[frequency] = ""
            if not env1090.value and auto_assignment[1090]:
                env1090.value = auto_assignment[1090]
            if not env978.value and auto_assignment[978]:
                env978.value = auto_assignment[978]

            stratuxv3 = any(
                [sdr._serial == env978.value and sdr._type == "stratuxv3" for sdr in self._sdrdevices.sdrs]
            )
            if stratuxv3:
                self._d.env_by_tags("uat_device_type").value = "stratuxv3"
            else:
                self._d.env_by_tags("uat_device_type").value = "rtlsdr"

            # handle 978 settings for stage1
            if env978.value:
                self._d.env_by_tags(["uat978", "is_enabled"]).list_set(0, True)
                self._d.env_by_tags("978url").list_set(0, "http://dump978/skyaware978")
                self._d.env_by_tags("978host").list_set(0, "dump978")
                self._d.env_by_tags("978piaware").list_set(0, "relay")
            else:
                self._d.env_by_tags(["uat978", "is_enabled"]).list_set(0, False)
                self._d.env_by_tags("978url").list_set(0, "")
                self._d.env_by_tags("978host").list_set(0, "")
                self._d.env_by_tags("978piaware").list_set(0, "")

            # next check for airspy devices
            airspy = any([sdr._serial == env1090.value and sdr._type == "airspy" for sdr in self._sdrdevices.sdrs])
            self._d.env_by_tags(["airspy", "is_enabled"]).value = airspy
            self._d.env_by_tags("airspyurl").list_set(0, f"http://airspy_adsb" if airspy else "")
            # SDRplay devices
            sdrplay = any([sdr._serial == env1090.value and sdr._type == "sdrplay" for sdr in self._sdrdevices.sdrs])
            self._d.env_by_tags(["sdrplay", "is_enabled"]).value = sdrplay

            # next - if we have exactly one SDR and it hasn't been assigned to anything, use it for 1090
            if (
                len(self._sdrdevices.sdrs) == 1
                and not airspy
                and not any(self._d.env_by_tags(p).value for p in purposes)
            ):
                env1090.value = self._sdrdevices.sdrs[0]._serial

            rtlsdr = any(sdr._type == "rtlsdr" and sdr._serial == env1090.value for sdr in self._sdrdevices.sdrs)
            if not rtlsdr:
                env1090.value = ""
            self._d.env_by_tags("readsb_device_type").value = "rtlsdr" if rtlsdr else ""

            if rtlsdr:
                # set rtl-sdr 1090 gain, bit hacky but means we don't have to restart the bulky ultrafeeder for gain changes
                self.setRtlGain()

            if airspy:
                # make sure airspy gain is within bounds
                gain = self._d.env_by_tags(["gain"]).value
                if gain == "autogain":
                    self._d.env_by_tags(["gain_airspy"]).value = "auto"
                elif make_int(gain) > 21:
                    self._d.env_by_tags(["gain_airspy"]).value = "21"
                    self._d.env_by_tags(["gain"]).value = "21"
                elif make_int(gain) < 0:
                    self._d.env_by_tags(["gain_airspy"]).value = "0"
                    self._d.env_by_tags(["gain"]).value = "0"
                else:
                    self._d.env_by_tags(["gain_airspy"]).value = gain

            if verbose & 1:
                print_err(f"in the end we have")
                print_err(f"1090serial {env1090.value}")
                print_err(f"978serial {env978.value}")
                print_err(f"airspy container is {self._d.is_enabled(['airspy'])}")
                print_err(f"SDRplay container is {self._d.is_enabled(['sdrplay'])}")
                print_err(f"dump978 container {self._d.list_is_enabled(['uat978'], 0)}")

        if self._d.env_by_tags("stage2_nano").value:
            do978 = bool(self._d.env_by_tags("978serial").value)

            # this code is here and not further up so get_base_info knows
            # about the various URLs for 978 / airspy / 1090
            self.setup_new_micro_site(
                "local",
                uat=do978,
                is_adsbim=True,
                brofm=False,
                do_import=True,
                do_restore=False,
            )
            # adjust 978
            for i in self.micro_indices():
                if self._d.env_by_tags("mf_ip").list_get(i) == "local":
                    self._d.env_by_tags(["uat978", "is_enabled"]).list_set(i, do978)

        # set all of the ultrafeeder config data up
        self.setup_ultrafeeder_args()

        # finally, check if this has given us enough configuration info to
        # start the containers
        if self.base_is_configured() or self._d.is_enabled("stage2"):
            self._d.env_by_tags(["base_config", "is_enabled"]).value = True
            if self.at_least_one_aggregator():
                self._d.env_by_tags("aggregators_chosen").value = True

            if self._d.is_feeder_image and not self._d.env_by_tags("journal_configured").value:
                try:
                    cmd = "/opt/adsb/scripts/journal-set-volatile.sh"
                    print_err(cmd)
                    subprocess.run(cmd, shell=True, timeout=5.0)
                    self.update_journal_state()
                    self._d.env_by_tags("journal_configured").value = True
                except:
                    pass

        for i in self.micro_indices():
            create_stage2_yml_files(i, self._d.env_by_tags("mf_ip").list_get(i))

        # check if we need the stage2 multiOutline job
        if self._d.is_enabled("stage2"):
            if not self._multi_outline_bg:
                self.push_multi_outline()
                self._multi_outline_bg = Background(60, self.push_multi_outline)
        else:
            self._multi_outline_bg = None

    @check_restart_lock
    def update(self):
        description = """
            This is the one endpoint that handles all the updates coming in from the UI.
            It walks through the form data and figures out what to do about the information provided.
        """
        # let's try and figure out where we came from - for reasons I don't understand
        # the regexp didn't capture the site number, so let's do this the hard way
        referer = request.headers.get("referer")
        m_arg = referer.rfind("?m=")
        if m_arg > 0:
            arg = make_int(referer[m_arg + 3 :])
        else:
            arg = 0
        if arg in self.micro_indices():
            sitenum = arg
            site = self._d.env_by_tags("site_name").list_get(sitenum)
        else:
            site = ""
            sitenum = 0
        allow_insecure = not self.check_secure_image()
        print_err(f"handling input from {referer} and site # {sitenum} / {site} (allow insecure is {allow_insecure})")
        # in the HTML, every input field needs to have a name that is concatenated by "--"
        # and that matches the tags of one Env
        form: Dict = request.form
        seen_go = False
        next_url = None
        for key, value in form.items():
            emptyStringPrint = "''"
            print_err(f"handling {key} -> {emptyStringPrint if value == '' else value}")
            # this seems like cheating... let's capture all of the submit buttons
            if value == "go" or value.startswith("go-"):
                seen_go = True
            if value == "go" or value.startswith("go-") or value == "wait":
                if key == "showmap" and value.startswith("go-"):
                    idx = make_int(value[3:])
                    self._next_url_from_director = f"/map_{idx}/"
                    print_err(f"after applying changes, go to map at {self._next_url_from_director}")
                if key == "sdrplay_license_accept":
                    self._d.env_by_tags("sdrplay_license_accepted").value = True
                if key == "sdrplay_license_reject":
                    self._d.env_by_tags("sdrplay_license_accepted").value = False
                if key == "add_micro" or key == "add_other" or key.startswith("import_micro"):
                    # user has clicked Add micro feeder on Stage 2 page
                    # grab the IP that we know the user has provided
                    ip = form.get("add_micro_feeder_ip")
                    uat = form.get("micro_uat")
                    brofm = is_true(form.get("micro_reduce")) and key == "add_micro"
                    is_adsbim = key != "add_other"
                    micro_data = {}
                    if not is_adsbim:
                        for mk in [
                            "micro_site_name",
                            "micro_lat",
                            "micro_lon",
                            "micro_alt",
                        ]:
                            micro_data[mk] = form.get(mk)
                    do_import = key.startswith("import_micro")
                    do_restore = key == "import_micro_full"
                    status, message = self.setup_new_micro_site(
                        ip,
                        uat=is_true(uat),
                        is_adsbim=is_adsbim,
                        brofm=brofm,
                        do_import=do_import,
                        do_restore=do_restore,
                        micro_data=micro_data,
                    )
                    if status:
                        print_err("successfully added new micro site")
                        self._next_url_from_director = url_for("stage2")
                    else:
                        print_err(f"failed to add new micro site: {message}")
                        flash(f"failed to add new micro site: {message}", "danger")
                        next_url = url_for("stage2")
                    continue
                if key.startswith("remove_micro_"):
                    # user has clicked Remove micro feeder on Stage 2 page
                    # grab the micro feeder number that we know the user has provided
                    num = int(key[len("remove_micro_") :])
                    name = self._d.env_by_tags("site_name").list_get(num)
                    self.remove_micro_site(num)
                    flash(f"Removed micro site {name}", "success")
                    self._next_url_from_director = url_for("stage2")
                    continue
                if key.startswith("edit_micro_"):
                    # user has clicked Edit micro feeder on Stage 2 page
                    # grab the micro feeder number that we know the user has provided
                    num = int(key[len("edit_micro_") :])
                    return render_template("stage2.html", edit_index=num)
                if key.startswith("cancel_edit_micro_"):
                    # discard changes
                    flash(f"Cancelled changes", "success")
                    return redirect(url_for("stage2"))
                if key.startswith("save_edit_micro_"):
                    # save changes
                    num = int(key[len("save_edit_micro_") :])
                    success, message = self.edit_micro_site(
                        num,
                        form.get(f"site_name_{num}"),
                        form.get(f"mf_ip_{num}"),
                        form.get(f"mf_uat_{num}"),
                        form.get(f"mf_brofm_{num}"),
                    )
                    if success:
                        self._next_url_from_director = url_for("stage2")
                    else:
                        flash(message, "error")
                        next_url = url_for("stage2")
                    continue
                if key == "set_stage2_data":
                    # just grab the new data and go back
                    next_url = url_for("stage2")
                if key == "turn_off_stage2":
                    # let's just switch back
                    self._d.env_by_tags("stage2").value = False
                    if self._multi_outline_bg:
                        self._multi_outline_bg.cancel()
                        self._multi_outline_bg = None
                    self._d.env_by_tags("aggregators_chosen").value = False
                    self._d.env_by_tags("aggregator_choice").value = ""

                if key == "aggregators":
                    # user has clicked Submit on Aggregator page
                    self._d.env_by_tags("aggregators_chosen").value = True
                    # set this to individual so if people have set "all" before can still deselect individual aggregators
                    self._d.env_by_tags("aggregator_choice").value = "individual"

                if allow_insecure and key == "shutdown":
                    # do shutdown
                    def do_halt():
                        sleep(0.5)
                        self._system.halt()

                    threading.Thread(target=do_halt).start()
                    return render_template("/shutdownpage.html")
                if allow_insecure and key == "reboot":
                    # initiate reboot
                    self._system.reboot()
                    return render_template("/restarting.html")
                if key == "restart_containers" or key == "recreate_containers":
                    containers = self._system.list_containers()
                    containers_to_restart = []
                    for container in containers:
                        # only restart the ones that have been checked
                        user_selection = form.get(f"restart-{container}", "0")
                        if user_selection == "1":
                            containers_to_restart.append(container)
                    self.write_envfile()
                    if key == "restart_containers":
                        self._system.restart_containers(containers_to_restart)
                    else:
                        self._system.recreate_containers(containers_to_restart)
                    self._next_url_from_director = request.url
                    return render_template("/restarting.html")
                if key == "log_persistence_toggle":
                    if self._persistent_journal:
                        cmd = "/opt/adsb/scripts/journal-set-volatile.sh"
                    else:
                        cmd = "/opt/adsb/scripts/journal-set-persist.sh"
                    try:
                        print_err(cmd)
                        subprocess.run(cmd, shell=True, timeout=5.0)
                        self.update_journal_state()
                    except:
                        pass
                    self._next_url_from_director = request.url
                if key == "secure_image":
                    self.set_secure_image()
                if key == "no_config_link":
                    self._d.env_by_tags("tar1090_image_config_link").value = ""
                if key == "allow_config_link":
                    self._d.env_by_tags("tar1090_image_config_link").value = f"WILL_BE_SET_IN_IMPLIED_SETTINGS"
                if key == "turn_on_gpsd":
                    self._d.env_by_tags(["use_gpsd", "is_enabled"]).value = True
                    # this updates the lat/lon/alt env variables as side effect, if there is a GPS fix
                    self.get_lat_lon_alt()
                if key == "turn_off_gpsd":
                    self._d.env_by_tags(["use_gpsd", "is_enabled"]).value = False
                if key.startswith("update_feeder_aps"):
                    channel = key.rsplit("_", 1)[-1]
                    if channel == "branch":
                        channel = self.extract_channel()
                    self.set_channel(channel)
                    print_err(f"updating feeder to {channel} channel")
                    self._system._restart.bg_run(cmdline="systemctl start adsb-feeder-update.service")
                    return render_template("/restarting.html")
                if key == "nightly_update" or key == "zerotier":
                    # this will be handled through the separate key/value pairs
                    pass
                if key == "os_update":
                    self._system._restart.bg_run(func=self._system.os_update)
                    self._next_url_from_director = request.url
                    return render_template("/restarting.html")
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
                            print_err(f"the login server URL didn't make sense {ts_cli_value}")
                            continue
                    print_err(f"starting tailscale (args='{ts_args}')")
                    try:
                        subprocess.run(
                            ["/usr/bin/systemctl", "enable", "--now", "tailscaled"],
                            timeout=20.0,
                        )
                        cmd = ["/usr/bin/tailscale", "up"]

                        name = self.onlyAlphaNumDash(self._d.env_by_tags("site_name").list_get(0))
                        cmd += [f"--hostname={name}"]

                        if ts_args:
                            cmd += [f"--login-server={shlex.quote(ts_cli_value)}"]
                        cmd += ["--accept-dns=false"]
                        print_err(f"running {cmd}")
                        proc = subprocess.Popen(
                            cmd,
                            stderr=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            text=True,
                        )
                        os.set_blocking(proc.stderr.fileno(), False)
                    except:
                        # this really needs a user visible error...
                        print_err("exception trying to set up tailscale - giving up")
                        continue
                    else:
                        startTime = time.time()
                        match = None
                        while time.time() - startTime < 30:
                            output = proc.stderr.readline()
                            if not output:
                                if proc.poll() != None:
                                    break
                                time.sleep(0.1)
                                continue
                            print_err(output.rstrip("\n"))
                            # standard tailscale result
                            match = re.search(r"(https://login\.tailscale.*)", output)
                            if match:
                                break
                            # when using a login-server
                            match = re.search(r"(https://.*/register/nodekey.*)", output)
                            if match:
                                break

                        proc.terminate()

                    if match:
                        login_link = match.group(1)
                        print_err(f"found login link {login_link}")
                        self._d.env_by_tags("tailscale_ll").value = login_link
                    else:
                        print_err(f"ERROR: tailscale didn't provide a login link within 30 seconds")
                    return redirect(url_for("systemmgmt"))
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
                        l_sitenum = make_int(value[5:])
                        l_site = self._d.env_by_tags("site_name").list_get(l_sitenum)
                        if not l_site:
                            print_err(f"can't find a site for sitenum {l_sitenum}")
                            l_sitenum = 0
                        else:
                            print_err(f"found other aggregator {key} for site {l_site} sitenum {l_sitenum}")
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
                    print_err(f"got aggregator object {aggregator_object} -- activating for sitenum {l_sitenum}")
                    try:
                        is_successful = aggregator_object._activate(aggregator_argument, l_sitenum)
                    except Exception as e:
                        print_err(f"error activating {key}: {e}")
                    if not is_successful:
                        print_err(f"did not successfully enable {base}")

                    # immediately start the containers in case the user doesn't click "apply settings" after requesting a key
                    seen_go = True
                    # go back to the page we were on after applying settings
                    self._next_url_from_director = request.url

                continue
            # now handle other form input
            if key == "clear_range" and value == "1":
                self.clear_range_outline(sitenum)
                continue
            if key == "resetgain" and value == "1":
                # tell the ultrafeeder container to restart the autogain processing
                if self._d.is_enabled("stage2_nano"):
                    cmdline = "docker exec nanofeeder /usr/local/bin/autogain1090 reset"
                else:
                    cmdline = "docker exec ultrafeeder /usr/local/bin/autogain1090 reset"
                try:
                    subprocess.run(cmdline, timeout=5.0, shell=True)
                except:
                    print_err("Error running Ultrafeeder autogain reset")
                continue
            if key == "resetuatgain" and value == "1":
                # tell the dump978 container to restart the autogain processing
                cmdline = "docker exec dump978 /usr/local/bin/autogain978 reset"
                try:
                    subprocess.run(cmdline, timeout=5.0, shell=True)
                except:
                    print_err("Error running UAT autogain reset")
                continue
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
                        subprocess.call("/usr/bin/systemctl enable --now zerotier-one", shell=True)
                        sleep(5.0)  # this gives the service enough time to get ready
                        subprocess.call(
                            ["/usr/sbin/zerotier-cli", "join", f"{value}"],
                        )
                    except:
                        print_err("exception trying to set up zerorier - giving up")
                if key in {"lat", "lon", "alt"}:
                    # remove letters, spaces, degree symbols
                    value = str(float(re.sub("[a-zA-Z° ]", "", value)))
                if key == "alt":
                    # remove decimals as well
                    value = str(int(float(value)))
                if key == "tz":
                    self.set_tz(value)
                    continue
                if key == "uatgain":
                    if value == "" or value == "auto":
                        value = "autogain"
                if key == "gain":
                    if value == "" or value == "auto":
                        value = "autogain"
                # deal with the micro feeder and stage2 initial setup
                if key == "aggregator_choice" and value in ["micro", "nano"]:
                    self._d.env_by_tags("aggregators_chosen").value = True
                    # disable all the aggregators in micro mode
                    for ev in self._d._env:
                        if "is_enabled" in ev.tags:
                            if "other_aggregator" in ev.tags or "ultrafeeder" in ev.tags:
                                ev.list_set(0, False)
                    if value == "nano" and self._d.is_feeder_image:
                        # make sure we don't log to disk at all
                        try:
                            subprocess.call("bash /opt/adsb/scripts/journal-set-volatile.sh", shell=True, timeout=5)
                            print_err("switched to volatile journal")
                        except:
                            print_err("exception trying to switch to volatile journal - ignoring")
                if key == "aggregator_choice" and value == "stage2":
                    next_url = url_for("stage2")
                    self._d.env_by_tags("stage2").value = True
                    if not self._multi_outline_bg:
                        self.push_multi_outline()
                        self._multi_outline_bg = Background(60, self.push_multi_outline)
                    unique_name = self.unique_site_name(form.get("site_name"), 0)
                    self._d.env_by_tags("site_name").list_set(0, unique_name)
                # if this is a regular feeder and the user is changing to 'individual' selection
                # (either in initial setup or when coming back to that setting later), show them
                # the aggregator selection page next
                if (
                    key == "aggregator_choice"
                    and not self._d.is_enabled("stage2")
                    and value == "individual"
                    and self._d.env_by_tags("aggregator_choice").value != "individual"
                ):
                    # show the aggregator selection
                    next_url = url_for("aggregators")
                # finally, painfully ensure that we remove explicitly asigned SDRs from other asignments
                # this relies on the web page to ensure that each SDR is only asigned on purpose
                # the key in quesiton will be explicitely set and does not need clearing
                # empty string means no SDRs assigned to that purpose
                purposes = self._sdrdevices.purposes()
                if key in purposes and value != "":
                    for clear_key in purposes:
                        if clear_key != key and value == self._d.env_by_tags(clear_key).value:
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
                    unique_name = self.unique_site_name(value, sitenum)
                    self._d.env_by_tags("site_name").list_set(sitenum, unique_name)
        # done handling the input data
        # what implied settings do we have (and could we simplify them?)

        self.handle_implied_settings()

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
            if self._d.is_enabled("sdrplay") and not self._d.is_enabled("sdrplay_license_accepted"):
                return redirect(url_for("sdrplay_license"))

            self._system._restart.bg_run(cmdline="/opt/adsb/docker-compose-start", silent=True)
            return render_template("/restarting.html")
        print_err("base config not completed", level=2)
        return redirect(url_for("director"))

    @check_restart_lock
    def expert(self):
        if request.method == "POST":
            return self.update()
        # make sure we only show the gpsd option if gpsd is correctly configured and running
        self._d.env_by_tags("has_gpsd").value = self._system.check_gpsd()
        return render_template("expert.html")

    @check_restart_lock
    def systemmgmt(self):
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
            "systemmgmt.html",
            rpw=self.rpw,
            channel=self.extract_channel(),
            containers=self._system.list_containers(),
            persistent_journal=self._persistent_journal,
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
            return "checked" if self._d.list_is_enabled(["ultrafeeder"] + tag, idx=m) else ""

        def others_enabled(tag, m=0):
            # stack_info(f"tags are {type(tag)} {tag}")
            if type(tag) == str:
                tag = [tag]
            if type(tag) != list:
                print_err(f"PROBLEM::: tag is {type(tag)}")
            return "checked" if self._d.list_is_enabled(["other_aggregator"] + tag, idx=m) else ""

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
            piastatport=str(m * 1000 + make_int(self._d.env_by_tags("piastatport").value)),
        )

    @check_restart_lock
    def director(self):
        # figure out where to go:
        if request.method == "POST":
            return self.update()
        if not self._d.is_enabled("base_config"):
            print_err(f"director redirecting to setup, base_config not completed")
            return self.setup()
        # if we already figured out where to go next, let's just do that
        if self._next_url_from_director:
            print_err(f"director redirecting to next_url_from_director: {self._next_url_from_director}")
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
        # we need to go to sdr_setup - unless we have at least one of the serials set up
        # for 978 or 1090 reporting

        # do we have duplicate SDR serials?
        if len(self._sdrdevices.duplicates) > 0:
            print_err("director redirecting to sdr_setup: duplicate SDR serials")
            return self.sdr_setup()

        # check that "something" is configured as input
        if (
            (len(self._sdrdevices) > 1 or any([sdr._type == "airspy" for sdr in self._sdrdevices.sdrs]))
            and not (
                self._d.env_by_tags("1090serial").value
                or self._d.env_by_tags("978serial").value
                or self._d.is_enabled("airspy")
            )
            and not self._d.is_enabled("stage2")
        ):
            print_err("director redirecting to sdr_setup: devices present but not configured")
            return self.sdr_setup()

        # if the user chose to individually pick aggregators but hasn't done so,
        # they need to go to the aggregator page
        if self.at_least_one_aggregator() or self._d.env_by_tags("aggregators_chosen"):
            return self.index()
        print_err("director redirecting to aggregators: to be configured")
        return self.aggregators()

    def every_minute(self):
        # make sure DNS works
        self.update_dns_state()

        self._sdrdevices._ensure_populated()

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
            self.local_address = result
        else:
            self.local_address = ""

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
            self.tailscale_address = result
        else:
            self.tailscale_address = ""
        zt_network = self._d.env_by_tags("zerotierid").value
        if zt_network:
            try:
                result = subprocess.run(
                    ["zerotier-cli", "get", f"{zt_network}", "ip4"],
                    shell=True,
                    capture_output=True,
                    timeout=2.0,
                ).stdout
            except:
                result = ""
            else:
                result = result.decode().strip()
            self.zerotier_address = result
        else:
            self.zerotier_address = ""
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
        self._d.env_by_tags("low_disk").value = shutil.disk_usage("/").free < 1024 * 1024 * 1024

    @check_restart_lock
    def index(self):
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
        n = self._d.env_by_tags("num_micro_sites").value + 1
        matrix = [0] * n
        for idx in range(len(aggregators)):
            agg = aggregators[idx][0]
            status_link_list = aggregators[idx][3]
            template_link = status_link_list[0]
            final_link = template_link
            for i in range(n):
                matrix[i] |= 1 << idx if self._d.list_is_enabled(agg, i) else 0
                if template_link.startswith("/"):
                    final_link = url_start + template_link.replace("STG2IDX", "" if i == 0 else f"_{i}")
                else:
                    match = re.search("<([^>]*)>", template_link)
                    if match:
                        final_link = template_link.replace(match.group(0), self._d.env(match.group(1)).list_get(i))
                if i == 0:
                    status_link_list[0] = final_link
                else:
                    status_link_list.append(final_link)
        agg_debug_print = f"final aggregator structure: {aggregators}"
        if agg_debug_print != self.last_aggregator_debug_print:
            self.last_aggregator_debug_print = agg_debug_print
            print_err(agg_debug_print)
        board = self._d.env_by_tags("board_name").value
        self._d.settings = matrix
        # there are many other boards I should list here - but Pi 3 and Pi Zero are probably the most common
        stage2_suggestion = board.startswith("Raspberry") and not (
            board.startswith("Raspberry Pi 4") or board.startswith("Raspberry Pi 5")
        )
        if self.local_address:
            local_address = self.local_address
        else:
            local_address = request.host.split(":")[0]

        return render_template(
            "index.html",
            aggregators=aggregators,
            local_address=local_address,
            tailscale_address=self.tailscale_address,
            zerotier_address=self.zerotier_address,
            stage2_suggestion=stage2_suggestion,
            matrix=matrix,
        )

    @check_restart_lock
    def setup(self):
        if request.method == "POST" and (
            request.form.get("submit") == "go" or request.form.get("set_stage2_data") == "go"
        ):
            return self.update()
        # is this a stage2 feeder?
        if self._d.is_enabled("stage2"):
            return render_template("stage2.html")
        # make sure DNS works
        self.update_dns_state()
        return render_template("setup.html", mem=self._memtotal)

    def micro_indices(self):
        if self._d.is_enabled("stage2"):
            # micro proxies start at 1
            return list(range(1, self._d.env_by_tags("num_micro_sites").value + 1))
        else:
            return []

    @check_restart_lock
    def stage2(self):
        if request.method == "POST":
            return self.update()
        return render_template("stage2.html")

    def temperatures(self):
        temperature_json = {}
        try:
            with open("/opt/adsb/extras/temperature.json", "r") as temperature_file:
                temperature_json = json.load(temperature_file)
                now = int(time.time())
                age = now - int(temperature_json.get("now", "0"))
                temperature_json["age"] = age
        except:
            pass
        return temperature_json

    def support(self):
        print_err(f"support request, {request.form}")
        if request.method != "POST":
            return render_template("support.html", url="")

        url = "Internal Error uploading logs"

        target = request.form.get("upload")
        print_err(f'trying to upload the logs with target: "{target}"')

        if not target:
            print_err(f"ERROR: support POST request without target")
            return render_template("support.html", url="Error, unspecified upload target!")

        if target == "0x0.st":
            success, output = run_shell_captured(
                command="bash /opt/adsb/log-sanitizer.sh | curl -F'expires=168' -F'file=@-'  https://0x0.st",
                timeout=60,
            )
            url = output.strip()
            if success:
                print_err(f"uploaded logs to {url}")
            else:
                print_err(f"failed to upload logs, output: {output}")
            return render_template("support.html", url=url)

        if target == "termbin.com":
            success, output = run_shell_captured(
                command="bash /opt/adsb/log-sanitizer.sh | nc termbin.com 9999",
                timeout=60,
            )
            # strip extra chars for termbin
            url = output.strip("\0\n").strip()
            if success:
                print_err(f"uploaded logs to {url}")
            else:
                print_err(f"failed to upload logs, output: {output}")
            return render_template("support.html", url=url)

        if target == "local_view" or target == "local_download":

            as_attachment = target == "local_download"

            fdOut, fdIn = os.pipe()
            pipeOut = os.fdopen(fdOut, "rb")
            pipeIn = os.fdopen(fdIn, "wb")

            def get_log(fobj):
                subprocess.run(
                    "bash /opt/adsb/log-sanitizer.sh",
                    shell=True,
                    stdout=fobj,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                )

            thread = threading.Thread(
                target=get_log,
                kwargs={
                    "fobj": pipeIn,
                },
            )
            thread.start()

            site_name = self._d.env_by_tags("site_name").list_get(0)
            now = datetime.now().replace(microsecond=0).isoformat().replace(":", "-")
            download_name = f"adsb-feeder-config-{site_name}-{now}.txt"
            return send_file(
                pipeOut,
                as_attachment=as_attachment,
                download_name=download_name,
            )

        return render_template("support.html", url="upload logs: unexpected code path")

    def info(self):
        board = self._d.env_by_tags("board_name").value
        base = self._d.env_by_tags("image_name").value
        current = self._d.env_by_tags("base_version").value
        ufargs = self._d.env_by_tags("ultrafeeder_extra_args").value
        envvars = self._d.env_by_tags("ultrafeeder_extra_env").value
        sdrs = [f"{sdr}" for sdr in self._sdrdevices.sdrs] if len(self._sdrdevices.sdrs) > 0 else ["none"]

        def simple_cmd_result(cmd):
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, timeout=2.0)
                return result.stdout.decode("utf-8")
            except:
                return f"failed to run '{cmd}'"

        storage = simple_cmd_result("df -h | grep -v overlay")
        kernel = simple_cmd_result("uname -a")
        memory = simple_cmd_result("free -h")
        top = simple_cmd_result("top -b -n1 | head -n5")
        journal = "persistent on disk" if self._persistent_journal else "in memory"

        containers = [
            self._d.env_by_tags(["container", container]).value
            for container in self._d.tag_for_name.values()
            if self._d.is_enabled(container) or container == "ultrafeeder"
        ]
        return render_template(
            "info.html",
            board=board,
            memory=memory,
            top=top,
            storage=storage,
            base=base,
            kernel=kernel,
            journal=journal,
            current=current,
            containers=containers,
            sdrs=sdrs,
            ufargs=ufargs,
            envvars=envvars,
        )

    def waiting(self):
        return render_template("waiting.html", title="ADS-B Feeder performing requested actions")

    def stream_log(self):
        logfile = "/run/adsb-feeder-image.log"

        def tail():
            with open(logfile, "r") as file:
                ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
                tmp = file.read()[-16 * 1024 :]
                # discard anything but the last 16 kB
                while self._system._restart.state == "restarting":
                    tmp += file.read(16 * 1024)
                    if tmp and tmp.find("\n") != -1:
                        block, tmp = tmp.rsplit("\n", 1)
                        block = ansi_escape.sub("", block)
                        lines = block.split("\n")
                        data = "".join(["data: " + line + "\n" for line in lines])
                        yield data + "\n\n"
                    else:
                        time.sleep(0.2)

        return Response(tail(), mimetype="text/event-stream")


def create_stage2_yml_from_template(stage2_yml_name, n, ip, template_file):
    if n:
        with open(template_file, "r") as stage2_yml_template:
            with open(stage2_yml_name, "w") as stage2_yml:
                stage2_yml.write(stage2_yml_template.read().replace("STAGE2NUM", f"{n}").replace("STAGE2IP", ip))
    else:
        print_err(f"could not find micro feedernumber in {stage2_yml_name}")


def create_stage2_yml_files(n, ip):
    if not n:
        return
    print_err(f"create_stage2_yml_files(n={n}, ip={ip})")
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
        create_stage2_yml_from_template(f"/opt/adsb/config/{yml_file}", n, ip, f"/opt/adsb/config/{template}")


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
            shutil.move(env_file, config_dir / ".env")

    moved = False
    for config_file in adsb_dir.glob("*.yml"):
        if config_file.exists():
            moved = True
            new_file = config_dir / config_file.name
            shutil.move(config_file, new_file)
    if moved:
        print_err(f"moved yml files to {config_dir}")

    if not pathlib.Path(config_dir / ".env").exists():
        # I don't understand how that could happen
        shutil.copyfile(adsb_dir / "docker.image.versions", config_dir / ".env")

    no_server = len(sys.argv) > 1 and sys.argv[1] == "--update-config"

    AdsbIm().run(no_server=no_server)
