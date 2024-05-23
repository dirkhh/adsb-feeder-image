import math
import os
import pathlib
import signal
import socketserver
import subprocess
import sys
import threading
import time
from flask import (
    Flask,
    redirect,
    render_template,
    request,
)
from sys import argv
from fakedns import DNSHandler


def print_err(*args, **kwargs):
    timestamp = time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.gmtime()
    ) + ".{0:03.0f}Z".format(math.modf(time.time())[0] * 1000)
    print(*((timestamp,) + args), file=sys.stderr, **kwargs)


class Hotspot:
    def __init__(self, wlan):
        self.app = Flask(__name__)
        self.wlan = wlan
        if pathlib.Path("/opt/adsb/adsb.im.version").exists():
            with open("/opt/adsb/adsb.im.version", "r") as f:
                self.version = f.read().strip()
        else:
            self.version = "unknown"
        self.comment = ""
        self.restart_state = ""
        self.ssid = ""
        self.passwd = ""
        self._dnsserver = None
        self._dns_thread = None

        self.app.add_url_rule("/restarting", view_func=self.restarting)

        self.app.add_url_rule(
            "/restart", view_func=self.restart, methods=["POST", "GET"]
        )
        self.app.add_url_rule(
            "/",
            "/",
            view_func=self.catch_all,
            defaults={"path": ""},
            methods=["GET", "POST"],
        )
        self.app.add_url_rule(
            "/<path:path>", view_func=self.catch_all, methods=["GET", "POST"]
        )

    def restart(self):
        if request.method == "POST":
            self.restart_state = "restarting"
            thread = threading.Thread(target=self.test_wifi)
            thread.start()
            print_err("started wifi test thread")
            return self.restart_state
        if request.method == "GET":
            return self.restart_state

    def catch_all(self, path):
        if request.method == "POST":
            self.ssid = request.form.get("ssid")
            self.passwd = request.form.get("passwd")
            return redirect("/restarting")
        return render_template(
            "hotspot.html", version=self.version, comment=self.comment
        )

    def restarting(self):
        return render_template("restart-wait.html")

    def run(self):
        self.setup_hotspot()
        self.app.run(host="0.0.0.0", port=80)

    def setup_hotspot(self):
        if not self._dnsserver:
            print_err("creating DNS server")
            self._dnsserver = socketserver.ThreadingUDPServer(("", 53), DNSHandler)
        print_err("starting DNS server")
        self._dns_thread = threading.Thread(target=self._dnsserver.serve_forever)
        self._dns_thread.start()
        subprocess.run(
            f"ip li set {self.wlan} up && ip ad add 192.168.199.1/24 broadcast 192.168.199.255 dev {self.wlan} && systemctl start hostapd.service && systemctl start isc-dhcp-server.service",
            shell=True,
        )
        print_err("started hotspot")

    def teardown_hotspot(self):
        if self._dnsserver:
            print_err("shutting down DNS server")
            self._dnsserver.shutdown()
        subprocess.run(
            f"systemctl stop hostapd.service && systemctl stop isc-dhcp-server.service && ip addr flush {self.wlan} && ip link set dev {self.wlan} down",
            shell=True,
        )
        print_err("turned off hotspot")

    def setup_wifi(self):
        self.teardown_hotspot()
        print_err(f"connecting to {self.ssid}")
        # switch hotplug to allow wifi
        with open("/etc/network/interfaces", "r") as current, open(
            "/etc/network/interfaces.new", "w"
        ) as update:
            lines = current.readlines()
            for line in lines:
                if "allow-hotplug" in line:
                    if self.wlan in line:
                        update.write(f"allow-hotplug {self.wlan}\n")
                    else:
                        update.write(f"# {line}")
                else:
                    update.write(f"{line}")
            os.remove("/etc/network/interfaces")
            os.rename("/etc/network/interfaces.new", "/etc/network/interfaces")
        output = subprocess.run(
            f"wpa_passphrase {self.ssid} {self.passwd} > /etc/wpa_supplicant/wpa_supplicant.conf && systemctl restart networking.service",
            shell=True,
            capture_output=True,
        )
        print_err(
            f"restarted networking.service: {output.returncode}\n{output.stderr.decode()}\n{output.stdout.decode()}"
        )

        # sleep for a few seconds to make sure we connect to the network
        time.sleep(5.0)
        # I guess here I should test the network, eh?
        print_err("exiting the hotspot app")
        open("/opt/adsb/continueboot", "w").close()
        signal.raise_signal(signal.SIGTERM)
        os._exit(0)

    def test_wifi(self):
        # the parent process needs to return from the call to POST
        time.sleep(2.0)
        print_err(f"testing the {self.ssid} network")
        self.teardown_hotspot()
        try:
            result = subprocess.run(
                f'bash -c "wpa_supplicant -i{self.wlan} -c<(wpa_passphrase {self.ssid} {self.passwd})"',
                shell=True,
                capture_output=True,
                timeout=10.0,
            )
        except subprocess.TimeoutExpired as e:
            # that's the expected behavior
            output = e.output.decode()
            if e.stderr:
                output += e.stderr.decode()
        else:
            output = result.stdout.decode()
            if result.stderr:
                output += result.stderr.decode()

        self.restart_state = "done"
        if "CTRL-EVENT-CONNECTED" in output:
            self.comment = "Success. The installation will continue (and this network will disconnect) in a few seconds."
        else:
            self.comment = (
                "Failed to connect, wrong SSID or password, please try again."
            )
        print_err(
            f"{self.comment}: attempt to connect resulted in {output} - returning to hotspot mode"
        )

        # now we bring back up the hotspot in order to deliver the result to the user
        self.setup_hotspot()
        if self.comment.startswith("Success"):
            # we wait a fairly long time to be sure that the browser catches on and shows
            # the 'continue' page
            print_err("waiting for browser to show 'continue' page")
            time.sleep(10.0)
            self.setup_wifi()


if __name__ == "__main__":
    wlan = "wlan0"
    if len(argv) == 2:
        wlan = argv[1]
    print_err(f"starting hotspot for {wlan}")
    hotspot = Hotspot(wlan)
    hotspot.run()
