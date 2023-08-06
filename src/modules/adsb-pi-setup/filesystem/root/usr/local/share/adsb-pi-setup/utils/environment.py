import sys

from os import path

ENV_FILE_PATH = "/opt/adsb/.env"


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


# extend the truthy concept to exclude all non-empty string except a few specific ones ([Tt]rue, [Oo]n, 1)
def is_true(value):
    if type(value) == str:
        return any({value.lower() == "true", value.lower == "on", value == "1"})
    return bool(value)


class Env:
    def __init__(
        self,
        name: str,
        value: str = None,
        is_mandatory: bool = True,
        default = None,
        default_call: callable = None,
        value_call: callable = None,
        tags: list = None,
        javascript: bool = False,
    ):
        self._name = name
        self._value = self._default = default
        if value != None:  # only overwrite the default value if an actual Value was passed in
            self._value = value
        self._is_mandatory = is_mandatory
        self._value_call = value_call
        self._tags = tags
        self._javascript = javascript
        self._file = ENV_FILE_PATH  # FIXME: storing this in every Env seems... suboptimal

        if default_call:
            self._default = default_call()

        # Always reconcile from file
        self._reconcile(value=None, pull=True)

    def _reconcile(self, value, pull: bool = False):
        if not path.isfile(self._file):
            # Let's create it
            open(self._file, "w").close()

        value_in_file = self._get_value_from_file()
        if pull and value_in_file:
            self._value = value_in_file
            return
        if value == value_in_file:
            return  # do not write to file if value is the same
        if value == None or value == "None":
            self._write_value_to_file("")
        else:
            self._write_value_to_file(value)

    def _get_values_from_file(self):
        ret = {}
        try:
            with open(self._file, "r") as f:
                for line in f.readlines():
                    if line.strip().startswith("#"):
                        continue
                    key, var = line.partition("=")[::2]
                    ret[key.strip()] = var.strip()
        except:
            pass

        return ret

    def _get_value_from_file(self):
        return self._get_values_from_file().get(self._name, None)

    def _write_value_to_file(self, new_value):
        values = self._get_values_from_file()
        if self._javascript:
            new_value = "1" if is_true(new_value) else "0"
        values[self._name] = new_value
        with open(self._file, "w") as f:
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
        if value != self._value:
            self._value = value
            self._reconcile(value)

    @property
    def tags(self):
        if not self._tags:
            return []
        return self._tags
