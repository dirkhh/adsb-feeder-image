import json
import subprocess
import sys
import traceback
from tempfile import TemporaryDirectory
from utils.multioutline import MultiOutline
from utils.util import make_int, print_err


n = make_int(sys.argv[1] if len(sys.argv) > 1 else 1)
try:
    mo_data = MultiOutline().create_outline(n)
    with open(f"/run/adsb-feeder-ultrafeeder/readsb/multiOutline.json", "w") as f:
        json.dump(mo_data, f)
except:
    print_err(traceback.format_exc())
    print_err("failed to push multiOutline.json")

hwt_data = None
try:
    hwt_data = MultiOutline().create_heywhatsthat(n)
except:
    print_err(traceback.format_exc())

# now we need to inject this into the stage2 tar1090
datadir = "/opt/adsb/data"
try:
    if hwt_data is not None:
        with open(f"{datadir}/upintheair.json", "w") as f:
            json.dump(hwt_data, f)
except:
    print_err(traceback.format_exc())
    print_err("failed to write heywhatsthat.json")
else:
    if hwt_data is not None:
        cmd = [
            "docker",
            "cp",
            f"{datadir}/upintheair.json",
            "ultrafeeder:/usr/local/share/tar1090/html-webroot/upintheair.json",
        ]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.SubprocessError:
            print_err("failed to push multiOutline.json")
