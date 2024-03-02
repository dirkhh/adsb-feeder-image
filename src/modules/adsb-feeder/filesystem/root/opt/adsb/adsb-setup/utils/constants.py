# dataclass
from dataclasses import dataclass
from os import getenv
from pathlib import Path
from uuid import uuid4

from .environment import Env, ENV_FILE_PATH, is_true
from .netconfig import NetConfig
from .util import print_err


@dataclass
class Constants:
    data_path = Path("/opt/adsb")
    config_path = data_path / "config"
    env_file_path = config_path / ".env"
    version_file = data_path / "adsb.im.version"
    is_feeder_image = True

    _proxy_routes = [
        # endpoint, port, url_path
        ["/map/", "TAR1090", "/"],
        ["/tar1090/", "TAR1090", "/"],
        ["/graphs1090/", "TAR1090", "/graphs1090/"],
        ["/graphs/", "TAR1090", "/graphs1090/"],
        ["/stats/", "TAR1090", "/graphs1090/"],
        ["/piaware/", "PIAWAREMAP", "/"],
        ["/fa/", "PIAWAREMAP", "/"],
        ["/flightaware/", "PIAWAREMAP", "/"],
        ["/piaware-stats/", "PIAWARESTAT", "/"],
        ["/pa-stats/", "PIAWARESTAT", "/"],
        ["/fa-stats/", "PIAWARESTAT", "/"],
        ["/fa-status/", "PIAWARESTAT", "/"],
        ["/fa-status.json/", "PIAWARESTAT", "/status.json"],
        ["/fr-status/", "FLIGHTRADAR", "/"],
        ["/fr/", "FLIGHTRADAR", "/"],
        ["/fr24/", "FLIGHTRADAR", "/"],
        ["/fr24-monitor.json", "FLIGHTRADAR", "/monitor.json"],
        ["/flightradar/", "FLIGHTRADAR", "/"],
        ["/flightradar24/", "FLIGHTRADAR", "/"],
        ["/planefinder/", "PLANEFINDER", "/"],
        ["/planefinder-stat/", "PLANEFINDER", "/stats.html"],
        ["/dump978/", "UAT978", "/skyaware978/"],
        ["/logs/", "DAZZLE", "/"],
        ["/dozzle/", "DAZZLE", "/"],
        ["/config/", "DAZZLE", "/setup"],
    ]

    @property
    def proxy_routes(self):
        ret = []
        for [endpoint, _env, path] in self._proxy_routes:
            env = "_ADSBIM_STATE_" + _env.upper() + "_PORT"
            ret.append([endpoint, self.env(env).value, path])
        return ret

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
        # "flyovr": NetConfig(
        #    "adsb,feed.flyovr.io,30004,beast_reduce_plus_out",
        #    "",
        #    has_policy=False,
        # ),
        "radarplane": NetConfig(
            "adsb,feed.radarplane.com,30001,beast_reduce_plus_out",
            "mlat,feed.radarplane.com,31090,39010",
            has_policy=True,
        ),
        "hpradar": NetConfig(
            "adsb,skyfeed.hpradar.com,30004,beast_reduce_plus_out",
            "mlat,skyfeed.hpradar.com,31090,39011",
            has_policy=False,
        ),
        "alive": NetConfig(
            "adsb,feed.airplanes.live,30004,beast_reduce_plus_out",
            "mlat,feed.airplanes.live,31090,39012",
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
        Env(
            "FEEDER_ENABLE_BIASTEE",
            default="False",
            tags=["biast", "is_enabled", "false_is_empty"],
        ),
        Env(
            "FEEDER_ENABLE_UATBIASTEE",
            default="False",
            tags=["uatbiast", "is_enabled", "false_is_empty"],
        ),
        Env("FEEDER_READSB_GAIN", default="autogain", tags=["gain"]),
        Env("FEEDER_AIRSPY_GAIN", default="auto", tags=["gain_airspy"]),
        Env("UAT_SDR_GAIN", default="autogain", tags=["uatgain"]),
        Env(
            "FEEDER_SERIAL_1090", is_mandatory=False, tags=["1090serial"]
        ),  # this is the SDR serial
        Env(
            "FEEDER_SERIAL_978", is_mandatory=False, tags=["978serial"]
        ),  # this is the SDR serial
        # Feeder
        Env(
            "FEEDER_ULTRAFEEDER_CONFIG", is_mandatory=True, tags=["ultrafeeder_config"]
        ),
        Env("ADSBLOL_UUID", default_call=lambda: str(uuid4()), tags=["adsblol_uuid"]),
        Env(
            "ULTRAFEEDER_UUID",
            default_call=lambda: str(uuid4()),
            tags=["ultrafeeder_uuid"],
        ),
        Env("MLAT_PRIVACY", default="True", tags=["mlat_privacy", "is_enabled"]),
        Env(
            "FEEDER_TAR1090_USEROUTEAPI",
            default="1",
            tags=["route_api", "is_enabled", "false_is_zero"],
        ),
        Env(  # this has no UI component, but we want to enable the advanced user to modify it in .env
            "TAR1090_RANGE_OUTLINE_DASH",
            default="[2,3]",
            tags=["range_outline_dash"],
        ),
        # 978
        Env(
            "FEEDER_ENABLE_UAT978", default="False", tags=["uat978", "is_enabled"]
        ),  # start the container
        Env(
            "FEEDER_URL_978", default="", tags=["978url"]
        ),  # add the URL to the dump978 map
        Env(
            "FEEDER_UAT978_HOST", default="", tags=["978host"]
        ),  # hostname ultrafeeder uses to get 978 data
        Env(
            "FEEDER_PIAWARE_UAT978", default="", tags=["978piaware"]
        ),  # magic setting for piaware to get 978 data
        # Misc
        Env(
            "_ADSBIM_HEYWHATSTHAT_ENABLED",
            is_mandatory=False,
            tags=["heywhatsthat", "is_enabled"],
        ),
        Env(
            "FEEDER_HEYWHATSTHAT_ID",
            is_mandatory=False,
            default="",
            tags=["heywhatsthat_id", "key"],
        ),
        # Other aggregators keys
        Env(
            "FEEDER_FR24_SHARING_KEY",
            is_mandatory=False,
            default="",
            tags=["flightradar", "key"],
        ),
        Env(
            "FEEDER_FR24_UAT_SHARING_KEY",
            is_mandatory=False,
            default="",
            tags=["flightradar_uat", "key"],
        ),
        Env(
            "FEEDER_PIAWARE_FEEDER_ID",
            is_mandatory=False,
            default="",
            tags=["flightaware", "key"],
        ),
        Env(
            "FEEDER_RADARBOX_SHARING_KEY",
            is_mandatory=False,
            default="",
            tags=["radarbox", "key"],
        ),
        Env(
            "FEEDER_RADARBOX_SN",
            is_mandatory=False,
            default="",
            tags=["radarbox", "sn"],
        ),
        Env(
            "FEEDER_RB_CPUINFO_HACK",
            is_mandatory=False,
            default="",
            tags=["rbcpuhack"],
        ),
        Env(
            "FEEDER_RB_THERMAL_HACK",
            is_mandatory=False,
            default="",
            tags=["rbthermalhack"],
        ),
        Env(
            "FEEDER_PLANEFINDER_SHARECODE",
            is_mandatory=False,
            default="",
            tags=["planefinder", "key"],
        ),
        Env(
            "FEEDER_ADSBHUB_STATION_KEY",
            is_mandatory=False,
            default="",
            tags=["adsbhub", "key"],
        ),
        Env(
            "FEEDER_OPENSKY_USERNAME",
            is_mandatory=False,
            default="",
            tags=["opensky", "user"],
        ),
        Env(
            "FEEDER_OPENSKY_SERIAL",
            is_mandatory=False,
            default="",
            tags=["opensky", "key"],
        ),
        Env(
            "FEEDER_RV_FEEDER_KEY",
            is_mandatory=False,
            default="",
            tags=["radarvirtuel", "key"],
        ),
        Env(
            "FEEDER_PLANEWATCH_API_KEY",
            is_mandatory=False,
            default="",
            tags=["planewatch", "key"],
        ),
        Env(
            "FEEDER_1090UK_API_KEY",
            is_mandatory=False,
            default="",
            tags=["1090uk", "key"],
        ),
        # ADSB.im specific
        Env("_ADSBIM_AGGREGATORS_SELECTION", tags=["aggregators"]),
        Env(
            "_ADSBIM_BASE_VERSION",
            is_mandatory=False,
            tags=["base_version", "norestore"],
        ),
        Env(
            "_ADSBIM_CONTAINER_VERSION",
            is_mandatory=False,
            tags=["container_version", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_BOARD_NAME",
            is_mandatory=False,
            tags=["board_name", "norestore"],
        ),
        Env("_ADSBIM_STATE_WEBPORT", default=80, tags=["webport"]),
        Env("_ADSBIM_STATE_DAZZLE_PORT", default=9999, tags=["dazzleport"]),
        Env("_ADSBIM_STATE_TAR1090_PORT", default=8080, tags=["tar1090port"]),
        Env("_ADSBIM_STATE_UAT978_PORT", default=9780, tags=["uatport"]),
        Env("_ADSBIM_STATE_PIAWAREMAP_PORT", default=8081, tags=["piamapport"]),
        Env("_ADSBIM_STATE_PIAWARESTAT_PORT", default=8082, tags=["piastatport"]),
        Env("_ADSBIM_STATE_FLIGHTRADAR_PORT", default=8754, tags=["frport"]),
        Env("_ADSBIM_STATE_PLANEFINDER_PORT", default=30053, tags=["pfport"]),
        Env("_ADSBIM_STATE_PACKAGE", tags=["pack", "norestore"]),
        Env(
            "_ADSBIM_STATE_IMAGE_NAME",
            # somehow I can't make a path relative to data_path work here...
            default_call=lambda: (
                Path("/opt/adsb/feeder-image.name").read_text()
                if Path("/opt/adsb/feeder-image.name").exists()
                else "ADS-B Feeder Image prior to v0.12"
            ),
            tags=["image_name", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_IS_SECURE_IMAGE",
            is_mandatory=False,
            default="False",
            tags=["secure_image", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_FLIGHTRADAR24_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "flightradar"],
        ),
        Env(
            "_ADSBIM_STATE_IS_PLANEWATCH_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "planewatch"],
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
            tags=["other_aggregator", "is_enabled", "adsbhub"],
        ),
        Env(
            "_ADSBIM_STATE_IS_OPENSKY_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "opensky"],
        ),
        Env(
            "_ADSBIM_STATE_IS_RADARVIRTUEL_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "radarvirtuel"],
        ),
        Env(
            "_ADSBIM_STATE_IS_1090UK_ENABLED",
            is_mandatory=False,
            tags=["other_aggregator", "is_enabled", "1090uk"],
        ),
        Env(
            "_ADSBIM_STATE_IS_AIRSPY_ENABLED",
            is_mandatory=False,
            tags=["airspy", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_DOZZLE_ENABLED",
            is_mandatory=False,
            default=True,
            tags=["dozzle", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_SSH_CONFIGURED",
            is_mandatory=False,
            tags=["ssh_configured", "is_enabled", "norestore"],
        ),
        Env(
            "_ADSB_STATE_SSH_KEY",
            is_mandatory=False,
            tags=["ssh_pub", "key", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_IS_BASE_CONFIG_FINISHED",
            default="0",
            is_mandatory=False,
            tags=["base_config", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_AGGREGATORS_CHOSEN",
            default=False,
            is_mandatory=False,
            tags=["aggregators_chosen"],
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
        Env(
            "_ADSBIM_STATE_TAILSCALE_LOGIN_LINK",
            is_mandatory=False,
            tags=["tailscale_ll"],
            default="",
        ),
        Env(
            "_ADSBIM_STATE_TAILSCALE_NAME",
            is_mandatory=False,
            tags=["tailscale_name"],
            default="",
        ),
        Env(
            "_ADSBIM_STATE_TAILSCALE_EXTRA_ARGS",
            is_mandatory=False,
            tags=["tailscale_extras"],
        ),
        # Container images
        # -- these names are magic and are used in yaml files and the structure
        #    of these names is used in scripting around that
        Env("ULTRAFEEDER_CONTAINER", tags=["ultrafeeder", "container"]),
        Env("FR24_CONTAINER", tags=["flightradar", "container"]),
        Env("FA_CONTAINER", tags=["flightaware", "container"]),
        Env("RB_CONTAINER", tags=["radarbox", "container"]),
        Env("PF_CONTAINER", tags=["planefinder", "container"]),
        Env("AH_CONTAINER", tags=["adsbhub", "container"]),
        Env("OS_CONTAINER", tags=["opensky", "container"]),
        Env("RV_CONTAINER", tags=["radarvirtuel", "container"]),
        Env("PW_CONTAINER", tags=["planewatch", "container"]),
        Env("TNUK_CONTAINER", tags=["1090uk", "container"]),
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
            "_ADSBIM_STATE_ADSBX_FEEDER_ID",
            is_mandatory=False,
            tags="adsbxfeederid",
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_TAT_ENABLED",
            is_mandatory=False,
            tags=["tat", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_PLANESPOTTERS_ENABLED",
            is_mandatory=False,
            tags=["planespotters", "ultrafeeder", "is_enabled"],
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
        # Env(
        #    "_ADSBIM_STATE_IS_ULTRAFEEDER_FLYOVR_ENABLED",
        #    is_mandatory=False,
        #    tags=["flyovr", "ultrafeeder", "is_enabled"],
        # ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_RADARPLANE_ENABLED",
            is_mandatory=False,
            tags=["radarplane", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_HPRADAR_ENABLED",
            is_mandatory=False,
            tags=["hpradar", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ALIVE_ENABLED",
            is_mandatory=False,
            tags=["alive", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_ULTRAFEEDER_EXTRA_ARGS",
            is_mandatory=False,
            tags=["ultrafeeder_extra_args"],
        ),
        Env(
            "_ADSBIM_STATE_REMOTE_SDR",
            is_mandatory=False,
            tags=["remote_sdr"],
        ),
        Env(
            "_ADSBIM_STATE_LAST_DNS_CHECK",
            is_mandatory=False,
            tags=["dns_state", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_FEEDER_IP",
            is_mandatory=False,
            tags=["feeder_ip", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_UNDER_VOLTAGE",
            is_mandatory=False,
            tags=["under_voltage", "norestore"],
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
            raise Exception(
                f"env_by_tags called with invalid argument {_tags} of type {type(_tags)}"
            )
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
        return e and e.value

    # helper function to get everything that needs to be written out written out
    def update_env(self):
        print_err("writing back .env file to persist settings")
        env_vars = {}
        with open(ENV_FILE_PATH, "r") as env_file:
            for line in env_file.readlines():
                if line.strip().startswith("#"):
                    continue
                key, var = line.partition("=")[::2]
                env_vars[key.strip()] = var.strip()
                # print_err(f"found {key.strip()} -> {var.strip()} in .env file")
            for e in self._env:
                if any(t == "false_is_zero" for t in e.tags):
                    env_vars[e.name] = "1" if is_true(e.value) else "0"
                elif any(t == "false_is_empty" for t in e.tags):
                    env_vars[e.name] = "True" if is_true(e.value) else ""
                else:
                    env_vars[e.name] = e.value

        with open(ENV_FILE_PATH, "w") as env_file:
            for key, value in env_vars.items():
                if key:
                    env_file.write(f"{key}={value}\n")

    # make sure our internal data is in sync with the .env file on disk
    def re_read_env(self):
        env_vars = {}
        with open(ENV_FILE_PATH, "r") as env_file:
            for line in env_file.readlines():
                if line.strip().startswith("#"):
                    continue
                key, var = line.partition("=")[::2]
                env_vars[key.strip()] = var.strip()
        # now that we have completed reading them, update each of the Env objects
        for e in self._env:
            if e.name in env_vars:
                e.value = env_vars[e.name]
