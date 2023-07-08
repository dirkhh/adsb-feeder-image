import subprocess
import threading
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
