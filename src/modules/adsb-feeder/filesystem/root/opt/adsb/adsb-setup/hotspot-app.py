import math
import os
import pathlib
import signal
import socketserver
import subprocess
import sys
import threading
import tempfile
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
        self.restart_state = "done"
        self.ssid = ""
        self.passwd = ""
        self._dnsserver = None
        self._dns_thread = None

        if pathlib.Path("/boot/dietpi").exists():
            self._baseos = "dietpi"
        elif pathlib.Path("/etc/rpi-issue").exists():
            self._baseos = "raspbian"
        else:
            print_err("unknown baseos - giving up")
            sys.exit(1)
        print_err("trying to scan for SSIDs")
        self.ssids = []
        i = 0
        while i < 10:
            i += 1
            self.scan_ssids()
            if len(self.ssids) > 0:
                break
            time.sleep(2.0)

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

    def scan_ssids(self):
        try:
            if self._baseos == "raspbian":
                output = subprocess.run(
                    "nmcli --terse --fields SSID dev wifi",
                    shell=True,
                    capture_output=True,
                )
            else:
                output = subprocess.run(
                    f"ip li set up dev {self.wlan} && iw dev {self.wlan} scan | grep SSID: | sed -e 's/^[:space:]*SSID: //'",
                    shell=True,
                    capture_output=True,
                )
        except subprocess.CalledProcessError as e:
            print_err(f"error scanning for SSIDs: {e}")
            return
        ssids = []
        for line in output.stdout.decode().split("\n"):
            if line and line != "--" and line not in ssids:
                ssids.append(line)
        if len(ssids) > 0:
            print_err(f"found SSIDs: {ssids}")
            self.ssids = ssids
        else:
            print_err("no SSIDs found")

    def restart(self):
        return self.restart_state

    def catch_all(self, path):
        if self.restart_state == "restarting":
            return redirect("/restarting")

        if request.method == "POST":
            self.lastUserInput = time.time()
            self.restart_state = "restarting"

            self.ssid = request.form.get("ssid")
            self.passwd = request.form.get("passwd")

            threading.Thread(target=self.test_wifi).start()
            print_err("started wifi test thread")

            return redirect("/restarting")

        return render_template(
            "hotspot.html", version=self.version, comment=self.comment, ssids=self.ssids
        )

    def restarting(self):
        return render_template("restart-wait.html")

    def run(self):
        self.setup_hotspot()

        self.lastUserInput = time.time()
        def idle_exit():
            while True:
                idleTime = time.time() - self.lastUserInput
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
                self._dns_thread = threading.Thread(
                    target=self._dnsserver.serve_forever
                )
                self._dns_thread.start()

        # in case of a wifi already being configured with wrong password,
        # we need to stop the relevant service to prevent it from disrupting hostapd

        if self._baseos == "dietpi":
            subprocess.run(
                f"systemctl stop networking.service",
                shell=True,
            )
        elif self._baseos == "raspbian":
            subprocess.run(
                f"systemctl stop NetworkManager",
                shell=True,
            )

        subprocess.run(
            f"ip li set {self.wlan} up && ip ad add 192.168.199.1/24 broadcast 192.168.199.255 dev {self.wlan} && systemctl start hostapd.service",
            shell=True,
        )
        time.sleep(2)
        subprocess.run(
            f"systemctl start isc-dhcp-server.service",
            shell=True,
        )
        print_err("started hotspot")

    def teardown_hotspot(self):
        subprocess.run(
            f"systemctl stop isc-dhcp-server.service; systemctl stop hostapd.service; ip ad del 192.168.199.1/24 dev {self.wlan}; ip addr flush {self.wlan}; ip link set dev {self.wlan} down",
            shell=True,
        )
        if self._baseos == "dietpi":
            subprocess.run(
                f"systemctl restart --no-block networking.service",
                shell=True,
            )
        elif self._baseos == "raspbian":
            subprocess.run(
                f"systemctl restart NetworkManager",
                shell=True,
            )
        # used to wait here, just spin around the wifi instead
        print_err("turned off hotspot")

    def setup_wifi(self):
        if self._dnsserver:
            print_err("shutting down DNS server")
            self._dnsserver.shutdown()

        print_err(f"connecting to '{self.ssid}'")
        if self._baseos == "dietpi":
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
                f"wpa_passphrase '{self.ssid}' '{self.passwd}' > /etc/wpa_supplicant/wpa_supplicant.conf && systemctl restart --no-block networking.service",
                shell=True,
                capture_output=True,
            )
            print_err(
                f"restarted networking.service: {output.returncode}\n{output.stderr.decode()}\n{output.stdout.decode()}"
            )
        elif self._baseos == "raspbian":
            # we should be all set already on raspbian
            print_err(f"started wlan connection to '{self.ssid}'")
        else:
            print_err(f"unknown baseos: can't set up wifi")

        # the shell script that launched this app will do a final connectivity check
        # if there is no connectivity despite being able to join the wifi, it will re-launch this app (unlikely)

        print_err("exiting the hotspot app")
        signal.raise_signal(signal.SIGTERM)
        os._exit(0)

    def test_wifi(self):
        # the parent process needs to return from the call to POST
        time.sleep(2.0)
        print_err(f"testing the '{self.ssid}' network")
        self.teardown_hotspot()

        # wpa_supplicant will step over each other unless we stop networking service during this test
        if self._baseos == "dietpi":
            subprocess.run(
                f"systemctl stop networking.service",
                shell=True,
            )

        # try for a while because it takes a bit for NetworkManager to come back up (for raspbian it was started in teardown_hotspot
        startTime = time.time()
        while time.time() - startTime < 17:
            if self._baseos == "dietpi":
                try:
                    fd, tmpConf = tempfile.mkstemp()
                    os.close(fd)
                    result = subprocess.run(
                        f"wpa_passphrase '{self.ssid}' '{self.passwd}' > '{tmpConf}'",
                        shell=True,
                        check=True,
                        capture_output=True,
                        timeout=5.0,
                    )
                    result = subprocess.run(
                        ["wpa_supplicant", f"-i{self.wlan}", f"-c{tmpConf}"],
                        shell=False,
                        capture_output=True,
                        timeout=5.0,
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
                finally:
                    pathlib.Path(tmpConf).unlink(missing_ok=True)

                success = "CTRL-EVENT-CONNECTED" in output

            elif self._baseos == "raspbian":
                try:
                    result = subprocess.run(
                        f"nmcli d wifi connect '{self.ssid}' password '{self.passwd}' ifname {self.wlan}",
                        shell=True,
                        capture_output=True,
                        timeout=5.0,
                    )
                except subprocess.SubprocessError as e:
                    # something went wrong
                    output = e.output.decode()
                    if e.stderr:
                        output += e.stderr.decode()
                else:
                    output = result.stdout.decode()
                    if result.stderr:
                        output += result.stderr.decode()
                success = "successfully activated" in output

            if success:
                print_err(f"successfully connected to '{self.ssid}'")
                break
            else:
                print_err(f"failed to connect to '{self.ssid}': {output}")
                # just to safeguard against super fast spin, sleep a tiny bit
                time.sleep(0.1)

        if self._baseos == "dietpi":
            subprocess.run(
                f"systemctl restart --no-block networking.service",
                shell=True,
            )

        if not success:
            self.comment = (
                "Failed to connect, wrong SSID or password, please try again."
            )
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
