import re
import sys
from functools import wraps

from flask import Flask, redirect, request


class RouteManager:
    def __init__(self, app: Flask):
        self.app = app

    def add_proxy_routes(self, proxy_routes):
        for endpoint, port, url_path in proxy_routes:
            r = self.function_factory(endpoint, port, url_path)
            self.app.add_url_rule(endpoint, endpoint, r)

    def function_factory(self, orig_endpoint, new_port, new_path):
        def f():
            return self.my_redirect(orig_endpoint, new_port, new_path)

        return f

    def my_redirect(self, orig, new_port, new_path):
        print(
            f"my_redirect called for endpoint {orig} with port {new_port} and path {new_path}",
            file=sys.stderr,
        )
        host_url = request.host_url.rstrip("/ ")
        host_url = re.sub(":\\d+$", "", host_url)
        new_path = new_path.rstrip("/ ")
        q: str = ""
        if request.query_string:
            q = f"?{request.query_string.decode()}"
        print(
            f"after cleanup: host|{host_url}| path|{new_path}| query-string|{q}|",
            file=sys.stderr,
        )
        url = f"{host_url}:{new_port}{new_path}{q}"
        # work around oddity in tar1090
        if url.endswith("graphs1090"):
            url += "/"
        print(f"redirecting {orig} to {url}", file=sys.stderr)
        return redirect(url)


def check_restart_lock(f):
    @wraps(f)
    def decorated_function(self, *args, **kwargs):
        if self._system._restart.lock.locked():
            return redirect("/restarting")
        return f(self, *args, **kwargs)
    return decorated_function
