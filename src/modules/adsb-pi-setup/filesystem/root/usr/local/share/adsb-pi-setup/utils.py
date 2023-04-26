import re
import subprocess
import threading
from os import getenv, path
from pprint import pprint
from typing import Dict
from uuid import uuid4


class DockerCompose:
    def __init__(self, docker_compose_path: str):
        self.docker_compose_path = docker_compose_path


class Restart:
    def __init__(self):
        self.lock = threading.Lock()

    def restart_systemd(self):
        if self.lock.locked():
            return False
        with self.lock:
            subprocess.call("/usr/bin/systemctl restart adsb-docker", shell=True)

    @property
    def state(self):
        if self.lock.locked():
            return "restarting"
        return "done"


class NetConfig:
    def __init__(self, adsb_config: str, mlat_config: str):
        self.adsb_config = adsb_config
        self.mlat_config = mlat_config

    def generate(self, mlat_privacy: bool = True, uuid: str = None):
        adsb_line = self.adsb_config
        mlat_line = self.mlat_config

        if uuid and len(uuid) == 36:
            adsb_line += f",uuid={uuid}"
            mlat_line += f",uuid={uuid}"

        if mlat_privacy:
            mlat_line += ",--privacy"
        print("Ready line: ", f"{adsb_line};{mlat_line}")
        return f"{adsb_line};{mlat_line}"

    @property
    def normal(self):
        return self.generate(None, None)


class NetConfigs:
    def __init__(self):
        self.configs = {
            "adsblol": NetConfig(
                "adsb,feed.adsb.lol,30004,beast_reduce_plus_out",
                "mlat,feed.adsb.lol,31090,39001",
            ),
            "adsbx": NetConfig(
                "adsb,feed1.adsbexchange.com,30004,beast_reduce_plus_out",
                "mlat,feed.adsbexchange.com,31090,39005",
            ),
            "tat": NetConfig(
                "adsb,feed.theairtraffic.com,30004,beast_reduce_plus_out",
                "mlat,feed.theairtraffic.com,31090,39004",
            ),
            "ps": NetConfig(
                "adsb,feed.planespotters.net,30004,beast_reduce_plus_out",
                "mlat,mlat.planespotters.net,31090,39003",
            ),
            "adsbone": NetConfig(
                "adsb,feed.adsb.one,64004,beast_reduce_plus_out",
                "mlat,feed.adsb.one,64006,39002",
            ),
            "adsbfi": NetConfig(
                "adsb,feed.adsb.fi,30004,beast_reduce_plus_out",
                "mlat,feed.adsb.fi,31090,39000",
            ),
        }

    def get_config(self, key):
        return self.configs.get(key)

    def get_keys(self):
        return self.configs.keys()

class EnvFile:
    def __init__(self, env_file_path: str, restart: Restart = None):
        self.env_file_path = env_file_path
        self.restart = restart
        self._setup()
        self.set_default_envs()

    def _setup(self):
        # if file does not exist, create it
        if not path.isfile(self.env_file_path):
            open(self.env_file_path, "w").close()

    def set_default_envs(self):
        env_values = self.envs.copy()
        default_envs = {
            "FEEDER_TAR1090_USEROUTEAPI": "1",
            "ADSBLOL_UUID": str(uuid4()),
            "ULTRAFEEDER_UUID": str(uuid4()),
            "MLAT_PRIVACY": "--privacy",
        }
        for key, value in default_envs.items():
            if key not in env_values:
                env_values[key] = value
        self.update(env_values)

        FEEDER_ULTRAFEEDER_CONFIG = self.generate_ultrafeeder_config(
            {"adsblol": "checked"}
        )
        if "FEEDER_ULTRAFEEDER_CONFIG" not in self.envs.keys():
            self.update({"FEEDER_ULTRAFEEDER_CONFIG": FEEDER_ULTRAFEEDER_CONFIG})


    @property
    def envs(self):
        env_values = {}

        with open(self.env_file_path) as f:
            for line in f.readlines():
                if line.strip().startswith("#"):
                    continue
                key, var = line.partition("=")[::2]
                env_values[key.strip()] = var.strip()

        return env_values

    def update(self, values: Dict[str, str]):
        with open(self.env_file_path, "r") as f:
            lines = f.readlines()

        updated_lines = []
        updated_keys = []
        for line in lines:
            if line.startswith("#") or not line.strip():
                updated_lines.append(line)
                continue
            for key, value in values.items():
                if line.startswith(key + "="):
                    updated_lines.append(f"{key}={value}\n")
                    updated_keys.append(key)
                    break
            else:
                updated_lines.append(line)

        for key, value in values.items():
            if key in updated_keys:
                continue
            updated_lines.append(f"{key}={value}\n")

        with open(self.env_file_path, "w") as f:
            f.writelines(updated_lines)

    @property
    def metadata(self):
        env_values = self.envs
        metadata = {}
        ultrafeeder = env_values["FEEDER_ULTRAFEEDER_CONFIG"].split(";")
        for key in NETCONFIGS.get_keys():
            adsb_normal, mlat_normal = NETCONFIGS.configs[key].normal.split(";")
            # check that in ultrafeeder,
            # these lines exist (checking if it starts with this is enough,
            # because we might change UUID or mlat privacy)
            # if it is true, we want to set metadata[key] = "checked"
            # else, we want to set metadata[key] = ""
            if (
                any(
                    line.startswith(adsb_normal)
                    for line in ultrafeeder
                )
                and any(
                    line.startswith(mlat_normal)
                    for line in ultrafeeder
                )
            ):
                metadata[key] = "checked"
            else:
                metadata[key] = ""

        metadata["adv_visible"] = (
            all(
                key in env_values and float(env_values[key]) != 0
                for key in ["FEEDER_LAT", "FEEDER_LONG", "FEEDER_ALT_M"]
            )
            and not self.restart.lock.locked()
        )

        metadata["route"] = (
            "checked" if env_values["FEEDER_TAR1090_USEROUTEAPI"] == "1" else ""
        )
        metadata["privacy"] = (
            "checked" if env_values["MLAT_PRIVACY"] == "--privacy" else ""
        )
        from pprint import pprint

        pprint(metadata)
        return metadata

    def generate_ultrafeeder_config(self, form_data):
        net_configs_list = []
        for key in NetConfigs().get_keys():
            if form_data.get(key):
                print("Itering for key", key)
                net_config = NetConfigs().get_config(key)
                config_string = net_config.generate(
                    mlat_privacy=self.envs["MLAT_PRIVACY"] == "--privacy",
                    uuid=self.envs["ADSBLOL_UUID"] if key == "adsblol" else None,
                )
                net_configs_list.append(config_string)
        print("net_configs_list", net_configs_list)
        return ";".join(net_configs_list)


RESTART = Restart()
ENV_FILE = EnvFile(
    env_file_path=getenv("ADSB_PI_SETUP_ENVFILE", "/opt/adsb/.env"), restart=RESTART
)
NETCONFIGS = NetConfigs()
