import json
import math
import os
import re
import subprocess
import sys
import time
from sys import argv

from flask import Flask, Response, redirect, render_template, request, url_for
from utils.auth import WebAuth

# Import authentication utilities (using relative import from parent directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def print_err(*args, **kwargs):
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".{0:03.0f}Z".format(math.modf(time.time())[0] * 1000)
    print(*((timestamp,) + args), file=sys.stderr, **kwargs)


app = Flask(__name__)


# to stay as independent from the larger code base as possible, manually load the required config keys
class ConfigClass:
    def __init__(self) -> None:
        self._enabled = False
        self._app_secret = ""
        self._user_name = ""
        self._password_hash = ""

    def get_config_json(self):
        try:
            config = json.load(open("/opt/adsb/config/config.json"))
            self._enabled = config.get("_ADSBIM_WEB_AUTH_ENABLED", False)
            self._user_name = config.get("_ADSBIM_WEB_AUTH_USERNAME", "")
            self._password_hash = config.get("_ADSBIM_WEB_AUTH_PASSWORD_HASH", "")
            self._app_secret = config.get("_ADSBIM_APP_SECRET", "")
        except Exception as ex:
            # oops, that sucks
            print_err(f"reading config from recovery app failed with {ex}")

    def enabled(self):
        self.get_config_json()
        return self._enabled

    def user_name(self):
        self.get_config_json()
        return self._user_name

    def password_hash(self):
        self.get_config_json()
        return self._password_hash

    def app_secret(self):
        self.get_config_json()
        return self._app_secret


# Initialize authentication
c = ConfigClass()
auth = WebAuth(
    app,
    c.app_secret(),
    c.user_name,
    c.password_hash,
    c.enabled,
)


# Add authentication check before each request
@app.before_request
def check_authentication():
    # List of routes that don't require authentication
    public_routes = ["login", "logout", "static", "stream_log"]
    if request.endpoint and request.endpoint in public_routes:
        return None

    # If authentication is enabled and user is not authenticated, redirect to login
    if not auth.is_authenticated():
        return redirect(url_for("login", next=request.url))

    return None


logfile = "/run/adsb-feeder-image.log"
theme = "auto"
git_repo_path = "/opt/adsb-feeder-update/adsb-feeder-image"
git_repo_url = "https://github.com/dirkhh/adsb-feeder-image"
rollback_in_progress = False
rollback_target_version = None
recovery_process = None


def ensure_git_repo():
    if not os.path.exists(git_repo_path):
        print_err(f"Cloning git repo to {git_repo_path}")
        try:
            os.makedirs(os.path.dirname(git_repo_path), exist_ok=True)
            subprocess.run(
                ["git", "clone", git_repo_url, git_repo_path],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except Exception as e:
            print_err(f"Failed to clone git repo: {e}")
            return False
    return True


def get_current_version():
    version_file = "/opt/adsb/adsb.im.version"
    try:
        with open(version_file, "r") as f:
            version = f.read().strip()
            # Extract just the version tag, removing any branch info in parentheses
            match = re.match(r"(v\d+\.\d+\.\d+(?:-beta\.\d+)?)", version)
            if match:
                return match.group(1)
            return version
    except Exception as e:
        print_err(f"Failed to read version file: {e}")
        return None


def get_git_tags_and_branches():
    tags = []
    branches = []
    if not ensure_git_repo():
        return [], []

    try:
        # Fetch latest tags
        subprocess.run(
            ["git", "fetch", "--tags"],
            cwd=git_repo_path,
            capture_output=True,
            timeout=30,
        )

        # Get all tags sorted by version
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            cwd=git_repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            tags = result.stdout.strip().split("\n")
            # Filter tags that match our version pattern
            version_pattern = re.compile(r"^v\d+\.\d+\.\d+(?:-beta\.\d+)?$")
            tags = [tag for tag in tags if version_pattern.match(tag)]

        # Get all remote branches
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=git_repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            branches = result.stdout.strip().split("\n")
            branches = [branch.replace("origin/", "").strip() for branch in branches if branch.strip()]

        #  print_err(f"tags: {tags} branches: {branches}")
        return tags, branches
    except Exception as e:
        print_err(f"Failed to get git tags and branches: {e}")
        return tags, branches


def get_previous_version():
    current = get_current_version()
    if not current:
        return None

    tags, _ = get_git_tags_and_branches()
    if not tags:
        return None
    release_tags = [tag for tag in tags if "-beta" not in tag]
    #  print_err(f"tags: {tags} release_tags: {release_tags} current: {current}")
    is_beta = "-beta" in current

    # Find current version in tags list
    try:
        current_index = tags.index(current)
    except ValueError:
        # Current version not in tags, use first release tag as fallback
        return release_tags[0] if release_tags else None

    # Look for the previous appropriate version
    if is_beta:
        # Extract beta number from current version (e.g., v3.0.6-beta.3 -> 3)
        beta_match = re.search(r"-beta\.(\d+)$", current)
        beta_num = int(beta_match.group(1)) if beta_match else 1

        if beta_num == 1:
            # For beta.1, find the previous release (non-beta) version
            for tag in tags[current_index + 1 :]:
                if "-beta" not in tag:
                    return tag
            return None
        else:
            # For beta.2+, find the previous beta (beta.N-1)
            if current_index + 1 < len(tags):
                return tags[current_index + 1]
            return None
    else:
        # For release, find the previous release tag (no -beta)
        try:
            release_index = release_tags.index(current)
            if release_index + 1 < len(release_tags):
                return release_tags[release_index + 1]
        except ValueError:
            pass

    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    """Handle login for web authentication."""
    if request.method == "GET":
        # Check if already authenticated
        if auth.is_authenticated():
            return redirect(url_for("recovery"))

        # Check if next parameter was provided
        next_page = request.args.get("next", "")
        return render_template("recovery-login.html", error=None, next=next_page, theme=theme)

    # POST method - process login
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    next_page = request.form.get("next", "") or request.args.get("next", "")

    if auth.login(username, password):
        # Successful login
        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return redirect(url_for("recovery"))
    else:
        # Failed login
        return render_template("login.html", error="Invalid username or password", next=next_page, theme=theme)


@app.route("/logout")
def logout():
    """Handle logout for web authentication."""
    auth.logout()
    return redirect(url_for("login"))


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


def start_recovery(target_version):
    global rollback_in_progress, rollback_target_version, recovery_process

    if os.path.exists("/opt/adsb/adsb.im.secure_image"):
        return (False, "Secure Image is set, rollback is disabled.")

    print_err(f"Starting recovery to version {target_version}")
    try:
        # Mark rollback as in progress
        rollback_in_progress = True
        rollback_target_version = target_version

        # Execute feeder-update with the target version
        recovery_process = subprocess.Popen(
            ["/opt/adsb/feeder-update", target_version],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give it a moment to start
        time.sleep(1)
        return True, None
    except Exception as e:
        print_err(f"Failed to start recovery: {e}")
        rollback_in_progress = False
        rollback_target_version = None
        recovery_process = None
        return False, str(e)


@app.route("/rollback")
def rollback():
    previous = get_previous_version()
    if not previous:
        print_err("Cannot determine previous version for rollback")
        return "Cannot determine previous version", 500

    success, error = start_recovery(previous)
    if not success:
        return f"Failed to start rollback: {error}", 500

    return redirect("/")


@app.route("/recover-to/<tagorbranch>")
def recover_to_tag(tagorbranch):
    tags, branches = get_git_tags_and_branches()
    if tagorbranch not in tags and tagorbranch not in branches:
        print_err(f"{tagorbranch} is not a valid tag or branch")
        return f"{tagorbranch} is not a valid tag or branch", 400

    # Validate tag format
    version_pattern = re.compile(r"^v\d+\.\d+\.\d+(?:-beta\.\d+)?$")
    if version_pattern.match(tagorbranch):
        tagorbranch = tagorbranch[1:]
    else:
        tagorbranch = f"origin/{tagorbranch}"

    success, error = start_recovery(tagorbranch)
    if not success:
        return f"Failed to start recovery: {error}", 500

    return redirect("/")


@app.route("/recovery-status")
def recovery_status():
    global rollback_in_progress, rollback_target_version, recovery_process

    if not rollback_in_progress:
        return "not-started"

    # Check if process is still running
    if recovery_process and recovery_process.poll() is None:
        return "in-progress"

    # Process finished so let the UI know
    rollback_in_progress = False
    rollback_target_version = None
    recovery_process = None
    return "completed"


@app.route("/restart")
def restarting():
    return "stream-log"


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def recovery(path):
    current = get_current_version()
    previous = get_previous_version()

    return render_template(
        "recovery.html",
        theme=theme,
        current_version=current,
        previous_version=previous,
        rollback_in_progress=rollback_in_progress,
        rollback_target_version=rollback_target_version,
    )


if __name__ == "__main__":
    port = 1089
    if len(argv) >= 2:
        port = int(argv[1])
    if len(argv) >= 3:
        logfile = argv[2]

    print_err(f"Starting recovery-app.py on port {port} streaming logfile {logfile}")
    if os.path.exists("/opt/adsb/config/config.json"):
        with open("/opt/adsb/config/config.json") as f:
            config = json.load(f)
        theme = config.get("_ASDBIM_CSS_THEME", "auto")

    # Suppress Flask development server warning
    import logging

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    app.run(host="0.0.0.0", port=port)
