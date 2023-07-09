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
    EnvFile,
    System,
    RouteManager,
    SDRDevices,
    check_restart_lock,
)
from werkzeug.utils import secure_filename


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class AdsbIm:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = urandom(16).hex()

        self._routemanager = RouteManager(self.app)

        self._system = System()
        self._envfile = EnvFile(constants=Constants())
        self._sdrdevices = SDRDevices(envfile=self._envfile)

        self.proxy_routes = Constants.proxy_routes
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
        self.app.add_url_rule("/expert", "expert", self.expert, methods=["GET", "POST"])
        self.app.add_url_rule(
            "/aggregators", "aggregators", self.aggregators, methods=["GET", "POST"]
        )
        self.app.add_url_rule("/", "director", self.director)
        self.app.add_url_rule("/index", "index", self.index)
        self.app.add_url_rule("/setup", "setup", self.setup, methods=["GET", "POST"])
        self.app.add_url_rule("/api/can_read_sdr", "can_read_sdr", self.can_read_sdr)

    def run(self):
        self._routemanager.add_proxy_routes(self.proxy_routes)
        debug = os.environ.get("FLASK_DEBUG") is not None
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
        env_values = self._envfile.envs
        env_values["FEEDER_TZ"] = browser_timezone
        return render_template(
            "setup.html", env_values=env_values, metadata=self._envfile.metadata
        )

    def restarting(self):
        return render_template(
            "restarting.html",
            env_values=self._envfile.envs,
            metadata=self._envfile.metadata,
        )

    def restart(self):
        if request.method == "POST":
            resp = self._restart.restart_systemd()
            return "restarting" if resp else "already restarting"
        if request.method == "GET":
            return self._restart.state

    def backup(self):
        return render_template(
            "/backup.html",
            env_values=self._envfile.envs,
            metadata=self._envfile.metadata,
        )

    def backup_execute(self):
        self._system.backup()
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
                env_values=self._envfile.envs,
                metadata=self._envfile.metadata,
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
            metadata = self._envfile.metadata
            metadata["changed"] = changed
            metadata["unchanged"] = unchanged
            return render_template("/restoreexecute.html", metadata=metadata)
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

    def can_read_sdr(self):
        return {
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
            env_values=self._envfile.envs,
            metadata=self._envfile.metadata,
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
            print_err(
                f"received serial1090 of {serial1090} and serial978 of {serial978}"
            )
            if serial1090:
                if not serial1090.startswith(("AIRSPY", "airspy")):
                    advanced_settings["FEEDER_1090"] = serial1090
                else:
                    advanced_settings["FEEDER_1090"] = "airspy"
                advanced_settings.update(self.setup_airspy_or_rtl())
            if serial978:
                advanced_settings["FEEDER_978"] = serial978
                advanced_settings["FEEDER_ENABLE_UAT978"] = "yes"
                advanced_settings["FEEDER_URL_978"] = "http://dump978/skyaware978"
            advanced_settings["SDR_MANUALLY_ASSIGNED"] = "1"
            # now we need to update the ENV_FILE so that the ultrafeeder configuration below is correct
            self._envfile.update(advanced_settings)
            print_err(
                "after the update, FEEDER_1090 is ",
                self._envfile.envs.get("FEEDER_1090"),
                " and FEEDER_978 is ",
                self._envfile.envs.get("FEEDER_978"),
            )
            net = self._envfile.generate_ultrafeeder_config(request.form)
            self._envfile.update({"FEEDER_ULTRAFEEDER_CONFIG": net, "UF": "1"})
            print_err(f"calculated ultrafeeder config of {net}")
        return redirect("/restarting")

    @check_restart_lock
    def expert(self):
        if request.method == "POST":
            return self.handle_expert_post_request()

        # FIXME what does this do ? it is a mystery.
        filecontent = {"have_backup": False}
        if path.exists("/opt/adsb/env-working") and path.exists(
            "/opt/adsb/docker-compose.yml-working"
        ):
            filecontent["have_backup"] = True
        with open("/opt/adsb/.env", "r") as env:
            filecontent["env"] = env.read()
        with open("/opt/adsb/docker-compose.yml") as dc:
            filecontent["dc"] = dc.read()
        # end of magic....

        return render_template(
            "expert.html",
            env_values=self._envfile.envs,
            metadata=self._envfile.metadata,
            filecontent=filecontent,
        )

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

    def handle_expert_post_request(self):
        env_values = self._envfile.envs
        allow_insecure = False if env_values.get("SECURE_IMAGE", "0") == "1" else True
        if request.form.get("shutdown") == "go":
            # do shutdown
            subprocess.run("/usr/sbin/halt", shell=True)
            return "System halted"  # that return statement is of course a joke
        if request.form.get("reboot") == "go":
            # initiate reboot
            subprocess.run("/usr/sbin/reboot now &", shell=True)
            return "System rebooting, please refresh in about a minute"
        if request.form.get("secure_image") == "go":
            self._envfile.update({"SECURE_IMAGE": "1"})
            self.secure_image()
            return redirect("/expert")
        if allow_insecure and request.form.get("ssh") == "go":
            ssh_pub = request.form.get("ssh-pub")
            ssh_dir = pathlib.Path("/root/.ssh")
            ssh_dir.mkdir(mode=0o700, exist_ok=True)
            with open(ssh_dir / "authorized_keys", "a+") as authorized_keys:
                authorized_keys.write(f"{ssh_pub}\n")
            flash("Public key for root account added.", "Notice")
            self._envfile.update({"SSH_CONFIGURED": "1"})
            return redirect("/expert")
        if request.form.get("update") == "go":
            # this needs a lot more checking and safety, but for now, just go
            cmdline = "/usr/bin/docker-update-adsb-im"
            subprocess.run(cmdline, timeout=600.0, shell=True)
            return redirect("/expert")
        if request.form.get("nightly_update") == "go":
            self._envfile.update(
                {
                    "NIGHTLY_BASE_UPDATE": "1"
                    if request.form.get("nightly_base")
                    else "0",
                    "NIGHTLY_CONTAINER_UPDATE": "1"
                    if request.form.get("nightly_container")
                    else "0",
                }
            )
        if request.form.get("zerotier") == "go":
            self._envfile.update(
                {
                    "ZEROTIER": "1",
                    "ZEROTIER_NETWORK_ID": request.form.get("zerotierid"),
                }
            )
            # make sure the service is enabled (it really should be)
            subprocess.call("/usr/bin/systemctl enable --now zerotier-one", shell=True)

            # now we need to connect to the network:
            subprocess.call(
                f"/usr/sbin/zerotier-cli join {self._envfile.envs.get('ZEROTIER_NETWORK_ID')}",
                shell=True,
            )
        if allow_insecure and request.form.get("you-asked-for-it") == "you-got-it":
            # well - let's at least try to save the old stuff
            if not path.exists("/opt/adsb/env-working"):
                try:
                    shutil.copyfile("/opt/adsb/.env", "/opt/adsb/env-working")
                except shutil.Error as err:
                    print(f"copying .env didn't work: {err.args[0]}: {err.args[1]}")
            if not path.exists("/opt/adsb/dc-working"):
                try:
                    shutil.copyfile(
                        "/opt/adsb/docker-compose.yml",
                        "/opt/adsb/docker-compose.yml-working",
                    )
                except shutil.Error as err:
                    print(
                        f"copying docker-compose.yml didn't work: {err.args[0]}: {err.args[1]}"
                    )
            with open("/opt/adsb/.env", "w") as env:
                env.write(request.form["env"])
            with open("/opt/adsb/docker-compose.yml", "w") as dc:
                dc.write(request.form["dc"])

            self._restart.restart_systemd()
            return redirect("restarting")

        if allow_insecure and request.form.get("you-got-it") == "give-it-back":
            # do we have saved old files?
            if path.exists("/opt/adsb/env-working"):
                try:
                    shutil.copyfile("/opt/adsb/env-working", "/opt/adsb/.env")
                except shutil.Error as err:
                    print(f"copying .env didn't work: {err.args[0]}: {err.args[1]}")
            if path.exists("/opt/adsb/docker-compose.yml-working"):
                try:
                    shutil.copyfile(
                        "/opt/adsb/docker-compose.yml-working",
                        "/opt/adsb/docker-compose.yml",
                    )
                except shutil.Error as err:
                    print(
                        f"copying docker-compose.yml didn't work: {err.args[0]}: {err.args[1]}"
                    )

            self._restart.restart_systemd()
            return redirect("restarting")

        print("request_form", request.form)
        return redirect("/")

    @check_restart_lock
    def aggregators(self):
        if request.method == "POST":
            return self.handle_aggregators_post_request()
        env_values = self._envfile.envs
        return render_template(
            "aggregators.html", env_values=env_values, metadata=self._envfile.metadata
        )

    # @app.route("/")

    def director(self):
        # figure out where to go:
        env_values = self._envfile.envs
        if env_values.get("BASE_CONFIG") != "1":
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
        return render_template(
            "index.html", env_values=self._envfile.envs, metadata=self._envfile.metadata
        )

    @check_restart_lock
    def setup(self):
        if request.method == "POST" and request.form.get("submit") == "go":
            # lat, lng, alt, form_timezone, mlat_name, aggregators = (
            #     request.form[key]
            #     for key in [
            #         "lat",
            #         "lng",
            #         "alt",
            #         "form_timezone",
            #         "mlat_name",
            #         "aggregators",
            #     ]
            # )
            print_err(
                f"got lat: {lat},",
                f" lng: {lng},",
                f" alt: {alt},",
                f" TZ: {form_timezone},",
                f" mlat-name: {mlat_name},",
                f" agg: {aggregators}",
            )
            if all([lat, lng, alt, form_timezone]):
                # first set the base data
                self._envfile.update(
                    {
                        "FEEDER_LAT": lat,
                        "FEEDER_LONG": lng,
                        "FEEDER_ALT_M": alt,
                        "FEEDER_TZ": form_timezone,
                        "MLAT_SITE_NAME": mlat_name,
                        "FEEDER_AGG": aggregators,
                    }
                )
                # while we are at it, set the local time zone
                subprocess.call(
                    f"/usr/bin/timedatectl set-timezone {form_timezone}", shell=True
                )
                # with the data just stored, we can now take a guess at the Ultrafeeder config
                # using the SDR mapping (in most cases this will be just one)
                # and the remaining base settings
                # We take the metadata,
                # and then add request.form on top...
                net = self._envfile.generate_ultrafeeder_config(request.form)
                self._envfile.update({"FEEDER_ULTRAFEEDER_CONFIG": net, "UF": "1"})
                sdr_per_frequency = self._sdrdevices.addresses_per_frequency
                self._envfile.update(
                    {
                        "FEEDER_ULTRAFEEDER_CONFIG": net,
                        "UF": "1" if net else "0",
                        "BASE_CONFIG": "1",
                    }
                )

                if not sdr_per_frequency[1090]:
                    return redirect(url_for("advanced"))
                if aggregators == "ind":
                    return redirect(url_for("aggregators"))
                return redirect(url_for("restarting"))

        return render_template(
            "setup.html", env_values=self._envfile.envs, metadata=self._envfile.metadata
        )

    # FIXME tear me up into my own class please.

    def handle_aggregators_post_request(self):
        print_err(request.form)
        if request.form.get("tar1090") == "go":
            self.update_env()
            self._restart.restart_systemd()
            return redirect("/restarting")
        for key, value in [
            ("get-fr24-sharing-key", self.fr24_setup),
            ("get-pw-api-key", self.pw_setup),
            ("get-fa-api-key", self.fa_setup),
            ("get-rb-sharing-key", self.rb_setup),
            ("get-pf-sharecode", self.pf_setup),
            ("get-ah-station-key", self.ah_setup),
            ("get-os-info", self.os_setup),
            ("get-rv-feeder-key", self.rv_setup),
            # FIXME move these to their own class
        ]:
            if request.form.get(key) == "go":
                return value()
        else:
            # how did we get here???
            return "something went wrong"

    def update_env(self):
        env_updates = {
            box: "1" if request.form.get(box) == "on" else "0"
            for box in ["FR24", "PW", "FA", "RB", "PF", "AH", "OS", "RV"]  # FIXME
        }
        net = self._envfile.generate_ultrafeeder_config(request.form)
        # ^ WTF? why are we messing with it here? FIXME
        env_updates["FEEDER_ULTRAFEEDER_CONFIG"] = net
        env_updates["UF"] = "1" if net else "0"
        # we should also check that there are the right keys given...
        self._envfile.update(env_updates)

if __name__ == "__main__":
    AdsbIm().run()
