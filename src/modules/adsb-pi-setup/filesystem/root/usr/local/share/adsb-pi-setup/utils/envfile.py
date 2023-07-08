from netconfig import NetConfigs, NetConfig
import subprocess
from uuid import uuid4
from system import Restart
from os import path
import sys


class EnvFile:
    def __init__(
        self, env_file_path: str, restart: Restart = None, netconfigs: NetConfigs = None
    ):
        self.env_file_path = env_file_path
        self.restart = restart
        self._setup()
        self.set_default_envs()
        self.netconfigs = netconfigs

    def _setup(self):
        # if file does not exist, create it
        if not path.isfile(self.env_file_path):
            open(self.env_file_path, "w").close()

    def set_default_envs(self):
        env_values = self.envs.copy()
        basev = "unknown"
        if path.isfile("/etc/adsb.im.version"):
            with open("/etc/adsb.im.version", "r") as v:
                basev = v.read().strip()
        if basev == "":
            # something went wrong setting up the version info when
            # the image was crated - try to get an approximation
            output: str = ""
            try:
                result = subprocess.run(
                    'ls -o -g --time-style="+%y%m%d" /etc/adsb.im.version | cut -d\  -f 4',
                    shell=True,
                    capture_output=True,
                    timeout=5.0,
                )
            except subprocess.TimeoutExpired as exc:
                output = exc.stdout.decode().strip()
            else:
                output = result.stdout.decode().strip()
            if len(output) == 6:
                basev = f"{output}-0"
        default_envs = {
            "FEEDER_TAR1090_USEROUTEAPI": "1",
            "FEEDER_RTL_SDR": "rtlsdr",
            "ADSBLOL_UUID": str(uuid4()),
            "ULTRAFEEDER_UUID": str(uuid4()),
            "MLAT_PRIVACY": "--privacy",
            "FEEDER_READSB_GAIN": "autogain",
            "FEEDER_HEYWHATSTHAT_ID": "",
            "HEYWHATSTHAT": "0",
            "FEEDER_AGG": "none",
            "FR24": "0",
            "PW": "0",
            "FA": "0",
            "RB": "0",
            "PF": "0",
            "AH": "0",
            "OS": "0",
            "RV": "0",
            "UF": "0",
            "AIRSPY": "0",
            "PORTAINER": "0",
            "BASE_CONFIG": "0",
            "NIGHTLY_BASE_UPDATE": "1",
            "NIGHTLY_CONTAINER_UPDATE": "1",
            "BASE_VERSION": basev,
            "CONTAINER_VERSION": basev,
        }
        for key, value in default_envs.items():
            if key not in env_values:
                env_values[key] = value
        self.update(env_values)

        feeder_ultrafeeder_config = self.generate_ultrafeeder_config()
        if feeder_ultrafeeder_config:
            self.update({"UF": "1"})
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
        for key in self.netconfigs.get_keys():
            adsb_normal, mlat_normal = self.netconfigs.configs[key].normal.split(";")
            # check that in ultrafeeder,
            # these lines exist (checking if it starts with this is enough,
            # because we might change UUID or mlat privacy)
            # if it is true, we want to set metadata[key] = "checked"
            # else, we want to set metadata[key] = ""
            if any(line.startswith(adsb_normal) for line in ultrafeeder) and any(
                line.startswith(mlat_normal) for line in ultrafeeder
            ):
                metadata[key] = "checked"
            else:
                metadata[key] = ""

        metadata["route"] = (
            "checked" if env_values["FEEDER_TAR1090_USEROUTEAPI"] == "1" else ""
        )
        metadata["privacy"] = (
            "checked" if env_values["MLAT_PRIVACY"] == "--privacy" else ""
        )
        metadata["biast"] = (
            "checked" if env_values.get("FEEDER_ENABLE_BIASTEE") == "true" else ""
        )
        metadata["heywhatsthat"] = (
            "checked" if env_values["HEYWHATSTHAT"] == "1" else ""
        )
        metadata["indagg"] = "1" if env_values["FEEDER_AGG"] == "ind" else ""
        fr24_enabled = (
            env_values["FR24"] == "1"
            and "FEEDER_FR24_SHARING_KEY" in env_values
            and re.match("^[0-9a-zA-Z]*$", env_values["FEEDER_FR24_SHARING_KEY"])
        )
        metadata["FR24"] = "checked" if fr24_enabled else ""
        metadata["PW"] = "checked" if env_values["PW"] == "1" else ""
        metadata["FA"] = "checked" if env_values["FA"] == "1" else ""
        metadata["RB"] = "checked" if env_values["RB"] == "1" else ""
        metadata["PF"] = "checked" if env_values["PF"] == "1" else ""
        metadata["AH"] = "checked" if env_values["AH"] == "1" else ""
        metadata["OS"] = "checked" if env_values["OS"] == "1" else ""
        metadata["RV"] = "checked" if env_values["RV"] == "1" else ""
        return metadata

    def generate_ultrafeeder_config(self, form_data={}):
        net_configs_list = []
        env_values = self.envs
        agg = env_values["FEEDER_AGG"]
        for key in self.netconfigs.get_keys():
            if agg == "all" or agg == "priv" or agg == "ind" and form_data.get(key):
                print("checking for key", key, file=sys.stderr)
                net_config = self.netconfigs.get_config(key)
                if agg != "priv" or net_config.has_policy:
                    config_string = net_config.generate(
                        mlat_privacy=env_values["MLAT_PRIVACY"] == "--privacy",
                        uuid=env_values["ADSBLOL_UUID"] if key == "adsblol" else None,
                    )
                    net_configs_list.append(config_string)
        print(
            f"1090: {env_values.get('FEEDER_1090')}, 978: {env_values.get('FEEDER_978')}",
            file=sys.stderr,
        )
        if env_values.get("FEEDER_978"):
            net_configs_list.append("adsb,dump978,30978,uat_in")
        if env_values.get("FEEDER_1090", "").startswith("airspy"):
            net_configs_list.append("adsb,airspy_adsb,30005,beast_in")
        print("net_configs_list", net_configs_list, file=sys.stderr)
        return ";".join(net_configs_list)
