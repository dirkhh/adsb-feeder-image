import sys

from os import path


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


FILE_PATH = "/opt/adsb/.env"  # FIXME


class Env:
    def __init__(
        self,
        name: str,
        value: str = None,
        is_mandatory: bool = True,
        default: str = "",
        default_call: callable = None,
        value_call: callable = None,
        tags: list = None,
    ):
        self._name = name
        self._value = value
        self._is_mandatory = is_mandatory
        self._default = default
        self._value_call = value_call
        self._tags = tags

        if default_call:
            self._default = default_call()

        # Always reconcile from FILE_PATH
        self._reconcile(pull=True)

    def _reconcile(self, pull: bool = False):
        print_err(f"reconcile for {self.name}")
        if not path.isfile(FILE_PATH):
            # Let's create it
            open(FILE_PATH, "w").close()

        var_in_file = self._get_value_from_file()
        if pull and var_in_file:
            self._value = var_in_file
            return

        if self._value:
            self._write_value_to_file()
            return

    def _get_values_from_file(self):
        ret = {}
        try:
            with open(FILE_PATH, "r") as f:
                for line in f.readlines():
                    if line.strip().startswith("#"):
                        continue
                    key, var = line.partition("=")[::2]
                    ret[key.strip()] = var.strip()
        except:
            pass

        return ret

    def _get_value_from_file(self):
        var = None
        try:
            values = self._get_values_from_file()
            var = values[self._name]
        except:
            pass
        return var

    def _write_value_to_file(self):
        # other parts of the code rely on fixed names and on
        # having the prefix values in the .env file as an indication
        # of whether this particular container is in use
        # this could of course all be replaced - but for now it seems
        # easier to simply duplicate this here in Python code
        container_prefix = {
            "_ADSBIM_STATE_IS_FLIGHTRADAR24_ENABLED": "FR24",
            "_ADSBIM_STATE_IS_PLANEWATCH_ENABLED": "PW",
            "_ADSBIM_STATE_IS_FLIGHTAWARE_ENABLED": "FA",
            "_ADSBIM_STATE_IS_RADARBOX_ENABLED": "RB",
            "_ADSBIM_STATE_IS_PLANEFINDER_ENABLED": "PF",
            "_ADSBIM_STATE_IS_ADSBHUB_ENABLED": "AH",
            "_ADSBIM_STATE_IS_RADARVIRTUEL_ENABLED": "RV",
            "_ADSBIM_STATE_IS_OPENSKY_ENABLED": "OS",
            "_ADSBIM_STATE_IS_AIRSPY_ENABLED": "AIRSPY",
            "_ADSBIM_STATE_IS_PORTAINER_ENABLED": "PORTAINER",
        }
        print_err(f"write_value_to_file for {self.name}")
        values = self._get_values_from_file()
        values[self._name] = self._value
        if self._name in container_prefix.keys():
            values[container_prefix[self._name]] = "1" if self._value.lower in { "1", "true", "on" } else "0"
        with open(FILE_PATH, "w") as f:
            for key, value in values.items():
                f.write(f"{key}={value}\n")

    def __str__(self):
        return f"Env({self._name}, {self._value})"

    @property
    def name(self):
        return self._name

    @property
    def is_mandatory(self) -> bool:
        return self._is_mandatory

    @property
    def value(self):
        if self._value_call:
            self.value = self._value_call()
            return self._value
        if self._value:
            return self._value
        return self._default

    @value.setter
    def value(self, value):
        self._value = value
        # FIXME: this is just annoying debugging stuff
        print_err(f"set value of {self.name} to {value}")
        self._reconcile()

    @property
    def tags(self):
        if not self._tags:
            return []
        return self._tags
