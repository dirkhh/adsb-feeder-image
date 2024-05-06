import json
import os
import os.path
import tempfile
from .util import print_err

CONF_DIR = "/opt/adsb/config"
ENV_FILE_PATH = CONF_DIR + "/.env"
USER_ENV_FILE_PATH = CONF_DIR + "/.env.user"
JSON_FILE_PATH = CONF_DIR + "/config.json"


def read_values_from_config_json():
    # print_err("reading .json file")
    if not os.path.exists(JSON_FILE_PATH):
        # this must be either a first run after an install,
        # or the first run after an upgrade from a version that didn't use the config.json
        print_err("WARNING: config.json doesn't exist, populating from .env")
        values = read_values_from_env_file()
        write_values_to_config_json(values, reason="config.json didn't exist")

    ret = {}
    try:
        ret = json.load(open(JSON_FILE_PATH, "r"))
    except:
        print_err("Failed to read .json file")
    return ret


def write_values_to_config_json(data: dict, reason="no reason provided"):
    try:
        print_err(f"config.json write: {reason}")
        fd, tmp = tempfile.mkstemp(dir=CONF_DIR)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, JSON_FILE_PATH)
    except:
        print_err(f"Error writing config.json to {JSON_FILE_PATH}")


def read_values_from_env_file():
    # print_err("reading .env file")
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
    return ret


def escape_env(line):
    # docker compose does weird stuff if there are $ in the env vars
    # escape them using $$
    return line.replace("$", "$$")


def write_values_to_env_file(values):
    # print_err("writing .env file")
    with open(ENV_FILE_PATH, "w") as f:
        for key, value in sorted(values.items()):
            key = key.strip()
            # _ADSBIM_STATE variables aren't needed in the .env file
            if key.startswith("_ADSBIM_STATE"):
                continue
            if type(value) == list:
                print_err(f"WARNING: ==== key {key} has list value {value}")
                for i in range(len(value)):
                    suffix = "" if i == 0 else f"_{i}"
                    env_line = f"{key}{suffix}={value[i]}\n"
                    env_line = escape_env(env_line)
                    f.write(env_line)
                    print_err(f"wrote {env_line.strip()} to .env", level=8)
            else:
                env_line = f"{key}={value.strip() if type(value) == str else value}\n"
                env_line = escape_env(env_line)
                f.write(env_line)
                print_err(f"wrote {env_line.strip()} to .env", level=8)
    # write the user env in the form that can be easily inserted into the yml file
    # using the name here so it comes from the values passed in
    val = values.get("_ADSBIM_STATE_EXTRA_ENV", None)
    if not val and os.path.isfile(USER_ENV_FILE_PATH):
        # truncate the file if it exists and no value is set
        with open(USER_ENV_FILE_PATH, "w") as f:
            pass
    if val:
        with open(USER_ENV_FILE_PATH, "w") as f:
            lines = val.split("\r\n")
            for line in lines:
                if line.strip():
                    f.write(f"      - {line.strip()}\n")


conversion = {
    # web ports, needed in docker-compose files
    "_ADSBIM_STATE_WEBPORT": "AF_WEBPORT",
    "_ADSBIM_STATE_DAZZLE_PORT": "AF_DAZZLE_PORT",
    "_ADSBIM_STATE_TAR1090_PORT": "AF_TAR1090_PORT",
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
