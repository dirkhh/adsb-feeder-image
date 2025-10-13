import json
import math
import os
import re
import sys
import time
from sys import argv

from flask import Flask, Response, render_template

app = Flask(__name__)
logfile = "/run/adsb-feeder-image.log"
title = "Restarting the ADS-B Feeder System"
theme = "auto"


# we need to fake having env_value_by_tag so that the waiting.html can be
# used both by this and the main app
@app.context_processor
def utility_processor():
    return {"env_value_by_tag": lambda _: theme}


def print_err(*args, **kwargs):
    level = int(kwargs.pop("level", 0))
    if level > 0 and int(verbose) & int(level) == 0:
        return
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".{0:03.0f}Z".format(
        math.modf(time.time())[0] * 1000
    )
    print(*((timestamp,) + args), file=sys.stderr, **kwargs)


@app.route("/stream-log")
def stream_log():

    def tail():
        with open(logfile, "r") as file:
            ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
            tmp = file.read()[-16 * 1024 :]
            # discard anything but the last 16 kB
            while True:
                tmp += file.read(16 * 1024)
                if tmp and tmp.find("\n") != -1:
                    block, tmp = tmp.rsplit("\n", 1)
                    block = ansi_escape.sub("", block)
                    lines = block.split("\n")
                    data = "".join(["data: " + line + "\n" for line in lines])
                    yield data + "\n\n"
                else:
                    time.sleep(0.2)

    return Response(tail(), mimetype="text/event-stream")


@app.route("/restart")
def restarting():
    return "stream-log"


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def waiting(path):
    return render_template("waiting.html", title=title)


if __name__ == "__main__":
    port = 80
    if len(argv) >= 2:
        port = int(argv[1])
    if len(argv) >= 3:
        logfile = argv[2]
    if len(argv) >= 4:
        title = argv[3] + " ADS-B Feeder System"

    print_err(f'Starting waiting-app.py on port {port} with title "{title}" streaming logfile {logfile}')
    if os.path.exists("/opt/adsb/config/config.json"):
        with open("/opt/adsb/config/config.json") as f:
            config = json.load(f)
        theme = config.get("_ASDBIM_CSS_THEME", "auto")

    # Suppress Flask development server warning
    import logging

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    app.run(host="0.0.0.0", port=port)
