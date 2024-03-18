import json
from os import path
import re
from typing import List, Union

from utils.util import print_err

ENV_FILE_PATH = "/opt/adsb/config/.env"
USER_ENV_FILE_PATH = "/opt/adsb/config/.env.user"
ENV_FLAG_FILE_PATH = "/opt/adsb/config/.env.flag"
JSON_FILE_PATH = "/opt/adsb/config/config.json"


# extend the truthy concept to exclude all non-empty string except a few specific ones ([Tt]rue, [Oo]n, 1)
def is_true(value):
    if type(value) == str:
        return any({value.lower() == "true", value.lower == "on", value == "1"})
    return bool(value)


class Env:
    def __init__(
        self,
        name: str,
        value: Union[str, List[str]] = None,
        is_mandatory: bool = True,
        default: any = None,
        default_call: callable = None,
        value_call: callable = None,
        tags: list = None,
    ):
        self._name = name
        self._value = self._default = default
        if (
            value != None
        ):  # only overwrite the default value if an actual Value was passed in
            self._value = value
        self._is_mandatory = is_mandatory
        self._value_call = value_call
        self._tags = tags

        if default_call:
            self._default = default_call()

        # Always reconcile from file
        self._reconcile(value=None, pull=True)

    def _reconcile(self, value, pull: bool = False):
        value_in_file = self._get_value_from_file()
        if pull and value_in_file != None:
            self._value = value_in_file
            return
        if value == value_in_file:
            return  # do not write to file if value is the same
        if value == None or value == "None":
            self._write_value_to_file("")
        else:
            self._write_value_to_file(value)

    def _get_values_from_file(self):
        ret = json.load(open(JSON_FILE_PATH, "r"))
        return ret

    def _get_values_from_env_file(self):
        ret = {}
        try:
            with open(ENV_FILE_PATH, "r") as f:
                for line in f.readlines():
                    if line.strip().startswith("#"):
                        continue
                    key, var = line.partition("=")[::2]
                    if key in conversion.keys():
                        key = conversion[key]
                    ret[key.strip()] = var.strip()
        except:
            print_err("Failed to read .env file")
            pass

        return ret

    def _get_value_from_file(self):
        # this is ugly because we need to be able to import a .env file
        # if there is no json file, but the moment we import the first
        # Env from the .env file, it will create the json file
        # so we rely on the calling code to have provided us with a flag file
        if path.exists(ENV_FLAG_FILE_PATH):
            return self._get_values_from_env_file().get(self._name, None)
        return self._get_values_from_file().get(self._name, None)

    def _write_file(self, values):
        json.dump(values, open(JSON_FILE_PATH, "w"))
        with open(ENV_FILE_PATH, "w") as f:
            for key, value in sorted(values.items()):
                # _ADSBIM_STATE variables aren't needed in the .env file
                if key.startswith("_ADSBIM_STATE"):
                    continue
                f.write(
                    f"{key.strip()}={value.strip() if type(value) == str else value}\n"
                )
        # write the user env in the form that can be easily inserted into the yml file
        # using the name here so it comes from the values passed in
        val = values.get("_ADSBIM_STATE_EXTRA_ENV", "\r\n")
        if val:
            with open(USER_ENV_FILE_PATH, "w") as f:
                lines = val.split("\r\n")
                for line in lines:
                    if line.strip():
                        f.write(f"      - {line.strip()}\n")

    def _write_value_to_file(self, new_value):
        values = self._get_values_from_file()
        if any(t == "false_is_zero" for t in self.tags):
            new_value = "1" if is_true(new_value) else "0"
        if any(t == "false_is_empty" for t in self.tags):
            new_value = "1" if is_true(new_value) else ""
        values[self._name] = new_value
        self._write_file(values)
        self._write_file(values)

    def __str__(self):
        return f"Env({self._name}, {self._value})"

    @property
    def name(self):
        return self._name

    @property
    def is_mandatory(self) -> bool:
        return self._is_mandatory

    @property
    def is_bool(self) -> bool:
        # if it has is_enabled in the tags, it is a bool and we
        # accept True/False, 1/0, and On/Off in setter,
        # and write True/False to file.
        return "is_enabled" in self._tags

    @property
    def value(self):
        if self.is_bool:
            return is_true(self._value)
        if self._value_call:
            return self._value_call()
        elif self._value != None:
            return self._value
        elif self._default != None:
            return self._default
        return ""

    @value.setter
    def value(self, value):
        # mess with value in case we are a bool
        # we get "1" from .env files and "on" from checkboxes in HTML
        if self.is_bool:
            value = is_true(value)
        # stupid Python with it's complex data types... modifying a list in the app
        # already modifies the existing object in memory - so we need to force a comparison
        # to the value in the file
        if type(self._value) == list or value != self._value:
            self._value = value
            self._reconcile(value)

    @property
    def tags(self):
        if not self._tags:
            return []
        return self._tags


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
    "_ADSBIM_STATE_IS_DOZZLE_ENABLED": "AF_IS_DOZZLE_ENABLED",
    "_ADSBIM_STATE_IS_AIRSPY_ENABLED": "AF_IS_AIRSPY_ENABLED",
    "_ADSBIM_STATE_IS_SECURE_IMAGE": "AF_IS_SECURE_IMAGE",
    "_ADSBIM_STATE_IS_NIGHTLY_BASE_UPDATE_ENABLED": "AF_IS_NIGHTLY_BASE_UPDATE_ENABLED",
    "_ADSBIM_STATE_IS_NIGHTLY_FEEDER_UPDATE_ENABLED": "AF_IS_NIGHTLY_FEEDER_UPDATE_ENABLED",
    "_ADSBIM_STATE_IS_NIGHTLY_CONTAINER_UPDATE_ENABLED": "AF_IS_NIGHTLY_CONTAINER_UPDATE_ENABLED",
}
