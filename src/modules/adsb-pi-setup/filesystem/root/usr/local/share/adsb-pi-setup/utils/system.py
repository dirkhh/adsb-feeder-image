import subprocess
import threading


class Restart:
    def __init__(self):
        self.lock = threading.Lock()

    def restart_systemd(self):
        if self.lock.locked():
            return False
        with self.lock:
            subprocess.call(
                "/usr/bin/bash /opt/adsb/adsb-system-restart.sh", shell=True
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
