from dataclasses import dataclass
import json
import os
from .util import is_true, print_err, stack_info
from .netconfig import UltrafeederConfig


@dataclass
class Config:
    # this is a singleton
    def __new__(cc):
        if not hasattr(cc, "instance"):
            cc.instance = super(Config, cc).__new__(cc)
        return cc.instance

    ENV_FILE_PATH = "/opt/adsb/config/.env"
    USER_ENV_FILE_PATH = "/opt/adsb/config/.env.user"
    ENV_FLAG_FILE_PATH = "/opt/adsb/config/.env.flag"
    JSON_FILE_PATH = "/opt/adsb/config/config.json"

    def write_to_config(self):
        print_err("writing .json file")
        data = {}
        for e in self._env:
            data[e._name] = e._value
        json.dump(data, open(self.JSON_FILE_PATH, "w"))

    def get_values_from_config(self):
        print_err("reading .json file")
        try:
            ret = json.load(open(self.JSON_FILE_PATH, "r"))
        except:
            stack_info("Failed to read .json file")
            ret = {}
        return ret

    def get_values_from_env_file(self):
        ret = {}
        try:
            with open(self.ENV_FILE_PATH, "r") as f:
                for line in f.readlines():
                    if line.strip().startswith("#"):
                        continue
                    key, var = line.partition("=")[::2]
                    if key in conversion.keys():
                        key = conversion[key]
                    ret[key.strip()] = var.strip()
        except:
            stack_info("Failed to read .env file")

        return ret

    def get_value_from_file(self, name):
        # this is ugly because we need to be able to import a .env file
        # if there is no json file, but the moment we import the first
        # Env from the .env file, it will create the json file
        # so we rely on the calling code to have provided us with a flag file
        if os.path.exists(self.ENV_FLAG_FILE_PATH):
            print_err(f"getting value for {name} from .env file")
            return self._get_values_from_env_file().get(name, None)
        return self._get_values_from_file().get(name, None)

    def write_values_to_env_file(self, values):
        # writes the values in the Dict passed in to the .env file
        stack_info("writing .env file")
        with open(self.ENV_FILE_PATH, "w") as f:
            for key, value in sorted(values.items()):
                # _ADSBIM_STATE variables aren't needed in the .env file
                if key.startswith("_ADSBIM_STATE"):
                    continue
                # if we have no MAP_NAME, use the MLAT_SITE_NAME - it's annoying that
                # we need to fix this up here, but in order to be able to seamlessly
                # migrate from older versions, this seemed like the easiest way to do it
                if key == "MAP_NAME" and not value:
                    value = values.get("MLAT_SITE_NAME", "")
                if type(value) == list:
                    # so now we need to write this out as multiple environment variables
                    for idx in range(len(value)):
                        v = value[idx]
                        f.write(
                            f"{key.strip()}_{idx}={v.strip() if type(v) == str else v}\n"
                        )
                else:
                    f.write(
                        f"{key.strip()}={value.strip() if type(value) == str else value}\n"
                    )
        # write the user env in the form that can be easily inserted into the yml file
        # using the name here so it comes from the values passed in
        val = values.get("_ADSBIM_STATE_EXTRA_ENV", None)
        if val:
            with open(self.USER_ENV_FILE_PATH, "w") as f:
                lines = val.split("\r\n")
                for line in lines:
                    if line.strip():
                        f.write(f"      - {line.strip()}\n")

        # finally we need to also update the config.json
        # note!!! this is a convenience call - it writes back the global Data()._env, not the Dict that was passed in here
        self.write_config()

    # helper function to get everything that needs to be written out written out
    def writeback_env(self):
        stack_info("writing out the .env file")
        env_vars = self.get_values_from_file()
        # if this is a stage2 server, get the number of micro proxies
        print_err("is this a stage2 server?")
        if self.is_enabled("stage2"):
            stage2 = True
            numsites = self.env("AF_NUM_MICRO_SITES").value
        else:
            stage2 = False
            numsites = 0
        for e in self._env:
            print_err(f"WRITEBACK {e} with type {type(e._value)}")
            # make sure we create the ultrafeeder configurations
            if e.name == "FEEDER_ULTRAFEEDER_CONFIG" and stage2:
                print_err(f"writing the stage2 Ultrafeeder config ")
                for i in range(numsites + 1):
                    if i >= len(self.ultrafeeder):
                        self.ultrafeeder.append(UltrafeederConfig(data=self, micro=i))
                    if type(self.ultrafeeder[i]) != UltrafeederConfig:
                        self.ultrafeeder[i] = UltrafeederConfig(data=self, micro=i)
                    uc = self.ultrafeeder[i].generate()
                    e.list_set(i, uc)
                    # 0 is the integrated feeder / micro feeder / home location of a stage 2 server
                    # 1...n are the micro feeder proxies
                    env_vars[self.env_name_by_idx("FEEDER_ULTRAFEEDER_CONFIG", i)] = uc
                continue
            if type(e._value) == list and stage2:
                # whenever we have a list, we write all elements with _idx notation
                for i in range(numsites + 1):
                    env_vars[self.env_name_by_idx(e.name, i)] = self.expand_value(
                        e, e.list_get(i)
                    )
            elif type(e._value) == list:
                env_vars[e.name] = self.expand_value(e, e.list_get(0))
            else:
                env_vars[e.name] = self.expand_value(e, e.value)

        print_err(f"read in from file and applied any in memory changes: {env_vars}")
        self.write_values_to_env_file(env_vars)

    # helper function to write the correct type of data to the .env file
    # value is an explicit argument so the caller can figure out if this is a list
    def expand_value(self, e, value):
        if any(t == "false_is_zero" for t in e.tags):
            return "1" if is_true(value) else "0"
        elif any(t == "false_is_empty" for t in e.tags):
            return "True" if is_true(value) else ""
        else:
            return value


conversion = {
    # web ports, needed in docker-compose files
    "_ADSBIM_STATE_WEBPORT": "AF_WEBPORT",
    "_ADSBIM_STATE_DAZZLE_PORT": "AF_DAZZLEPORT",
    "_ADSBIM_STATE_TAR1090_PORT": "AF_TAR1090PORT",
    "_ADSBIM_STATE_PIAWAREMAP_PORT": "AF_PIAWAREMAP_PORT",
    "_ADSBIM_STATE_PIAWARESTAT_PORT": "AF_PIAWARESTAT_PORT",
    "_ADSBIM_STATE_FLIGHTRADAR_PORT": "AF_FLIGHTRADAR_PORT",
    "_ADSBIM_STATE_PLANEFINDER_PORT": "AF_PLANEFINDER_PORT",
    # flag variables, used by shell scripts
    "_ADSBIM_STATE_IS_BASE_CONFIG_FINISHED": "AF_IS_BASE_CONFIG_FINISHED",
    "_ADSBIM_STATE_IS_FLIGHTRADAR24_ENABLED": "AF_IS_FLIGHTRADAR24_ENABLED",
    "_ADSBIM_STATE_IS_PLANEWATCH_ENABLED": "AF_IS_PLANEWATCH_ENABLED",
    "_ADSBIM_STATE_IS_FLIGHTAWARE_ENABLED": "AF_IS_FLIGHTAWARE_ENABLED",
    "_ADSBIM_STATE_IS_RADARBOX_ENABLED": "AF_IS_RADARBOX_ENABLED",
    "_ADSBIM_STATE_IS_PLANEFINDER_ENABLED": "AF_IS_PLANEFINDER_ENABLED",
    "_ADSBIM_STATE_IS_ADSBHUB_ENABLED": "AF_IS_ADSBHUB_ENABLED",
    "_ADSBIM_STATE_IS_OPENSKY_ENABLED": "AF_IS_OPENSKY_ENABLED",
    "_ADSBIM_STATE_IS_RADARVIRTUEL_ENABLED": "AF_IS_RADARVIRTUEL_ENABLED",
    "_ADSBIM_STATE_IS_1090UK_ENABLED": "AF_IS_1090UK_ENABLED",
    "_ADSBIM_STATE_IS_AIRSPY_ENABLED": "AF_IS_AIRSPY_ENABLED",
    "_ADSBIM_STATE_IS_SECURE_IMAGE": "AF_IS_SECURE_IMAGE",
    "_ADSBIM_STATE_IS_NIGHTLY_BASE_UPDATE_ENABLED": "AF_IS_NIGHTLY_BASE_UPDATE_ENABLED",
    "_ADSBIM_STATE_IS_NIGHTLY_FEEDER_UPDATE_ENABLED": "AF_IS_NIGHTLY_FEEDER_UPDATE_ENABLED",
    "_ADSBIM_STATE_IS_NIGHTLY_CONTAINER_UPDATE_ENABLED": "AF_IS_NIGHTLY_CONTAINER_UPDATE_ENABLED",
}
