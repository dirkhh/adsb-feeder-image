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
        startTime = time.time()
        while time.time() - startTime < 20:
            self.scan_ssids()
            if len(self.ssids) > 0:
                break

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

    def wpa_cli_reconfigure(self):
        connected = False
        output = ""
        try:
            proc = subprocess.Popen(
                    ["wpa_cli", f"-i{self.wlan}"],
                    stderr=subprocess.STDOUT,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    text=True,
                    )
            os.set_blocking(proc.stdout.fileno(), False)


            startTime = time.time()
            reconfigured = False
            while time.time() - startTime < 20:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.01)
                    continue

                output += line
                #print(line, end="")
                if "Interactive mode" in line:
                    proc.stdin.write("reconfigure\n")
                    proc.stdin.flush()
                if "reconfigure" in line:
                    reconfigured = True
                if reconfigured and "CTRL-EVENT-CONNECTED" in line:
                    connected = True
                    break
        except:
            pass
        finally:
            if proc:
                proc.terminate()


        if not connected:
            print_err(f"Couldn't connect after wpa_cli reconfigure: ouput: {output}")

        return connected

    def wpa_cli_scan(self):
        ssids = []
        try:
            proc = subprocess.Popen(
                    ["wpa_cli", f"-i{self.wlan}"],
                    stderr=subprocess.STDOUT,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    text=True,
                    )
            os.set_blocking(proc.stdout.fileno(), False)

            output = ""

            startTime = time.time()
            while time.time() - startTime < 15:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.01)
                    continue

                output += line
                #print(line, end="")
                if line.count("Interactive mode"):
                    proc.stdin.write("scan\n")
                    proc.stdin.flush()
                if line.count("CTRL-EVENT-SCAN-RESULTS"):
                    proc.stdin.write("scan_results\n")
                    proc.stdin.flush()
                    break

            startTime = time.time()
            while time.time() - startTime < 1:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.01)
                    continue

                output += line
                if line.count("\t"):
                    fields = line.rstrip("\n").split("\t")
                    if len(fields) == 5:
                        ssids.append(fields[4])

        except:
            print_err(f"ERROR in wpa_cli_scan(), wpa_cli ouput: {output}")
        finally:
            if proc:
                proc.terminate()

        return ssids


    def scan_ssids(self):
        if self._baseos == "raspbian":
            try:
                output = subprocess.run(
                        "nmcli --terse --fields SSID dev wifi",
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
        else:
            ssids = self.wpa_cli_scan()

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
        return render_template("hotspot-restarting.html")

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
                f"systemctl stop NetworkManager wpa_supplicant",
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
                f"systemctl restart --no-block networking.service",
                shell=True,
                capture_output=True,
            )
            print_err(
                f"restarted networking.service: {output.returncode}\n{output.stderr.decode()}\n{output.stdout.decode()}"
            )
        elif self._baseos == "raspbian":
            subprocess.run(
                f"systemctl restart wpa_supplicant NetworkManager",
                shell=True,
            )
        # used to wait here, just spin around the wifi instead
        print_err("turned off hotspot")

    def writeWpaConf(self, ssid=None, passwd=None, path=None):
        try:
            with open(path, "w") as conf:
                conf.write(
"""
# WiFi country code, set here in case the access point does send one
country=GB
# Grant all members of group "netdev" permissions to configure WiFi, e.g. via wpa_cli or wpa_gui
ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev
# Allow wpa_cli/wpa_gui to overwrite this config file
update_config=1
# disable p2p as it can cause errors
p2p_disabled=1
"""
                )
                output = subprocess.run(
                    ["wpa_passphrase", f"{ssid}", f"{passwd}"],
                    capture_output=True,
                    check=True,
                )
                conf.write(output.stdout.decode())
        except:
            print_err(f"ERROR when writing wpa supplicant config to {path}")

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

        success = False

        if self._baseos == "dietpi":
            self.writeWpaConf(ssid=self.ssid, passwd=self.passwd, path="/etc/wpa_supplicant/wpa_supplicant.conf")
            success = self.wpa_cli_reconfigure()

        elif self._baseos == "raspbian":
            # try for a while because it takes a bit for NetworkManager to come back up
            startTime = time.time()
            while time.time() - startTime < 20:
                try:
                    result = subprocess.run(
                        ["nmcli", "d", "wifi", "connect", f"{self.ssid}", "password", f"{self.passwd}", "ifname", f"{self.wlan}"],
                        capture_output=True,
                        timeout=20.0,
                    )
                except subprocess.SubprocessError as e:
                    # something went wrong
                    output = ""
                    if e.stdout:
                        output += e.stdout.decode()
                    if e.stderr:
                        output += e.stderr.decode()
                else:
                    output = result.stdout.decode() + result.stderr.decode()

                success = "successfully activated" in output

                if success:
                    break
                else:
                    # just to safeguard against super fast spin, sleep a bit
                    print_err(f"failed to connect to '{self.ssid}': {output}")
                    time.sleep(2)
                    continue

        if success:
            print_err(f"successfully connected to '{self.ssid}'")
        else:
            print_err(f"test_wifi failed to connect to '{self.ssid}'")

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
