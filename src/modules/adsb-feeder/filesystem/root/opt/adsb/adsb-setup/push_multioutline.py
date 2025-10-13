import json
import subprocess
import sys
import traceback

from utils.multioutline import MultiOutline
from utils.util import make_int, print_err

n = make_int(sys.argv[1] if len(sys.argv) > 1 else 1)

# multioutline
try:
    mo_data = MultiOutline().create_outline(n)
    with open(f"/run/adsb-feeder-ultrafeeder/readsb/multiOutline.json", "w") as f:
        json.dump(mo_data, f)
except:
    print_err(traceback.format_exc(), level=8)
    print_err("failed to push multiOutline.json verbose 8 for details")


# heywhatsthat

tmpfile = "/run/stage2_upintheair.json"
try:
    hwt_data = MultiOutline().create_heywhatsthat(n)
    if hwt_data is not None:
        with open(tmpfile, "w") as f:
            json.dump(hwt_data, f)
        cmd = [
            "docker",
            "cp",
            tmpfile,
            "ultrafeeder:/usr/local/share/tar1090/html-webroot/upintheair.json",
        ]
        subprocess.run(cmd, check=True)
except:
    print_err(traceback.format_exc(), level=8)
    print_err("failed to push heywhatsthat.json - verbose 8 for details")
