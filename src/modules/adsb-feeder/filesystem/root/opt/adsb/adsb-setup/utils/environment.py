from typing import List, Union
from utils.config import read_values_from_config_json, write_values_to_config_json, config_lock
from utils.util import is_true, print_err, stack_info, make_int


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

        if default_call:
            self._default = default_call()
        else:
            self._default = default

        if type(self._default) == list:
            self._value = [self._default[0]]
        else:
            self._value = self._default

        if value != None:
            # only overwrite the default value if an actual Value was passed in
            self._value = value
        self._is_mandatory = is_mandatory
        self._value_call = value_call
        self._tags = tags

        # Always reconcile from file
        self._reconcile(value=None, pull=True)

    def _reconcile(self, value, pull: bool = False):
        with config_lock:
            file_values = read_values_from_config_json()
            value_in_file = file_values.get(self._name, None)

            if pull and value_in_file != None:
                if self._default != None and type(value_in_file) != type(self._default):
                    if type(self._default) == bool:
                        self._value = is_true(value_in_file)
                        return
                    if type(self._default) == list and len(self._default) > 0:
                        if type(self._default[0]) == type(value_in_file):
                            self._value = [value_in_file]
                            stack_info(f"converting {self._name} to list {self._value}")
                            return
                        if type(self._default[0]) == bool and (value_in_file.lower() in ["true", "false", "0", "1"]):
                            self._value = [is_true(value_in_file)]
                            stack_info(f"converting {self._name} to list {self._value}")
                            return
                    if type(self._default) == int and type(value_in_file) == str:
                        try:
                            self._value = int(value_in_file)
                            return
                        except Exception as e:
                            print_err(f"cannot convert {value_in_file} to int - {e}")
                    print_err(
                        f"got value {value_in_file} of type {type(value_in_file)} from file - discarding as type of {self._name} should be {type(self._default)}"
                    )
                else:
                    if type(value_in_file) == list and self.is_bool:
                        self._value = [is_true(v) for v in value_in_file]
                        return
                    self._value = value_in_file

                return

            if value == value_in_file:
                return  # do not write to file if value is the same
            if value == None or value == "None":
                value = ""

            file_values[self._name] = value
            write_values_to_config_json(file_values, reason=f"{self._name} = {value}")

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
    def is_list(self) -> bool:
        return type(self._default) == list

    @property
    def value(self):
        if self._value_call:
            return self._value_call()
        elif self._value != None:
            return self._value
        elif self._default != None:
            if type(self._default) == list:
                return [self._default[0]]
            else:
                return self._default
            return self._default
        return ""

    @value.setter
    def value(self, value):
        # mess with value in case we are a bool
        # we get "1" from .env files and "on" from checkboxes in HTML
        if self.is_bool:
            value = is_true(value)
        # stupid Python with its complex data types... modifying a list in the app
        # already modifies the existing object in memory - so we need to force a comparison
        # to the value in the file
        if type(self._value) == list:
            stack_info(f"WAIT == using standard setter to assign a list {self} -- {value} -- {type(value)}")
            self.list_set(0, value)
            self._reconcile(value)
            return
        if type(self._value) == list or value != self._value:
            self._value = value
            self._reconcile(value)

    def _list_pad(self, idx: int):
        # make sure we have at least idx + 1 values, padding with default if necessary
        # only call after you verified that this env is a list and idx is an int
        # internal function - does not reconcile
        if idx >= len(self._value):
            d = None
            if type(self._default) != list:
                print_err(f"{self._name}: default type should be list: {type(self._default)}, using None as default")
            elif len(self._default) == 0:
                print_err(f"{self._name}: default list len should be 1: {len(self._default)}")
            else:
                d = self._default[0]
            while len(self._value) <= idx:
                self._value.append(d)

    def list_set(self, idx, value):
        # mess with value in case we are a bool
        # we get "1" from .env files and "on" from checkboxes in HTML
        if self.is_bool:
            value = is_true(value)
        idx = make_int(idx)
        if type(self._value) != list:
            stack_info(f"{self._name} is not a list, converting")
            self._value = [self._value]
            self.list_set(idx, value)
            return

        if idx < len(self._value) and self._value[idx] == value:
            # no change, return silently
            return

        if idx >= len(self._value):
            self._list_pad(idx)

        print_err(f"list_set {self._name}[{idx}] = {value}")
        self._value[idx] = value
        self._reconcile(self._value)

    def list_get(self, idx):
        idx = make_int(idx)
        if type(self._value) != list:
            stack_info(f"{self._name} is not a list, converting")
            self._value = [self._value]
        if idx < len(self._value):
            return self._value[idx]
        if type(self._default) == list and len(self._default) == 1:
            while len(self._value) <= idx:
                self._value.append(self._default[0])
                self._reconcile(self._value)
            return self._value[idx]

        if type(self._default) != list:
            print_err(f"{self._name}: default type should be list: {type(self._default)}")
        if type(self._default) == list and len(self._default) != 1:
            print_err(f"{self._name}: default list len should be 1: {len(self._default)}")

        stack_info(f"{self._name} only has {len(self._value)} values and no default, asking for {idx}")
        return ""

    def list_remove(self, idx=-1):
        idx = make_int(idx)
        if type(self._value) != list:
            print_err(f"{self._name} is not a list, giving up")
            return
        if idx == -1:
            idx = len(self._value) - 1
        while idx < len(self._value):
            self._value.pop()
        self._reconcile(self._value)

    def list_move(self, from_idx, to_idx):
        from_idx = make_int(from_idx)
        to_idx = make_int(to_idx)
        if type(self._value) != list:
            print_err(f"{self._name} is not a list, giving up")
            return
        # make sure the list is long enough for the operation to complete, padding with default if necessary
        idx = max(from_idx, to_idx)
        if idx >= len(self._value):
            self._list_pad(idx)
        self._value.insert(to_idx, self._value.pop(from_idx))
        self._reconcile(self._value)

    @property
    def tags(self):
        if not self._tags:
            return []
        return self._tags
