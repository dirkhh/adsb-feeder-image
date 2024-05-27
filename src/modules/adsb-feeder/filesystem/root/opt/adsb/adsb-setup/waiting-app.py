from flask import Flask, Response, render_template
from sys import argv
import time

app = Flask(__name__)
logfile = "/opt/adsb/adsb-setup.log"
action = "Restarting the"


@app.route("/stream-log")
def stream_log():
    file = open(logfile, "r")

    def tail():
        line = ""
        while True:
            tmp = file.readline()
            if tmp:
                line += tmp
                if line.endswith("\n"):
                    yield f"{line}\n\n"
                    line = "data:"
            else:
                time.sleep(0.2)

    return Response(tail(), mimetype="text/event-stream")


@app.route("/restarting")
def restarting():
    return "restarting"


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def waiting(path):
    return render_template("waiting.html", action=action)


if __name__ == "__main__":
    port = 80
    if len(argv) >= 2:
        port = int(argv[1])
    if len(argv) >= 3:
        logfile = argv[2]
    if len(argv) >= 4:
        action = argv[3]
    app.run(host="0.0.0.0", port=port)
