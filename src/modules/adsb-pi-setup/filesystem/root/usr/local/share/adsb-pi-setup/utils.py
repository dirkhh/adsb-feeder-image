import re
import subprocess
import sys
import threading
from os import getenv, path
from typing import Dict
from uuid import uuid4


class Restart:
    def __init__(self):
        self.lock = threading.Lock()

    def restart_systemd(self):
        if self.lock.locked():
            return False
        with self.lock:
            subprocess.call("/usr/bin/systemctl daemon-reload", shell=True)
            subprocess.call("/usr/bin/systemctl restart adsb-docker", shell=True)
            subprocess.call("/usr/bin/systemctl disable adsb-bootstrap", shell=True)
            subprocess.call("/usr/bin/systemctl stop adsb-bootstrap", shell=True)

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
        return self.generate(False, None)  # without uuid or mlat privacy flag


class NetConfigs:
    def __init__(self):
        self.configs = {
            "adsblol": NetConfig(
                "adsb,feed.adsb.lol,30004,beast_reduce_plus_out",
                "mlat,feed.adsb.lol,31090,39001",
            ),
            "flyitaly": NetConfig(
                "adsb,dati.flyitalyadsb.com,4905,beast_reduce_plus_out",
                "mlat,dati.flyitalyadsb.com,30100,39002",
            ),
            "adsbx": NetConfig(
                "adsb,feed1.adsbexchange.com,30004,beast_reduce_plus_out",
                "mlat,feed.adsbexchange.com,31090,39003",
            ),
            "tat": NetConfig(
                "adsb,feed.theairtraffic.com,30004,beast_reduce_plus_out",
                "mlat,feed.theairtraffic.com,31090,39004",
            ),
            "ps": NetConfig(
                "adsb,feed.planespotters.net,30004,beast_reduce_plus_out",
                "mlat,mlat.planespotters.net,31090,39005",
            ),
            "adsbone": NetConfig(
                "adsb,feed.adsb.one,64004,beast_reduce_plus_out",
                "mlat,feed.adsb.one,64006,39006",
            ),
            "adsbfi": NetConfig(
                "adsb,feed.adsb.fi,30004,beast_reduce_plus_out",
                "mlat,feed.adsb.fi,31090,39007",
            ),
            "avdelphi": NetConfig(
                "adsb,data.avdelphi.com,24999,beast_reduce_plus_out",
                "",
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
            "FEEDER_READSB_GAIN": "autogain",
            "FR24": "0",
            "PW": "0",
            "FA": "0",
            "RB": "0",
            "PF": "0",
            "AH": "0",
            "OS": "0",
            "RV": "0",
        }
        for key, value in default_envs.items():
            if key not in env_values:
                env_values[key] = value
        self.update(env_values)

        feeder_ultrafeeder_config = self.generate_ultrafeeder_config(
            {"adsblol": "checked"}
        )
        if "FEEDER_ULTRAFEEDER_CONFIG" not in self.envs.keys():
            self.update({"FEEDER_ULTRAFEEDER_CONFIG": feeder_ultrafeeder_config})

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
            if not key or key in updated_keys:
                continue
            updated_lines.append(f"{key}={value}\n")

        with open(self.env_file_path, "w") as f:
            f.writelines(updated_lines)

    @property
    def metadata(self):
        env_values = self.envs
        metadata = {}
        ultrafeeder = env_values.get("FEEDER_ULTRAFEEDER_CONFIG", "").split(";")
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
        fr24_enabled = env_values["FR24"] == "1" and \
                       "FEEDER_FR24_SHARING_KEY" in env_values and \
                       re.match("^[0-9a-zA-Z]*$", env_values["FEEDER_FR24_SHARING_KEY"])
        metadata["FR24"] = (
            "checked" if fr24_enabled else ""
        )
        metadata["PW"] = (
            "checked" if env_values["PW"] == "1" else ""
        )
        metadata["FA"] = (
            "checked" if env_values["FA"] == "1" else ""
        )
        metadata["RB"] = (
            "checked" if env_values["RB"] == "1" else ""
        )
        metadata["PF"] = (
            "checked" if env_values["PF"] == "1" else ""
        )
        metadata["AH"] = (
            "checked" if env_values["AH"] == "1" else ""
        )
        metadata["OS"] = (
            "checked" if env_values["OS"] == "1" else ""
        )
        metadata["RV"] = (
            "checked" if env_values["RV"] == "1" else ""
        )
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
