# dataclass
import sys

from dataclasses import dataclass
from os import name
from pathlib import Path
from uuid import uuid4

from .environment import Env
from .netconfig import NetConfig


def print_err(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


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
        "planespotters": NetConfig(
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
        Env("FEEDER_LAT", tags=["lat"]),
        Env("FEEDER_LONG", tags=["lng"]),
        Env("FEEDER_ALT_M", tags=["alt"]),
        Env("FEEDER_TZ", tags=["form_timezone"]),
        Env("MLAT_SITE_NAME", tags=["mlat_name"]),
        # SDR
        Env("FEEDER_RTL_SDR", default="rtlsdr", tags=["rtlsdr"]),
        Env("FEEDER_ENABLE_BIASTEE", default="false", tags=["biast", "is_enabled"]),
        Env("FEEDER_READSB_GAIN", default="autogain", tags=["autogain", "is_enabled"]),
        Env("FEEDER_SERIAL_1090", is_mandatory=False, tags=["1090"]),  # FIXME
        Env("FEEDER_978", is_mandatory=False, tags=["978"]),  # FIXME
        # Feeder
        Env("ADSBLOL_UUID", default_call=lambda: str(uuid4()), tags=["adsblol_uuid"]),
        Env(
            "ULTRAFEEDER_UUID",
            default_call=lambda: str(uuid4()),
            tags=["ultrafeeder_uuid"],
        ),
        Env("MLAT_PRIVACY", default="--privacy", tags=["mlat_privacy", "is_enabled"]),
        Env(
            "FEEDER_TAR1090_USEROUTEAPI",
            default="true",
            tags=["route_api", "is_enabled"],
        ),
        # Misc
        Env(
            "_ADSBIM_HEYWHATSTHAT_ENABLED",
            is_mandatory=False,
            tags=["heywhatsthat", "is_enabled"],
        ),
        Env(
            "FEEDER_HEYWHATSTHAT_ID",
            is_mandatory=False,
            tags=["heywhatsthat_id", "key"],
        ),
        # Other aggregators keys
        Env("FEEDER_FR24_SHARING_KEY", is_mandatory=False, tags=["fr24", "key"]),
        Env(
            "FEEDER_PIAWARE_FEEDER_ID", is_mandatory=False, tags=["flightaware", "user"]
        ),
        Env(
            "FEEDER_RADARBOX_SHARING_KEY",
            is_mandatory=False,
            tags=["radarbox", "key"],
        ),
        Env(
            "FEEDER_PLANEFINDER_SHARECODE",
            is_mandatory=False,
            tags=["planefinder", "key"],
        ),
        Env("FEEDER_ADSBHUB_STATION_KEY", is_mandatory=False, tags=["adsb_hub", "key"]),
        Env("FEEDER_OPENSKY_USERNAME", is_mandatory=False, tags=["opensky", "user"]),
        Env("FEEDER_OPENSKY_SERIAL", is_mandatory=False, tags=["opensky", "pass"]),
        Env("FEEDER_RV_FEEDER_KEY", is_mandatory=False, tags=["radar_virtuel", "key"]),
        Env(
            "FEEDER_PLANEWATCH_API_KEY", is_mandatory=False, tags=["plane_watch", "key"]
        ),
        # ADSB.im specific
        Env("_ADSBIM_AGGREGATORS_SELECTION", tags=["aggregators"]),
        Env("_ADSBIM_BASE_VERSION", is_mandatory=False, tags=["base_version"]),
        Env(
            "_ADSBIM_CONTAINER_VERSION", is_mandatory=False, tags=["container_version"]
        ),
        Env(
            "_ADSBIM_STATE_IS_SECURE_IMAGE",
            is_mandatory=False,
            default="false",
            tags=["secure_image", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_FLIGHTRADAR24_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "fr24"],
        ),
        Env(
            "_ADSBIM_STATE_IS_PLANEWATCH_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "plane_watch"],
        ),
        Env(
            "_ADSBIM_STATE_IS_FLIGHTAWARE_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "flightaware"],
        ),
        Env(
            "_ADSBIM_STATE_IS_RADARBOX_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "radarbox"],
        ),
        Env(
            "_ADSBIM_STATE_IS_PLANEFINDER_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "planefinder"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ADSBHUB_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "adsb_hub"],
        ),
        Env(
            "_ADSBIM_STATE_IS_OPENSKY_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "opensky"],
        ),
        Env(
            "_ADSBIM_STATE_IS_RADARVIRTUEL_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "radar_virtuel"],
        ),
        Env(
            "_ADSBIM_STATE_IS_AIRSPY_ENABLED",
            is_mandatory=False,
            tags=["airspy", "enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_PORTAINER_ENABLED",
            is_mandatory=False,
            tags=["portainer", "enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_SSH_CONFIGURED",
            is_mandatory=False,
            tags=["ssh_configured", "is_enabled"],
        ),
        Env("_ADSB_STATE_SSH_KEY", is_mandatory=False, tags=["ssh_pub", "key"]),
        Env(
            "_ADSBIM_STATE_IS_BASE_CONFIG_FINISHED",
            default="0",
            tags=["base_config", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_NIGHTLY_BASE_UPDATE_ENABLED",
            is_mandatory=False,
            tags=["nightly_base_update", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_NIGHTLY_FEEDER_UPDATE_ENABLED",
            is_mandatory=False,
            tags=["nightly_feeder_update", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_NIGHTLY_CONTAINER_UPDATE_ENABLED",
            is_mandatory=False,
            tags=["nightly_container_update", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_ZEROTIER_KEY",
            is_mandatory=False,
            tags=["zerotierid", "key"],
        ),
        # Container images
        # -- these names are magic and are used in yaml files and the structure
        #    of these names is used in scripting around that
        Env("ULTRAFEEDER_CONTAINER", tags=["ultrafeeder", "container"]),
        Env("FR24_CONTAINER", tags=["fr24", "container"]),
        Env("FA_CONTAINER", tags=["flightaware", "container"]),
        Env("RB_CONTAINER", tags=["radarbox", "container"]),
        Env("PF_CONTAINER", tags=["planefinder", "container"]),
        Env("AH_CONTAINER", tags=["adsb_hub", "container"]),
        Env("OS_CONTAINER", tags=["opensky", "container"]),
        Env("RV_CONTAINER", tags=["radar_virtuel", "container"]),
        Env("PW_CONTAINER", tags=["plane_watch", "container"]),
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
            "_ADSBIM_STATE_IS_ULTRAFEEDER_PS_ENABLED",
            is_mandatory=False,
            tags=["ps", "ultrafeeder"],
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

    # helper function to find env by tags
    # Return only if there is one env with all the tags,
    # Raise error if there are more than one match
    def env_by_tags(self, _tags):
        if type(_tags) == str:
            tags = [_tags]
        elif type(_tags) == list:
            tags = _tags
        else:
            raise Exception(f"env_by_tags called with invalid argument {_tags} of type {type(_tags)}")
        matches = []
        if not tags:
            return None
        for e in self._env:
            if not e.tags:
                print_err(f"{e} has no tags")
            if all(t in e.tags for t in tags):
                matches.append(e)
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise Exception("More than one match for tags")
        return matches[0]

    # helper function to see if something is enabled
    def is_enabled(self, *tags):
        # we append is_enabled to tags
        taglist = list(tags)
        taglist.append("is_enabled")
        e = self.env_by_tags(taglist)
        print_err(f"is_enabled called for {tags} -> {e}")
        return e and any({e.value == "1", e.value == "true", e.value == "on"})
