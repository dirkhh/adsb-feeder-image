import io
import os
import pathlib
import subprocess
import threading
import zipfile

from .constants import Constants
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


class System:
    def __init__(self, constants: Constants):
        self._restart = Restart(Lock())
        self._constants = constants

    @property
    def restart(self):
        return self._restart

    def halt(self):
        subprocess.call("sudo halt", shell=True)

    def _get_backup_data(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, mode="w") as backup_zip:
            backup_zip.write(self._constants.env_file_path, arcname=".env")
            for f in self._constants.data_path.glob("*.yml"):
                backup_zip.write(f, arcname=os.path.basename(f))
            for f in self._constants.data_path.glob("*.yaml"):  # FIXME merge with above
                backup_zip.write(f, arcname=os.path.basename(f))
            uf_path = pathlib.Path(self._constants.data_path / "ultrafeeder")
            if uf_path.is_dir():
                for f in uf_path.rglob("*"):
                    backup_zip.write(f, arcname=f.relative_to(self._constants.data_path))
        data.seek(0)
        return data
