import filecmp
import io
import json
import os.path
import pathlib
import re
import shutil
import subprocess
import zipfile

from aggregators import handle_aggregators_post_request
from flask import Flask, flash, render_template, request, redirect, send_file, url_for
from os import urandom, path
from typing import List, Tuple
from utils import RESTART, ENV_FILE, print_err
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = urandom(16).hex()


# let's play proxy, shall we?
proxy_routes = [
    # endpoint, port, url_path
    ["/map/", 8080, "/"],
    ["/tar1090/", 8080, "/"],
    ["/graphs1090/", 8080, "/graphs1090/"],
    ["/graphs/", 8080, "/graphs1090/"],
    ["/stats/", 8080, "/graphs1090/"],
    ["/piaware/", 8081, "/"],
    ["/fa/", 8081, "/"],
    ["/flightaware/", 8081, "/"],
    ["/piaware-stats/", 8082, "/"],
    ["/pa-stats/", 8082, "/"],
    ["/fa-stats/", 8082, "/"],
    ["/fa-status/", 8082, "/"],
    ["/config/", 5000, "/setup"],
    ["/fr-status/", 8754, "/"],
    ["/fr/", 8754, "/"],
    ["/fr24/", 8754, "/"],
    ["/flightradar/", 8754, "/"],
    ["/flightradar24/", 8754, "/"],
    ["/portainer/", 9443, "/"],
]


# inner function used to redirect the caller to the correct endpoint
def my_redirect(orig, new_port, new_path):
    print_err(f"my_redirect called for endpoint {orig} with port {new_port} and path {new_path}")
    host_url = request.host_url.rstrip("/ ")
    host_url = re.sub(":\\d+$", "", host_url)
    new_path = new_path.rstrip("/ ")
    q: str = ""
    if request.query_string:
        q = f"?{request.query_string.decode()}"
    print_err(f"after cleanup: host|{host_url}| path|{new_path}| query-string|{q}|")
    url = f"{host_url}:{new_port}{new_path}{q}"
    # work around oddity in tar1090
    if url.endswith("graphs1090"):
        url += "/"
    print_err(f"redirecting {orig} to {url}")
    return redirect(url)


# factory to create local functions that respond to the route endpoint
def function_factory(orig_endpoint, new_port, new_path):
    def f():
        return my_redirect(orig_endpoint, new_port, new_path)

    return f


for endpoint, port, url_path in proxy_routes:
    r = function_factory(endpoint, port, url_path)
    print_err(f"{r} for {endpoint}")
    app.add_url_rule(endpoint, endpoint, r)


@app.route("/propagateTZ")
def get_tz():
    browser_timezone = request.args.get("tz")
    env_values = ENV_FILE.envs
    env_values["FEEDER_TZ"] = browser_timezone
    return render_template(
        "setup.html", env_values=env_values, metadata=ENV_FILE.metadata
    )


@app.route("/restarting", methods=(["GET"]))
def restarting():
    return render_template(
        "restarting.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata
    )


@app.route("/restart", methods=(["GET", "POST"]))
def restart():
    if request.method == "POST":
        resp = RESTART.restart_systemd()
        return "restarting" if resp else "already restarting"
    if request.method == "GET":
        return RESTART.state


@app.route("/backup")
def backup():
    return render_template("/backup.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata)


@app.route("/backupexecute")
def backup_execute():
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
    return send_file(data, mimetype="application/zip", as_attachment=True, download_name="adsb-feeder-config.zip")


@app.route("/restore", methods=['GET', 'POST'])
def restore():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file submitted')
            return redirect(request.url)
        file = request.files['file']
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == '':
            flash('No file selected')
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
        return render_template("/restore.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata)


@app.route("/executerestore", methods=["GET", "POST"])
def executerestore():
    if request.method == "GET":
        # the user has uploaded a zip file and we need to take a look.
        # be very careful with the content of this zip file...
        filename = request.args['zipfile']
        adsb_path = pathlib.Path("/opt/adsb")
        restore_path = pathlib.Path("/opt/adsb/restore")
        restored_files: List[str] = []
        with zipfile.ZipFile(restore_path / filename, "r") as restore_zip:
            for name in restore_zip.namelist():
                print_err(f"found file {name} in archive")
                # only accept the .env file and simple .yml filenames
                if name != ".env" and not name.startswith("ultrafeeder/") and \
                   (not name.endswith(".yml") or name != secure_filename(name)):
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
        return redirect("/advanced")  # that's a good place from where the user can continue

# first number (num) tells us how many SDRs there are (or -1 if unknown),
# second bool (access) tells us if we have full access
# third list of strings gives us the serial numbers (assuming num > 0 and access True)
def check_sdrs() -> Tuple[int, bool, List[str]]:
    num = -1
    access = False
    serials: List[str] = []
    output: str = ""
    if not os.path.isfile("/usr/bin/rtl_eeprom"):
        print_err("can't find rtl_eeprom")
        return num, False, serials
    try:
        result = subprocess.run("/usr/bin/rtl_eeprom", shell=True, capture_output=True, timeout=20.0)
    except subprocess.TimeoutExpired as exc:
        output = exc.stderr.decode()
    else:
        output = result.stderr.decode()
    print_err(f"coming back from first call with {output}")
    match = re.search("Found (\\d+) device", output)
    if match:
        num = int(match.group(1))
    match = re.search("usb_claim_interface error",output)
    if not match:
        access = True
        match = re.search("Serial number:\\s+(\\S+)", output)
        if match:
            serials.append(match.group(1))
        for i in range(1, num):
            try:
                result = subprocess.run(f"/usr/bin/rtl_eeprom -d {i}", shell=True, capture_output=True, timeout=20.0)
            except subprocess.TimeoutExpired as exc:
                output = exc.stderr.decode()
            else:
                output = result.stderr.decode()
            print_err(f"coming back from call number {i} with {output}")
            match = re.search("Serial number:\\s+(\\S+)", output)
            if match:
                serials.append(match.group(1))
    if 0 < num != len(serials):
        print_err(f"found {num} SDRs but only {len(serials)} serial numbers")
    return num, access, serials


@app.route("/api/can_read_sdr")
def can_read_sdr():
    num, access, serials = check_sdrs()
    sdr_state = {"num": num, "access": access, "serials": serials}
    return json.dumps(sdr_state)


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
    print_err("request_form", request.form)
    if request.form.get("submit") == "go":
        advanced_settings = {
                "FEEDER_TAR1090_USEROUTEAPI": "1" if request.form.get("route") else "0",
                "MLAT_PRIVACY": "--privacy" if request.form.get("privacy") else "",
                "HEYWHATSTHAT": "1" if request.form.get("heywhatsthat") else "",
                "FEEDER_HEYWHATSTHAT_ID": request.form.get("FEEDER_HEYWHATSTHAT_ID", default=""),
                "FEEDER_READSB_ENABLE_BIASTEE": "true" if request.form.get("biast") else "",
            }
        serial1090 = request.form.get("1090", default="")
        serial978 = request.form.get("978", default="")
        if serial1090:
            advanced_settings["ADSB_SDR_SERIAL"] = serial1090
        if serial978:
            advanced_settings["UAT_SDR_SERIAL"] = serial978
            advanced_settings["FEEDER_ENABLE_UAT978"] = "yes"
            advanced_settings["FEEDER_URL_978"] = "http://dump978/skyaware978"
        ENV_FILE.update(advanced_settings)
    return redirect("/restarting")


@app.route("/expert", methods=("GET", "POST"))
def expert():
    if request.method == "POST":
        return handle_expert_post_request()
    env_values = ENV_FILE.envs
    if RESTART.lock.locked():
        return redirect("/restarting")
    filecontent = {'have_backup': False}
    if path.exists("/opt/adsb/env-working") and path.exists("/opt/adsb/docker-compose.yml-working"):
        filecontent['have_backup'] = True
    with open("/opt/adsb/.env", "r") as env:
        filecontent['env'] = env.read()
    with open("/opt/adsb/docker-compose.yml") as dc:
        filecontent['dc'] = dc.read()
    return render_template(
        "expert.html", env_values=env_values, metadata=ENV_FILE.metadata, filecontent=filecontent
    )


def handle_expert_post_request():
    if request.form.get("ssh") == "go":
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
        ENV_FILE.update({
            "NIGHTLY_BASE_UPDATE": "1" if request.form.get("nightly_base") else "0",
            "NIGHTLY_CONTAINER_UPDATE": "1" if request.form.get("nightly_container") else "0",
        })
    if request.form.get("zerotier") == "go":
        ENV_FILE.update({
            "ZEROTIER": "1",
            "ZEROTIER_NETWORK_ID": request.form.get("zerotierid"),
        })
        # make sure the service is enabled (it really should be)
        subprocess.call("/usr/bin/systemctl enable --now zerotier", shell=True)

        # now we need to connect to the network:
        subprocess.call(f"/usr/sbin/zerotier-cli join {ENV_FILE.envs.get('ZEROTIER_NETWORK_ID')}")
    if request.form.get("you-asked-for-it") == "you-got-it":
        # well - let's at least try to save the old stuff
        if not path.exists("/opt/adsb/env-working"):
            try:
                shutil.copyfile("/opt/adsb/.env", "/opt/adsb/env-working")
            except shutil.Error as err:
                print(f"copying .env didn't work: {err.args[0]}: {err.args[1]}")
        if not path.exists("/opt/adsb/dc-working"):
            try:
                shutil.copyfile("/opt/adsb/docker-compose.yml", "/opt/adsb/docker-compose.yml-working")
            except shutil.Error as err:
                print(f"copying docker-compose.yml didn't work: {err.args[0]}: {err.args[1]}")
        with open("/opt/adsb/.env", "w") as env:
            env.write(request.form["env"])
        with open("/opt/adsb/docker-compose.yml", "w") as dc:
            dc.write(request.form["dc"])

        RESTART.restart_systemd()
        return redirect("restarting")

    if request.form.get("you-got-it") == "give-it-back":
        # do we have saved old files?
        if path.exists("/opt/adsb/env-working"):
            try:
                shutil.copyfile("/opt/adsb/env-working", "/opt/adsb/.env")
            except shutil.Error as err:
                print(f"copying .env didn't work: {err.args[0]}: {err.args[1]}")
        if path.exists("/opt/adsb/docker-compose.yml-working"):
            try:
                shutil.copyfile("/opt/adsb/docker-compose.yml-working", "/opt/adsb/docker-compose.yml")
            except shutil.Error as err:
                print(f"copying docker-compose.yml didn't work: {err.args[0]}: {err.args[1]}")

        RESTART.restart_systemd()
        return redirect("restarting")

    print("request_form", request.form)
    return redirect("/")


@app.route("/aggregators", methods=("GET", "POST"))
def aggregators():
    if RESTART.lock.locked():
        return redirect("/restarting")
    if request.method == "POST":
        return handle_aggregators_post_request()
    env_values = ENV_FILE.envs
    return render_template(
        "aggregators.html", env_values=env_values, metadata=ENV_FILE.metadata
    )


@app.route("/")
def director():
    # figure out where to go:
    env_values = ENV_FILE.envs
    if env_values.get("BASE_CONFIG") != "1":
        return setup()
    num_sdrs = env_values.get("NUM_SDRS")
    if num_sdrs and int(num_sdrs) > 1 and not env_values.get("ADSB_SDR_SERIAL"):
        return advanced()
    return index()


@app.route("/index")
def index():
    return render_template(
        "index.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata
    )

    
@app.route("/setup", methods=("GET", "POST"))
def setup():
    if RESTART.lock.locked():
        return redirect("/restarting")
    if request.method == "POST" and request.form.get("submit") == "go":
        lat, lng, alt, form_timezone, mlat_name, agg = (
            request.form[key]
            for key in ["lat", "lng", "alt", "form_timezone", "mlat_name", "aggregators", ]
        )
        print_err(f"got lat: {lat}, lng: {lng}, alt: {alt}, TZ: {form_timezone}, mlat-name: {mlat_name}, agg: {agg}")
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
            subprocess.call(f"/usr/bin/timedatectl set-timezone {form_timezone}", shell=True)
            # with the data just stored, we can now create the Ultrafeeder config
            # and the remaining base settings
            net = ENV_FILE.generate_ultrafeeder_config(request.form)
            num, access, serials = check_sdrs()
            ENV_FILE.update(
                {
                    "FEEDER_ULTRAFEEDER_CONFIG": net,
                    "UF": "1" if net else "0",
                    "BASE_CONFIG": "1",
                    "NUM_SDRS": num
                }
            )
            if num > 1 and not ENV_FILE.envs.get("ADSB_SDR_SERIAL"):
                return redirect(url_for("advanced"))
            return redirect(url_for("restarting"))

    return render_template(
        "setup.html", env_values=ENV_FILE.envs, metadata=ENV_FILE.metadata
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
