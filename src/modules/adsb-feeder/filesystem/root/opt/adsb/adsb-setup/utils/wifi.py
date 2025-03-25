import os
import subprocess
import time
import traceback

from utils.util import print_err, run_shell_captured


class Wifi:
    def __init__(self, wlan="wlan0"):
        if os.path.exists("/boot/dietpi"):
            self.baseos = "dietpi"
        elif os.path.exists("/etc/rpi-issue"):
            self.baseos = "raspbian"
        else:
            print_err("unknown baseos - no idea what to do")
            self.baseos = "unknown"
        self.wlan = wlan

    def get_ssid(self):
        try:
            # if you aren't on wifi, this will return an empty string
            ssid = subprocess.run(
                "iwgetid -r",
                shell=True,
                capture_output=True,
                timeout=2.0,
            ).stdout.decode("utf-8")
        except:
            ssid = ""

        return ssid.strip()

    def wpa_cli_reconfigure(self):
        connected = False
        output = ""
        # wait for wpa_supplicant to be running
        startTime = time.time()
        success = False
        while time.time() - startTime < 45:
            success, output = run_shell_captured("pgrep wpa_supplicant", timeout=5)
            if success:
                break
        if not success:
            print_err("timeout while waiting for wpa_supplicant to start")

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
                # print_err(f"wpa_cli: {line.rstrip()})")
                if "Interactive mode" in line:
                    proc.stdin.write("reconfigure\n")
                    proc.stdin.flush()
                if "reconfigure" in line:
                    reconfigured = True
                if reconfigured and "CTRL-EVENT-CONNECTED" in line:
                    connected = True
                    break
        except:
            print_err(traceback.format_exc())
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
                # print(line, end="")
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

    def writeWpaConf(self, ssid=None, passwd=None, path=None, country_code="GB"):
        try:
            with open(path, "w") as conf:
                conf.write(
                    f"""
# WiFi country code, set here in case the access point does send one
country={country_code}
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
        except Exception as e:
            print_err(f"ERROR when writing wpa supplicant config to {path}")
            print_err("exception: " + str(e))
            return False

        return True

    def dietpi_add_wifi_hotplug(self):
        # enable hotplug in case this is an old dietpi image (before may 2024)
        changedInterfaces = False
        with open("/etc/network/interfaces", "r") as current, open("/etc/network/interfaces.new", "w") as update:
            lines = current.readlines()
            for line in lines:
                if line.startswith("#") and "allow-hotplug" in line and self.wlan in line:
                    changedInterfaces = True
                    update.write(f"allow-hotplug {self.wlan}\n")
                else:
                    update.write(f"{line}")

        if changedInterfaces:
            print_err(f"uncommenting allow-hotplug for {self.wlan}")
            os.rename("/etc/network/interfaces.new", "/etc/network/interfaces")
            output = subprocess.run(
                f"systemctl restart --no-block networking.service",
                shell=True,
                capture_output=True,
            )
        else:
            os.remove("/etc/network/interfaces.new")

    def wifi_connect(self, ssid, passwd, country_code="GB"):
        success = False

        if self.baseos == "dietpi":
            self.dietpi_add_wifi_hotplug()

            # wpa_supplicant can take extremely long to start up as long as eth0 has allow-hotplug
            # wpa_cli_reconfigure will wait for that so this test can take up to 60 seconds

            # test wifi
            success = self.writeWpaConf(
                ssid=ssid, passwd=passwd, path="/etc/wpa_supplicant/wpa_supplicant.conf", country_code=country_code
            )
            if success:
                success = self.wpa_cli_reconfigure()

        elif self.baseos == "raspbian":
            # try for a while because it takes a bit for NetworkManager to come back up
            startTime = time.time()
            while time.time() - startTime < 20:
                try:
                    result = subprocess.run(
                        [
                            "nmcli",
                            "d",
                            "wifi",
                            "connect",
                            f"{ssid}",
                            "password",
                            f"{passwd}",
                            "ifname",
                            f"{self.wlan}",
                        ],
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
                    print_err(f"failed to connect to '{ssid}': {output}")
                    time.sleep(2)
                    continue

        return success

    def scan_ssids(self):
        try:
            if self.baseos == "raspbian":
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
            elif self.baseos == "dietpi":
                ssids = self.wpa_cli_scan()

            if len(ssids) > 0:
                print_err(f"found SSIDs: {ssids}")
                self.ssids = ssids
            else:
                print_err("no SSIDs found")

        except Exception as e:
            print_err(f"ERROR in scan_ssids(): {e}")
