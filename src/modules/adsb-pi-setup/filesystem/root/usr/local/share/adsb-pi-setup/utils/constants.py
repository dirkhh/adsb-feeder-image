# dataclass

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .environment import Env
from .netconfig import NetConfig
from .system import Version


@dataclass
class Constants:
    data_path = Path("/opt/adsb")
    env_file_path = data_path / ".env"
    version_file = Path("/etc/adsb.im.version")

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
    # Other aggregator tags
    _oat = ["other_aggregator", "is_enabled"]
    _env = {
        # Mandatory!
        # Position
        Env("FEEDER_LAT", True, frontend_names=["lat"]),
        Env("FEEDER_LON", True, frontend_names=["lng"]),
        Env("FEEDER_ALT_M", True, frontend_names=["alt"]),
        Env("FEEDER_TZ", True, frontend_names=["form_timezone"]),
        Env("MLAT_SITE_NAME", True, frontend_names=["mlat_name"]),
        # SDR
        Env("FEEDER_RTL_SDR", True, default="rtlsdr"),
        Env("FEEDER_ENABLE_BIASTEE", True, default="false"),
        Env("FEEDER_SERIAL_1090", False),  # FIXME
        Env("FEEDER_SERIAL_978", False),  # FIXME
        Env("FEEDER_READSB_GAIN", True, default="autogain"),
        # Feeder
        Env("ADSBLOL_UUID", True, default_call=lambda: str(uuid4())),
        Env("ULTRAFEEDER_UUID", True, default_call=lambda: str(uuid4())),
        Env("MLAT_PRIVACY", True, default="--privacy", frontend_names=["mlat_privacy"]),
        Env("FEEDER_TAR1090_USEROUTEAPI", True, default="1"),
        # Misc
        Env("FEEDER_HEYWHATSTHAT_ID", False),
        # ADSB.im specific
        Env("_ADSBIM_VERSION", False, tags=["version"]),
        Env("_ADSBIM_VERSION_DATE", False),
        Env("_ADSBIM_VERSION_HASH", False),
        Env("_ADSBIM_IS_FLIGHTRADAR24_ENABLED", False, tags=["fr24"]),
        Env(
            "_ADSBIM_IS_PLANEWATCH_ENABLED",
            False,
            tags=[*_oat, "plane_watch"],
            frontend_names=["PW"],
        ),
        Env(
            "_ADSBIM_IS_FLIGHTAWARE_ENABLED",
            False,
            tags=[*_oat, "flightaware"],
            frontend_names=["FA"],
        ),
        Env(
            "_ADSBIM_IS_RADARBOX24_ENABLED",
            False,
            tags=[*_oat, "radarbox24"],
            frontend_names=["RB"],
        ),
        Env(
            "_ADSBIM_IS_PLANEFINDER_ENABLED",
            False,
            tags=[*_oat, "planefinder"],
            frontend_names=["PF"],
        ),
        Env(
            "_ADSBIM_IS_ADSBHUB_ENABLED",
            False,
            tags=[*_oat, "adsb_hub"],
            frontend_names=["AH"],
        ),
        Env(
            "_ADSBIM_IS_OPENSKY_ENABLED",
            False,
            tags=[*_oat, "opensky"],
            frontend_names=["OS"],
        ),
        Env(
            "_ADSBIM_IS_RADARVIRTUEL_ENABLED",
            False,
            tags=[*_oat, "radar_virtuel"],
            frontend_names=["RV"],
        ),
        Env(
            "_ADSBIM_IS_ULTRAFEEDER_ENABLED",
            False,
            tags=[*_oat, "ultrafeeder"],
        ),
        Env("_ADSBIM_IS_AIRSPY_ENABLED", False, tags=["airspy", "enabled"]),
        Env("_ADSBIM_IS_PORTAINER_ENABLED", False, tags=["portainer", "enabled"]),
        Env("_ADSBIM_IS_BASE_CONFIG_FINISHED", False, tags=["base_config", "finished"]),
        Env(
            "_ADSBIM_IS_NIGHTLY_BASE_UPDATE_ENABLED",
            False,
            tags=["nightly_base_update", "enabled"],
        ),
        Env("_ADSBIM_IS_NIGHTLY_CONTAINER_UPDATE_ENABLED", False),
    }

    # helper function to find env by name
    def env(self, name: str):
        for e in self.env:
            if e.name == name:
                return e
        return None

    # helper function to find env by frontend name
    def env_by_frontend(self, name: str):
        for e in self.env:
            if name in e.frontend_names:
                return e
        return None

    # helper function to find env by tags
    def env_by_tags(self, tags: list):
        for e in self.env:
            if any(tag in e.tags for tag in tags):
                return e
        return None
