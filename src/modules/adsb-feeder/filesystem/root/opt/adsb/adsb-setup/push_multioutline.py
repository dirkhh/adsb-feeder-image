import json
import subprocess
import sys
import time
import traceback

from utils.multioutline import MultiOutline
from utils.util import make_int, print_err

n = make_int(sys.argv[1] if len(sys.argv) > 1 else 1)

t1 = time.process_time()

# multioutline
try:
    mo_data = MultiOutline().create_outline(n)
    with open(f"/run/adsb-feeder-ultrafeeder/readsb/multiOutline.json", "w") as f:
        json.dump(mo_data, f)
except Exception:
    print_err(traceback.format_exc(), level=8)
    print_err("failed to push multiOutline.json verbose 8 for details")

t2 = time.process_time()
print_err(f"multioutline generation CPU seconds used: {round(t2 - t1, 3)}")

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
except Exception:
    print_err(traceback.format_exc(), level=8)
    print_err("failed to push heywhatsthat.json - verbose 8 for details")

t3 = time.process_time()
print_err(f"heywhatsthat generation CPU seconds used: {round(t3 - t2, 3)}")
