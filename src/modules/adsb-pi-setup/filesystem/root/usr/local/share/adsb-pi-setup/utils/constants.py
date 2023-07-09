# dataclass

from dataclasses import dataclass
from .netconfig import NetConfig

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

    netconfigs = {
        "adsblol": NetConfig(
            "adsb,feed.adsb.lol,30004,beast_reduce_plus_out",
            "mlat,feed.adsb.lol,31090,39001",
            has_policy=True,
        ),
        "flyitaly": NetConfig(
            "adsb,dati.flyitalyadsb.com,4905,beast_reduce_plus_out",
            "mlat,dati.flyitalyadsb.com,30100,39002",
            has_policy=True,
        ),
        "adsbx": NetConfig(
            "adsb,feed1.adsbexchange.com,30004,beast_reduce_plus_out",
            "mlat,feed.adsbexchange.com,31090,39003",
            has_policy=True,
        ),
        "tat": NetConfig(
            "adsb,feed.theairtraffic.com,30004,beast_reduce_plus_out",
            "mlat,feed.theairtraffic.com,31090,39004",
            has_policy=False,
        ),
        "ps": NetConfig(
            "adsb,feed.planespotters.net,30004,beast_reduce_plus_out",
            "mlat,mlat.planespotters.net,31090,39005",
            has_policy=True,
        ),
        "adsbone": NetConfig(
            "adsb,feed.adsb.one,64004,beast_reduce_plus_out",
            "mlat,feed.adsb.one,64006,39006",
            has_policy=False,
        ),
        "adsbfi": NetConfig(
            "adsb,feed.adsb.fi,30004,beast_reduce_plus_out",
            "mlat,feed.adsb.fi,31090,39007",
            has_policy=False,
        ),
        "avdelphi": NetConfig(
            "adsb,data.avdelphi.com,24999,beast_reduce_plus_out",
            "",
            has_policy=True,
        ),
    }
