import json
import subprocess
import sys
from tempfile import TemporaryDirectory
from utils.multioutline import MultiOutline
from utils.util import make_int, print_err


n = make_int(sys.argv[1] if len(sys.argv) > 1 else 1)
try:
    mo_data = MultiOutline().create(n)
except:
    print_err("failed to create MultiOutline class - maybe just a timing issue?")
    exit(0)

# now we need to inject this into the stage2 tar1090
with TemporaryDirectory(prefix="/tmp/adsb") as tmpdir:
    try:
        with open(f"{tmpdir}/multiOutline.json", "w") as f:
            json.dump(mo_data, f)
    except:
        print_err("failed to write multiOutline.json")
    else:
        cmd = f"docker cp {tmpdir}/multiOutline.json ultrafeeder:/run/readsb/"
        try:
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.SubprocessError:
            print_err("failed to push multiOutline.json")
