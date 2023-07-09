import re
import subprocess
import sys
from os import path
from typing import Dict
from uuid import uuid4

from .constants import Constants


class EnvFile:
    def __init__(self, constants: Constants):
        self.constants = constants
        self._setup()
        self.set_default_envs()
        self.netconfigs = self.constants.netconfigs

    def _setup(self):
        # if file does not exist, create it
        if not path.isfile(self.constants.env_file_path):
            open(self.constants.env_file_path, "w").close()

    def _get_base_version(self):
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
            return basev

    def set_default_envs(self):
        # We get the current envs from the file
        env_values = self.envs.copy()

        # get the default envs from the constants
        default_envs = Constants.default_envs.copy()
        add = {
            "ADSBLOL_UUID": str(uuid4()),
            "ULTRAFEEDER_UUID": str(uuid4()),
            "BASE_VERSION": self._get_base_version(),
            "CONTAINER_VERSION": self._get_base_version(),
        }
        default_envs.update(add)
        # Ensure if they are not in the file, they are added
        print("default_envs", default_envs, file=sys.stderr)
        for key, value in default_envs.items():
            if key not in env_values:
                env_values[key] = value
        self.update(env_values)

        # feeder_ultrafeeder_config = self.generate_ultrafeeder_config()
        # FIXME nope nope! this is not the right place to do this.
        # if "FEEDER_ULTRAFEEDER_CONFIG" not in self.envs.keys():
        #     self.update({"FEEDER_ULTRAFEEDER_CONFIG": feeder_ultrafeeder_config})
        #     self.update({"UF": "1"})

    @property
    def envs(self):
        env_values = {}

        with open(self.constants.env_file_path) as f:
            for line in f.readlines():
                if line.strip().startswith("#"):
                    continue
                key, var = line.partition("=")[::2]
                env_values[key.strip()] = var.strip()

        return env_values

    def update(self, values: Dict[str, str]):
        with open(self.constants.env_file_path, "r") as f:
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

        with open(self.constants.env_file_path, "w") as f:
            f.writelines(updated_lines)

    @property
    def metadata(self):
        metadata = {}
        ultrafeeder = self.envs.get("FEEDER_ULTRAFEEDER_CONFIG", "").split(";")
        for key in self.constants.netconfigs.keys():
            adsb_normal, mlat_normal = self.constants.netconfigs[key].normal.split(";")
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
            "checked" if self.envs["FEEDER_TAR1090_USEROUTEAPI"] == "1" else ""
        )
        metadata["privacy"] = (
            "checked" if self.envs["MLAT_PRIVACY"] == "--privacy" else ""
        )
        metadata["biast"] = (
            "checked" if self.envs.get("FEEDER_ENABLE_BIASTEE") == "true" else ""
        )
        metadata["heywhatsthat"] = "checked" if self.envs["HEYWHATSTHAT"] == "1" else ""
        fr24_enabled = (
            self.envs["FR24"] == "1"
            and "FEEDER_FR24_SHARING_KEY" in self.envs
            and re.match("^[0-9a-zA-Z]*$", self.envs["FEEDER_FR24_SHARING_KEY"])
        )
        metadata["FR24"] = "checked" if fr24_enabled else ""
        metadata["PW"] = "checked" if self.envs["PW"] == "1" else ""
        metadata["FA"] = "checked" if self.envs["FA"] == "1" else ""
        metadata["RB"] = "checked" if self.envs["RB"] == "1" else ""
        metadata["PF"] = "checked" if self.envs["PF"] == "1" else ""
        metadata["AH"] = "checked" if self.envs["AH"] == "1" else ""
        metadata["OS"] = "checked" if self.envs["OS"] == "1" else ""
        metadata["RV"] = "checked" if self.envs["RV"] == "1" else ""
        return metadata

    def generate_ultrafeeder_config(self, metadata_override: Dict[str, str] = None):
        metadata = self.metadata.copy()
        # WARNING: The metadata is always ephemeral.
        # It is not saved back.
        # Sometimes we get a metadata_override, which is a dict of key: value.
        # This is because we need this extra information to generate the ultrafeeder config.
        # By generating the ultrafeeder config, we will find this information again.
        # This is because the ultrafeeder config is generated from the metadata, and the metadata is generated from the ultrafeeder config.
        # This is a chicken and egg problem.
        # FIXME please
        if metadata_override:
            metadata.update(metadata_override)

        # This is the magic that generates the ultrafeeder config
        # FIXME make this more readable... split it up
        candidate = set(
            self.envs.get("FEEDER_ULTRAFEEDER_CONFIG", "").split(";").copy()
        )
        initial_setup = self.envs.get("FEEDER_AGG")
        mlat_privacy = (
            metadata.get("privacy", "checked") == "checked"
            or self.envs.get("MLAT_PRIVACY") == "--privacy"
        )
        print("metadata", metadata, file=sys.stderr)
        print("initial_setup", initial_setup, file=sys.stderr)
        print("mlat_privacy", mlat_privacy, file=sys.stderr)

        # This only runs at start.
        if candidate == [""] and initial_setup:
            # we are in initial setup
            # let's switch based on 3 options, all, priv, ind
            if initial_setup in ["all", "priv"]:
                # add all netconfigs
                for key in self.constants.netconfigs.keys():
                    net_config = self.constants.netconfigs[key].generate(
                        mlat_privacy=mlat_privacy,
                        uuid=self.envs.get("ADSBLOL_UUID")
                        if key == "adsblol"
                        else None,
                    )
                    # If we are only privacy policy, skip netconfigs without policy
                    if (
                        initial_setup == "priv"
                        and not self.constants.netconfigs[key].has_policy
                    ):
                        continue
                    candidate.add(net_config)
            elif initial_setup == "ind":
                # get screwed... you need to do it yourself.
                ...
        else:
            # This runs every other time....
            # Let's make 2 lists, keys_to_remove and keys_to_add
            # If metadata[key] is in netconfigs and "on"; add it to keys_to_add
            # If metadata[key] is in netconfigs and not "on"; add it to keys_to_remove

            keys_to_add = [
                key
                for key in metadata
                if metadata[key] == "on" and key in self.constants.netconfigs.keys()
            ]
            keys_to_remove = [
                key
                for key in metadata
                if metadata[key] != "on" and key in self.constants.netconfigs.keys()
            ]


            for key in keys_to_remove:
                normal_lines = self.constants.netconfigs[key].normal.split(";")
                for line in candidate.copy():
                    if any(
                        line.startswith(normal_line) for normal_line in normal_lines
                    ):
                        candidate.remove(line)
            for key in keys_to_add:
                net_config = self.constants.netconfigs[key].generate(
                    mlat_privacy=mlat_privacy,
                    uuid=self.envs.get("ADSBLOL_UUID") if key == "adsblol" else None,
                )
                candidate.add(net_config)

        if self.envs.get("FEEDER_978"):
            candidate.add("adsb,dump978,30978,uat_in")
        if self.envs.get("FEEDER_1090", "").startswith("airspy"):
            candidate.add("adsb,airspy_adsb,30005,beast_in")

        # Remove empty value from set, if any
        candidate.discard("")

        print("net_configs_list", candidate, file=sys.stderr)
        return ";".join(candidate)
