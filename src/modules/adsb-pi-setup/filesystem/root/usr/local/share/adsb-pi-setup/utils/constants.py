# dataclass

from dataclasses import dataclass


@dataclass
class Constants:
    proxy_routes = [
        # endpoint, port, url_path
        ["/map/", 8080, "/"],
        ["/tar1090/", 8080, "/"],
        ["/graphs1090/", 8080, "/graphs1090/"],
        ["/graphs/", 8080, "/graphs1090/"],
        ["/stats/", 8080, "/graphs1090/"],
        ["/piaware/", 8081, "/"],
        ["/fa/", 8081, "/"],
        ["/flightaware/", 8081, "/"],
        ["/piaware-stats/", 8082, "/"],
        ["/pa-stats/", 8082, "/"],
        ["/fa-stats/", 8082, "/"],
        ["/fa-status/", 8082, "/"],
        ["/config/", 5000, "/setup"],
        ["/fr-status/", 8754, "/"],
        ["/fr/", 8754, "/"],
        ["/fr24/", 8754, "/"],
        ["/flightradar/", 8754, "/"],
        ["/flightradar24/", 8754, "/"],
        ["/portainer/", 9443, "/"],
        ["/dump978/", 9780, "/skyaware978/"],
    ]

    # these are the default values for the env file
    default_envs = {
            "FEEDER_TAR1090_USEROUTEAPI": "1",
            "FEEDER_RTL_SDR": "rtlsdr",
            "MLAT_PRIVACY": "--privacy",
            "FEEDER_READSB_GAIN": "autogain",
            "FEEDER_HEYWHATSTHAT_ID": "",
            "FEEDER_AGG": "",
            "HEYWHATSTHAT": "0",
            "FR24": "0",
            "PW": "0",
            "FA": "0",
            "RB": "0",
            "PF": "0",
            "AH": "0",
            "OS": "0",
            "RV": "0",
            "UF": "0",
            "AIRSPY": "0",
            "PORTAINER": "0",
            "BASE_CONFIG": "0",
            "NIGHTLY_BASE_UPDATE": "1",
            "NIGHTLY_CONTAINER_UPDATE": "1",
    }

    env_file_path = "/opt/adsb/.env"
