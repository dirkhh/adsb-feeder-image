import json
from os import path
import re
from typing import List, Union
from utils.config import read_values_from_config_json, write_values_to_config_json
from utils.util import is_true, print_err


class Env:
    def __init__(
        self,
        name: str,
        value: Union[str, List[str]] = None,
        is_mandatory: bool = False,
        default: any = None,
        default_call: callable = None,
        value_call: callable = None,
        tags: list = None,
    ):
        self._name = name
        self._value = self._default = default
        if value != None:
            # only overwrite the default value if an actual Value was passed in
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
            if type(self._default) != NoneType and type(value_in_file) != type(
                self._default
            ):
                if type(self._default) == bool:
                    self._value = is_true(value_in_file)
                    return
                print_err(
                    f"got value of type {type(value_in_file)} from file - discarding as type of {self._name} should be {type(self._default)}"
                )
            else:
                self._value = value_in_file

            return
        if value == value_in_file:
            return  # do not write to file if value is the same
        if value == None or value == "None":
            self._write_value_to_file("")
        else:
            self._write_value_to_file(value)

    def _get_value_from_file(self):
        return read_values_from_config_json().get(self._name, None)

    def _write_value_to_file(self, new_value):
        print_err(f"adding {self._name} = {new_value} to config")
        # make sure we follow the weird rules for some of the variables
        # (these are mainly driven by how they are used once they get exported to .env)
        if any(t == "false_is_zero" for t in self.tags):
            value = "1" if is_true(value) else "0"
        if any(t == "false_is_empty" for t in self.tags):
            value = "1" if is_true(value) else ""
        values = read_values_from_config_json()
        values[self._name] = value
        write_values_to_config_json(values)

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
        if type(self._value) == list:
            print_err(
                f"WAIT == using standard setter to assign a list {self} -- {value} -- {type(value)}"
            )
            self._value = value
            self._reconcile(value)
            return
        if type(self._value) == list or value != self._value:
            self._value = value
            self._reconcile(value)

    def list_set(self, idx, value):
        idx = int(idx)
        print_err(f"set {self._name}[{idx}] = {value}")
        if type(self._value) != list:
            print_err(f"{self._name} is not a list, converting")
            self._value = [self._value]
            self.list_set(idx, value)
            return
        default_value = self._default[0] if len(self._default) == 1 else None
        while len(self._value) < idx:
            self._value.append(default_value)
        if idx == len(self._value):
            self._value.append(value)
        else:
            self._value[idx] = value
        self._reconcile(self._value)
        print_err(f"after reconcile {self._name} = {self._value}")

    def list_get(self, idx):
        idx = int(idx)
        if type(self._value) != list:
            print_err(f"{self._name} is not a list, giving up")
            return None
        if idx < len(self._value):
            return self._value[idx]
        if type(self._default) == list and len(self._default) == 1:
            while len(self._value) <= idx:
                self._value.append(self._default[0])
            return self._value[idx]
        stack_info(
            f"{self._name} only has {len(self._value)} values and no default, asking for {idx}"
        )
        return None

    def list_remove(self, idx=-1):
        idx = int(idx)
        if type(self._value) != list:
            print_err(f"{self._name} is not a list, giving up")
            return
        if idx == -1:
            idx = len(self._value) - 1
        while idx < len(self._value):
            self._value.pop()
        self._reconcile(self._value)

    @property
    def tags(self):
        if not self._tags:
            return []
        return self._tags
