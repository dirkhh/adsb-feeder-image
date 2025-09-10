import copy
import filecmp
import gzip
import json
import math
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
import traceback
from uuid import uuid4
import sys
import zipfile
from base64 import b64encode
from datetime import datetime, timezone
from os import urandom
from time import sleep
from typing import Dict, List, Tuple
from zlib import compress
from copy import deepcopy

from utils.config import (
    config_lock,
    log_consistency_warning,
    read_values_from_config_json,
    read_values_from_env_file,
    write_values_to_config_json,
    write_values_to_env_file,
)
from utils.util import create_fake_info, make_int, print_err, report_issue, mf_get_ip_and_triplet, string2file
from utils.wifi import Wifi

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


from utils.data import Data
from utils.environment import Env
from utils.flask import RouteManager, check_restart_lock
from utils.netconfig import NetConfig, UltrafeederConfig
from utils.other_aggregators import (
    ADSBHub,
    FlightAware,
    FlightRadar24,
    OpenSky,
    PlaneFinder,
    PlaneWatch,
    RadarBox,
    RadarVirtuel,
    Uk1090,
    Sdrmap,
)
from utils.sdr import SDR, SDRDevices
from utils.agg_status import AggStatus, ImStatus
from utils.system import System
from utils.util import (
    cleanup_str,
    generic_get_json,
    is_true,
    print_err,
    stack_info,
    verbose,
    make_int,
    run_shell_captured,
)
from utils.background import Background
from utils.wifi import Wifi

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

        # set Cache-Control max-age for static files served
        # cachebust.sh ensures that the browser doesn't get outdated files
        self.app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 1209600

        self.exiting = False

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
                "env_values": self._d.env_values,
            }

        self._routemanager = RouteManager(self.app)
        self._d = Data()
        self._system = System(data=self._d)
        # let's only instantiate the Wifi class if we are on WiFi
        self.wifi = None
        self.wifi_ssid = ""

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

        self._sdrdevices = SDRDevices(assignment_function=self.sdr_assignments, data=self._d)

        for i in [0] + self.micro_indices():
            self._d.ultrafeeder.append(UltrafeederConfig(data=self._d, micro=i))

        self.last_dns_check = 0
        self.undervoltage_epoch = 0

        self._current_site_name = None
        self._agg_status_instances = dict()
        self._im_status = ImStatus(self._d)
        self._next_url_from_director = ""
        self._last_stage2_contact = ""
        self._last_stage2_contact_time = 0

        self._last_base_info = dict()

        self._multi_outline_bg = None

        self.lastSetGainWrite = 0

        # no one should share a CPU serial with AirNav, so always create fake cpuinfo;
        # also identify if we would use the thermal hack for RB and Ultrafeeder
        if create_fake_info([0] + self.micro_indices()):
            self._d.env_by_tags("rbthermalhack").value = "/sys/class/thermal"
        else:
            self._d.env_by_tags("rbthermalhack").value = ""

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
            "sdrmap--submit": Sdrmap(self._system),
        }
        # fmt: off
        self.all_aggregators = [
            # tag, name, map link, status link, table number
            ["adsblol", "adsb.lol", "https://adsb.lol/", ["https://api.adsb.lol/0/me"], 0],
            ["flyitaly", "Fly Italy ADSB", "https://mappa.flyitalyadsb.com/", ["https://my.flyitalyadsb.com/am_i_feeding"], 0],
            ["avdelphi", "AVDelphi", "https://www.avdelphi.com/coverage.html", [""], 0],
            ["planespotters", "Planespotters", "https://radar.planespotters.net/", ["https://www.planespotters.net/feed/status"], 0],
            ["tat", "TheAirTraffic", "https://globe.theairtraffic.com/", ["https://theairtraffic.com/feed/myip/"], 0],
            ["adsbfi", "adsb.fi", "https://globe.adsb.fi/", ["https://api.adsb.fi/v1/myip"], 0],
            ["adsbx", "ADSBExchange", "https://globe.adsbexchange.com/", ["https://www.adsbexchange.com/myip/"], 0],
            ["hpradar", "HPRadar", "https://skylink.hpradar.com/", [""], 0],
            ["alive", "airplanes.live", "https://globe.airplanes.live/", ["https://airplanes.live/myfeed/"], 0],
            ["flightradar", "flightradar24", "https://www.flightradar24.com/", ["/fr24STG2IDX/"], 1],
            ["planewatch", "Plane.watch", "https:/plane.watch/desktop.html", [""], 1],
            ["flightaware", "FlightAware", "https://www.flightaware.com/live/map", ["/fa-statusSTG2IDX/"], 1],
            ["radarbox", "AirNav Radar", "https://www.airnavradar.com/coverage-map", ["https://www.airnavradar.com/stations/<FEEDER_RADARBOX_SN>"], 1],
            ["planefinder", "PlaneFinder", "https://planefinder.net/", ["/planefinder-statSTG2IDX/"], 1],
            ["adsbhub", "ADSBHub", "https://www.adsbhub.org/coverage.php", [""], 1],
            ["opensky", "OpenSky", "https://opensky-network.org/network/explorer", ["https://opensky-network.org/receiver-profile?s=<FEEDER_OPENSKY_SERIAL>"], 1],
            ["radarvirtuel", "RadarVirtuel", "https://www.radarvirtuel.com/", [""], 1],
            ["1090uk", "1090MHz UK", "https://1090mhz.uk", ["https://www.1090mhz.uk/mystatus.php?key=<FEEDER_1090UK_API_KEY>"], 1],
            ["sdrmap", "sdrmap", "https://sdrmap.org/", [""], 1],
        ]
        self.agg_matrix = None
        self.agg_structure = []
        self.last_cache_agg_status = 0
        self.ci = False
        self.cache_agg_status_lock = threading.Lock()
        self.miscLock = threading.Lock()
        self.last_aggregator_debug_print = None
        self.microfeeder_setting_tags = (
            "site_name", "lat", "lon", "alt", "tz", "mf_version", "max_range",
            "adsblol_uuid", "adsblol_link", "ultrafeeder_uuid", "mlat_privacy", "route_api",
            "uat978", "heywhatsthat", "heywhatsthat_id",
            "flightradar--key", "flightradar_uat--key", "flightradar--is_enabled",
            "planewatch--key", "planewatch--is_enabled",
            "flightaware--key", "flightaware--is_enabled",
            "radarbox--key", "radarbox--snkey", "radarbox--is_enabled",
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
            "hpradar--is_enabled",
            "alive--is_enabled",
            "uat978--is_enabled",
            "sdrmap--is_enabled", "sdrmap--user", "sdrmap--key",
        )

        self._routemanager.add_proxy_routes(self._d.proxy_routes)
        self.app.add_url_rule("/geojson", "geojson", self.geojson)
        self.app.add_url_rule("/icons.png", "iconspng", self.iconspng)
        self.app.add_url_rule("/change_sdr_serial/<oldserial>/<newserial>", "change_sdr_serial", self.change_sdr_serial)
        self.app.add_url_rule("/change_sdr_serial_ui", "change_sdr_serial_ui", self.change_sdr_serial_ui)
        self.app.add_url_rule("/hotspot_test", "hotspot_test", self.hotspot_test)
        self.app.add_url_rule("/restarting", "restarting", self.restarting)
        self.app.add_url_rule("/shutdownpage", "shutdownpage", self.shutdownpage)
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
        self.app.add_url_rule("/index", "index", self.index, methods=["GET", "POST"])
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
        self.app.add_url_rule("/api/stats", "stats", self.stats)
        self.app.add_url_rule("/api/micro_settings", "micro_settings", self.micro_settings)
        self.app.add_url_rule("/api/check_remote_feeder/<ip>", "check_remote_feeder", self.check_remote_feeder)
        self.app.add_url_rule(f"/api/status/<agg>", "beast", self.agg_status)
        self.app.add_url_rule("/api/stage2_connection", "stage2_connection", self.stage2_connection)
        self.app.add_url_rule("/api/get_temperatures.json", "temperatures", self.temperatures)
        self.app.add_url_rule("/api/ambient_raw", "ambient_raw", self.ambient_raw)
        self.app.add_url_rule("/api/check_changelog_status", "check_changelog_status", self.check_changelog_status)
        self.app.add_url_rule("/api/mark_changelog_seen", "mark_changelog_seen", self.mark_changelog_seen, methods=["POST"])
        self.app.add_url_rule("/api/scan_wifi", "scan_wifi", self.scan_wifi)
        self.app.add_url_rule("/api/closest_airport/<lat>/<lon>", "closest_airport", self.closest_airport)
        self.app.add_url_rule(f"/feeder-update-<channel>", "feeder-update", self.feeder_update)
        self.app.add_url_rule(f"/get-logs", "get-logs", self.get_logs)
        self.app.add_url_rule(f"/view-logs", "view-logs", self.view_logs)
        # fmt: on
        self.update_boardname()
        self.update_version()
        self.update_meminfo()
        self.update_journal_state()

        self._d.previous_version = self.get_previous_version()
        if self._d.previous_version != "":
            self._d.env_by_tags("previous_version").value = self._d.previous_version

        self.load_planes_seen_per_day()

        while len(self._d.env_by_tags("site_name").value) > self._d.env_by_tags("num_micro_sites").valueint + 1:
            actual_len = len(self._d.env_by_tags("site_name").value)
            nominal_len = self._d.env_by_tags("num_micro_sites").valueint + 1
            print_err(f"BAD CONFIG STATE, site_name list too long {actual_len} > {nominal_len}, removing one element")
            self._d.env_by_tags("site_name").list_remove()

        # now all the envs are loaded and reconciled with the data on file - which means we should
        # actually write out the potentially updated values (e.g. when plain values were converted
        # to lists)
        with config_lock:
            write_values_to_config_json(self._d.env_values, reason="Startup")

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
                    manufacturer: str = ""
                    prod: str = ""
                    try:
                        prod = subprocess.run(
                            "dmidecode -s system-product-name",
                            shell=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip()
                        manufacturer = subprocess.run(
                            "dmidecode -s system-manufacturer",
                            shell=True,
                            capture_output=True,
                            text=True,
                        ).stdout.strip()
                    except:
                        pass
                    if prod or manufacturer:
                        board = f"Native on {manufacturer} {prod} {platform.machine()} system"
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
        conf_version = self._d.env_by_tags("base_version").valuestr
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

    def get_previous_version(self):
        previous_version = ""
        pv_file = "/opt/adsb/adsb.im.previous-version"

        if pathlib.Path(pv_file).exists():
            with open(pv_file, "r") as f:
                previous_version = f.read().strip()

        return previous_version

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
            "pv": self._d.previous_version,
            "cv": self.agg_matrix,
        }
        if self._d.env_by_tags("initial_version").value == "":
            self._d.env_by_tags("initial_version").value = self._d.env_by_tags("base_version").value
        return b64encode(compress(pickle.dumps(image))).decode("utf-8")

    def check_secure_image(self):
        return self._d.secure_image_path.exists()

    def set_secure_image(self):
        # set legacy env variable as well for webinterface
        self._d.env_by_tags("secure_image").value = True
        if not self.check_secure_image():
            self._d.secure_image_path.touch(exist_ok=True)
            print_err("secure_image has been set")

    def toggle_hotspot(self):
        if self._d.hotspot_disabled_path.exists():
            self._d.hotspot_disabled_path.unlink(missing_ok=True)
            print_err("hotspot has been enabled")
        else:
            self._d.hotspot_disabled_path.touch(exist_ok=True)
            print_err("hotspot has been disabled")

    def update_dns_state(self):
        def update_dns():
            dns_state = self._system.check_dns()
            self._d.env_by_tags("dns_state").value = dns_state
            if not dns_state:
                print_err("ERROR: we appear to have lost DNS")

        self.last_dns_check = time.time()
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
            subprocess.run(["/bin/bash", "/opt/adsb/scripts/mdns-alias-setup.sh", f"{host_name}"])
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
        board = self._d.env_by_tags("board_name").valuestr
        if board.startswith("Raspberry Pi 5"):
            self._d.env_by_tags(["container", "planefinder"]).value = (
                "ghcr.io/sdr-enthusiasts/docker-planefinder:5.0.161_arm64"
            )

        # as we migrate from pre v3.0.1 to v3.0.1 we need to sync the new feeder type
        # variables based on existing settings - the rest of the code must ensure that
        # these stay in sync, so this should only ever create change the first time
        # the app is run
        # fmt: off
        if self._d.env_by_tags("aggregator_choice").value != "":
            self._d.env_by_tags("is_adsb_feeder").value = self._d.env_by_tags("aggregator_choice").value != "nonadsb"
        elif not self._d.is_enabled("is_adsb_feeder"):
            self._d.env_by_tags("aggregator_choice").value = "nonadsb"
        if not self._d.is_enabled("is_acars_feeder"):
            self._d.env_by_tags("is_acars_feeder").value = (
                self._d.is_enabled("acarsdec") or self._d.is_enabled("acarsdec2") or self._d.is_enabled("dumpvdl2")
            )
        if not self._d.is_enabled("is_hfdl_feeder"):
            self._d.env_by_tags("is_hfdl_feeder").value = self._d.is_enabled("hfdlobserver") or self._d.is_enabled("dumphfdl")
        if not self._d.is_enabled("is_ais_feeder"):
            self._d.env_by_tags("is_ais_feeder").value = self._d.is_enabled("shipfeeder")
        if not self._d.is_enabled("is_sonde_feeder"):
            self._d.env_by_tags("is_sonde_feeder").value = self._d.is_enabled("sonde")
        # fmt: on

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

        # reset undervoltage indicator
        self._d.env_by_tags("under_voltage").value = False

        threading.Thread(target=self.monitor_dmesg).start()

        self.app.run(
            host="0.0.0.0",
            port=self._d.env_by_tags("webport").valueint,
            debug=debug,
        )

    # only need to check for undervoltage during runtime in monitor_dmesg
    # let's keep this around for the moment
    def check_undervoltage(self):
        # next check if there were under-voltage events (this is likely only relevant on an RPi)
        self._d.env_by_tags("under_voltage").value = False
        board = self._d.env_by_tags("board_name").valuestr
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

    def pi5_usb_current_limited(self):
        try:
            with open("/chosen/power/usb_max_current_enable", "r") as f:
                text = f.read().strip()
                if text == "0":
                    print_err("USB current limited to 600mA, this is only sufficient for a single SDR")
                    return True
                return False
        except:
            return False


    def monitor_dmesg(self):
        while True:
            try:
                # --follow-new: Wait and print only new messages.
                proc = subprocess.Popen(
                    ["dmesg", "--follow-new"],
                    stderr=subprocess.STDOUT,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    text=True,
                )
                if proc.stdout != None:
                    while line := proc.stdout.readline():
                        if "New USB device found" in line or "USB disconnect" in line:
                            self._sdrdevices.ensure_populated()
                        if "Undervoltage" in line or "under-voltage" in line:
                            self._d.env_by_tags("under_voltage").value = True
                            self.undervoltage_epoch = time.time()
                        # print_err(f"dmesg: {line.rstrip()}")

            except:
                print_err(traceback.format_exc())

            # this shouldn't happen
            print_err("monitor_dmesg: unexpected exit")
            time.sleep(3600)

    def set_tz(self, timezone):
        # timezones don't have spaces, only underscores
        # replace spaces with underscores to correct this common error
        timezone = timezone.replace(" ", "_")

        success = self.set_system_tz(timezone)
        if success:
            self._d.env("FEEDER_TZ").list_set(0, timezone)
        else:
            report_issue(f"timezone {timezone} probably invalid, defaulting to UTC")
            self._d.env("FEEDER_TZ").list_set(0, "UTC")
            self.set_system_tz("UTC")

    def set_system_tz(self, timezone):
        # timedatectl can fail on dietpi installs (Failed to connect to bus: No such file or directory)
        # thus don't rely on timedatectl and just set environment for containers regardless of timedatectl working
        try:
            print_err(f"calling timedatectl set-timezone {timezone}")
            subprocess.run(["timedatectl", "set-timezone", f"{timezone}"], check=True)
        except subprocess.SubprocessError:
            print_err(f"failed to set up timezone ({timezone}) using timedatectl, try dpkg-reconfigure instead")
            try:
                subprocess.run(["test", "-f", f"/usr/share/zoneinfo/{timezone}"], check=True)
            except:
                print_err(f"setting timezone: /usr/share/zoneinfo/{timezone} doesn't exist")
                return False
            try:
                subprocess.run(["ln", "-sf", f"/usr/share/zoneinfo/{timezone}", "/etc/localtime"])
                subprocess.run("dpkg-reconfigure --frontend noninteractive tzdata", shell=True)
            except:
                pass

        return True

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

    def geojson(self):
        print_err("got geojson request")
        if self._d.is_enabled("run_shipfeeder"):
            return self.ais_file("geojson")
        return ("{}", 204)  # HTTPStatus.NO_CONTENT

    def iconspng(self):
        print_err("got icons.png request")
        return self.ais_file("icons.png")

    # get the requested file from the ais_catcher running in the shipfeeder docker container
    def ais_file(self, file):
        res = requests.request(
            method="GET",
            url=f"http://localhost:{self._d.env_by_tags('aiscatcherport').valueint}/{file}",
            headers={k: v for k, v in request.headers if k.lower() != "host"},  # exclude 'host' header
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
        )

        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        ]
        headers = [(k, v) for k, v in res.raw.headers.items() if k.lower() not in excluded_headers]

        response = Response(res.content, res.status_code, headers=headers)
        return response

    def hotspot_test(self):
        return render_template("hotspot.html", version="123", comment="comment", ssids=list(range(20)))

    def restarting(self):
        return render_template("restarting.html")

    def shutdownpage(self):
        if self.exiting:
            return render_template("shutdownpage.html")
        else:
            return render_template("restarting.html")

    def restart(self):
        if self.exiting:
            return "exiting"

        self._system._restart.wait_restart_done(timeout=0.9)
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
                subprocess.run(
                    f"docker exec {uf_container} pkill collectd",
                    timeout=10.0,
                    shell=True,
                    check=True,
                )
            except:
                report_issue(f"{context}: docker exec failed - backed up graph data might miss up to 6h")
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
                        return

                report_issue(f"{context}: writeback timed out - backed up graph data might miss up to 6h")

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
                            uf_path = (
                                adsb_path / "ultrafeeder" / str(self._d.env_by_tags("mf_ip").list_get(microIndex))
                            )

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
                            if graphs_path.exists():
                                backup_zip.write(graphs_path, arcname=graphs_path.relative_to(adsb_path))
                            else:
                                report_issue(f"graphs1090 backup failed, file not found: {graphs_path}")

            except BrokenPipeError:
                report_issue(f"warning: backup download aborted mid-stream")

        thread = threading.Thread(
            target=zip2fobj,
            kwargs={
                "fobj": pipeIn,
                "include_graphs": include_graphs,
                "include_heatmap": include_heatmap,
            },
        )
        thread.start()

        site_name = self._d.env_by_tags("site_name_sanitized").list_get(0)
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
            subprocess.call("/opt/adsb/docker-compose-adsb down -t 30", timeout=40.0, shell=True)
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
        zt_network = self._d.env_by_tags("zerotierid").valuestr
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

        # adjust the planes per day stuff to potentially more / less microsites
        self.load_planes_seen_per_day()

        # make sure the cpuinfo files for stage2 exist before calling compose up
        create_fake_info([0] + self.micro_indices())

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

    def scan_wifi(self):
        wifi_ssids = []

        if self.wifi is None:
            self.wifi = Wifi()
        self.wifi.scan_ssids()
        wifi_ssids = self.wifi.ssids

        jsonString = json.dumps(
            {
                "ssids": wifi_ssids,
            },
        )
        return Response(jsonString, mimetype="application/json")

    # to avoid compatibility issues and migration issues when upgrading, we use a rather
    # inconsistent naming scheme for the serial number Env variables
    def sdr_serial_name_from_purpose(self, purpose):
        if "other" not in purpose:
            return f"{purpose}serial"
        return purpose

    def serial_env_names(self):
        return {self.sdr_serial_name_from_purpose(p) for p in self._sdrdevices.purposes()}

    def configured_serials(self):
        return {
            serial for serial in {self._d.env_by_tags(e).valuestr for e in self.serial_env_names()} if serial != ""
        }

    def closest_airport(self, lat, lon):
        airport, status = generic_get_json(f"https://adsb.im/api/closest_airport/{lat}/{lon}", timeout=10.0)
        if status != 200:
            print_err(f"closest_airport({lat}, {lon}) failed with status {status}")
            return None
        return airport

    def sdr_info(self):
        # get our guess for the right SDR to frequency mapping
        # and then update with the actual settings
        serial_guess: Dict[str, str] = self._sdrdevices.addresses_per_frequency
        print_err(f"serial guess: {serial_guess}")
        serials: Dict[str, str] = {
            f: self._d.env_by_tags(self.sdr_serial_name_from_purpose(f)).valuestr
            for f in self._sdrdevices.purposes()
            if "other" not in f
        }
        configured_serials = self.configured_serials()
        available_serials: list[str] = [sdr._serial for sdr in self._sdrdevices.sdrs]
        for f in ["978", "1090"]:
            if (not serials[f] or serials[f] not in available_serials) and serial_guess[f] not in configured_serials:
                serials[f] = serial_guess[f]

        print_err(f"sdr_info->frequencies: {str(serials)}")
        sdr_warning = ""
        max_sdr_per_bus = 4 if "x86" in self._d.env_by_tags("board_name").valuestr else 3
        buscount: Dict[str, int] = {}
        for sdr in self._sdrdevices.sdrs:
            buscount[sdr._address[:3]] = buscount.get(sdr._address[:3], 0) + 1
            if buscount[sdr._address[:3]] > max_sdr_per_bus:
                sdr_warning += f"There are possibly too many SDRs on bus {sdr._address[:3]}. "
                break
        jsonString = json.dumps(
            {
                "sdrdevices": [sdr._json for sdr in self._sdrdevices.sdrs],
                "sdr_warning": sdr_warning,
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

    def sdr_config(self, value):
        try:
            sdr_data_list = json.loads(value)
        except:
            print_err(f"sdr_config: got {value} and can't parse as JSON")
            return
        if not type(sdr_data_list) == list:
            print_err(f"sdr_config: got {sdr_data_list} and not a list")
            return
        print_err(f"sdr_config: got {sdr_data_list}")
        for sdr_data in sdr_data_list:
            sdr = self._sdrdevices.get_sdr_by_serial(sdr_data.get("serial"))
            if sdr is not self._sdrdevices.null_sdr:
                if all(
                    {
                        sdr_data.get("serial") == sdr._serial,
                        sdr_data.get("purpose") == sdr.purpose,
                        sdr_data.get("gain") == sdr.gain,
                        sdr_data.get("biastee") == sdr.biastee,
                    }
                ):
                    continue
                idx = -1
                for i in range(len(self._sdrdevices.sdrs)):
                    if sdr == self._sdrdevices.sdrs[i]:
                        idx = i
                        break
                print_err(f"modifying SDR #{idx} id: {id(sdr)} sdr: {sdr}")
                if sdr_data["purpose"] == "other":
                    sdr_data["purpose"] = f"other-{idx}"
                if sdr_data["purpose"] != sdr.purpose:
                    # remove the SDR from the old purpose and add for the new one
                    if sdr.purpose != "":
                        if sdr.purpose.startswith("other"):
                            for i in range(16):
                                if self._d.env_by_tags(f"other-{i}").value == sdr._serial:
                                    self._d.env_by_tags(f"other-{i}").value = ""
                        else:
                            self._d.env_by_tags(self._sdrdevices.purpose_env(sdr.purpose)).value = ""
                        self._d.env_by_tags(self._sdrdevices.purpose_env(sdr.purpose)).value = ""
                    # if another SDR had that purpose, remove that and switch it to unsassigned
                    exist_serial = self._d.env_by_tags(self._sdrdevices.purpose_env(sdr_data["purpose"])).valuestr
                    if exist_serial != "":
                        previous_sdr = self._sdrdevices.get_sdr_by_serial(exist_serial)
                        if previous_sdr is not self._sdrdevices.null_sdr:
                            print_err(
                                f"SDR serial {exist_serial} was previously assigned for purpose {sdr_data['purpose']}"
                            )
                            previous_sdr.purpose = ""
                    self._d.env_by_tags(self._sdrdevices.purpose_env(sdr_data["purpose"])).value = sdr_data["serial"]
                gainenv, biasteeenv = self._sdrdevices.set_sdr_data(sdr, sdr_data)
                print_err(
                    f"got env names {gainenv} and {biasteeenv} to set gain {sdr_data['gain']} and biastee {sdr_data['biastee']}"
                )
                if gainenv:
                    gain = sdr_data["gain"]
                    # all this SHOULD have been validated already client-side
                    # let's make sure we don't have 'auto' in there for containers that
                    # don't support it
                    if not sdr.purpose in ["1090", "1090_2", "978", "ais", "sonde"] and "auto" in gain:
                        if sdr.purpose in ["acars", "acars_2"] and sdr._type != "airspy":
                            gain = "-10"
                        else:
                            gain = "0"
                    if sdr._type == "airspy" and sdr.purpose == "1090":
                        gain = self.adjust_airspy_gain(gain)
                        self._d.env_by_tags("gain_airspy").value = gain
                    if sdr._type == "rtlsdr" and not (sdr.purpose in ["acars", "acars_2"] and gain == "-10"):
                        if "auto" in gain:
                            pass
                        else:
                            numgain = make_int(gain)
                            if numgain < 0:
                                gain = "0"
                            elif numgain >= 50:
                                gain = "49.6"
                    elif sdr._type == "sdrplay" and gain != "" and gain != "-10":
                        # I don't understand why gain values for hfdl are different?
                        if sdr.purpose == "hfdl":
                            if gain != "":
                                numgain = make_int(gain)
                                if numgain <= 0:
                                    gain = "0"
                                elif numgain > 45:
                                    gain = "45"
                        elif "auto" in gain:
                            pass
                        else:
                            numgain = make_int(gain)
                            if numgain < 20:
                                gain = "20"
                            elif numgain > 59:
                                gain = "59"
                    sdr.gain = gain
                    self._d.env_by_tags(gainenv).value = gain
                if biasteeenv:
                    self._d.env_by_tags(biasteeenv).value = sdr_data["biastee"]
                print_err(f"modified SDR id: {id(sdr)} sdr: {sdr}")
            else:
                print_err(f"SDR with serial {sdr_data['serial']} not found")
        print_err(f"updated SDRs: {self._sdrdevices.sdrs}")
        return

    def uf_suffix(self, i):
        suffix = f"uf_{i}" if i != 0 else "ultrafeeder"
        if self._d.env_by_tags("aggregator_choice").value == "nano":
            suffix = "nanofeeder"
        return suffix

    def stats(self):
        # collect the stats for each microfeeder and ensure that they are all the same
        # length by padding with zeros (that means the value for days for which we have
        # no data is 0)
        plane_stats = []
        l = 0
        for i in [0] + self.micro_indices():
            plane_stats.append([len(self.planes_seen_per_day[i])] + self.plane_stats[i])
            l = max(l, len(plane_stats[-1]))
        for i in range(len(plane_stats)):
            plane_stats[i] = plane_stats[i] + [0] * (l - len(plane_stats[i]))
        return Response(json.dumps(plane_stats), mimetype="application/json")

    def stage2_stats(self):
        ret = []
        for i in [0] + self.micro_indices():
            if i == 0 and not self._d.is_enabled("stage2"):
                # if this is supposed to be a feeder by itself, make sure it actually
                # has a source of data...
                # print_err("check an actual feeder that is not a stage2")
                configured_serials = self.configured_serials()
                # print_err(
                #     f"configured serials: {configured_serials} remote_sdr: {self._d.env_by_tags('remote_sdr').value}"
                # )
                if len(configured_serials) == 0:
                    if self._d.env_by_tags("remote_sdr").value == "":
                        print_err("neither an SDR nor a remote SDR is configured")
                        ret.append(
                            {
                                "pps": 0,
                                "mps": 0,
                                "uptime": 0,
                                "planes": 0,
                                "tplanes": 0,
                                "nosdr": 1,
                            }
                        )
                        continue
            tplanes = len(self.planes_seen_per_day[i])
            ip = self._d.env_by_tags("mf_ip").list_get(i)
            ip, triplet = mf_get_ip_and_triplet(ip)
            suffix = self.uf_suffix(i)
            try:
                with open(f"/run/adsb-feeder-{suffix}/readsb/stats.prom") as f:
                    uptime = 0
                    found = 0
                    pps = 0
                    mps = 0
                    planes = 0
                    for line in f:
                        if "position_count_total" in line:
                            pps = int(line.split()[1]) / 60
                            # show precise position rate if less than 1
                            pps = round(pps, 1) if pps < 1 else round(pps)
                            found |= 1
                        if "readsb_messages_valid" in line:
                            mps = round(int(line.split()[1]) / 60)
                            found |= 4
                        if "readsb_aircraft_with_position" in line:
                            planes = int(line.split()[1])
                            found |= 8
                        if i != 0 and f'readsb_net_connector_status{{host="{ip}"' in line:
                            uptime = int(line.split()[1])
                            found |= 2
                        if i == 0 and "readsb_uptime" in line:
                            uptime = int(int(line.split()[1]) / 1000)
                            found |= 2
                        if found == 15:
                            break
                    ret.append(
                        {
                            "pps": pps,
                            "mps": mps,
                            "uptime": uptime,
                            "planes": planes,
                            "tplanes": tplanes,
                        }
                    )
            except FileNotFoundError:
                ret.append({"pps": 0, "mps": 0, "uptime": 0, "planes": 0, "tplanes": tplanes})
            except:
                print_err(traceback.format_exc())
                ret.append({"pps": 0, "mps": 0, "uptime": 0, "planes": 0, "tplanes": tplanes})
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

    def generate_agg_structure(self):
        aggregators = copy.deepcopy(self.all_aggregators)
        n = len(self.micro_indices()) + 1
        matrix = [0] * n
        active_aggregators = []
        for idx in range(len(aggregators)):
            agg = aggregators[idx][0]
            status_link_list = aggregators[idx][3]
            template_link = status_link_list[0]
            final_link = template_link
            agg_enabled = False
            for i in range(n):
                agg_enabled |= self._d.list_is_enabled(agg, i)
                matrix[i] |= 1 << idx if self._d.list_is_enabled(agg, i) else 0
                if template_link.startswith("/"):
                    final_link = template_link.replace("STG2IDX", "" if i == 0 else f"_{i}")
                else:
                    match = re.search("<([^>]*)>", template_link)
                    if match:
                        final_link = template_link.replace(match.group(0), self._d.env(match.group(1)).list_get(i))
                if i == 0:
                    status_link_list[0] = final_link
                else:
                    status_link_list.append(final_link)

            if agg_enabled:
                active_aggregators.append(aggregators[idx])

        agg_debug_print = f"final aggregator structure: {active_aggregators}"
        if agg_debug_print != self.last_aggregator_debug_print:
            self.last_aggregator_debug_print = agg_debug_print
            print_err(agg_debug_print)

        self.agg_matrix = matrix
        self.agg_structure = active_aggregators

    def cache_agg_status(self):
        with self.cache_agg_status_lock:
            now = time.time()
            if now < self.last_cache_agg_status + 5:
                return
            self.last_cache_agg_status = now

        # print_err("caching agg status")

        # launch all the status checks there are in separate threads
        # they will be requested by the index page soon
        for entry in self.agg_structure:
            agg = entry[0]
            for idx in [0] + self.micro_indices():
                if self._d.list_is_enabled(agg, idx):
                    threading.Thread(target=self.get_agg_status, args=(agg, idx)).start()

    def get_agg_status(self, agg, idx):

        status = self._agg_status_instances.get(f"{agg}-{idx}")
        if status is None:
            status = self._agg_status_instances[f"{agg}-{idx}"] = AggStatus(
                agg,
                idx,
                self._d,
                f"http://127.0.0.1:{self._d.env_by_tags('webport').valueint}",
                self._system,
            )

        res = {
            "beast": status.beast,
            "mlat": status.mlat,
        }

        if agg == "adsbx":
            res["adsbxfeederid"] = self._d.env_by_tags("adsbxfeederid").list_get(idx)
        elif agg == "adsblol":
            res["adsblollink"] = (self._d.env_by_tags("adsblol_link").list_get(idx),)
        elif agg == "alive":
            res["alivemaplink"] = (self._d.env_by_tags("alivemaplink").list_get(idx),)

        return res

    def agg_status(self, agg):
        # print_err(f'agg_status(agg={agg})')
        if agg == "im":
            return json.dumps(self._im_status.check())

        self.cache_agg_status()

        res = dict()

        # collect the data retrieved in the threads, this works due do each agg status object having a lock
        for idx in [0] + self.micro_indices():
            if self._d.list_is_enabled(agg, idx):
                res[idx] = self.get_agg_status(agg, idx)

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

    def extract_channel(self) -> tuple[str, str]:
        channel = self._d.env_by_tags("base_version").valuestr
        if channel:
            match = re.search(r"\((.*?)\)", channel)
            if match:
                channel = match.group(1)
        branch = channel
        if channel in ["stable", "beta", "main"]:
            channel = ""
        if channel and not channel.startswith("origin/"):
            channel = f"origin/{channel}"
        return channel, branch

    def clear_range_outline(self, idx=0):
        suffix = self.uf_suffix(idx)
        print_err(f"resetting range outline for {suffix}")
        setGainPath = pathlib.Path(f"/run/adsb-feeder-{suffix}/readsb/setGain")

        self.waitSetGainRace()
        string2file(path=setGainPath, string=f"resetRangeOutline", verbose=True)

    def waitSetGainRace(self):
        # readsb checks this the setGain file every 0.2 seconds
        # avoid races by only writing to it every 0.25 seconds
        wait = self.lastSetGainWrite + 0.25 - time.time()

        if wait > 0:
            time.sleep(wait)

        self.lastSetGainWrite = time.time()

    def set_rpw(self):
        issues_encountered = False
        success, output = run_shell_captured(f"echo 'root:{self.rpw}' | chpasswd")
        if not success:
            print_err(f"failed to overwrite root password: {output}")
            issues_encountered = True

        if os.path.exists("/etc/ssh/sshd_config"):
            success, output = run_shell_captured(
                "sed -i -e '/^PermitRootLogin.*/d' -e '/^PasswordAuthentication no.*/d' /etc/ssh/sshd_config &&"
                + "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && "
                + "systemctl restart sshd",
                timeout=5,
            )
            if not success:
                print_err(f"failed to allow root ssh login: {output}")
                issues_encountered = True

        success, output = run_shell_captured(
            "systemctl is-enabled ssh || systemctl is-enabled dropbear || "
            + "systemctl enable --now ssh || systemctl enable --now dropbear",
            timeout=60,
        )
        if not success:
            print_err(f"failed to enable ssh: {output}")
            issues_encountered = True

        if issues_encountered:
            report_issue("failure while setting root password, check logs for details")

    def unique_site_name(self, name, idx=-1):
        # make sure that a site name is unique - if the idx is given that's
        # the current value and excluded from the check
        existing_names = self._d.env_by_tags("site_name")
        names = [existing_names.list_get(n) for n in range(0, len(existing_names.value)) if n != idx]
        while name in names:
            name += "_"
        return name

    def get_base_info(self, n, do_import=False):
        mf_ip = self._d.env_by_tags("mf_ip").list_get(n)
        port = self._d.env_by_tags("mf_port").list_get(n)
        if not port:
            port = "80"
        ip, triplet = mf_get_ip_and_triplet(mf_ip)

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
                self._d.env_by_tags("site_name").list_set(n, self.unique_site_name(base_info["name"], idx=n))
                if mf_ip in ["local", "local2"]:
                    self._d.env_by_tags("site_name").list_set(
                        n, self.unique_site_name(f"{base_info['name']} {mf_ip}", idx=n)
                    )
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

            # stage2 nanofeeder / nanofeeder_2 are local and local2
            if mf_ip == "local":
                if self._d.is_enabled("airspy"):
                    self._d.env_by_tags("airspyurl").list_set(n, "http://airspy_adsb")
                    self._d.env_by_tags("rtlsdrurl").list_set(n, "")
                elif self._d.env_by_tags("readsb_device_type").value == "rtlsdr":
                    self._d.env_by_tags("rtlsdrurl").list_set(n, "http://nanofeeder")
                    self._d.env_by_tags("airspyurl").list_set(n, "")
                else:
                    self._d.env_by_tags("rtlsdrurl").list_set(n, "")
                    self._d.env_by_tags("airspyurl").list_set(n, "")
            elif mf_ip == "local2":
                # local2 only supports rtl-sdr as the primary use case is 2 rtl-sdr with differing
                # gain. otherwise would need setting up more code to run a 2nd airspy container for
                # example
                self._d.env_by_tags("rtlsdrurl").list_set(n, "http://nanofeeder_2")
            else:
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
        check_ports = ["80", "1099"]
        if "," in ip:
            # if the user specifies a specific port, assume it's not an adsb.im install
            check_ports = []
        ip, triplet = mf_get_ip_and_triplet(ip)
        json_dict = {}
        for port in check_ports:
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
            "--add-host",
            "host.docker.internal:host-gateway",
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
        os.makedirs(self._d.config_path / "ultrafeeder", exist_ok=True)
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
            report_issue(f"ERROR when importing graphs and history from {ip}")
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
        n = self._d.env_by_tags("num_micro_sites").valueint

        # store the IP address so that get_base_info works
        # and assume port is 80 (get_base_info will fix that if it's wrong)
        self._d.env_by_tags("mf_ip").list_set(n + 1, key)
        self._d.env_by_tags("mf_port").list_set(n + 1, "80")
        self._d.env_by_tags("mf_brofm").list_set(n + 1, brofm)

        if not is_adsbim:
            # well that's unfortunate
            # we might get asked to create a UI for this at some point. Not today, though
            n += 1
            name = self.unique_site_name(micro_data.get("micro_site_name"))
            print_err(f"Micro feeder at {key} is not an adsb.im feeder, adding with index {n}, using name {name}")
            self._d.env_by_tags("num_micro_sites").value = n
            self._d.env_by_tags("site_name").list_set(n, name)
            self._d.env_by_tags("lat").list_set(n, micro_data.get("micro_lat", ""))
            self._d.env_by_tags("lon").list_set(n, micro_data.get("micro_lon", ""))
            self._d.env_by_tags("alt").list_set(n, micro_data.get("micro_alt", ""))
            self._d.env_by_tags("tz").list_set(n, "UTC")
            self._d.env_by_tags("mf_version").list_set(n, "not an adsb.im feeder")
            self._d.env_by_tags(["uat978", "is_enabled"]).list_set(n, uat)
            # accessing the microfeeder envs will create them
            for e in self._d.stage2_envs:
                e.list_get(n)
            # create fake cpu info for airnav
            create_fake_info([0] + self.micro_indices())
            self.plane_stats.append([])
            self.planes_seen_per_day.append(set())
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
        # accessing the microfeeder envs will create them
        for e in self._d.stage2_envs:
            e.list_get(n)
        # create fake cpu info for airnav
        create_fake_info([0] + self.micro_indices())
        self.plane_stats.append([])
        self.planes_seen_per_day.append(set())

        return (True, "")

    def remove_micro_site(self, num):
        # carefully shift everything down
        print_err(f"removing micro site {num}")

        # deal with plane stats
        for i in range(num, self._d.env_by_tags("num_micro_sites").valueint):
            self.plane_stats[i] = self.plane_stats[i + 1]
            self.planes_seen_per_day[i] = self.planes_seen_per_day[i + 1]

        self.plane_stats.pop()
        self.planes_seen_per_day.pop()

        # deal with env vars
        log_consistency_warning(False)
        for e in self._d.stage2_envs:
            print_err(f"shifting {e.name} down and deleting last element {e._value}")
            for i in range(num, self._d.env_by_tags("num_micro_sites").valueint):
                e.list_set(i, e.list_get(i + 1))
            while len(e._value) > self._d.env_by_tags("num_micro_sites").valueint:
                e.list_remove()
        self._d.env_by_tags("num_micro_sites").value = self._d.env_by_tags("num_micro_sites").valueint - 1
        log_consistency_warning(True)
        # now read them in to get a consistency warning if needed
        read_values_from_config_json(check_integrity=True)

    def edit_micro_site(self, num: int, site_name, ip, uat, brofm, new_idx: int):
        print_err(
            f"editing micro site {num} from {self._d.env_by_tags('site_name').list_get(num)} at "
            + f"{self._d.env_by_tags('mf_ip').list_get(num)} to {site_name} at {ip}"
            + (f" (new index {new_idx})" if new_idx != num else "")
        )
        if new_idx < 0 or new_idx > self._d.env_by_tags("num_micro_sites").valueint:
            print_err(f"invalid new index {new_idx}, ignoring")
            new_idx = num
        old_ip = str(self._d.env_by_tags("mf_ip").list_get(num))
        if old_ip != ip:
            if any([s in ip for s in ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "..", "$"]]):
                print_err(f"found suspicious characters in IP address {ip} - let's not use this in a command")
                return (False, f"found suspicious characters in IP address {ip} - rejected")
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
                            f"/opt/adsb/docker-compose-adsb down uf_{num} -t 30",
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

        # now that all the editing has been done, move things around if needed
        if new_idx != num:
            print_err(f"moving micro site {num} to {new_idx}")

            for e in self._d.stage2_envs:
                e.list_move(num, new_idx)
            self.plane_stats.insert(new_idx, self.plane_stats.pop(num))
            self.planes_seen_per_day.insert(new_idx, self.planes_seen_per_day.pop(num))

        return (True, "")

    def setRtlGain(self):
        if self._d.is_enabled("stage2_nano") or self._d.env_by_tags("aggregator_choice").value == "nano":
            gaindir = pathlib.Path("/opt/adsb/config/nanofeeder/globe_history/autogain")
            setGainPath = pathlib.Path("/run/adsb-feeder-nanofeeder/readsb/setGain")
        else:
            gaindir = pathlib.Path("/opt/adsb/config/ultrafeeder/globe_history/autogain")
            setGainPath = pathlib.Path("/run/adsb-feeder-ultrafeeder/readsb/setGain")
        try:
            gaindir.mkdir(exist_ok=True, parents=True)
        except:
            pass
        gain = self._d.env_by_tags(["1090gain"]).value

        # autogain is configured via the container env vars to be always enabled
        # so we can change gain on the fly without changing env vars
        # for manual gain the autogain script in the container can be asked to do nothing
        # by touching the suspend file

        # the container based autogain script is never used now but the env var
        # READSB_GAIN=autogain must remain set so we can change the gain
        # without recreating the container, be it a change to a number or to
        # 'auto' gain built into readsb
        if False:
            (gaindir / "suspend").unlink(missing_ok=True)
        else:
            (gaindir / "suspend").touch(exist_ok=True)

            # this file sets the gain on readsb start
            string2file(path=(gaindir / "gain"), string=f"{gain}\n")

            # this adjusts the gain while readsb is running
            self.waitSetGainRace()
            string2file(path=setGainPath, string=f"{gain}\n")

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

    def update_hfdlobserver_config(self):
        if self._d.is_enabled("hfdlobserver"):
            config_template = pathlib.Path("/opt/adsb/hfdlobserver/compose/settings.yaml.sample")
            config_lines = config_template.read_text().splitlines()
            local_config = "%LOCAL_EDITS_DONT_MANAGE%=1" in config_lines
            # we have config settings or the user has edited the file themselves - etiher way we want to run the container
            self._d.env_by_tags("run_hfdlobserver").value = local_config or (
                self._d.env_by_tags("hfdlobserver_feed_id").value != ""
                and self._d.env_by_tags("hfdlobserver_ip").value != ""
            )
            if local_config:
                print_err("user requested not to manage hfdlobserver config")
                return
            if not self._d.env_by_tags("run_hfdlobserver").value:
                print_err(
                    f"hfdlobserver not enabled {self._d.env_by_tags('hfdlobserver_feed_id').value} / {self._d.env_by_tags('hfdlobserver_ip').value}"
                )
                return
            placeholders = [
                "hfdlobserver_feed_id",
                "hfdlobserver_ip",
            ]
            for p in placeholders:
                config_lines = [l.replace("%" + p + "%", str(self._d.env_by_tags(p).value)) for l in config_lines]
            config = pathlib.Path("/opt/adsb/hfdlobserver/compose/settings.yaml")
            config_backup = pathlib.Path("/opt/adsb/hfdlobserver/compose/settings.yaml.bak")
            if config.exists():
                config.rename(config_backup)
            with open(config, "w") as f:
                f.write("\n".join(config_lines))
            config.chmod(0o644)
            print_err("hfdlobserver config updated")
        else:
            self._d.env_by_tags("run_hfdlobserver").value = False

    def update_sonde_config(self):
        # is this enabled and configured?
        if (
            self._d.is_enabled("sonde")
            and self._d.env_by_tags("sondeserial").value
            and self._d.env_by_tags("sonde_sdr_type").value
        ):
            config_template = pathlib.Path("/opt/adsb/radiosonde/station.cfg.template")
            config_lines = config_template.read_text().splitlines()
            if "%LOCAL_EDITS_DONT_MANAGE%=1" in config_lines:
                # the user told us not to mess with their changes
                print_err("user requested not to manage radiosonde config")
                return
            placeholders = [
                "sonde_sdr_type",
                "sondeserial",
                "sonde_device_ppm",
                "sondegain",
                "sondebiastee",
                "sonde_min_freq",
                "sonde_max_freq",
                "sonde_callsign",
                "sonde_share_position",
            ]
            for p in placeholders:
                value = self._d.env_by_tags(p).value
                # Convert "auto" to "-1" for radiosonde autogain
                if p == "sondegain" and str(value).startswith("auto"):
                    value = "-1"
                config_lines = [l.replace("%" + p + "%", str(value)) for l in config_lines]
            placeholders = [
                "lat",
                "lon",
                "alt",
            ]
            for p in placeholders:
                config_lines = [
                    l.replace("%" + p + "%", str(self._d.env_by_tags(p).list_get(0))) for l in config_lines
                ]

            new_config = "\n".join(config_lines)

            config = pathlib.Path("/opt/adsb/radiosonde/station.cfg")
            config_backup = pathlib.Path("/opt/adsb/radiosonde/station.cfg.bak")

            if config.exists():
                try:
                    config.rename(config_backup)
                except:
                    # if the station.cfg doesn't exist when compose up is called, docker will create
                    # a directory named station.cfg which needs to be removed for us to be able to
                    # proceed
                    try:
                        config.rmdir()
                    except:
                        pass

            with open(config, "w") as f:
                f.write(new_config)
            config.chmod(0o644)
            # print_err("radiosonde config updated")

            if config_backup.exists():
                with open(config_backup, "r") as f:
                    old_config = f.read()
                    if old_config != new_config:
                        print_err(f"radiosonde: config / station.cfg has changed, restarting container")
                        success, output = run_shell_captured(f"docker restart radiosonde")

    def adjust_airspy_gain(self, gain):
        if gain.startswith("auto"):
            return "auto"
        elif make_int(gain) > 21:
            return "21"
        elif make_int(gain) < 0:
            return "0"
        return gain

    def handle_non_adsb(self):
        # if the user explicitly says they don't want ADS-B, then don't
        # assign any SDRs to ADS-B functions
        if not self._d.is_enabled("is_adsb_feeder"):
            print_err("is_adsb_feeder not selected, disabling ADS-B")
            self._d.env_by_tags("aggregator_choice").value = "nonadsb"
            self._d.env_by_tags("readsb_device_type").value = ""
            self._d.env_by_tags("1090serial").value = ""
            self._d.env_by_tags("978serial").value = ""
            self._d.env_by_tags("1090_2serial").value = ""
            self._d.env_by_tags("mlathub_disable").value = True
            for sdr in self._sdrdevices.sdrs:
                if sdr.purpose in ["1090", "1090_2", "978"]:
                    sdr.purpose = ""
            # while these SDRs can be used by other containers, these three containers
            # are specifically for ADS-B
            self._d.env_by_tags("airspy").value = False
            self._d.env_by_tags("sdrplay").value = False
            self._d.env_by_tags("uat978").list_set(0, False)
        else:
            print_err("no action on ADS-B functions")
        # these two are a 1:1 map, so we can just enable them
        # the rest are controlled by their individual checkboxes which are
        # already propagagted
        if self._d.is_enabled("is_sonde_feeder"):
            self._d.env_by_tags("sonde").value = True
        if self._d.is_enabled("is_ais_feeder"):
            self._d.env_by_tags("shipfeeder").value = True

    def handle_temp_sensor(self, temp_sensor, dht22_pin=0):
        if temp_sensor.value == "dht22":
            if self._d.env_by_tags("board_name").valuestr.startswith("Raspberry Pi 5"):
                # pigpiod doesn't work on the pi5, rely on native dht program
                default_file_content = f"GPIO_PIN={dht22_pin}\n"
            elif self._d.env_by_tags("board_name").valuestr.startswith("Raspberry Pi"):
                # this is not a commonly used feature, so let's install dependencies here
                success, output = run_shell_captured(
                    "dpkg-query -l pigpiod 2>&1 | grep -q ii || apt install -y python3-pigpio pigpiod && systemctl enable --now pigpiod",
                    timeout=600,
                )
                if not success:
                    report_issue(f"failed to install pigpiod and python3-pigpio - check the logs for details")
                    print_err(f"failed to install pigpiod and python3-pigpio: {output}")
                    temp_sensor.value = ""
                    return
                default_file_content = f"GPIO_PIN={dht22_pin}\n"
            else:
                print_err(f"temp_sensor: {temp_sensor.value} is not supported on this board")
                temp_sensor.value = ""
                return
        elif temp_sensor.value == "temper_usb":
            # this is not a commonly used feature, so let's install dependencies here
            success, output = run_shell_captured(
                "dpkg-query -l python3-serial > /dev/null || apt install -y python3-serial",
                timeout=600,
            )
            if not success:
                report_issue(f"failed to install python3-serial - check the logs for details")
                print_err(f"failed to install python3-serial: {output}")
                temp_sensor.value = ""
                return
            default_file_content = f"DEVICE=usb-temper\n"
        elif temp_sensor.value == "bme280":
            # this is not a commonly used feature, so let's install dependencies here
            success, output = run_shell_captured(
                "dpkg-query -l python3-bme280 > /dev/null || apt install -y python3-bme280 python3-smbus",
                timeout=600,
            )
            if not success:
                report_issue(f"failed to install python3-serial - check the logs for details")
                print_err(f"failed to install python3-serial: {output}")
                temp_sensor.value = ""
                return
            success, output = run_shell_captured("lsmod | grep i2c_bcm2835 > /dev/null", timeout=30)
            if not success:
                report_issue(f"i2c is not enabled - please manually enable i2c and reboot your device")
                print_err(f"i2c is not enabled - please manually enable i2c and reboot your device")
                # but we still continue and leave things enabled
            default_file_content = f"DEVICE=bme280\n"
        else:
            _, output = run_shell_captured(
                "systemctl is-enabled adsb-temperature.service && systemctl disable --now adsb-temperature.service",
                timeout=20,
            )
            self._d.env_by_tags("graphs1090_other_temp1").value = ""
            self._d.env_by_tags("temperature_block").value = False
            self._d.env_by_tags("has_dht22").value = False
            temp_sensor.value = ""
            return

        # we have a temperature sensor and dependency install (if needed) succeeded
        # let's turn on the service
        # first, write out the default config file
        open("/opt/adsb/extras/adsb-temperature.default", "w").write(default_file_content)
        success, output = run_shell_captured(
            "systemctl is-active adsb-temperature.service || systemctl enable --now adsb-temperature.service",
            timeout=20,
        )
        if not success:
            report_issue(f"failed to enable adsb-temperature.service - check the logs for details")
            print_err(f"failed to enable adsb-temperature.service: {output}")
            temp_sensor.value = ""
            return
        self._d.env_by_tags("temperature_block").value = True
        self._d.env_by_tags("graphs1090_other_temp1").value = "/run/ambient-temperature"

    def handle_implied_settings(self):
        self.handle_non_adsb()
        if self._d.env_by_tags("aggregator_choice").value in ["micro", "nano", "nonadsb"]:
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

        # make sure we have a closest airport
        if self._d.env_by_tags("closest_airport").list_get(0) == "":
            airport = self.closest_airport(
                self._d.env_by_tags("lat").list_get(0), self._d.env_by_tags("lon").list_get(0)
            )
            if airport:
                self._d.env_by_tags("closest_airport").list_set(0, airport.get("icao", ""))

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

        if self._d.is_enabled("stage2") and self._d.env_by_tags("1090_2serial").value:
            self._d.env_by_tags("stage2_nano_2").value = True
        else:
            self._d.env_by_tags("stage2_nano_2").value = False

        for sitenum in [0] + self.micro_indices():
            site_name = str(self._d.env_by_tags("site_name").list_get(sitenum))
            sanitized = "".join(c if c.isalnum() or c in "-_." else "_" for c in site_name)
            self._d.env_by_tags("site_name_sanitized").list_set(sitenum, sanitized)

            # fixup altitude mishaps by stripping the value
            # strip meter units and whitespace for good measure
            alt = self._d.env_by_tags("alt").list_get(sitenum)
            alt_m = alt.strip().strip("m").strip()
            self._d.env_by_tags("alt").list_set(sitenum, alt_m)

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
                f"http://HOSTNAME:{self._d.env_by_tags('webport').valueint}/"
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

        # fix up airspy installs without proper serial number configuration
        if self._d.is_enabled("airspy"):
            if self._d.env_by_tags("1090serial").valuestr == "" or self._d.env_by_tags(
                "1090serial"
            ).valuestr.startswith("AIRSPY SN:"):
                self._sdrdevices.ensure_populated()
                airspy_serials = [sdr._serial for sdr in self._sdrdevices.sdrs if sdr._type == "airspy"]
                if len(airspy_serials) == 1:
                    self._d.env_by_tags("1090serial").value = airspy_serials[0]

        # make all the smart choices for plugged in SDRs - unless we are a stage2 that hasn't explicitly requested SDR support
        # only run this for initial setup or when the SDR setup is requested via the interface
        if (
            not self._d.is_enabled("stage2")
            or self._d.is_enabled("stage2_nano")
        ) and not self._d.env_by_tags("sdrs_locked").value:
            # first grab the SDRs plugged in and check if we have one identified for UAT
            env978 = self._d.env_by_tags("978serial")
            env1090 = self._d.env_by_tags("1090serial")
            if env978.value != "" and not any(
                [(sdr._serial == env978.value and sdr.purpose == "978") for sdr in self._sdrdevices.sdrs]
            ):
                env978.value = ""
            if env1090.value != "" and not any(
                [(sdr._serial == env1090.value and sdr.purpose == "1090") for sdr in self._sdrdevices.sdrs]
            ):
                env1090.value = ""
            auto_assignment = self._sdrdevices.addresses_per_frequency

            configured_serials = self.configured_serials()

            # if we have an actual asignment, that overrides the auto-assignment,
            # delete the auto-assignment
            for frequency in ["978", "1090"]:
                if auto_assignment[frequency] in configured_serials:
                    auto_assignment[frequency] = ""
            if not env1090.value and auto_assignment["1090"]:
                env1090.value = auto_assignment["1090"]
            if not env978.value and auto_assignment["978"]:
                env978.value = auto_assignment["978"]

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
            # Mode-S Beast
            modesbeast = any(
                [sdr._serial == env1090.value and sdr._type == "modesbeast" for sdr in self._sdrdevices.sdrs]
            )

            # rtl-sdr
            rtlsdr = any(sdr._type == "rtlsdr" and sdr._serial == env1090.value for sdr in self._sdrdevices.sdrs)

            if rtlsdr:
                self._d.env_by_tags("readsb_device_type").value = "rtlsdr"
            elif modesbeast:
                self._d.env_by_tags("readsb_device_type").value = "modesbeast"
            else:
                self._d.env_by_tags("readsb_device_type").value = ""

            if airspy:
                # make sure airspy gain is within bounds
                gain = self._d.env_by_tags(["1090gain"]).valuestr
                airspy_gain = self.adjust_airspy_gain(gain)
                self._d.env_by_tags(["gain_airspy"]).value = airspy_gain
                self._d.env_by_tags(["1090gain"]).value = airspy_gain
            else:
                gain = self._d.env_by_tags(["1090gain"]).valuestr
                if gain == "":
                    self._d.env_by_tags(["1090gain"]).value = "auto"

            gain = self._d.env_by_tags(["978gain"]).valuestr
            if gain == "" or gain == "auto":
                self._d.env_by_tags(["978gain"]).value = "autogain"

            if verbose & 1:
                print_err(f"in the end we have")
                print_err(f"1090serial {env1090.value}")
                print_err(f"1090_2serial {self._d.env_by_tags('1090_2serial').value}")
                print_err(f"978serial {env978.value}")
                print_err(f"airspy container is {self._d.is_enabled(['airspy'])}")
                print_err(f"SDRplay container is {self._d.is_enabled(['sdrplay'])}")
                print_err(f"dump978 container {self._d.list_is_enabled(['uat978'], 0)}")

            # if the base config is completed, lock down further SDR changes so they only happen on
            # user request
            if self.base_is_configured():
                self._d.env_by_tags("sdrs_locked").value = True

        # needs to happen even for locked SDRs due to readsb_device env var not existing before 2.3.5
        if self._d.env_by_tags("readsb_device_type").value == "rtlsdr":
            self._d.env_by_tags("readsb_device").value = self._d.env_by_tags("1090serial").value
            # set rtl-sdr 1090 gain, bit hacky but means we don't have to restart the bulky ultrafeeder for gain changes
            self.setRtlGain()
        else:
            self._d.env_by_tags("readsb_device").value = ""

        if self._d.env_by_tags("stage2_nano").value:
            do978 = bool(self._d.env_by_tags("978serial").value)

            # this code is here and not further up so get_base_info knows
            # about the various URLs for 978 / airspy / 1090
            log_consistency_warning(False)
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
            log_consistency_warning(True)
            read_values_from_config_json(check_integrity=True)

        if self._d.env_by_tags("stage2_nano_2").value:
            # this code is here and not further up so get_base_info knows
            # about the various URLs for 978 / airspy / 1090
            log_consistency_warning(False)
            self.setup_new_micro_site(
                "local2",
                uat=False,
                is_adsbim=True,
                brofm=False,
                do_import=True,
                do_restore=False,
            )
            log_consistency_warning(True)
            read_values_from_config_json(check_integrity=True)

        # set all of the ultrafeeder config data up
        self.setup_ultrafeeder_args()

        # ensure that our 1090 and 978 SDRs have the correct purpose set
        sdr1090 = self._sdrdevices.get_sdr_by_serial(self._d.env_by_tags("1090serial").valuestr)
        sdr978 = self._sdrdevices.get_sdr_by_serial(self._d.env_by_tags("978serial").valuestr)
        if not sdr1090 is self._sdrdevices.null_sdr:
            sdr1090.purpose = "1090"
        if not sdr978 is self._sdrdevices.null_sdr:
            sdr978.purpose = "978"

        # create the non-ADS-B SDR strings
        acarsserial = self._d.env_by_tags("acarsserial").valuestr
        acarssdr = self._sdrdevices.get_sdr_by_serial(acarsserial)
        if acarssdr != self._sdrdevices.null_sdr:
            acarssdr.purpose = "acars"
            if acarssdr._type == "airspy":
                self._d.env_by_tags("acarsserial_rtl").value = ""
                self._d.env_by_tags("acarsserial_airspy").value = acarsserial
                acarsstring = ""
            elif acarssdr._type == "rtlsdr":
                self._d.env_by_tags("acarsserial_rtl").value = acarsserial
                self._d.env_by_tags("acarsserial_airspy").value = ""
                acarsstring = ""
            else:
                self._d.env_by_tags("acarsserial_rtl").value = ""
                self._d.env_by_tags("acarsserial_airspy").value = ""
                acarsstring = f"driver={acarssdr._type},serial={acarsserial}"
            self._d.env_by_tags("run_acarsdec").value = self._d.is_enabled(["acarsdec"])
            if self._d.is_enabled("run_acarsdec") and self._d.env_by_tags("acars_feed_id").value == "":
                self._d.env_by_tags("acars_feed_id").value = (
                    f"{self._d.env_by_tags('initials').list_get(0)}-{self._d.env_by_tags('closest_airport').list_get(0)}-ACARS"
                )
        else:
            acarsstring = ""
            self._d.env_by_tags("run_acarsdec").value = False
        acars_2serial = self._d.env_by_tags("acars_2serial").valuestr
        acars_2sdr = self._sdrdevices.get_sdr_by_serial(acars_2serial)
        if acars_2sdr != self._sdrdevices.null_sdr:
            acars_2sdr.purpose = "acars_2"
            if acars_2sdr._type == "airspy":
                self._d.env_by_tags("acars_2serial_rtl").value = ""
                self._d.env_by_tags("acars_2serial_airspy").value = acars_2serial
                acars_2string = ""
            elif acars_2sdr._type == "rtlsdr":
                self._d.env_by_tags("acars_2serial_rtl").value = acars_2serial
                self._d.env_by_tags("acars_2serial_airspy").value = ""
                acars_2string = ""
            else:
                self._d.env_by_tags("acars_2serial_rtl").value = ""
                self._d.env_by_tags("acars_2serial_airspy").value = ""
                acars_2string = f"driver={acars_2sdr._type},serial={acars_2serial}"
            self._d.env_by_tags("run_acarsdec2").value = self._d.is_enabled(["acarsdec2"])
            if self._d.is_enabled("run_acarsdec2") and self._d.env_by_tags("acars_2_feed_id").value == "":
                self._d.env_by_tags("acars_2_feed_id").value = (
                    f"{self._d.env_by_tags('initials').list_get(0)}-{self._d.env_by_tags('closest_airport').list_get(0)}-ACARS2"
                )
        else:
            acars_2string = ""
            self._d.env_by_tags("run_acarsdec2").value = False
        vdl2serial = self._d.env_by_tags("vdl2serial").valuestr
        vdl2sdr = self._sdrdevices.get_sdr_by_serial(vdl2serial)
        if vdl2sdr != self._sdrdevices.null_sdr:
            vdl2sdr.purpose = "vdl2"
            if vdl2sdr._type == "rtlsdr":
                self._d.env_by_tags("vdl2serial_rtl").value = vdl2serial
                vdl2string = ""
                vdl2devicesettings = ""
            else:
                self._d.env_by_tags("vdl2serial_rtl").value = ""
                vdl2string = f"driver={vdl2sdr._type},serial={vdl2serial}"
                vdl2devicesettings = "biastee=true" if self._d.is_enabled(["vdl2biastee"]) else "biastee=false"
            self._d.env_by_tags("run_dumpvdl2").value = self._d.is_enabled(["dumpvdl2"])
            if self._d.is_enabled("run_dumpvdl2") and self._d.env_by_tags("vdl2_feed_id").value == "":
                self._d.env_by_tags("vdl2_feed_id").value = (
                    f"{self._d.env_by_tags('initials').list_get(0)}-{self._d.env_by_tags('closest_airport').list_get(0)}-VDLM2"
                )
        else:
            self._d.env_by_tags("vdl2serial_rtl").value = ""
            vdl2string = ""
            vdl2devicesettings = ""
            self._d.env_by_tags("run_dumpvdl2").value = False
        hfdlserial = self._d.env_by_tags("hfdlserial").valuestr
        hfdlsdr = self._sdrdevices.get_sdr_by_serial(hfdlserial)
        if hfdlsdr != self._sdrdevices.null_sdr:
            hfdlsdr.purpose = "hfdl"
            hfdlstring = f"driver={hfdlsdr._type},serial={hfdlserial}"
            if hfdlsdr._type == "sdrplay" and hfdlserial == "SDRplay w/o serial":
                hfdlstring = f"driver={hfdlsdr._type}"
            self._d.env_by_tags("run_dumphfdl").value = self._d.is_enabled(["dumphfdl"])
            if self._d.is_enabled("run_dumphfdl") and self._d.env_by_tags("hfdl_feed_id").value == "":
                self._d.env_by_tags("hfdl_feed_id").value = (
                    f"{self._d.env_by_tags('initials').list_get(0)}-{self._d.env_by_tags('closest_airport').list_get(0)}-HFDL"
                )
        else:
            hfdlstring = ""
            self._d.env_by_tags("run_dumphfdl").value = False
        sondeserial = self._d.env_by_tags("sondeserial").valuestr
        sondesdr = self._sdrdevices.get_sdr_by_serial(sondeserial)
        if sondesdr != self._sdrdevices.null_sdr:
            sondesdr.purpose = "sonde"
            sonde_sdr_type = sondesdr._type
            self._d.env_by_tags("run_sonde").value = self._d.is_enabled(["sonde"])
            if self._d.is_enabled("run_sonde") and self._d.env_by_tags("sonde_callsign").value == "":
                self._d.env_by_tags("sonde_callsign").value = (
                    f"{self._d.env_by_tags('initials').list_get(0)}-{self._d.env_by_tags('closest_airport').list_get(0)}-SONDE"
                )
        else:
            sonde_sdr_type = ""
            self._d.env_by_tags("run_sonde").value = False
        aisserial = self._d.env_by_tags("aisserial").valuestr
        aissdr = self._sdrdevices.get_sdr_by_serial(aisserial)
        if aissdr != self._sdrdevices.null_sdr:
            aissdr.purpose = "ais"
            self._d.env_by_tags("ais_sdr_type").value = aissdr._type
            self._d.env_by_tags("run_shipfeeder").value = self._d.is_enabled(["shipfeeder"])
            if self._d.is_enabled("run_shipfeeder") and self._d.env_by_tags("ais_station_name").value == "":
                self._d.env_by_tags("ais_station_name").value = (
                    f"{self._d.env_by_tags('initials').list_get(0)}-{self._d.env_by_tags('closest_airport').list_get(0)}-AIS"
                )
            self._d.env_by_tags("tar1090_aiscatcher_url").value = (
                f"http://HOSTNAME:{self._d.env_by_tags('webport').value}/"
                if self._d.is_enabled(["shipfeeder"]) and self._d.is_enabled(["show_ships_on_map"])
                else ""
            )
        else:
            self._d.env_by_tags("tar1090_aiscatcher_url").value = ""
            self._d.env_by_tags("run_shipfeeder").value = False

        # hfdlobserver is a bit different -- all we need to do is check if it's enabled
        self.update_hfdlobserver_config()

        # set the non-ADS-B SDR strings
        self._d.env_by_tags("acars_sdr_string").value = acarsstring
        self._d.env_by_tags("acars_2_sdr_string").value = acars_2string
        self._d.env_by_tags("vdl2_sdr_string").value = vdl2string
        self._d.env_by_tags("vdl2devicesettings").value = vdl2devicesettings
        self._d.env_by_tags("hfdl_sdr_string").value = hfdlstring
        self._d.env_by_tags("sonde_sdr_type").value = sonde_sdr_type.upper()

        # sort out if we need the acars_router and acarshub
        self._d.env_by_tags("acars_router").value = (
            self._d.is_enabled("run_acarsdec")
            or self._d.is_enabled("run_acarsdec2")
            or self._d.is_enabled("run_dumpvdl2")
            or self._d.is_enabled("run_dumphfdl")
            or self._d.is_enabled("hfdlobserver")
        )

        self._d.env_by_tags("acarshub_acars").value = "external" if self._d.is_enabled("run_acarsdec") else "false"
        self._d.env_by_tags("acarshub_vdl2").value = "external" if self._d.is_enabled("run_dumpvdl2") else "false"
        self._d.env_by_tags("acarshub_hfdl").value = (
            "external" if self._d.is_enabled("run_dumphfdl") or self._d.is_enabled("hfdlobserver") else "false"
        )

        self._d.env_by_tags("acarshub").value = self._d.is_enabled("acars_router")
        feed_acars_udp = "acarshub:5550;"
        feed_acars_tcp = ""
        feed_vdl2_udp = "acarshub:5555;"
        feed_vdl2_tcp = ""
        feed_hfdl_udp = "acarshub:5556;"
        feed_hfdl_tcp = ""
        if self._d.list_is_enabled("feed_acars_airframes", 0):
            feed_vdl2_tcp += "feed.airframes.io:5553;"
            feed_acars_udp += "feed.airframes.io:5550;"
            feed_hfdl_tcp += "feed.airframes.io:5556;"
        if self._d.list_is_enabled("feed_acars_acarsdrama", 0):
            feed_acars_udp += "feedthe.acarsdrama.com:5550;"
            feed_vdl2_udp += "feedthe.acarsdrama.com:5555;"
        if self._d.list_is_enabled("feed_acars_avdelphi", 0):
            feed_acars_udp += "data.avdelphi.com:5556;"
            feed_vdl2_udp += "data.avdelphi.com:5600;"
        if self._d.list_is_enabled("feed_acars_adsblol", 0):
            feed_acars_tcp += "feed-acars.adsb.lol:5550;"
            feed_vdl2_tcp += "feed-acars.adsb.lol:5552;"
            feed_hfdl_tcp += "feed-acars.adsb.lol:5551;"

        if not self._d.is_enabled(["run_acarsdec"]):
            feed_acars_udp = ""
            feed_acars_tcp = ""
        if not self._d.is_enabled(["run_dumpvdl2"]):
            feed_vdl2_udp = ""
            feed_vdl2_tcp = ""
        if not (self._d.is_enabled(["run_dumphfdl"]) or self._d.is_enabled(["hfdlobserver"])):
            feed_hfdl_udp = ""
            feed_hfdl_tcp = ""

        self._d.env_by_tags("feed_string_acars_udp").value = feed_acars_udp.rstrip(";")
        self._d.env_by_tags("feed_string_acars_tcp").value = feed_acars_tcp.rstrip(";")
        self._d.env_by_tags("feed_string_vdl2_udp").value = feed_vdl2_udp.rstrip(";")
        self._d.env_by_tags("feed_string_vdl2_tcp").value = feed_vdl2_tcp.rstrip(";")
        self._d.env_by_tags("feed_string_hfdl_udp").value = feed_hfdl_udp.rstrip(";")
        self._d.env_by_tags("feed_string_hfdl_tcp").value = feed_hfdl_tcp.rstrip(";")

        # AIS stuff -- this needs to be extended for stage 2
        self._d.env_by_tags("ais_airframes_station_id").list_set(
            0,
            (
                self._d.env_by_tags("ais_station_name").value
                if self._d.list_is_enabled(["ais_feed_airframes"], idx=0)
                else ""
            ),
        )

        # SONDE stuff
        # sadly, that's configured through an annoying yml config file
        # we're trying to be clever and edit this from a template
        self.update_sonde_config()

        if verbose or 1:
            print_err(f"ACARS container {self._d.is_enabled(['run_acarsdec'])}")
            print_err(f"ACARS2 container {self._d.is_enabled(['run_acarsdec2'])}")
            print_err(f"VDL2 container {self._d.is_enabled(['run_dumpvdl2'])}")
            print_err(f"HFDL container {self._d.is_enabled(['run_dumphfdl'])}")
            print_err(f"AIS container {self._d.is_enabled(['run_shipfeeder'])}")
            print_err(f"SONDE container {self._d.is_enabled(['run_sonde'])}")

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

        self.dozzle_yml_from_template()

        # check if we need the stage2 multiOutline job
        if self._d.is_enabled("stage2"):
            if not self._multi_outline_bg:
                self.push_multi_outline()
                self._multi_outline_bg = Background(60, self.push_multi_outline)
        else:
            self._multi_outline_bg = None

        self.generate_agg_structure()

        # do we have any temperature sensors enabled? This shouldn't be needed
        # here, but because we changed the name of the Env variable from being
        # just about the DHT22 to support multiple different ones, this is the
        # cleanest way to transition
        if self._d.env_by_tags("temp_sensor").value == "" and self._d.is_enabled("has_dht22"):
            self._d.env_by_tags("temp_sensor").value = "dht22"

    def sdr_assignments(self) -> Dict[str, Tuple[str, str, bool]]:
        assignments = {}
        for purpose in self._sdrdevices.purposes():
            serial = self._d.env_by_tags(self.sdr_serial_name_from_purpose(purpose)).valuestr
            # careful - env tags might not exist
            try:
                gain = self._d.env_by_tags(f"{purpose}gain").valuestr
            except:
                gain = ""
            try:
                biastee = bool(self._d.env_by_tags(f"{purpose}biastee").value)
            except:
                biastee = False
            assignments[purpose] = (serial, gain, biastee)
        return assignments

    def set_docker_concurrent(self, value):
        self._d.env_by_tags("docker_concurrent").value = value
        if not os.path.exists("/etc/docker/daemon.json") and value:
            # this is the default, nothing to do
            return
        try:
            with open("/etc/docker/daemon.json", "r") as f:
                daemon_json = json.load(f)
        except:
            daemon_json = {}
        new_daemon_json = daemon_json.copy()
        if value:
            del new_daemon_json["max-concurrent-downloads"]
        else:
            new_daemon_json["max-concurrent-downloads"] = 1
        if new_daemon_json != daemon_json:
            print_err(f"set_docker_concurrent({value}): applying change")
            with open("/etc/docker/daemon.json", "w") as f:
                json.dump(new_daemon_json, f, indent=2)
            # reload docker config (this is sufficient for the max-concurrent-downloads setting)
            success, output = run_shell_captured("bash -c 'kill -s SIGHUP $(pidof dockerd)'", timeout=5)
            if not success:
                print_err(f"failed to reload docker config: {output}")

    def enabled_purposes(self):
        ep = set() if self._d.env_by_tags("aggregator_choice").value == "nonadsb" else {"1090", "978"}
        if self._d.env_by_tags("aggregator_choice").value == "stage2":
            ep.add("1090_2")
        purpose_pairs = {
            ("acars", "acarsdec"),
            ("acars_2", "acarsdec2"),
            ("vdl2", "dumpvdl2"),
            ("hfdl", "dumphfdl"),
            ("ais", "shipfeeder"),
            ("sonde", "sonde"),
        }
        for purpose, tag in purpose_pairs:
            if self._d.is_enabled([tag]):
                ep.add(purpose)
        return ep

    def nonadsb_is_correctly_configured(self):
        # this will return true if at least one of the non-ADS-B protocols is enabled and all
        # of the enabled ones have their feed ID set;
        # once one of the non-ADS-B protocols is enabled, the expert page goes through the
        # update() flow and we need to ensure that the required feed IDs are set as well
        non_adsb_enabled = any(
            {
                self._d.is_enabled(["acarsdec"]),
                self._d.is_enabled(["acarsdec2"]),
                self._d.is_enabled(["dumpvdl2"]),
                self._d.is_enabled(["dumphfdl"]),
                self._d.is_enabled(["sonde"]),
                self._d.is_enabled(["shipfeeder"]),
            }
        )
        inconsistent_non_adsb_config = any(
            {
                self._d.is_enabled(["acarsdec"]) and self._d.env_by_tags("acars_feed_id").value == "",
                self._d.is_enabled(["acarsdec2"]) and self._d.env_by_tags("acars_2_feed_id").value == "",
                self._d.is_enabled(["dumpvdl2"]) and self._d.env_by_tags("vdl2_feed_id").value == "",
                self._d.is_enabled(["dumphfdl"]) and self._d.env_by_tags("hfdl_feed_id").value == "",
                self._d.is_enabled(["sonde"]) and self._d.env_by_tags("sonde_callsign").value == "",
                self._d.is_enabled(["shipfeeder"]) and self._d.env_by_tags("ais_station_name").value == "",
            }
        )
        return non_adsb_enabled and not inconsistent_non_adsb_config

    @check_restart_lock
    def update(self):
        description = """
            This is the one endpoint that handles all the updates coming in from the UI.
            It walks through the form data and figures out what to do about the information provided.
        """
        # let's try and figure out where we came from - for reasons I don't understand
        # the regexp didn't capture the site number, so let's do this the hard way
        extra_args = ""
        referer = request.headers.get("referer")
        m_arg = referer.rfind("?m=")
        if m_arg > 0:
            arg = make_int(referer[m_arg + 3 :])
        else:
            arg = 0
        if arg in self.micro_indices():
            sitenum = arg
            site = self._d.env_by_tags("site_name").list_get(sitenum)
            extra_args = f"?m={sitenum}"
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
                    brofm = is_true(form.get("micro_reduce")) and key != "add_other"
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
                    log_consistency_warning(False)
                    status, message = self.setup_new_micro_site(
                        ip,
                        uat=is_true(uat),
                        is_adsbim=is_adsbim,
                        brofm=brofm,
                        do_import=do_import,
                        do_restore=do_restore,
                        micro_data=micro_data,
                    )
                    log_consistency_warning(True)
                    read_values_from_config_json(check_integrity=True)
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
                        make_int(form.get(f"site_order_{num}")),
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

                    # we redirect to the aggregator page if this is not set
                    # thus it is imperative to set it otherwise there can be a redirect cycle
                    self._d.env_by_tags("aggregators_chosen").value = True

                    # if aggregator choice currently is "all" or "privacy", change it to
                    # "individual" as the user presumably wants to change the selection
                    if self._d.env_by_tags("aggregator_choice").valuestr in ["all", "privacy"]:
                        self._d.env_by_tags("aggregator_choice").value = "individual"

                    # NOTE: seems like these 2 variables have an unfortunate name as they indicate
                    # that at least one aggregator is selected, not that a choice has been made
                    if any([form.get(key) == "1" for key in form.keys() if "feed_acars" in key]):
                        self._d.env_by_tags("acars_aggregators_chosen").value = True
                    if any([form.get(key) == "1" for key in form.keys() if "ais_feed" in key]):
                        self._d.env_by_tags("ais_aggregators_chosen").value = True

                if key == "sdr_setup" and value == "go":
                    # user has clicked Submit on the SDR Setup page -- let's send them back there
                    self._next_url_from_director = request.url
                    self._d.env_by_tags("sdrs_locked").value = False

                if allow_insecure and key == "shutdown":
                    # schedule shutdown in 0.5 seconds
                    self._system.shutdown(delay=0.5)
                    self.exiting = True
                    return redirect(url_for("shutdownpage"))
                if allow_insecure and key == "reboot":
                    # schedule reboot in 0.5 seconds
                    self._system.reboot(delay=0.5)
                    self.exiting = True
                    return redirect(url_for("restarting"))
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
                if key == "acarshub_to_disk" and value == "go":
                    run_shell_captured("docker stop acarshub", timeout=30)
                    run_shell_captured(
                        "mkdir -p /opt/adsb/config/acarshub_data"
                        + "&& cp -f /run/acars_data/* /opt/adsb/config/acarshub_data"
                        + "&& rm -rf /run/acars_data",
                        timeout=30,
                    )
                    self._d.env_by_tags("acarshub_data_path").value = "/opt/adsb/config/acarshub_data"
                if key == "acarshub_to_run" and value == "go":
                    run_shell_captured("docker stop acarshub", timeout=30)
                    run_shell_captured(
                        "mkdir -p /run/acars_data"
                        + "&& cp -f /opt/adsb/config/acarshub_data/* /run/acars_data"
                        + "&& rm -rf /opt/adsb/config/acarshub_data",
                        timeout=30,
                    )
                    self._d.env_by_tags("acarshub_data_path").value = "/run/acars_data"
                if key == "secure_image":
                    self.set_secure_image()
                if allow_insecure and key == "toggle_hotspot":
                    self.toggle_hotspot()
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
                if key in ["enable_parallel_docker", "disable_parallel_docker"]:
                    self.set_docker_concurrent(key == "enable_parallel_docker")
                if key.startswith("update_feeder_aps"):
                    channel = key.rsplit("_", 1)[-1]
                    if channel == "branch":
                        channel, _ = self.extract_channel()
                    return self.do_feeder_update(channel)
                if key == "nightly_update" or key == "zerotier":
                    # this will be handled through the separate key/value pairs
                    pass
                if key == "os_update":
                    self._system._restart.bg_run(func=self._system.os_update)
                    self._next_url_from_director = request.url
                    return render_template("/restarting.html")
                # generic pattern to use buttons to enable or disable 'is_enabled' style env vars
                if key.endswith("--disable") and value == "go":
                    tags = [t.replace("disable", "is_enabled") for t in key.split("--")]
                    e = self._d.env_by_tags(tags)
                    if e:
                        e.value = False
                        print_err(f"disabled {tags}")
                        self._next_url_from_director = request.url
                        # this is how we disable the non-ADS-B containers on the expert page
                        # check if we are still feeding
                        if key.startswith("acarsdec") or key.startswith("dumpvdl2"):
                            self._d.env_by_tags("is_acars_feeder").value = (
                                self._d.is_enabled("acarsdec")
                                or self._d.is_enabled("acarsdec2")
                                or self._d.is_enabled("dumpvdl2")
                            )
                        if key.startswith("dumphfdl") or key.startswith("hfdlobserver"):
                            self._d.env_by_tags("is_hfdl_feeder").value = self._d.is_enabled(
                                "hfdlobserver"
                            ) or self._d.is_enabled("dumphfdl")
                        if key.startswith("shipfeeder"):
                            self._d.env_by_tags("is_ais_feeder").value = False
                        if key.startswith("sonde"):
                            self._d.env_by_tags("is_sonde_feeder").value = False

                        continue
                if key.endswith("--enable") and value == "go":
                    tags = [t.replace("enable", "is_enabled") for t in key.split("--")]
                    e = self._d.env_by_tags(tags)
                    if e:
                        e.value = True
                        print_err(f"enabled {tags}")
                        self._next_url_from_director = request.url
                        # this is how we enable the non-ADS-B containers on the expert page
                        if key.startswith("acarsdec") or key.startswith("dumpvdl2"):
                            self._d.env_by_tags("is_acars_feeder").value = True
                        if key.startswith("dumphfdl") or key.startswith("hfdlobserver"):
                            self._d.env_by_tags("is_hfdl_feeder").value = True
                        if key.startswith("shipfeeder"):
                            self._d.env_by_tags("is_ais_feeder").value = True
                        if key.startswith("sonde"):
                            self._d.env_by_tags("is_sonde_feeder").value = True
                        continue
                if key.endswith("--update") and value == "go":
                    self._next_url_from_director = request.url
                    continue
                if key.startswith("temp_sensor_") and value == "go":
                    self._d.env_by_tags("temp_sensor").value = (
                        form.get("temp_sensor", "") if key.endswith("enable") else ""
                    )
                    self.handle_temp_sensor(self._d.env_by_tags("temp_sensor"), form.get("dht22_pin", "4"))
                    self._next_url_from_director = request.url
                    continue

                if allow_insecure and key == "tailscale_disable_go" and form.get("tailscale_disable") == "disable":
                    success, output = run_shell_captured(
                        "systemctl disable --now tailscaled && systemctl mask tailscaled", timeout=30
                    )
                    continue
                if allow_insecure and key == "zerotier" and form.get("zerotier_disable") == "disable":
                    self._d.env_by_tags("zerotierid").value = ""
                    success, output = run_shell_captured(
                        "systemctl disable --now zerotier-one && systemctl mask zerotier-one", timeout=30
                    )
                    continue
                if allow_insecure and key == "tailscale":
                    # grab extra arguments if given
                    ts_args = form.get("tailscale_extras", "")
                    if ts_args:
                        # right now we really only want to allow the login server arg
                        try:
                            ts_cli_switch, ts_cli_value = ts_args.split("=")
                        except:
                            ts_cli_switch, ts_cli_value = ["", ""]

                        if ts_cli_switch != "--login-server":
                            report_issue(
                                "at this point we only allow the --login-server=<server> argument; "
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
                            report_issue(f"the login server URL didn't make sense {ts_cli_value}")
                            continue
                    print_err(f"starting tailscale (args='{ts_args}')")
                    try:
                        subprocess.run(
                            ["/usr/bin/systemctl", "unmask", "tailscaled"],
                            timeout=20.0,
                        )
                        subprocess.run(
                            ["/usr/bin/systemctl", "enable", "--now", "tailscaled"],
                            timeout=20.0,
                        )
                        cmd = ["/usr/bin/tailscale", "up"]

                        name = self.onlyAlphaNumDash(self._d.env_by_tags("site_name").list_get(0))
                        # due to the following error, we just add --reset to the options
                        # Error: changing settings via 'tailscale up' requires mentioning all
                        # non-default flags. To proceed, either re-run your command with --reset or
                        # use the command below to explicitly mention the current value of
                        # all non-default settings:
                        cmd += ["--reset"]
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
                        report_issue("exception trying to set up tailscale - giving up")
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
                        report_issue(f"ERROR: tailscale didn't provide a login link within 30 seconds")
                    return redirect(url_for("systemmgmt"))
                # tailscale handling uses 'continue' to avoid deep nesting - don't add other keys
                # here at the end - instead insert them before tailscale
                continue
            if value == "stay" or value.startswith("stay-"):
                if allow_insecure and key == "rpw":
                    print_err("updating the root password")
                    self.set_rpw()
                    continue
                if key == "wifi":
                    print_err("updating the wifi settings")
                    ssid = form.get("wifi_ssid")
                    password = form.get("wifi_password")

                    def connect_wifi():
                        if self.wifi is None:
                            self.wifi = Wifi()
                        status = self.wifi.wifi_connect(ssid, password)
                        print_err(f"wifi_connect returned {status}")
                        self.update_net_dev()

                    self._system._restart.bg_run(func=connect_wifi)
                    self._next_url_from_director = url_for("systemmgmt")
                    # FIXME: let user know
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
                    aggregator_argument = form.get(f"{base}--key", "")
                    if base == "flightradar":
                        uat_arg = form.get(f"{base}_uat--key", "")
                        aggregator_argument += f"::{uat_arg}"
                    if base == "opensky":
                        user = form.get(f"{base}--user", "")
                        aggregator_argument += f"::{user}"
                    if base == "sdrmap":
                        user = form.get(f"{base}--user", "")
                        aggregator_argument += f"::{user}"
                    aggregator_object = self._other_aggregators[key]
                    print_err(f"got aggregator object {aggregator_object} -- activating for sitenum {l_sitenum}")
                    try:
                        is_successful = aggregator_object._activate(aggregator_argument, l_sitenum)
                    except Exception as e:
                        print_err(f"error activating {key}: {e}")
                    if not is_successful:
                        report_issue(f"did not successfully enable {base}")

                    # immediately start the containers in case the user doesn't click "apply settings" after requesting a key
                    seen_go = True
                    # go back to the page we were on after applying settings
                    self._next_url_from_director = request.url

                continue
            # now handle other form input
            if key == "sdr_setup_data" and value != "":
                self.sdr_config(value)
                continue
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
                    report_issue("Error running Ultrafeeder autogain reset")
                continue
            if key == "resetuatgain" and value == "1":
                # tell the dump978 container to restart the autogain processing
                cmdline = "docker exec dump978 /usr/local/bin/autogain978 reset"
                try:
                    subprocess.run(cmdline, timeout=5.0, shell=True)
                except:
                    report_issue("Error running UAT autogain reset")
                continue
            if allow_insecure and key == "ssh_pub":
                ssh_dir = pathlib.Path("/root/.ssh")
                ssh_dir.mkdir(mode=0o700, exist_ok=True)
                with open(ssh_dir / "authorized_keys", "a+") as authorized_keys:
                    authorized_keys.write(f"{value}\n")
                self._d.env_by_tags("ssh_configured").value = True
                success, output = run_shell_captured(
                    "systemctl is-enabled ssh || systemctl is-enabled dropbear || "
                    + "systemctl enable --now ssh || systemctl enable --now dropbear",
                    timeout=60,
                )
                if not success:
                    report_issue(f"failed to enable ssh - check the logs for details")
                    print_err(f"failed to enable ssh: {output}")
                if success:
                    report_issue(f"added ssh key: {value}")
                continue
            try:
                e = self._d.env_by_tags(key.split("--"))
            except:
                # if the key isn't creating a valid tag, just skip it
                continue
            if allow_insecure and key == "zerotierid":
                try:
                    subprocess.call("/usr/bin/systemctl unmask zerotier-one", shell=True)
                    subprocess.call("/usr/bin/systemctl enable --now zerotier-one", shell=True)
                    sleep(5.0)  # this gives the service enough time to get ready
                    subprocess.call(
                        ["/usr/sbin/zerotier-cli", "join", f"{value}"],
                    )
                except:
                    report_issue("exception trying to set up zerorier - giving up")
            if key in {"lat", "lon"}:
                # remove letters, spaces, degree symbols
                value = str(float(re.sub("[a-zA-Z° ]", "", value)))
                # if the user changed their location we need to update the remembered
                # closest airport
                lat = str(float(re.sub("[a-zA-Z° ]", "", form.get("lat", ""))))
                long = str(float(re.sub("[a-zA-Z° ]", "", form.get("lon", ""))))
                if lat != self._d.env_by_tags("lat").list_get(0) or long != self._d.env_by_tags("lon").list_get(0):
                    airport = self.closest_airport(lat, long)
                    if airport:
                        self._d.env_by_tags("closest_airport").list_set(0, airport["icao"])
            if key == "tz":
                self.set_tz(value)
                continue
            if key == "aggregator_choice" and value == "nonadsb":
                self.handle_non_adsb()
            # deal with the micro feeder and stage2 initial setup
            if key == "aggregator_choice" and value in ["micro", "nano", "nonadsb"]:
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
                unique_name = self.unique_site_name(form.get("site_name"), idx=0)
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
            serial_envs = self.serial_env_names()
            if key in serial_envs and value != "":
                for clear_key in serial_envs:
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
                unique_name = self.unique_site_name(value, idx=sitenum)
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

            self._system._restart.bg_run(cmdline="/opt/adsb/docker-compose-start", silent=False)
            return render_template("/restarting.html", extra_args=extra_args)
        print_err("base config not completed", level=2)
        return redirect(url_for("director"))

    @check_restart_lock
    def expert(self):
        if request.method == "POST":
            return self.update()
        # make sure we only show the gpsd option if gpsd is correctly configured and running
        self._d.env_by_tags("has_gpsd").value = self._system.check_gpsd()
        os_flag_file = self._d.data_path / "os.adsb.feeder.image"
        is_image = os_flag_file.exists()
        # retrieve the busiest known frequencies JSON from the adsb.im website
        url = f"https://adsb.im/api/best_frequencies/{self._d.env_by_tags('lat').list_get(0)}/{self._d.env_by_tags('lon').list_get(0)}?threshold=98"
        acars_frequencies = ""
        vdl2_frequencies = ""
        frequencies_json, status_code = generic_get_json(url)
        if status_code != 200:
            print_err(f"failed to retrieve best_frequencies JSON from {url}: {status_code}")
        else:
            print_err(f"frequencies_json: {frequencies_json}")
            acars_frequencies = "; ".join(
                sorted([f"{int(freq)/1000:.3f}" for freq in frequencies_json.get("acars", "")])
            )
            vdl2_frequencies = "; ".join(
                sorted([f"{int(freq)/1000:.3f}" for freq in frequencies_json.get("vdl2", "")])
            )

        return render_template(
            "expert.html",
            is_image=is_image,
            best_acars_frequencies=acars_frequencies,
            best_vdl2_frequencies=vdl2_frequencies,
        )

    def change_sdr_serial_ui(self):
        return render_template("change_sdr_serial_ui.html")

    @check_restart_lock
    def change_sdr_serial(self, oldserial, newserial):
        print_err(f"request to change SDR serial from {oldserial} to {newserial}")
        if self._sdrdevices.get_sdr_by_serial(oldserial) is self._sdrdevices.null_sdr:
            print_err("no SDR with serial " + oldserial + " found")
            return f"[ERROR] no SDR with serial {oldserial} found"

        with self._system._restart_lock:
            containers = self._system.list_containers()
            containers = [c for c in containers if c not in {"dozzle", "adsb-setup-proxy", "acars_router", "acarshub"}]

            print_err(
                f"stopping containers potentially accessing SDRs ({containers}) in order to be able to access SDRs"
            )
            self._system.stop_containers(containers)
            result = self._sdrdevices.change_sdr_serial(oldserial, newserial)
            self._system.start_containers()

        return result

    @check_restart_lock
    def systemmgmt(self):
        if request.method == "POST":
            return self.update()
        tailscale_running = False
        zerotier_running = False
        if self._d.is_feeder_image:
            success, output = run_shell_captured("ps -e", timeout=2)
            zerotier_running = "zerotier-one" in output
            tailscale_running = "tailscaled" in output
            # is tailscale set up?
            try:
                if not tailscale_running:
                    raise ProcessLookupError
                result = subprocess.run(
                    "tailscale status --json 2>/dev/null",
                    shell=True,
                    check=True,
                    capture_output=True,
                )
            except:
                # a non-zero return value means tailscale isn't configured or tailscale is disabled
                # reset both associated env vars
                # if tailscale recovers / is re-enabled and the system management page is visited,
                # the code below will set the appropriate tailscale_name once more.
                self._d.env_by_tags("tailscale_name").value = ""
                self._d.env_by_tags("tailscale_ll").value = ""
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
        # so that a third update button will be shown - separately, pass along unconditional
        # information on the current branch the user is on so we can show that in the explanatory text.
        channel, current_branch = self.extract_channel()
        return render_template(
            "systemmgmt.html",
            tailscale_running=tailscale_running,
            zerotier_running=zerotier_running,
            hotspot_enabled=not self._d.hotspot_disabled_path.exists(),
            rpw=self.rpw,
            channel=channel,
            current_branch=current_branch,
            containers=self._system.list_containers(),
            persistent_journal=self._persistent_journal,
            wifi=self.wifi_ssid,
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

        def nonadsb_enabled(tag, m=0):
            # stack_info(f"tags are {type(tag)} {tag}")
            if type(tag) == str:
                tag = [tag]
            if type(tag) != list:
                print_err(f"PROBLEM::: tag is {type(tag)}")
            return "checked" if self._d.list_is_enabled(tag, idx=m) else ""

        # is this a stage2 site and you are looking at an individual micro feeder,
        # or is this a regular feeder? If we have a query argument m that is a non-negative
        # number, then yes it is
        if self._d.is_enabled("stage2"):
            print_err("setting up aggregators on a stage 2 system")
            try:
                m = int(request.args.get("m"))
            except:
                m = 0
            if m == 0:  # do not set up aggregators for the aggregated feed
                if self._d.env_by_tags("num_micro_sites").value == "0":
                    # things aren't set up yet, bail out to the stage 2 setup
                    return redirect(url_for("stage2"))
                else:
                    # data sharing for the combined data is impossible,
                    # redirect instead of showing the data sharing page
                    return redirect(url_for("director"))
            site = self._d.env_by_tags("site_name").list_get(m)
            print_err(f"setting up aggregators for site {site} (m={m})")
        else:
            site = ""
            m = 0
        return render_template(
            "aggregators.html",
            uf_enabled=uf_enabled,
            others_enabled=others_enabled,
            nonadsb_enabled=nonadsb_enabled,
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
            print_err("duplicate SDR serials detected")
            # return self.sdr_setup()

        # check if we need SDRs and any of the SDRs aren't configured
        if self._d.env_by_tags("aggregator_choice").value != "nonadsb" or self.nonadsb_is_correctly_configured():
            # do we have purposes that have been enabled that don't have an SDR assigned?
            enabled_purposes = self.enabled_purposes()
            assigned_purposes = {s.purpose for s in self._sdrdevices.sdrs if s.purpose not in ["other", ""]}
            available_serials = [sdr._serial for sdr in self._sdrdevices.sdrs]
            if any([purpose not in assigned_purposes for purpose in enabled_purposes]):
                configured_serials = self.configured_serials()
                if any([serial not in configured_serials for serial in available_serials]):
                    print_err(f"configured serials: {configured_serials}")
                    print_err(f"available serials: {available_serials}")
                    print_err("director redirecting to sdr_setup: unconfigured devices present")
                    report_issue(f"New SDR detected, please check / adjust the configuration and apply the changes!")
                    return self.sdr_setup()

            used_serials = [self._d.env_by_tags(purpose).value for purpose in ["978serial", "1090serial"]]
            used_serials = [serial for serial in used_serials if serial != ""]
            if any([serial not in available_serials for serial in used_serials]):
                print_err(f"used serials: {used_serials}")
                print_err(f"available serials: {available_serials}")
                print_err("director redirecting to sdr_setup: at least one used device is not present")
                report_issue(f"Missing SDR detected, please check / adjust the configuration and apply the changes!")
                return self.sdr_setup()
        elif not self._d.is_enabled("stage2"):
            # we don't do ADS-B, we don't do any of the other protocols, and this isn't a stage 2
            # let's send the user to the non-ADS-B setup
            return self.expert()

        # if the user chose to individually pick aggregators but hasn't done so,
        # they need to go to the aggregator page
        if self.at_least_one_aggregator() or self._d.env_by_tags("aggregators_chosen"):
            return self.index()
        print_err("director redirecting to aggregators: to be configured")
        return self.aggregators()

    def reset_planes_seen_per_day(self):
        self.planes_seen_per_day = [set() for i in [0] + self.micro_indices()]

    def load_planes_seen_per_day(self):
        # set limit on how many days of statistics to keep
        self.plane_stats_limit = 14
        # we base this on UTC time so it's comparable across time zones
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.reset_planes_seen_per_day()
        self.plane_stats_day = start_of_day.timestamp()
        self.plane_stats = [[] for i in [0] + self.micro_indices()]
        try:
            with gzip.open("/opt/adsb/adsb_planes_seen_per_day.json.gz", "r") as f:
                planes = json.load(f)
                ts = planes.get("timestamp", 0)

                planelists = planes.get("planes")
                planestats = planes.get("stats")

                while len(planelists) < len([0] + self.micro_indices()):
                    print_err("load_planes: WEIRD or backup restore: padding planelists")
                    planelists.append([])
                while len(planestats) < len([0] + self.micro_indices()):
                    print_err("load_planes: WEIRD or backup restore: padding planestats")
                    planestats.append([])

                # print_err(planelists)
                # print_err(planestats)

                if ts >= start_of_day.timestamp():
                    # ok, this dump is from today
                    for i in [0] + self.micro_indices():
                        # json can't store sets, so we use list on disk, but sets in memory
                        self.planes_seen_per_day[i] = set(planelists[i])

                for i in [0] + self.micro_indices():
                    self.plane_stats[i] = planestats[i]

                diff = start_of_day.timestamp() - ts
                if diff > 0:
                    print_err(f"loading planes_seen_per_day: file not from this utc day")
                    days = math.ceil(diff / (24 * 60 * 60))
                    if days > 0:
                        days -= 1
                        for i in [0] + self.micro_indices():
                            self.plane_stats[i].insert(0, len(planelists[i]))
                    if days > 0:
                        print_err(f"loading planes_seen_per_day: padding with {days} zeroes")
                    while days > 0:
                        days -= 1
                        for i in [0] + self.micro_indices():
                            self.plane_stats[i].insert(0, 0)

                for i in [0] + self.micro_indices():
                    while len(self.plane_stats[i]) > self.plane_stats_limit:
                        self.plane_stats[i].pop()

        except:
            print_err(f"error loading planes_seen_per_day:\n{traceback.format_exc()}")
            pass

    def write_planes_seen_per_day(self):
        # we want to make absolutely sure we don't throw any errors here as this is
        # called during termination
        try:
            # json can't store sets, so we use list on disk, but sets in memory
            planelists = [list(self.planes_seen_per_day[i]) for i in [0] + self.micro_indices()]
            planes = {"timestamp": int(time.time()), "planes": planelists, "stats": self.plane_stats}
            planes_json = json.dumps(planes, indent=2)

            path = "/opt/adsb/adsb_planes_seen_per_day.json.gz"
            tmp = path + ".tmp"
            with gzip.open(tmp, "w") as f:
                f.write(planes_json.encode("utf-8"))
            os.rename(tmp, path)
            print_err("wrote planes_seen_per_day")
        except Exception as e:
            print_err(f"error writing planes_seen_per_day:\n{traceback.format_exc()}")
            pass

    def get_current_planes(self, idx):
        planes = set()
        path = "/run/adsb-feeder-" + self.uf_suffix(idx) + "/readsb/aircraft.json"
        try:
            with open(path) as f:
                aircraftdict = json.load(f)
                aircraft = aircraftdict.get("aircraft", [])
                planes = set([plane["hex"] for plane in aircraft if not plane["hex"].startswith("~")])
        except:
            pass
        return planes

    def track_planes_seen_per_day(self):
        # we base this on UTC time so it's comparable across time zones
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        ultrafeeders = [0] + self.micro_indices()
        if self.plane_stats_day != start_of_day.timestamp():
            self.plane_stats_day = start_of_day.timestamp()
            print_err("planes_seen_per_day: new day!")
            # it's a new day, store and then reset the data
            self.ci = True
            for i in ultrafeeders:
                self.plane_stats[i].insert(0, len(self.planes_seen_per_day[i]))
                if len(self.plane_stats[i]) > self.plane_stats_limit:
                    self.plane_stats[i].pop()
            self.reset_planes_seen_per_day()
        if now.minute == 0:
            # this function is called once every minute - so this triggers once an hour
            # write the data to disk every hour
            self.write_planes_seen_per_day()
        for i in ultrafeeders:
            # using sets it's really easy to keep track of what we've seen
            self.planes_seen_per_day[i] |= self.get_current_planes(i)
        if self.ci:
            pv = self._d.previous_version
            self._d.previous_version = "check-in"
            r = self._im_status.check(True)
            self._d.previous_version = pv
            if r.get("latest_tag", "unknown") != "unknown":
                self.ci = False

    def update_net_dev(self):
        dev = ""
        addr = ""
        try:
            result = subprocess.run(
                "ip route get 1 | head -1  | cut -d' ' -f5,7",
                shell=True,
                capture_output=True,
                timeout=2.0,
            ).stdout
        except:
            result = ""
        else:
            result = result.decode().strip()
            if " " in result:
                dev, addr = result.split(" ")
            else:
                dev = result
                addr = ""
        if result and addr:
            self.local_address = addr
            self.local_dev = dev
        else:
            self.local_address = ""
            self.local_dev = ""

        if self.local_dev.startswith("wlan"):
            if self.wifi is None:
                self.wifi = Wifi()
            self.wifi_ssid = self.wifi.get_ssid()
        else:
            self.wifi_ssid = ""

    def every_minute(self):
        # track the number of planes seen per day - that's a fun statistic to have and
        # readsb makes it a bit annoying to get that
        self.track_planes_seen_per_day()

        # make sure DNS works, every 5 minutes is sufficient
        if time.time() - self.last_dns_check > 300:
            self.update_dns_state()

        self._sdrdevices.ensure_populated()

        self.update_net_dev()

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

        # reset undervoltage warning after 2h
        if self._d.env_by_tags("under_voltage").value and time.time() - self.undervoltage_epoch > 2 * 3600:
            self._d.env_by_tags("under_voltage").value = False

        # now let's check for disk space
        self._d.env_by_tags("low_disk").value = shutil.disk_usage("/").free < 1024 * 1024 * 1024

        if self._d.previous_version:
            print_err(f"sending previous version: {self._d.previous_version}")
            self._im_status.check()

    @check_restart_lock
    def index(self):
        # if we get to show the feeder homepage, the user should have everything figured out
        # and we can remove the pre-installed ssh-keys and password
        with self.miscLock:
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
                alphabet = string.ascii_letters + string.digits
                self.rpw = "".join(secrets.choice(alphabet) for i in range(12))
                self.set_rpw()
                os.remove("/opt/adsb/adsb.im.passwd.and.keys")

        board = self._d.env_by_tags("board_name").valuestr
        # there are many other boards I should list here - but Pi 3 and Pi Zero are probably the most common
        stage2_suggestion = board.startswith("Raspberry") and not (
            board.startswith("Raspberry Pi 4") or board.startswith("Raspberry Pi 5")
        )
        if self.local_address:
            local_address = self.local_address
        else:
            local_address = request.host.split(":")[0]

        # this indicates that the last docker-compose-adsb up call failed
        compose_up_failed = os.path.exists("/opt/adsb/state/compose_up_failed")

        ipv6_broken = False
        if compose_up_failed:
            ipv6_broken = self._system.is_ipv6_broken()
            if ipv6_broken:
                print_err("ERROR: broken IPv6 state detected")

        # refresh docker ps cache so the aggregator status is nicely up to date
        threading.Thread(target=self._system.refreshDockerPs).start()

        self.cache_agg_status()

        channel, current_branch = self.extract_channel()

        # take a look at the SDRs configured so that the index page can be adjusted accordingly
        adsb = len([sdr for sdr in self._sdrdevices.sdrs if sdr.purpose in ["1090", "1090_2", "978"]]) > 0
        return render_template(
            "index.html",
            aggregators=self.agg_structure,
            agg_tables=list({entry[4] for entry in self.agg_structure}),
            local_address=local_address,
            tailscale_address=self.tailscale_address,
            zerotier_address=self.zerotier_address,
            stage2_suggestion=stage2_suggestion,
            matrix=self.agg_matrix,
            compose_up_failed=compose_up_failed,
            channel=channel,
            adsb=adsb,
            pi5_usb_current_limited=self.pi5_usb_current_limited(),
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

    def micro_indices(self) -> List[int]:
        if self._d.is_enabled("stage2"):
            # micro proxies start at 1
            return list(range(1, self._d.env_by_tags("num_micro_sites").valueint + 1))
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
            with open("/run/adsb-feeder-ultrafeeder/temperature.json", "r") as temperature_file:
                temperature_json = json.load(temperature_file)
                now = int(time.time())
                age = now - int(temperature_json.get("now", "0"))
                temperature_json["age"] = age
        except:
            pass
        return temperature_json

    def ambient_raw(self):
        temperature = ""
        try:
            with open("/run/adsb-feeder-ultrafeeder/ambient-temperature", "r") as temperature_file:
                temperature = temperature_file.read().strip()
        except:
            pass
        return temperature

    def check_changelog_status(self):
        """Check if changelog should be shown to user"""
        try:
            seen_changelog = self._d.env_by_tags("seen_changelog").value
            print_err(f"_ADSBIM_SEEN_CHANGELOG value from env_by_tags: {seen_changelog}")

            if not seen_changelog:
                previous_version = self._d.env_by_tags("previous_version").valuestr.split("(")[0]
                current_version = self._d.env_by_tags("base_version").valuestr.split("(")[0]

                print_err(f"Version check - old: {previous_version}, current: {current_version}")

                if (
                    previous_version
                    and current_version
                    and previous_version != current_version
                    and previous_version != "unknown-install"
                    and previous_version != "image-install"
                    and previous_version != "app-install"
                ):

                    changelog_response, status_code = generic_get_json(
                        f"https://adsb.im/api/changelog/{previous_version}/{current_version}"
                    )

                    changelog_content = changelog_response if status_code == 200 else "Failed to fetch changelog"

                    print_err("Changelog should be shown")
                    return {
                        "show_changelog": True,
                        "previous_version": previous_version,
                        "new_version": current_version,
                        "changelog": changelog_content,
                    }

                else:
                    print_err("Changelog should not be shown - versions same or missing")

            return {"show_changelog": False}

        except Exception as e:
            print_err(f"Error checking changelog status: {e}")
            return {"show_changelog": False}

    def mark_changelog_seen(self):
        """Mark changelog as seen by setting _ADSBIM_SEEN_CHANGELOG to True"""
        try:
            self._d.env_by_tags("seen_changelog").value = True
            print_err("Marked changelog as seen")
            return {"success": True}

        except Exception as e:
            print_err(f"Error marking changelog as seen: {e}")
            return {"success": False, "error": str(e)}

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
                command="bash /opt/adsb/log-sanitizer.sh 2>&1 | curl -F'expires=168' -F'file=@-'  https://0x0.st",
                timeout=60,
            )
            url = output.strip()
            if success:
                print_err(f"uploaded logs to {url}")
            else:
                print_err(f"failed to upload logs, output: {output}")
                report_issue(f"failed to upload logs")
            return render_template("support.html", url=url)

        if target == "termbin.com":
            success, output = run_shell_captured(
                command="bash /opt/adsb/log-sanitizer.sh 2>&1 | nc termbin.com 9999",
                timeout=60,
            )
            # strip extra chars for termbin
            url = output.strip("\0\n").strip()
            if success:
                print_err(f"uploaded logs to {url}")
            else:
                print_err(f"failed to upload logs, output: {output}")
                report_issue(f"failed to upload logs")
            return render_template("support.html", url=url)

        if target == "local_view" or target == "local_download":
            return self.download_logs(target)

        return render_template("support.html", url="upload logs: unexpected code path")

    def get_logs(self):
        return self.download_logs("local_download")

    def view_logs(self):
        return self.download_logs("local_view")

    def download_logs(self, target):
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
        kernel = simple_cmd_result("uname -rvmo")
        memory = simple_cmd_result("free -h")
        top = simple_cmd_result("top -b -n1 | head -n5")
        journal = "persistent on disk" if self._persistent_journal else "in memory"

        if self._system.is_ipv6_broken():
            ipv6 = "IPv6 is broken (IPv6 address assigned but can't connect to IPv6 hosts)"
        else:
            ipv6 = "IPv6 is working or disabled"

        netdog = simple_cmd_result("tail -n 10 /opt/adsb/logs/netdog.log 2>/dev/null")

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
            ipv6=ipv6,
            current=current,
            containers=containers,
            sdrs=sdrs,
            ufargs=ufargs,
            envvars=envvars,
            netdog=netdog,
        )

    def waiting(self):
        return render_template("waiting.html", title="ADS-B Feeder is performing requested actions")

    def stream_log(self):
        logfile = "/run/adsb-feeder-image.log"

        def tail():
            with open(logfile, "r") as file:
                ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
                tmp = file.read()[-16 * 1024 :]
                # discard anything but the last 16 kB
                while self._system._restart.state == "busy":
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

    @check_restart_lock
    def feeder_update(self, channel):
        if channel not in ["stable", "beta", "oldstable"]:
            return "This update functionality is only available for stable, beta and oldstable"
        return self.do_feeder_update(channel)

    # internal helper function to start the feeder update
    def do_feeder_update(self, channel):
        self.set_channel(channel)
        print_err(f"updating feeder to {channel} channel")
        # the webinterface needs to stay in the waiting state until the feeder-update stops it
        # because this is not guaranteed otherwise, add a sleep to the command running in the
        # background
        self._system._restart.bg_run(cmdline="systemctl start adsb-feeder-update.service; sleep 30")
        self.exiting = True
        return render_template("/restarting.html")


    def dozzle_yml_from_template(self):
        # env vars are not supported in certain places in compose ymls,
        # in even more places in docker v20 which is still somewhat prevalent
        template_file = "/opt/adsb/config/dozzle_template.yml"
        yml_file = "/opt/adsb/config/dozzle.yml"
        with open(template_file, "r") as template:
            with open(yml_file, "w") as yml:
                yml.write(template.read().replace("DOCKER_IPV6", "true" if self._d.is_enabled("docker_ipv6") else "false"))


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
        [f"sdrmap_{n}.yml", "sdrmap_stage2_template.yml"],
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

    a = AdsbIm()

    def signal_handler(sig, frame):
        print_err(f"received signal {sig}, shutting down...")
        a.exiting = True
        a.write_planes_seen_per_day()
        signal.signal(sig, signal.SIG_DFL)  # Restore default handler
        signal.raise_signal(sig)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)

    a.run(no_server=no_server)
