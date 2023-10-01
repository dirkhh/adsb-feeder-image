from flask import Flask
from sys import argv

app = Flask(__name__)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    return "restarting"


if __name__ == "__main__":
    port = 80
    if len(argv) == 2:
        port = int(argv[1])
    app.run(host="0.0.0.0", port=port)
