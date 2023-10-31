import filecmp
import io
import json
from operator import is_
import os.path
import pathlib
import pickle
import platform
import re
import shutil
import subprocess
from time import sleep
import zipfile
from base64 import b64encode
from os import path, urandom
from typing import Dict, List
from zlib import compress

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
    AggStatus,
    ImStatus,
    System,
    check_restart_lock,
    UltrafeederConfig,
    cleanup_str,
    print_err,
)
from werkzeug.utils import secure_filename


class AdsbIm:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = urandom(16).hex()

        @self.app.context_processor
        def env_functions():
            return {
                "is_enabled": lambda tag: self._constants.is_enabled(tag),
                "env_value_by_tag": lambda tag: self._constants.env_by_tags(
                    [tag]
                ).value,  # this one takes a single tag
                "env_value_by_tags": lambda tags: self._constants.env_by_tags(
                    tags
                ).value,  # this one takes a list of tags
                "env_values": self._constants.envs,
            }

        self._routemanager = RouteManager(self.app)
        self._constants = Constants()

        # the maintainer of adsb.one asked us to change users' over to feeding airplane.live
        # I'm not thrilled with just doing that, but... it seems to make sense here?
        adsbone_env = self._constants.env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ADSBONE_ENABLED"
        )
        if adsbone_env.value:
            adsbone_env.value = False
            self._constants.env(
                "_ADSBIM_STATE_IS_ULTRAFEEDER_ALIVE_ENABLED"
            ).value = True
            print_err(
                "found adsb.one enabled and made sure that airplanes.live is emabled instead"
            )

        self._system = System(constants=self._constants)
        self._sdrdevices = SDRDevices()
        self._ultrafeeder = UltrafeederConfig(constants=self._constants)

        # update Env ultrafeeder to have value self._ultrafeed.generate()
        self._constants.env_by_tags(
            "ultrafeeder_config"
        )._value_call = self._ultrafeeder.generate
        self._constants.env_by_tags("pack")._value_call = self.pack_im
        self._other_aggregators = {
            "adsbhub--submit": ADSBHub(self._system),
            "flightaware--submit": FlightAware(self._system),
            "flightradar--submit": FlightRadar24(self._system),
            "opensky--submit": OpenSky(self._system),
            "planefinder--submit": PlaneFinder(self._system),
            "planewatch--submit": PlaneWatch(self._system),
            "radarbox--submit": RadarBox(self._system),
            "radarvirtuel--submit": RadarVirtuel(self._system),
        }
        # fmt: off
        self.all_aggregators = [
            # tag, name, map link, status link
            ["adsblol", "adsb.lol", "https://adsb.lol/", "https://api.adsb.lol/0/me"],
            ["flyitaly", "Fly Italy ADSB", "https://mappa.flyitalyadsb.com/", "https://my.flyitalyadsb.com/am_i_feeding"],
            ["avdelphi", "AVDelphi", "https://www.avdelphi.com/coverage.html", ""],
            ["planespotters", "Planespotters", "https://radar.planespotters.net/", "https://www.planespotters.net/feed/status"],
            ["tat", "TheAirTraffic", "https://globe.theairtraffic.com/", "https://theairtraffic.com/feed/myip/"],
            ["flyovr", "FLYOVR.io", "https://globe.flyovr.io/", ""],
            ["radarplane", "RadarPlane", "https://radarplane.com/", "https://radarplane.com/feed"],
            ["adsbfi", "adsb.fi", "https://globe.adsb.fi/", "https://api.adsb.fi/v1/myip"],
            ["adsbx", "ADSBExchange", "https://globe.adsbexchange.com/", "https://www.adsbexchange.com/myip/"],
            ["hpradar", "HPRadar", "https://skylink.hpradar.com/", ""],
            ["alive", "airplanes.live", "https://globe.airplanes.live/", "https://airplanes.live/myfeed/"],
            ["flightradar", "flightradar24", "https://www.flightradar24.com/", "/fr24-monitor.json"],
            ["planewatch", "Plane.watch", "https:/plane.watch/desktop.html", ""],
            ["flightaware", "FlightAware", "https://www.flightaware.com/#home-live-map", "/fa-status"],
            ["radarbox", "RadarBox", "https://www.radarbox.com/coverage-map", ""],
            ["planefinder", "PlaneFinder", "https://planefinder.net/", "/planefinder-stat"],
            ["adsbhub", "ADSBHub", "https://www.adsbhub.org/coverage.php", ""],
            ["opensky", "OpenSky", "https://opensky-network.org/network/explorer", "https://opensky-network.org/receiver-profile?s=<FEEDER_OPENSKY_SERIAL>"],
            ["radarvirtuel", "RadarVirtuel", "https://www.radarvirtuel.com/", ""],
        ]
        self.proxy_routes = self._constants.proxy_routes
        self.app.add_url_rule("/propagateTZ", "propagateTZ", self.get_tz)
        self.app.add_url_rule("/restarting", "restarting", self.restarting)
        self.app.add_url_rule("/restart", "restart", self.restart, methods=["GET", "POST"])
        self.app.add_url_rule("/running", "running", self.running)
        self.app.add_url_rule("/backup", "backup", self.backup)
        self.app.add_url_rule("/backupexecute", "backupexecute", self.backup_execute)
        self.app.add_url_rule("/restore", "restore", self.restore, methods=["GET", "POST"])
        self.app.add_url_rule("/executerestore", "executerestore", self.executerestore, methods=["GET", "POST"])
        self.app.add_url_rule("/advanced", "advanced", self.advanced, methods=["GET", "POST"])
        self.app.add_url_rule("/expert", "expert", self.expert, methods=["GET", "POST"])
        self.app.add_url_rule("/aggregators", "aggregators", self.aggregators, methods=["GET", "POST"])
        self.app.add_url_rule("/", "director", self.director, methods=["GET", "POST"])
        self.app.add_url_rule("/index", "index", self.index)
        self.app.add_url_rule("/setup", "setup", self.setup, methods=["GET", "POST"])
        self.app.add_url_rule("/update", "update", self.update, methods=["POST"])
        self.app.add_url_rule("/api/sdr_info", "sdr_info", self.sdr_info)
        self.app.add_url_rule(f"/api/status/<agg>", "beast", self.agg_status)
        # fmt: on
        self.update_boardname()

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
        self._constants.env_by_tags("board_name").value = board

    def pack_im(self) -> str:
        image = {
            "in": self._constants.env_by_tags("image_name").value,
            "bn": self._constants.env_by_tags("board_name").value,
            "bv": self._constants.env_by_tags("base_version").value,
            "cv": self._constants.env_by_tags("container_version").value,
        }
        return b64encode(compress(pickle.dumps(image)))

    def run(self):
        self._routemanager.add_proxy_routes(self.proxy_routes)
        debug = os.environ.get("ADSBIM_DEBUG") is not None
        self._debug_cleanup()
        self._constants.update_env()
        # prepare for app use (vs ADS-B Feeder Image use)
        # newer images will include a flag file that indicates that this is indeed
        # a full image - but in case of upgrades from older version, this heuristic
        # should be sufficient to guess if this is an image or an app
        os_flag_file = self._constants.data_path / "os.adsb.feeder.image"
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
            self._constants.is_feeder_image = False
            with open(
                self._constants.data_path / "adsb-setup/templates/expert.html", "r+"
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

        self.app.run(
            host="0.0.0.0",
            port=int(self._constants.env_by_tags("webport").value),
            debug=debug,
        )

    def _debug_cleanup(self):
        """
        This is a debug function to clean up the docker-starting.lock file
        """
        # rm /opt/adsb/docker-starting.lock
        try:
            os.remove(self._constants.data_path / "docker-starting.lock")
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

    def running(self):
        return "OK"

    def backup(self):
        return render_template("/backup.html")

    def backup_execute(self):
        adsb_path = pathlib.Path("/opt/adsb/config")
        data = io.BytesIO()
        with zipfile.ZipFile(data, mode="w") as backup_zip:
            backup_zip.write(adsb_path / ".env", arcname=".env")
            for f in adsb_path.glob("*.yml"):
                backup_zip.write(f, arcname=os.path.basename(f))
            uf_path = pathlib.Path(adsb_path / "ultrafeeder")
            if uf_path.is_dir():
                for f in uf_path.rglob("*"):
                    backup_zip.write(f, arcname=f.relative_to(adsb_path))
        data.seek(0)
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
                restore_path = pathlib.Path("/opt/adsb/config/restore")
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
            filename = request.args["zipfile"]
            adsb_path = pathlib.Path("/opt/adsb/config")
            restore_path = adsb_path / "restore"
            restore_path.mkdir(mode=0o755, exist_ok=True)
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
            saw_uf = False
            for name in restored_files:
                if name.startswith("ultrafeeder/"):
                    saw_uf = True
                elif os.path.isfile(adsb_path / name):
                    if filecmp.cmp(adsb_path / name, restore_path / name):
                        print_err(f"{name} is unchanged")
                        unchanged.append(name)
                    else:
                        print_err(f"{name} is different from current version")
                        changed.append(name)
            if saw_uf:
                changed.append("ultrafeeder/")
            return render_template(
                "/restoreexecute.html", changed=changed, unchanged=unchanged
            )
        else:
            # they have selected the files to restore
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
                    if pathlib.Path(adsb_path / name).exists():
                        shutil.move(adsb_path / name, restore_path / (name + ".dist"))
                    shutil.move(restore_path / name, adsb_path / name)
            self._constants.re_read_env()
            self.update_boardname()
            # make sure we are connected to the right Zerotier network
            zt_network = self._constants.env_by_tags("zerotierid").value
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
            try:
                subprocess.call(
                    "/opt/adsb/docker-compose-start", timeout=180.0, shell=True
                )
            except subprocess.TimeoutExpired:
                print_err("timeout expired re-starting docker... trying to continue...")
            return redirect(url_for("director"))

    def base_is_configured(self):
        base_config: set[Env] = {
            env for env in self._constants._env if env.is_mandatory
        }
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
            if self._constants.is_enabled(key):
                print_err(f"no semi-annonymous aggregator, but enabled {key}")
                return True

        return False

    def sdr_info(self):
        self._sdrdevices._ensure_populated()
        # get our guess for the right SDR to frequency mapping
        # and then update with the actual settings
        frequencies: Dict[str, str] = self._sdrdevices.addresses_per_frequency
        for freq in [1090, 978]:
            setting = self._constants.env_by_tags(f"{freq}serial")
            if setting and setting.value != "":
                frequencies[freq] = setting.value
        return json.dumps(
            {
                "sdrdevices": [sdr._json for sdr in self._sdrdevices.sdrs],
                "frequencies": frequencies,
            }
        )

    def agg_status(self, agg):
        if agg == "im":
            status = ImStatus(self._constants).check()
            return json.dumps(status)
        status = AggStatus(agg, self._constants, request.host_url.rstrip("/ "))
        if agg == "adsbx":
            return json.dumps(
                {
                    "beast": status.beast,
                    "mlat": status.mlat,
                    "adsbxfeederid": self._constants.env_by_tags("adsbxfeederid").value,
                }
            )
        return json.dumps({"beast": status.beast, "mlat": status.mlat})

    @check_restart_lock
    def advanced(self):
        if request.method == "POST":
            return self.update()

        # just in case things have changed (the user plugged in a new device for example)
        self._sdrdevices._ensure_populated()
        return render_template("advanced.html")

    def set_channel(self, channel: str):
        with open(self._constants.data_path / "update-channel", "w") as update_channel:
            print(channel, file=update_channel)

    def clear_range_outline(self):
        # is the file where we expect it?
        rangedirs = (
            self._constants.config_path
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

    def update(self):
        description = """
            This is the one endpoint that handles all the updates coming in from the UI.
            It walks through the form data and figures out what to do about the information provided.
        """
        # in the HTML, every input field needs to have a name that is concatenated by "--"
        # and that matches the tags of one Env
        form: Dict = request.form
        seen_go = False
        allow_insecure = not self._constants.is_enabled("secure_image")
        for key, value in form.items():
            # print_err(f"handling {key} -> {value} (allow insecure is {allow_insecure})")
            # this seems like cheating... let's capture all of the submit buttons
            if value == "go":
                seen_go = True
            if value == "go" or value == "wait":
                if key == "shutdown":
                    # do shutdown
                    self._system.halt()
                    return render_template("/waitandredirect.html")
                if key == "reboot":
                    # initiate reboot
                    self._system.reboot()
                    return render_template("/waitandredirect.html")
                if key == "secure_image":
                    self._constants.env_by_tags("secure_image").value = True
                    self.secure_image()
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
                if key == "nightly_update" or key == "zerotier":
                    # this will be handled through the separate key/value pairs
                    pass
                if key == "tailscale":
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
                            f"/usr/bin/tailscale up {ts_args} 2> /tmp/out &",
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
                    self._constants.env_by_tags("tailscale_ll").value = login_link
                    return redirect(url_for("expert"))
                # tailscale handling uses 'continue' to avoid deep nesting - don't add other keys
                # here at the end - instead insert them before tailscale
                continue
            if value == "stay":
                if key == "clear_range":
                    self.clear_range_outline()
                    continue

                if key in self._other_aggregators:
                    is_successful = False
                    base = key.replace("--submit", "")
                    aggregator_argument = form.get(f"{base}--key", None)
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
            e = self._constants.env_by_tags(key.split("--"))
            if e:
                if allow_insecure and key == "ssh_pub":
                    ssh_dir = pathlib.Path("/root/.ssh")
                    ssh_dir.mkdir(mode=0o700, exist_ok=True)
                    with open(ssh_dir / "authorized_keys", "a+") as authorized_keys:
                        authorized_keys.write(f"{value}\n")
                    self._constants.env_by_tags("ssh_configured").value = True
                if key == "zerotierid":
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
                e.value = value
        # done handling the input data
        # what implied settings do we have (and could we simplify them?)
        # first grab the SDRs plugged in and check if we have one identified for UAT
        self._sdrdevices._ensure_populated()
        s978 = self._constants.env_by_tags("978serial").value
        if s978 != "" and not any(
            [sdr._serial == s978 for sdr in self._sdrdevices.sdrs]
        ):
            self._constants.env_by_tags("978serial").value = ""
        auto_assignment = self._sdrdevices.addresses_per_frequency
        print_err(f"SDR auto_assignment would be {auto_assignment}")
        if (
            not self._constants.env_by_tags("1090serial").value
            and auto_assignment[1090]
        ):
            self._constants.env_by_tags("1090serial").value = auto_assignment[1090]
        if not self._constants.env_by_tags("978serial").value and auto_assignment[978]:
            self._constants.env_by_tags("978serial").value = auto_assignment[978]
        if self._constants.env_by_tags("978serial").value:
            self._constants.env_by_tags(["uat978", "is_enabled"]).value = True
            self._constants.env_by_tags("978url").value = "http://dump978/skyaware978"
            self._constants.env_by_tags("978host").value = "dump978"
            self._constants.env_by_tags("978piaware").value = "relay"
        else:
            self._constants.env_by_tags(["uat978", "is_enabled"]).value = False
            self._constants.env_by_tags("978url").value = ""
            self._constants.env_by_tags("978host").value = ""
            self._constants.env_by_tags("978piaware").value = ""

        # next check for airspy devices
        airspy = any([sdr._type == "airspy" for sdr in self._sdrdevices.sdrs])
        self._constants.env_by_tags(["airspy", "is_enabled"]).value = airspy
        if (
            len(self._sdrdevices.sdrs) == 1
            and not airspy
            and not self._constants.env_by_tags("978serial").value
        ):
            self._constants.env_by_tags("1090serial").value = self._sdrdevices.sdrs[
                0
            ]._serial
        if airspy:
            self._constants.env_by_tags("1090serial").value = ""

        rtlsdr = not airspy and self._constants.env_by_tags("1090serial").value != ""
        self._constants.env_by_tags("rtlsdr").value = "rtlsdr" if rtlsdr else ""

        print_err(f"in the end we have")
        print_err(f"1090serial {self._constants.env_by_tags('1090serial').value}")
        print_err(f"978serial {self._constants.env_by_tags('978serial').value}")
        print_err(
            f"airspy container is {self._constants.env_by_tags(['airspy', 'is_enabled']).value}"
        )
        print_err(
            f"dump978 container {self._constants.env_by_tags(['uat978', 'is_enabled']).value}"
        )

        # let's make sure we write out the updated ultrafeeder config
        self._constants.update_env()

        # if the button simply updated some field, stay on the same page
        if not seen_go:
            return redirect(request.url)

        # finally, check if this has given us enough configuration info to
        # start the containers
        if self.base_is_configured():
            self._constants.env_by_tags(["base_config"]).value = True
            if self.at_least_one_aggregator():
                return redirect(url_for("restarting"))
            return redirect(url_for("aggregators"))
        return redirect(url_for("director"))

    @check_restart_lock
    def expert(self):
        if request.method == "POST":
            return self.update()
        if self._constants.is_feeder_image:
            # is tailscale set up?
            try:
                result = subprocess.run("tailscale status", shell=True, check=True)
            except:
                # a non-zero return value means tailscale isn't configured
                self._constants.env_by_tags("tailscale_name").value = ""
            else:
                try:
                    result = subprocess.run(
                        "tailscale status | head -1 | awk '{print $2}'",
                        shell=True,
                        capture_output=True,
                    )
                except:
                    self._constants.env_by_tags("tailscale_name").value = ""
                else:
                    tailscale_name = result.stdout.decode()
                    print_err(f"configured as {tailscale_name} on tailscale")
                    self._constants.env_by_tags("tailscale_name").value = tailscale_name
                    self._constants.env_by_tags("tailscale_ll").value = ""
        return render_template("expert.html")

    def secure_image(self):
        output: str = ""
        try:
            result = subprocess.run(
                "/opt/adsb/secure-image", shell=True, capture_output=True
            )
        except subprocess.TimeoutExpired as exc:
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
            return (
                "checked"
                if self._constants.is_enabled("other_aggregator", *tags)
                else ""
            )

        return render_template(
            "aggregators.html",
            uf_enabled=uf_enabled,
            others_enabled=others_enabled,
        )

    def director(self):
        # figure out where to go:
        if request.method == "POST":
            return self.update()
        if not self._constants.is_enabled("base_config"):
            return self.setup()

        # If we have more than one SDR, or one of them is an airspy,
        # we need to go to advanced - unless we have at least one of the serials set up
        # for 978 or 1090 reporting
        self._sdrdevices._ensure_populated()

        # check that "something" is configured as input
        if (
            len(self._sdrdevices) > 1
            or any([sdr._type == "airspy" for sdr in self._sdrdevices.sdrs])
        ) and not (
            self._constants.env_by_tags("1090serial").value
            or self._constants.env_by_tags("978serial").value
            or self._constants.is_enabled("airspy")
        ):
            return self.advanced()

        # if the user chose to individually pick aggregators but hasn't done so,
        # they need to go to the aggregator page
        if self.at_least_one_aggregator():
            return self.index()
        return self.aggregators()

    def index(self):
        aggregators = self.all_aggregators
        for idx in range(len(aggregators)):
            if aggregators[idx][3]:
                if aggregators[idx][3][0] == "/":
                    aggregators[idx][3] = (
                        request.host_url.rstrip("/ ") + aggregators[idx][3]
                    )
                match = re.search("<([^>]*)>", aggregators[idx][3])
                if match:
                    print_err(
                        f"found {match.group(0)} - replace with {self._constants.env(match.group(1)).value}"
                    )
                    aggregators[idx][3] = aggregators[idx][3].replace(
                        match.group(0), self._constants.env(match.group(1)).value
                    )
        return render_template("index.html", aggregators=aggregators)

    @check_restart_lock
    def setup(self):
        if request.method == "POST" and request.form.get("submit") == "go":
            return self.update()
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
        "uat978.yml",
    }
    adsb_dir = pathlib.Path("/opt/adsb")
    config_dir = pathlib.Path("/opt/adsb/config")
    if not config_dir.exists():
        config_dir.mkdir()
        env_file = adsb_dir / ".env"
        if env_file.exists():
            env_file.rename(config_dir / ".env")
        else:
            # I don't understand how that could happen
            open(config_dir / ".env", "w").close()
    for file_name in config_files:
        config_file = pathlib.Path(adsb_dir / file_name)
        if config_file.exists():
            new_file = pathlib.Path(config_dir / file_name)
            config_file.rename(new_file)
            print_err(f"moved {config_file} to {new_file}")

    AdsbIm().run()
