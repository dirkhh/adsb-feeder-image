import re
from functools import wraps

from flask import Flask, redirect, request

from utils.util import print_err


class RouteManager:
    def __init__(self, app: Flask, data):
        self.app = app
        self._d = data

    def add_proxy_routes(self, proxy_routes):
        # print_err(f"adding proxy_routes {proxy_routes}", level=2)
        for endpoint, port, url_path in proxy_routes:
            # print_err(f"add_proxy_route {endpoint} {port } {url_path}")
            r = self.function_factory(endpoint, port, url_path)
            self.app.add_url_rule(endpoint, endpoint, r)

    def function_factory(self, orig_endpoint, new_port, new_path):
        # inc_port / idx is the id of the stage2 microfeeder
        # but inc_port and idx do different things to the forward so it can't be one variable
        def f(idx=0, inc_port=0, sub_path=""):
            return self.my_redirect(orig_endpoint, new_port, new_path, idx=idx, inc_port=inc_port, sub_path=sub_path)

        return f

    def my_redirect(self, orig, new_port, new_path, idx=0, inc_port=0, sub_path=""):
        # inc_port / idx is the id of the stage2 microfeeder
        # but inc_port and idx do different things to the forward so it can't be one variable
        # example endpoint: '/fa-status.json_<int:inc_port>/'
        # example endpoint: '/map_<int:idx>/'
        print_err(f"request.host_url: {request.host_url} orig: {orig} new_path: {new_path} sub_path:{sub_path}", level=8)
        if inc_port > 0:
            # this is ugly. we need too look up the port
            endpoint = re.sub("_.*$", "/", orig)
            for ep, ep_name, ep_path in self._d._proxy_routes:
                if endpoint == ep:
                    name= ep_name
            print_err(f"endpoint: {endpoint} name: {name}", level=8)
            env_name = "AF_" + name + "_PORT_" + str(inc_port)
            # this port value is only in the env file not the envs
            # but conveniently we can look a the vals we put into the env file
            new_port = self._d._env_file_vals[env_name]
        #new_port += inc_port * 1000
        host_url = request.host_url.rstrip("/ ")
        host_url = re.sub(":\\d+$", "", host_url)
        new_path += sub_path
        if idx > 0:
            new_path = f"/{idx}{new_path}"
        q: str = ""
        if request.query_string:
            q = f"?{request.query_string.decode()}"
        url = f"{host_url}:{new_port}{new_path}{q}"
        print_err(f"redirecting {orig} to {url} inc_port: {inc_port} idx: {idx}", level=8)
        return redirect(url)


def check_restart_lock(f):
    @wraps(f)
    def decorated_function(self, *args, **kwargs):
        if self._system._restart.lock.locked():
            return redirect("/restarting")
        return f(self, *args, **kwargs)

    return decorated_function
