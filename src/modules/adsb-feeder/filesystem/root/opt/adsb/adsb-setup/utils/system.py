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

    def restart_containers(self):
        return self.restart(cmdline="bash /opt/adsb/docker-compose-restart-all")

    def compose_up(self):
        return self.restart(cmdline="bash /opt/adsb/adsb-system-restart.sh")

    def restart(self, cmdline=None):

        gotLock = self.lock.acquire(blocking=False)

        if not gotLock:
            # we could not acquire the lock
            print_err(f"restart locked, couldn't run: {cmdline}")
            return False

        # we have acquired the lock

        def do_restart():
            try:
                print_err(f"Calling {cmdline}")
                # discard output, scripts should log directly to /opt/adsb/adsb-setup.log
                subprocess.run(
                    cmdline,
                    shell=True,
                    capture_output=True,
                )
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

    @property
    def restart(self):
        return self._restart

    def halt(self) -> None:
        subprocess.call("halt", shell=True)

    def reboot(self) -> None:
        subprocess.call("reboot", shell=True)

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
