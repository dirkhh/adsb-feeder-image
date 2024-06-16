import re
from functools import wraps

from utils.util import print_err

from flask import Flask, redirect, request


class RouteManager:
    def __init__(self, app: Flask):
        self.app = app

    def add_proxy_routes(self, proxy_routes):
        # print_err(f"adding proxy_routes {proxy_routes}", level=2)
        for endpoint, port, url_path in proxy_routes:
            # print_err(f"add_proxy_route {endpoint} {port } {url_path}")
            r = self.function_factory(endpoint, port, url_path)
            self.app.add_url_rule(endpoint, endpoint, r)

    def function_factory(self, orig_endpoint, new_port, new_path):
        # inc_port / idx is the id of the stage2 microfeeder
        def f(idx=0, inc_port=0, sub_path=""):
            return self.my_redirect(orig_endpoint, new_port, new_path, idx=idx, inc_port=inc_port, sub_path=sub_path)

        return f

    def my_redirect(self, orig, new_port, new_path, idx=0, inc_port=0, sub_path=""):
        # inc_port / idx is the id of the stage2 microfeeder
        # example endpoint: '/fa-status.json_<int:inc_port>/'
        # example endpoint: '/map_<int:idx>/'
        new_port += inc_port * 1000
        host_url = request.host_url.rstrip("/ ")
        host_url = re.sub(":\\d+$", "", host_url)
        new_path += sub_path
        new_path = new_path.rstrip("/ ")
        if idx > 0:
            new_path = f"/{idx}{new_path}"
        q: str = ""
        if request.query_string:
            q = f"?{request.query_string.decode()}"
        url = f"{host_url}:{new_port}{new_path}{q}"
        # work around oddity in tar1090 and dump978
        if url.endswith("graphs1090") or url.endswith("skyaware978"):
            url += "/"
        print_err(f"redirecting {orig} to {url}")
        return redirect(url)


def check_restart_lock(f):
    @wraps(f)
    def decorated_function(self, *args, **kwargs):
        if self._system._restart.lock.locked():
            return redirect("/restarting")
        return f(self, *args, **kwargs)

    return decorated_function
