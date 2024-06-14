import json
import subprocess
import sys
from tempfile import TemporaryDirectory
from utils.multioutline import MultiOutline
from utils.util import make_int, print_err


n = make_int(sys.argv[1] if len(sys.argv) > 1 else 1)
try:
    mo_data = MultiOutline().create_outline(n)
except:
    print_err("failed to create MultiOutline class")
    exit(0)

hwt_data = None
try:
    hwt_data = MultiOutline().create_heywhatsthat(n)
except:
    # this can happen if none of the micro feeds have HeyWhatsthat IDs
    pass

# now we need to inject this into the stage2 tar1090
datadir = "/opt/adsb/data"
try:
    with open(f"{datadir}/multiOutline.json", "w") as f:
        json.dump(mo_data, f)
    if hwt_data is not None:
        with open(f"{datadir}/upintheair.json", "w") as f:
            json.dump(hwt_data, f)
except:
    print_err("failed to write multiOutline.json or heywhatsthat.json")
else:
    cmd = ["docker", "cp", f"{datadir}/multiOutline.json", "ultrafeeder:/run/readsb/"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.SubprocessError:
        print_err("failed to push multiOutline.json")
    if hwt_data is not None:
        cmd = ["docker", "cp", f"{datadir}/upintheair.json", "ultrafeeder:/usr/local/share/tar1090/html-webroot/upintheair.json"]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.SubprocessError:
            print_err("failed to push multiOutline.json")
