import os
import requests
import socket
import subprocess
import threading
import time

from .data import Data
from .util import print_err


class Lock:
    # This class is used to lock the system from being modified while
    # pending changes are being made.
    def __init__(self):
        self.lock = threading.Lock()

    def acquire(self):
        return self.lock.acquire()

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

    def restart_systemd(self):
        if self.lock.locked():
            print_err("restart locked")
            return False
        with self.lock:
            print_err("Calling /opt/adsb/adsb-system-restart.sh")
            # discard output, script is logging directly to /opt/adsb/adsb-setup.log
            subprocess.run(
                "/usr/bin/bash /opt/adsb/adsb-system-restart.sh",
                shell=True,
                capture_output=True,
            )
            return True

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
        if os.path.exists("/opt/adsb/docker.lock"):
            os.remove("/opt/adsb/docker.lock")
        self._restart_lock = Lock()
        self._restart = Restart(self._restart_lock)
        self._d = data

    @property
    def restart(self):
        return self._restart

    def halt(self) -> None:
        subprocess.call("halt", shell=True)

    def reboot(self) -> None:
        subprocess.call("reboot", shell=True)

    def restart_containers(self):
        try:
            subprocess.call("bash /opt/adsb/docker-compose-restart-all &", shell=True)
        except:
            print_err("failed to start the container restart script in the background")
            return
        open("/opt/adsb/docker.lock", "w").close()
        # give the shell script a couple seconds to get going before we return the waiting page
        time.sleep(2.0)

    def docker_restarting(self):
        return os.path.exists("/opt/adsb/docker.lock")

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
