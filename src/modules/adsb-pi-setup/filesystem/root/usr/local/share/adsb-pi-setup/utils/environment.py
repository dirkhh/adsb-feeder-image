import sys

from os import path


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


ENV_FILE_PATH = "/opt/adsb/.env"  # FIXME
#fixed ADSBIM_ENV_FILE_PATH = "/opt/adsb/.adsbim.env"  # FIXME


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

        # Always reconcile from file
        self._reconcile(pull=True)

    def _reconcile(self, pull: bool = False):
        #fixed ENV_FILE_PATH = ADSBIM_ENV_FILE_PATH if self._name.startswith("_ADSBIM") else ENV_FILE_PATH
        print_err(f"reconcile for {self.name} in {ENV_FILE_PATH}")
        if not path.isfile(ENV_FILE_PATH):
            # Let's create it
            open(ENV_FILE_PATH, "w").close()

        var_in_file = self._get_value_from_file(ENV_FILE_PATH)
        if pull and var_in_file:
            self._value = var_in_file
            return

        if self._value:
            self._write_value_to_file(ENV_FILE_PATH)
            return

    def _get_values_from_file(self, filepath):
        ret = {}
        try:
            with open(filepath, "r") as f:
                for line in f.readlines():
                    if line.strip().startswith("#"):
                        continue
                    key, var = line.partition("=")[::2]
                    ret[key.strip()] = var.strip()
        except:
            pass

        return ret

    def _get_value_from_file(self, filepath):
        return self._get_values_from_file(filepath).get(self._name, None)

    def _write_value_to_file(self, filepath):
        print_err(f"write_value_to_file for {self.name}")
        values = self._get_values_from_file(filepath)
        values[self._name] = self._value
        with open(filepath, "w") as f:
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
        self._reconcile()
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
