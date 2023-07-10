# dataclass

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .environment import Env
from .netconfig import NetConfig


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
            has_policy=True,
        ),
        "avdelphi": NetConfig(
            "adsb,data.avdelphi.com,24999,beast_reduce_plus_out",
            "",
            has_policy=True,
        ),
    }
    # Other aggregator tags
    _env = {
        # Mandatory!
        # Position
        Env("FEEDER_LAT", True, frontend_names=["lat"]),
        Env("FEEDER_LONG", True, frontend_names=["lng"]),
        Env("FEEDER_ALT_M", True, frontend_names=["alt"]),
        Env("FEEDER_TZ", True, frontend_names=["form_timezone"]),
        Env("MLAT_SITE_NAME", True, frontend_names=["mlat_name"]),
        # SDR
        Env("FEEDER_RTL_SDR", True, default="rtlsdr"),
        Env("FEEDER_ENABLE_BIASTEE", True, default="false"),
        Env("FEEDER_READSB_GAIN", True, default="autogain"),
        Env("FEEDER_SERIAL_1090", False, frontend_names=["1090"]),  # FIXME
        Env("FEEDER_978", False, frontend_names=["978"]),  # FIXME
        # Feeder
        Env("ADSBLOL_UUID", True, default_call=lambda: str(uuid4())),
        Env("ULTRAFEEDER_UUID", True, default_call=lambda: str(uuid4())),
        Env("MLAT_PRIVACY", True, default="--privacy", frontend_names=["mlat_privacy"]),
        Env("FEEDER_TAR1090_USEROUTEAPI", True, default="1"),
        # Misc
        Env(
            "FEEDER_HEYWHATSTHAT_ID", False, frontend_names=["FEEDER_HEYWHATSTHAT_ID"]
        ),  # FIXME
        # Other aggregators keys
        Env("FEEDER_FR24_SHARING_KEY", False, tags=["fr24", "key"]),
        Env("FEEDER_PIAWARE_FEEDER_ID", False, tags=["flightaware", "user"]),
        Env("FEEDER_RADARBOX_SHARING_KEY", False, tags=["radarbox24", "key"]),
        Env("FEEDER_PLANEFINDER_SHARECODE", False, tags=["planefinder", "key"]),
        Env("FEEDER_ADSBHUB_STATION_KEY", False, tags=["adsb_hub", "key"]),
        Env("FEEDER_OPENSKY_USERNAME", False, tags=["opensky", "user"]),
        Env("FEEDER_OPENSKY_SERIAL", False, tags=["opensky", "pass"]),
        Env("FEEDER_RV_FEEDER_KEY", False, tags=["radar_virtuel", "key"]),
        Env("FEEDER_PLANEWATCH_API_KEY", False, tags=["plane_watch", "key"]),
        # ADSB.im specific
        Env(
            "_ADSB_IM_AGGREGATORS_SELECTION",
            True,
            default="",
            frontend_names=["aggregators"],
        ),
        Env("_ADSBIM_VERSION", False, tags=["version"]),
        Env("_ADSBIM_VERSION_DATE", False),
        Env("_ADSBIM_VERSION_HASH", False),
        Env(
            "_ADSB_STATE_IS_SECURE_IMAGE",
            is_mandatory=False,
            default=False,
            tags=["secure_image", "is_enabled"]
        ),
        Env(
            "_ADSBIM_STATE_IS_FLIGHTRADAR24_ENABLED",
            False,
            tags=["other_aggregator", "is_enabled", "fr24"],
            frontend_names=["FR"],
        ),
        Env(
            "_ADSBIM_STATE_IS_PLANEWATCH_ENABLED",
            False,
            tags=["other_aggregator", "is_enabled", "plane_watch"],
            frontend_names=["PW"],
        ),
        Env(
            "_ADSBIM_STATE_IS_FLIGHTAWARE_ENABLED",
            False,
            tags=["other_aggregator", "is_enabled", "flightaware"],
            frontend_names=["FA"],
        ),
        Env(
            "_ADSBIM_STATE_IS_RADARBOX24_ENABLED",
            False,
            tags=["other_aggregator", "is_enabled", "radarbox24"],
            frontend_names=["RB"],
        ),
        Env(
            "_ADSBIM_STATE_IS_PLANEFINDER_ENABLED",
            False,
            tags=["other_aggregator", "is_enabled", "planefinder"],
            frontend_names=["PF"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ADSBHUB_ENABLED",
            False,
            tags=["other_aggregator", "is_enabled", "adsb_hub"],
            frontend_names=["AH"],
        ),
        Env(
            "_ADSBIM_STATE_IS_OPENSKY_ENABLED",
            False,
            tags=["other_aggregator", "is_enabled", "opensky"],
            frontend_names=["OS"],
        ),
        Env(
            "_ADSBIM_STATE_IS_RADARVIRTUEL_ENABLED",
            False,
            tags=["other_aggregator", "is_enabled", "radar_virtuel"],
            frontend_names=["RV"],
        ),
        Env("_ADSBIM_STATE_IS_AIRSPY_ENABLED", False, tags=["airspy", "enabled"]),
        Env("_ADSBIM_STATE_IS_PORTAINER_ENABLED", False, tags=["portainer", "enabled"]),
        Env(
            "_ADSBIM_STATE_IS_BASE_CONFIG_FINISHED",
            True,
            default="0",
            tags=["base_config", "finished"],
        ),
        Env(
            "_ADSBIM_STATE_IS_NIGHTLY_BASE_UPDATE_ENABLED",
            False,
            tags=["nightly_base_update", "is_enabled"],
        ),Env(
            "_ADSBIM_STATE_IS_NIGHTLY_FEEDER_UPDATE_ENABLED",
            False,
            tags=["nightly_feeder_update", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_NIGHTLY_CONTAINER_UPDATE_ENABLED",
            False,
            tags=["nightly_container_update", "is_enabled"]),
        )
        # Other aggregator images
        Env("_ADSBIM_CONTAINER_FR24", True, tags=["fr24", "container"]),
        Env("_ADSBIM_CONTAINER_FLIGHTAWARE", True, tags=["flightaware", "container"]),
        Env("_ADSBIM_CONTAINER_RADARBOX24", True, tags=["radarbox24", "container"]),
        Env("_ADSBIM_CONTAINER_PLANEFINDER", True, tags=["planefinder", "container"]),
        Env("_ADSBIM_CONTAINER_ADSBHUB", True, tags=["adsb_hub", "container"]),
        Env("_ADSBIM_CONTAINER_OPENSKY", True, tags=["opensky", "container"]),
        Env(
            "_ADSBIM_CONTAINER_RADARVIRTUEL", True, tags=["radar_virtuel", "container"]
        ),
        Env("_ADSBIM_CONTAINER_ULTRAFEEDER", True, tags=["ultrafeeder", "container"]),
        Env("_ADSBIM_CONTAINER_PLANEWATCH", True, tags=["plane_watch", "container"]),
        # Ultrafeeder config
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ADSBLOL_ENABLED",
            is_mandatory=False,
            tags=["adsblol", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_FLYITALYADSB_ENABLED",
            is_mandatory=False,
            tags=["flyitaly", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ADSBX_ENABLED",
            is_mandatory=False,
            tags=["adsbx", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_TAT_ENABLED",
            is_mandatory=False,
            tags=["tat", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_PS_ENABLED", False, tags=["ps", "ultrafeeder"]
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ADSBONE_ENABLED",
            is_mandatory=False,
            tags=["adsbone", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ADSBFI_ENABLED",
            is_mandatory=False,
            tags=["adsbfi", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_AVDELPHI_ENABLED",
            is_mandatory=False,
            tags=["avdelphi", "ultrafeeder", "is_enabled"],
        ),
    }

    @property
    def envs(self):
        return {e.name: e.value for e in self._env}

    # helper function to find env by name
    def env(self, name: str):
        for e in self._env:
            if e.name == name:
                return e
        return None

    # helper function to find env by frontend name
    def env_by_frontend(self, name: str):
        for e in self._env:
            if name in e.frontend_names:
                return e
        return None

    # helper function to find env by tags
    # Return only if there is one env with all the tags,
    # Raise error if there are more than one match
    def env_by_tags(self, tags: list):
        matches = []
        for e in self._env:
            if all(t in e.tags for t in tags):
                matches.append(e)
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise Exception("More than one match for tags")
        return matches[0]
