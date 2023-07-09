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
        self._restart_lock = Lock()
        self._restart = Restart(self._restart_lock)
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

class Version:
    def __init__(self):
        self._version = None

        self.file_path = Constants().version_file
        # We have to initialise Constants() here to avoid a circular import
        # Usually that sucks. But in this case, we're only using the version file path.
        # So it's not too bad.

    def _get_base_version(self):
        basev = "unknown"
        if os.path.isfile(self.constants.version_file):
            with open(self.constants.version_file, "r") as v:
                basev = v.read().strip()
        if basev == "":
            # something went wrong setting up the version info when
            # the image was crated - try to get an approximation
            output: str = ""
            try:
                result = subprocess.run(
                    'ls -o -g --time-style="+%y%m%d" /etc/adsb.im.version | cut -d\  -f 4',
                    shell=True,
                    capture_output=True,
                    timeout=5.0,
                )
            except subprocess.TimeoutExpired as exc:
                output = exc.stdout.decode().strip()
            else:
                output = result.stdout.decode().strip()
            if len(output) == 6:
                basev = f"{output}-0"
            return basev

    def __str__(self):
        if self._version is None:
            self._version = self._get_base_version()
        return self._version
