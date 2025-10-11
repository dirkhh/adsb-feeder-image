import math
import os
import pathlib
import signal
import socketserver
import subprocess
import sys
import threading
import time
from sys import argv

from fakedns import DNSHandler
from flask import (
    Flask,
    redirect,
    render_template,
    request,
)
from utils.wifi import Wifi


def print_err(*args, **kwargs):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".{0:03.0f}Z".format(math.modf(time.time())[0] * 1000)
    print(*((timestamp,) + args), file=sys.stderr, **kwargs)


class Hotspot:
    def __init__(self, wlan):
        self.app = Flask(__name__)
        self.wlan = wlan
        self.wifi = Wifi(wlan)
        if pathlib.Path("/opt/adsb/adsb.im.version").exists():
            with open("/opt/adsb/adsb.im.version", "r") as f:
                self.version = f.read().strip()
        else:
            self.version = "unknown"
        self.comment = ""
        self.restart_state = "done"
        self.ssid = ""
        self.passwd = ""
        self._dnsserver = None
        self._dns_thread = None
        self._baseos = self.wifi.baseos
        if self._baseos == "unknown":
            print_err("unknown baseos - giving up")
            sys.exit(1)
        print_err("trying to scan for SSIDs")
        self.wifi.ssids = []
        startTime = time.time()
        while time.time() - startTime < 20:
            self.wifi.scan_ssids()
            if len(self.wifi.ssids) > 0:
                break

        self.app.add_url_rule("/hotspot", view_func=self.hotspot, methods=["GET"])
        self.app.add_url_rule("/restarting", view_func=self.restarting)

        self.app.add_url_rule("/restart", view_func=self.restart, methods=["POST", "GET"])
        self.app.add_url_rule(
            "/",
            "/",
            view_func=self.catch_all,
            defaults={"path": ""},
            methods=["GET", "POST"],
        )
        self.app.add_url_rule("/<path:path>", view_func=self.catch_all, methods=["GET", "POST"])

    def restart(self):
        return self.restart_state

    def hotspot(self):
        return render_template("hotspot.html", version=self.version, comment=self.comment, ssids=self.wifi.ssids)

    def catch_all(self, path):
        # Catch all requests not explicitly handled. Since our fake DNS server
        # resolves all names to us, this may literally be any request the
        # client tries to make to anyone. If it looks like they're sending us
        # wifi credentials, try those and restart. In all other cases, render
        # the /hotspot page.
        if self.restart_state == "restarting":
            return redirect("/restarting")

        if self._request_looks_like_wifi_credentials():
            self.lastUserInput = time.monotonic()
            self.restart_state = "restarting"

            self.ssid = request.form.get("ssid", "")
            self.passwd = request.form.get("passwd", "")

            threading.Thread(target=self.test_wifi).start()
            print_err("started wifi test thread")

            return redirect("/restarting")

        return self.hotspot()

    def _request_looks_like_wifi_credentials(self):
        return request.method == "POST" and "ssid" in request.form and "passwd" in request.form

    def restarting(self):
        return render_template("hotspot-restarting.html")

    def run(self):
        self.setup_hotspot()

        self.lastUserInput = time.monotonic()

        def idle_exit():
            while True:
                idleTime = time.monotonic() - self.lastUserInput
                if idleTime > 300:
                    break

                time.sleep(300 - idleTime)

            # 5 minutes without user interaction: quit the app and have the shell script check if networking is working now
            self.restart_state = "restarting"
            self.teardown_hotspot()
            print_err("exiting the hotspot app after 5 minutes idle")
            signal.raise_signal(signal.SIGTERM)

        threading.Thread(target=idle_exit).start()

        self.app.run(host="0.0.0.0", port=80)

    def setup_hotspot(self):
        if not self._dnsserver and not self._dns_thread:
            print_err("creating DNS server")
            try:
                self._dnsserver = socketserver.ThreadingUDPServer(("", 53), DNSHandler)
            except OSError as e:
                print_err(f"failed to create DNS server: {e}")
            else:
                print_err("starting DNS server")
                self._dns_thread = threading.Thread(target=self._dnsserver.serve_forever)
                self._dns_thread.start()

        # in case of a wifi already being configured with wrong password,
        # we need to stop the relevant service to prevent it from disrupting hostapd

        if self._baseos == "dietpi":
            subprocess.run(
                "systemctl stop networking.service",
                shell=True,
            )
        elif self._baseos == "raspbian":
            subprocess.run(
                "systemctl stop NetworkManager wpa_supplicant; iw reg set 00",
                shell=True,
            )

        subprocess.run(
            f"ip li set {self.wlan} up && "
            f"ip ad add 192.168.199.1/24 broadcast 192.168.199.255 dev {self.wlan} && "
            f"systemctl start hostapd.service",
            shell=True,
        )
        time.sleep(2)
        subprocess.run(
            "systemctl start isc-dhcp-server.service",
            shell=True,
        )
        print_err("started hotspot")

    def teardown_hotspot(self):
        subprocess.run(
            f"systemctl stop isc-dhcp-server.service; "
            f"systemctl stop hostapd.service; "
            f"ip ad del 192.168.199.1/24 dev {self.wlan}; "
            f"ip addr flush {self.wlan}; "
            f"ip link set dev {self.wlan} down",
            shell=True,
        )
        if self._baseos == "dietpi":
            output = subprocess.run(
                "systemctl restart --no-block networking.service",
                shell=True,
                capture_output=True,
            )
            print_err(f"restarted networking.service: {output.returncode}\n{output.stderr.decode()}\n{output.stdout.decode()}")
        elif self._baseos == "raspbian":
            subprocess.run(
                "iw reg set PA; systemctl restart wpa_supplicant NetworkManager",
                shell=True,
            )
        # used to wait here, just spin around the wifi instead
        print_err("turned off hotspot")

    def setup_wifi(self):
        if self._dnsserver:
            print_err("shutting down DNS server")
            self._dnsserver.shutdown()

        print_err(f"connected to wifi: '{self.ssid}'")

        # the shell script that launched this app will do a final connectivity check
        # if there is no connectivity despite being able to join the wifi, it will re-launch this app (unlikely)

        print_err("exiting the hotspot app")
        signal.raise_signal(signal.SIGTERM)
        os._exit(0)

    def test_wifi(self):
        # the parent process needs to return from the call to POST
        time.sleep(1.0)
        self.teardown_hotspot()

        print_err(f"testing the '{self.ssid}' network")

        success = self.wifi.wifi_connect(self.ssid, self.passwd)

        if success:
            print_err(f"successfully connected to '{self.ssid}'")
        else:
            print_err(f"test_wifi failed to connect to '{self.ssid}'")

            self.comment = "Failed to connect, wrong SSID or password, please try again."
            # now we bring back up the hotspot in order to deliver the result to the user
            # and have them try again
            self.setup_hotspot()
            self.restart_state = "done"
            return

        self.setup_wifi()
        self.restart_state = "done"
        return


if __name__ == "__main__":
    wlan = "wlan0"
    if len(argv) == 2:
        wlan = argv[1]
    print_err(f"starting hotspot for {wlan}")
    hotspot = Hotspot(wlan)

    hotspot.run()
