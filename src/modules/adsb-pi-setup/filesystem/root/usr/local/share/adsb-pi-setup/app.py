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
from utils import Constants, EnvFile, NetConfigs, Restart, RouteManager, SDRDevices
from werkzeug.utils import secure_filename


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class AdsbIm:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = urandom(16).hex()
        self._routemanager = RouteManager(self.app)
        self.proxy_routes = Constants.PROXY_ROUTES
        self.app.add_url_rule("/propagateTZ", "/propagateTZ", self.get_tz)
        self.app.add_url_rule("/restarting", "/restarting", self.restarting)
        self.app.add_url_rule(
            "/restart", "/restart", self.restart, methods=["GET", "POST"]
        )
        self.app.add_url_rule("/backup", "/backup", self.backup)
        self.app.add_url_rule("/backup_execute", "/backup_execute", self.backup_execute)
        self.app.add_url_rule(
            "/restore", "/restore", self.restore, methods=["GET", "POST"]
        )

    def run(self):
        self._routemanager.add_proxy_routes(self.proxy_routes)
        self._restart = Restart()
        self._netconfigs = NetConfigs()
        self._sdrdevices = SDRDevices()
        self._envfile = EnvFile(
            Constants.ENV_FILE_PATH, restart=self._restart, netconfigs=self._netconfigs
        )
        self.app.run(host="0.0.0.0", port=5000, debug=True)

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
        adsb_path = pathlib.Path("/opt/adsb")
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
                "/restore.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata
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
                if not name.startswith("ultrafeeder/") and os.path.isfile(adsb_path / name):
                    if filecmp.cmp(adsb_path / name, restore_path / name):
                        print_err(f"{name} is unchanged")
                        unchanged.append(name)
                    else:
                        print_err(f"{name} is different from current version")
                        changed.append(name)
                elif name == "ultrafeeder/":
                    changed.append("ultrafeeder")
            metadata = ENV_FILE.metadata
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
        env_values = ENV_FILE.envs
        sdrs = get_sdr_info()
        serials = [sdr["serial"] for sdr in sdrs["sdrs"]]
        use = []
        for i in range(len(serials)):
            if serials[i] == env_values.get("FEEDER_1090"):
                use.append("1090")
            elif serials[i] == env_values.get("FEEDER_978"):
                use.append("978")
            elif (
                serials[i].startswith(("AIRSPY", "airspy"))
                and env_values.get("FEEDER_1090") == "airspy"
            ):
                use.append("1090")
            else:
                use.append("")
        sdr_state = {"num": sdrs["num"], "serials": serials, "use": use}
        return json.dumps(sdr_state)


#@app.route("/advanced", methods=("GET", "POST"))
    def advanced(self):
        if request.method == "POST":
            return handle_advanced_post_request()
        if RESTART.lock.locked():
            return redirect("/restarting")
        # just in case things have changed (the user plugged in a new device for example)
        num = get_sdr_info()["num"]
        ENV_FILE.update({"NUM_SDRS": num})
        env_values = ENV_FILE.envs
        return render_template(
            "advanced.html", env_values=env_values, metadata=ENV_FILE.metadata
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
            num = get_sdr_info()["num"]
            advanced_settings["NUM_SDRS"] = num
            advanced_settings["SDR_MANUALLY_ASSIGNED"] = "1"
            # now we need to update the ENV_FILE so that the ultrafeeder configuration below is correct
            ENV_FILE.update(advanced_settings)
            envs = ENV_FILE.envs
            print_err(
                f"after the update, FEEDER_1090 is {envs.get('FEEDER_1090')} and FEEDER_978 is {envs.get('FEEDER_978')}"
            )
            net = ENV_FILE.generate_ultrafeeder_config(request.form)
            ENV_FILE.update({"FEEDER_ULTRAFEEDER_CONFIG": net, "UF": "1"})
            print_err(f"calculated ultrafeeder config of {net}")
        return redirect("/restarting")


    def setup_airspy_or_rtl(self):
        envs = ENV_FILE.envs
        update = {}
        if envs.get("FEEDER_1090") == "airspy":
            update["AIRSPY"] = "1"
            update["FEEDER_RTL_SDR"] = ""
        elif envs.get("FEEDER_1090"):
            update["AIRSPY"] = "0"
            update["FEEDER_RTL_SDR"] = "rtlsdr"
        else:
            update["AIRSPY"] = "0"
            update["FEEDER_RTL_SDR"] = ""
        return update


#@app.route("/expert", methods=("GET", "POST"))
    def expert(self):
        if request.method == "POST":
            return handle_expert_post_request()
        env_values = ENV_FILE.envs
        if RESTART.lock.locked():
            return redirect("/restarting")
        filecontent = {"have_backup": False}
        if path.exists("/opt/adsb/env-working") and path.exists(
            "/opt/adsb/docker-compose.yml-working"
        ):
            filecontent["have_backup"] = True
        with open("/opt/adsb/.env", "r") as env:
            filecontent["env"] = env.read()
        with open("/opt/adsb/docker-compose.yml") as dc:
            filecontent["dc"] = dc.read()
        return render_template(
            "expert.html",
            env_values=env_values,
            metadata=ENV_FILE.metadata,
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
        env_values = ENV_FILE.envs
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
            ENV_FILE.update({"SECURE_IMAGE": "1"})
            secure_image()
            return redirect("/expert")
        if allow_insecure and request.form.get("ssh") == "go":
            ssh_pub = request.form.get("ssh-pub")
            ssh_dir = pathlib.Path("/root/.ssh")
            ssh_dir.mkdir(mode=0o700, exist_ok=True)
            with open(ssh_dir / "authorized_keys", "a+") as authorized_keys:
                authorized_keys.write(f"{ssh_pub}\n")
            flash("Public key for root account added.", "Notice")
            ENV_FILE.update({"SSH_CONFIGURED": "1"})
            return redirect("/expert")
        if request.form.get("update") == "go":
            # this needs a lot more checking and safety, but for now, just go
            cmdline = "/usr/bin/docker-update-adsb-im"
            subprocess.run(cmdline, timeout=600.0, shell=True)
            return redirect("/expert")
        if request.form.get("nightly_update") == "go":
            ENV_FILE.update(
                {
                    "NIGHTLY_BASE_UPDATE": "1" if request.form.get("nightly_base") else "0",
                    "NIGHTLY_CONTAINER_UPDATE": "1"
                    if request.form.get("nightly_container")
                    else "0",
                }
            )
        if request.form.get("zerotier") == "go":
            ENV_FILE.update(
                {
                    "ZEROTIER": "1",
                    "ZEROTIER_NETWORK_ID": request.form.get("zerotierid"),
                }
            )
            # make sure the service is enabled (it really should be)
            subprocess.call("/usr/bin/systemctl enable --now zerotier-one", shell=True)

            # now we need to connect to the network:
            subprocess.call(
                f"/usr/sbin/zerotier-cli join {ENV_FILE.envs.get('ZEROTIER_NETWORK_ID')}",
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

            RESTART.restart_systemd()
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

            RESTART.restart_systemd()
            return redirect("restarting")

        print("request_form", request.form)
        return redirect("/")


#@app.route("/aggregators", methods=("GET", "POST"))
    def aggregators(self):
        if RESTART.lock.locked():
            return redirect("/restarting")
        if request.method == "POST":
            return handle_aggregators_post_request()
        env_values = ENV_FILE.envs
        return render_template(
            "aggregators.html", env_values=env_values, metadata=ENV_FILE.metadata
        )


    #@app.route("/")

    def director(self):
        # figure out where to go:
        env_values = ENV_FILE.envs
        if env_values.get("BASE_CONFIG") != "1":
            return setup()
        num_sdrs = env_values.get("NUM_SDRS")
        if (
            num_sdrs
            and int(num_sdrs) > 1
            and not (env_values.get("FEEDER_1090") or env_values.get("AIRSPY") == "1")
        ):
            return advanced()
        return index()


    #@app.route("/index")
    def index(self):
        return render_template(
            "index.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata
        )


    #@app.route("/setup", methods=("GET", "POST"))
    def setup(self):
        if RESTART.lock.locked():
            return redirect("/restarting")
        if request.method == "POST" and request.form.get("submit") == "go":
            lat, lng, alt, form_timezone, mlat_name, agg = (
                request.form[key]
                for key in [
                    "lat",
                    "lng",
                    "alt",
                    "form_timezone",
                    "mlat_name",
                    "aggregators",
                ]
            )
            print_err(
                f"got lat: {lat}, lng: {lng}, alt: {alt}, TZ: {form_timezone}, mlat-name: {mlat_name}, agg: {agg}"
            )
            if all([lat, lng, alt, form_timezone]):
                # first set the base data
                ENV_FILE.update(
                    {
                        "FEEDER_LAT": lat,
                        "FEEDER_LONG": lng,
                        "FEEDER_ALT_M": alt,
                        "FEEDER_TZ": form_timezone,
                        "MLAT_SITE_NAME": mlat_name,
                        "FEEDER_AGG": agg,
                    }
                )
                # while we are at it, set the local time zone
                subprocess.call(
                    f"/usr/bin/timedatectl set-timezone {form_timezone}", shell=True
                )
                # with the data just stored, we can now take a guess at the Ultrafeeder config
                # using the SDR mapping (in most cases this will be just one)
                # and the remaining base settings
                sdr_mapping = map_sdrs()
                sdr_mapping.update(setup_airspy_or_rtl())
                ENV_FILE.update(sdr_mapping)
                net = ENV_FILE.generate_ultrafeeder_config(request.form)
                num = get_sdr_info()["num"]
                ENV_FILE.update(
                    {
                        "FEEDER_ULTRAFEEDER_CONFIG": net,
                        "UF": "1" if net else "0",
                        "BASE_CONFIG": "1",
                        "NUM_SDRS": num,
                    }
                )
                if not ENV_FILE.envs.get("FEEDER_1090"):
                    return redirect(url_for("advanced"))
                if agg == "ind":
                    return redirect(url_for("aggregators"))
                return redirect(url_for("restarting"))

        return render_template(
            "setup.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata
        )
