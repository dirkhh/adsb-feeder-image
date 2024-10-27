import os
import requests
import socket
import subprocess
import threading
import time
from time import sleep

from .data import Data
from .util import print_err, run_shell_captured


class Lock:
    # This class is used to lock the system from being modified while
    # pending changes are being made.
    def __init__(self):
        self.lock = threading.Lock()

    def acquire(self, blocking=True, timeout=-1):
        return self.lock.acquire(blocking=blocking, timeout=timeout)

    def release(self):
        return self.lock.release()

    def locked(self):
        return self.lock.locked()

    # make sure we can use "with Lock() as lock:"

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()


class Restart:
    def __init__(self, lock: Lock):
        self.lock = lock

    def bg_run(self, cmdline=None, func=None, silent=False):

        if not cmdline and not func:
            print_err(f"WARNING: bg_run called without something to do")
            return False

        gotLock = self.lock.acquire(blocking=False)

        if not gotLock:
            # we could not acquire the lock
            print_err(f"restart locked, couldn't run: {cmdline}")
            return False

        # we have acquired the lock

        def do_restart():
            try:
                if cmdline:
                    print_err(f"Calling {cmdline}")
                    subprocess.run(
                        cmdline,
                        shell=True,
                        capture_output=silent,
                    )
                if func:
                    func()
            finally:
                self.lock.release()

        threading.Thread(target=do_restart).start()

        return True

    def wait_restart_done(self, timeout=-1):
        # acquire and release the lock immediately
        if self.lock.acquire(blocking=True, timeout=timeout):
            self.lock.release()

    @property
    def state(self):
        if self.lock.locked():
            return "restarting"
        return "done"

    @property
    def is_restarting(self):
        return self.lock.locked()


class System:
    def __init__(self, data: Data):
        self._restart_lock = Lock()
        self._restart = Restart(self._restart_lock)
        self._d = data

        self.gateway_ips = None

    @property
    def restart(self):
        return self._restart

    def halt(self) -> None:
        subprocess.call("halt", shell=True)

    def reboot(self) -> None:
        # best effort: allow reboot even if lock is held
        gotLock = self._restart.lock.acquire(blocking=False)

        def do_reboot():
            sleep(0.5)
            subprocess.call("reboot", shell=True)
            # just in case the reboot doesn't work,
            # release the lock after 30 seconds:
            if gotLock:
                sleep(30)
                self._restart.lock.release()

        threading.Thread(target=do_reboot).start()

    def os_update(self) -> None:
        subprocess.call("apt-get update && apt-get upgrade -y", shell=True)

    def check_dns(self):
        try:
            responses = list(
                i[4][0]  # raw socket structure/internet protocol info/address
                for i in socket.getaddrinfo("adsb.im", 0)
                # if i[0] is socket.AddressFamily.AF_INET
                # and i[1] is socket.SocketKind.SOCK_RAW
            )
        except:
            return False
        return responses != list()

    def is_ipv6_broken(self):
        success, output = run_shell_captured(
            "ip -6 addr show scope global $(ip -j route get 1.2.3.4 | jq '.[0].dev' -r) | grep inet6 | grep -v 'inet6 f'"
        )
        if not success:
            # no global ipv6 addresses assigned, this means we don't have ipv6 so it can't be broken
            return False
        # we have at least one global ipv6 address, check if it works:
        success, output = run_shell_captured("curl -o /dev/null -6 https://google.com")

        if success:
            # it's working, so it's not broken
            return False

        # we have an ipv6 address but curl -6 isn't working
        return True

    def check_ip(self):
        requests.packages.urllib3.util.connection.HAS_IPV6 = False
        status = -1
        try:
            response = requests.get(
                "http://v4.ipv6-test.com/api/myip.php",
                headers={
                    "User-Agent": "Python3/requests/adsb.im",
                    "Accept": "text/plain",
                },
            )
        except (
            requests.HTTPError,
            requests.ConnectionError,
            requests.Timeout,
            requests.RequestException,
        ) as err:
            status = err.errno
        except:
            status = -1
        else:
            return response.text, response.status_code
        return None, status

    def check_gpsd(self):
        # gateway IP shouldn't change on a system, buffer it for the duration the program runs
        if self.gateway_ips:
            gateway_ips = self.gateway_ips
        else:
            # find host address on the docker network
            command = "docker exec adsb-setup-proxy ip route | mawk '/default/{ print($3) }'"
            success, output = run_shell_captured(
                command=command,
                timeout=5,
            )
            if success and len(output.strip()) > 4:
                self.gateway_ips = gateway_ips = [output.strip()]
            else:
                gateway_ips = ["172.17.0.1", "172.18.0.1"]
                print_err(f"ERROR: command: {command} failed with output: {output}")

        print_err(f"gpsd check: checking ips: {gateway_ips}")

        for ip in gateway_ips:
            # Create a TCP socket
            # print_err(f"Checking for gpsd: {ip}:2947")
            s = socket.socket()
            s.settimeout(2)
            try:
                s.connect((ip, 2947))
                print_err(f"Connected to gpsd on {ip}:2947")
                return True
            except socket.error as e:
                print_err(f"No gpsd on {ip}:2947 detected")
            finally:
                s.close()
        return False

    def list_containers(self):
        containers = []
        try:
            result = subprocess.run(
                ["docker", "ps", "--format='{{json .Names}}'"],
                capture_output=True,
                timeout=5,
            )
            output = result.stdout.decode("utf-8")
            for line in output.split("\n"):
                if line and line[1] == '"' and line[-2] == '"':
                    # the names show up as '"ultrafeeder"'
                    containers.append(line[2:-2])
        except subprocess.SubprocessError() as e:
            print_err(f"docker ps failed {e}")
        return containers

    def restart_containers(self, containers):
        print_err(f"restarting {containers}")
        try:
            subprocess.run(["/opt/adsb/docker-compose-adsb", "restart"] + containers)
        except:
            print_err("docker compose restart failed")

    def recreate_containers(self, containers):
        print_err(f"recreating {containers}")
        try:
            subprocess.run(["/opt/adsb/docker-compose-adsb", "down"] + containers)
            subprocess.run(["/opt/adsb/docker-compose-adsb", "up", "-d"] + containers)
        except:
            print_err("docker compose recreate failed")
