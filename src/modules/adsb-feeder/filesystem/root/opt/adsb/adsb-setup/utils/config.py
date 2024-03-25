import json
from .util import print_err


ENV_FILE_PATH = "/opt/adsb/config/.env"
USER_ENV_FILE_PATH = "/opt/adsb/config/.env.user"
JSON_FILE_PATH = "/opt/adsb/config/config.json"


def read_values_from_config_json():
    # print_err("reading .json file")
    ret = {}
    try:
        ret = json.load(open(JSON_FILE_PATH, "r"))
    except:
        print_err("Failed to read .json file")
    return ret


def write_values_to_config_json(data: dict):
    # print_err("writing .json file")
    json.dump(data, open(JSON_FILE_PATH, "w"))


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


def write_values_to_env_file(values):
    # print_err("writing .env file")
    with open(ENV_FILE_PATH, "w") as f:
        for key, value in sorted(values.items()):
            # _ADSBIM_STATE variables aren't needed in the .env file
            if key.startswith("_ADSBIM_STATE"):
                continue
            f.write(f"{key.strip()}={value.strip() if type(value) == str else value}\n")
    # write the user env in the form that can be easily inserted into the yml file
    # using the name here so it comes from the values passed in
    val = values.get("_ADSBIM_STATE_EXTRA_ENV", None)
    if val:
        with open(USER_ENV_FILE_PATH, "w") as f:
            lines = val.split("\r\n")
            for line in lines:
                if line.strip():
                    f.write(f"      - {line.strip()}\n")


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
