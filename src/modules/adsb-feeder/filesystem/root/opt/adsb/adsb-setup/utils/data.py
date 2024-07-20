# dataclass
from dataclasses import dataclass
from pathlib import Path

from .environment import Env
from .netconfig import NetConfig
from .util import is_true, print_err
from utils.config import read_values_from_env_file


@dataclass
class Data:
    def __new__(cc):
        if not hasattr(cc, "instance"):
            cc.instance = super(Data, cc).__new__(cc)
        return cc.instance

    data_path = Path("/opt/adsb")
    config_path = data_path / "config"
    env_file_path = config_path / ".env"
    version_file = data_path / "adsb.im.version"
    secure_image_path = data_path / "adsb.im.secure_image"
    is_feeder_image = True
    settings = None
    _env_by_tags_dict = dict()
    ultrafeeder = []

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
        ["/dozzle/<sub_path>", "DAZZLE", "/"],
        ["/config/", "DAZZLE", "/setup"],
    ]

    @property
    def proxy_routes(self):
        ret = []
        for [endpoint, _env, path] in self._proxy_routes:
            env = "AF_" + _env.upper() + "_PORT"
            port = self.env(env).value
            ret.append([endpoint, port, path])
            if endpoint in [
                "/fr24-monitor.json",
                "/fa-status.json/",
                "/planefinder-stat/",
                "/fa-status/",
                "/fr24/",
            ]:
                # inc_port is the id of the stage2 microfeeder
                # example endpoint: '/fa-status.json_<int:inc_port>/'
                # this is passed to the URL handling function in flask.py
                # this function will add (inc_port * 1000) to the port
                if endpoint[-1] == "/":
                    ret.append([endpoint[:-1] + f"_<int:inc_port>/", port, path])
                else:
                    ret.append([endpoint + f"_<int:inc_port>", port, path])
            if endpoint in [
                "/map/",
                "/stats/",
            ]:
                # idx is the id of the stage2 microfeeder
                # example endpoint: '/map_<int:idx>/'
                # this is passed to the URL handling function in flask.py
                # this function will insert /idx into the URL after the domain
                if endpoint[-1] == "/":
                    ret.append([endpoint[:-1] + f"_<int:idx>/", port, path])
                else:
                    ret.append([endpoint + f"_<int:idx>", port, path])
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
    # we have four different types of "feeders":
    # 1. integrated feeders (single SBC where one Ultrafeeder collects from SDR and send to aggregator)
    # 2. micro feeders (SBC with SDR(s) attached, talking to a stage2 micro proxy)
    # 3. stage2 micro proxies (run on the stage2 system, each talking to a micro feeder and to aggregators)
    # 4. stage2 aggregator (showing a combined map of the micro feeders)
    # most feeder related values are lists with element 0 being used either for an
    # integrated feeder, a micro feeder, or the aggregator in a stage2 setup, and
    # elements 1 .. num_micro_sites are used for the micro-proxy instances
    _env = {
        # Mandatory site data
        Env("FEEDER_LAT", default=[""], is_mandatory=True, tags=["lat"]),
        Env("FEEDER_LONG", default=[""], is_mandatory=True, tags=["lon"]),
        Env("FEEDER_ALT_M", default=[""], is_mandatory=True, tags=["alt"]),
        Env("FEEDER_TZ", default=[""], is_mandatory=True, tags=["tz"]),
        Env("MLAT_SITE_NAME", default=[""], is_mandatory=True, tags=["site_name"]),
        #
        # SDR settings are only valid on an integrated feeder or a micro feeder, not on stage2
        # misnomer, FEEDER_RTL_SDR is used as follows: READSB_DEVICE_TYPE=${FEEDER_RTL_SDR}
        Env("FEEDER_RTL_SDR", default="rtlsdr", tags=["readsb_device_type"]),
        Env(
            "FEEDER_ENABLE_BIASTEE",
            default=False,
            tags=["biast", "is_enabled", "false_is_empty"],
        ),
        Env(
            "FEEDER_ENABLE_UATBIASTEE",
            default=False,
            tags=["uatbiast", "is_enabled", "false_is_empty"],
        ),
        Env("FEEDER_READSB_GAIN", default="autogain", tags=["gain"]),
        Env("FEEDER_AIRSPY_GAIN", default="auto", tags=["gain_airspy"]),
        Env("UAT_SDR_GAIN", default="autogain", tags=["uatgain"]),
        Env("FEEDER_SERIAL_1090", tags=["1090serial"]),
        Env("FEEDER_SERIAL_978", tags=["978serial"]),
        Env("FEEDER_UAT_DEVICE_TYPE", default="rtlsdr", tags=["uat_device_type"]),
        Env("FEEDER_UNUSED_SERIAL_0", tags=["other-0"]),
        Env("FEEDER_UNUSED_SERIAL_1", tags=["other-1"]),
        Env("FEEDER_UNUSED_SERIAL_2", tags=["other-2"]),
        Env("FEEDER_UNUSED_SERIAL_3", tags=["other-3"]),
        Env("READSB_NET_BR_OPTIMIZE_FOR_MLAT", tags=["beast-reduce-optimize-for-mlat"]),
        Env("FEEDER_MAX_RANGE", default=[300], tags=["max_range"]),
        Env("FEEDER_USE_GPSD", default=False, tags=["use_gpsd", "is_enabled"]),
        Env("_ADSBIM_FEEDER_HAS_GPSD", default=False, tags=["has_gpsd", "is_enabled"]),
        Env("_ADSBIM_STATE_TEMPERATURE_BLOCK", default=False, tags=["temperature_block", "is_enabled"]),
        #
        # Ultrafeeder config, used for all 4 types of Ultrafeeder instances
        Env("FEEDER_ULTRAFEEDER_CONFIG", default=[""], tags=["ultrafeeder_config"]),
        Env("ADSBLOL_UUID", default=[""], tags=["adsblol_uuid"]),
        Env("ADSBLOL_LINK", default=[""], tags=["adsblol_link"]),
        Env("ULTRAFEEDER_UUID", default=[""], tags=["ultrafeeder_uuid"]),
        Env("MLAT_PRIVACY", default=[False], tags=["mlat_privacy", "is_enabled"]),
        Env(
            "FEEDER_TAR1090_USEROUTEAPI",
            default=[True],
            tags=["route_api", "is_enabled", "false_is_zero"],
        ),
        Env(
            "FEEDER_TAR1090_CONFIGJS_APPEND",
            default="",
            tags=["tar1090_configjs_append"],
        ),
        Env(
            "FEEDER_TAR1090_IMAGE_CONFIG_LINK",
            default="http://HOSTNAME:80/",
            tags=["tar1090_image_config_link"],
        ),
        Env(  # this has no UI component, but we want to enable the advanced user to modify it in .env
            "TAR1090_RANGE_OUTLINE_DASH",
            default="[2,3]",
            tags=["range_outline_dash"],
        ),
        Env("_ASDBIM_TAR1090_QUERY_PARAMS", default="", tags=["tar1090_query_params"]),
        # 978
        # start the container (integrated / micro) or the replay
        Env("FEEDER_ENABLE_UAT978", default=[False], tags=["uat978", "is_enabled"]),
        Env(
            "FEEDER_UAT_REPLAY978",
            default=[""],
            tags=["replay978"],
        ),
        # hostname ultrafeeder uses to get 978 data
        Env("FEEDER_UAT978_HOST", default=[""], tags=["978host"]),
        Env("FEEDER_RB_UAT978_HOST", default=[""], tags=["rb978host"]),
        # add the URL to the dump978 map
        Env("FEEDER_URL_978", default=[""], tags=["978url"]),
        # URL to get Airspy stats (used in stage2)
        Env("FEEDER_URL_AIRSPY", default=[""], tags=["airspyurl"]),
        # port for Airspy stats (used in micro feeder and handed to stage2 via base_info)
        Env("FEEDER_AIRSPY_PORT", default=8070, tags=["airspyport"]),
        # URL to get remote 1090 stats data (for gain, %-age of strong signals, and signal graph)
        Env("FEEDER_URL_RTLSDR", default=[""], tags=["rtlsdrurl"]),
        # magic setting for piaware to get 978 data
        Env("FEEDER_PIAWARE_UAT978", default=[""], tags=["978piaware"]),
        # Misc
        Env(
            "_ADSBIM_HEYWHATSTHAT_ENABLED",
            default=[False],
            tags=["heywhatsthat", "is_enabled"],
        ),
        Env(
            "FEEDER_HEYWHATSTHAT_ID",
            default=[""],
            tags=["heywhatsthat_id", "key"],
        ),
        # Other aggregators keys
        Env(
            "FEEDER_FR24_SHARING_KEY",
            default=[""],
            tags=["flightradar", "key"],
        ),
        Env(
            "FEEDER_FR24_UAT_SHARING_KEY",
            default=[""],
            tags=["flightradar_uat", "key"],
        ),
        Env(
            "FEEDER_PIAWARE_FEEDER_ID",
            default=[""],
            tags=["flightaware", "key"],
        ),
        Env(
            "FEEDER_RADARBOX_SHARING_KEY",
            default=[""],
            tags=["radarbox", "key"],
        ),
        Env(
            "FEEDER_RADARBOX_SN",
            default=[""],
            tags=["radarbox", "sn"],
        ),
        Env(
            "FEEDER_RB_THERMAL_HACK",
            is_mandatory=False,
            default="",
            tags=["rbthermalhack"],
        ),
        Env(
            "FEEDER_PLANEFINDER_SHARECODE",
            default=[""],
            tags=["planefinder", "key"],
        ),
        Env(
            "FEEDER_ADSBHUB_STATION_KEY",
            default=[""],
            tags=["adsbhub", "key"],
        ),
        Env(
            "FEEDER_OPENSKY_USERNAME",
            default=[""],
            tags=["opensky", "user"],
        ),
        Env(
            "FEEDER_OPENSKY_SERIAL",
            default=[""],
            tags=["opensky", "key"],
        ),
        Env(
            "FEEDER_RV_FEEDER_KEY",
            default=[""],
            tags=["radarvirtuel", "key"],
        ),
        Env(
            "FEEDER_PLANEWATCH_API_KEY",
            default=[""],
            tags=["planewatch", "key"],
        ),
        Env(
            "FEEDER_1090UK_API_KEY",
            default=[""],
            tags=["1090uk", "key"],
        ),
        # ADSB.im specific
        Env("_ADSBIM_AGGREGATORS_SELECTION", tags=["aggregator_choice"]),
        Env(
            "_ADSBIM_BASE_VERSION",
            default="",
            tags=["base_version", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_BOARD_NAME",
            tags=["board_name", "norestore"],
        ),
        # ports used by our proxy system
        Env("AF_WEBPORT", default=80, tags=["webport", "norestore"]),
        Env("AF_DAZZLE_PORT", default=9999, tags=["dazzleport", "norestore"]),
        Env("AF_TAR1090_PORT", default=8080, tags=["tar1090port", "norestore"]),
        Env("AF_TAR1090_PORT_ADJUSTED", default=8080, tags=["tar1090portadjusted"]),
        Env("AF_UAT978_PORT", default=9780, tags=["uatport", "norestore"]),
        Env("AF_PIAWAREMAP_PORT", default=8081, tags=["piamapport", "norestore"]),
        Env("AF_PIAWARESTAT_PORT", default=8082, tags=["piastatport", "norestore"]),
        Env("AF_FLIGHTRADAR_PORT", default=8754, tags=["frport"]),
        Env("AF_PLANEFINDER_PORT", default=30053, tags=["pfport"]),
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
        # legacy secure image state, now handled via separate file
        # keep it around to handle updates from before the changeover
        # and easy checks in webinterface
        Env(
            "AF_IS_SECURE_IMAGE",
            default=False,
            tags=["secure_image", "is_enabled", "norestore"],
        ),
        Env(
            "AF_APP_INIT_DONE",
            default=False,
            tags=["app_init_done", "is_enabled", "norestore"],
        ),
        Env(
            "AF_IS_FLIGHTRADAR24_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "flightradar"],
        ),
        Env(
            "AF_IS_PLANEWATCH_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "planewatch"],
        ),
        Env(
            "AF_IS_FLIGHTAWARE_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "flightaware"],
        ),
        Env(
            "AF_IS_RADARBOX_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "radarbox"],
        ),
        Env(
            "AF_IS_PLANEFINDER_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "planefinder"],
        ),
        Env(
            "AF_IS_ADSBHUB_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "adsbhub"],
        ),
        Env(
            "AF_IS_OPENSKY_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "opensky"],
        ),
        Env(
            "AF_IS_RADARVIRTUEL_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "radarvirtuel"],
        ),
        Env(
            "AF_IS_1090UK_ENABLED",
            default=[False],
            tags=["other_aggregator", "is_enabled", "1090uk"],
        ),
        Env(
            "AF_IS_AIRSPY_ENABLED",
            tags=["airspy", "is_enabled"],
        ),
        Env(
            "AF_IS_SDRPLAY_ENABLED",
            tags=["sdrplay", "is_enabled"],
        ),
        Env(
            "AF_IS_SDRPLAY_LICENSE_ACCEPTED",
            tags=["sdrplay_license_accepted", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_SSH_CONFIGURED",
            tags=["ssh_configured", "is_enabled", "norestore"],
        ),
        Env(
            "_ADSB_STATE_SSH_KEY",
            tags=["ssh_pub", "key", "norestore"],
        ),
        Env(
            "AF_IS_BASE_CONFIG_FINISHED",
            default=False,
            tags=["base_config", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_AGGREGATORS_CHOSEN",
            default=False,
            tags=["aggregators_chosen"],
        ),
        Env(
            "AF_IS_NIGHTLY_BASE_UPDATE_ENABLED",
            tags=["nightly_base_update", "is_enabled"],
        ),
        Env(
            "AF_IS_NIGHTLY_FEEDER_UPDATE_ENABLED",
            tags=["nightly_feeder_update", "is_enabled"],
        ),
        Env(
            "AF_IS_NIGHTLY_CONTAINER_UPDATE_ENABLED",
            tags=["nightly_container_update", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_ZEROTIER_KEY",
            tags=["zerotierid", "key"],
        ),
        Env(
            "_ADSBIM_STATE_TAILSCALE_LOGIN_LINK",
            tags=["tailscale_ll"],
            default="",
        ),
        Env(
            "_ADSBIM_STATE_TAILSCALE_NAME",
            tags=["tailscale_name"],
            default="",
        ),
        Env(
            "_ADSBIM_STATE_TAILSCALE_EXTRA_ARGS",
            tags=["tailscale_extras"],
        ),
        Env(
            "_ADSBIM_STATE_EXTRA_ENV",
            tags=["ultrafeeder_extra_env"],
        ),
        # Ultrafeeder config
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ADSBLOL_ENABLED",
            default=[False],
            tags=["adsblol", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_FLYITALYADSB_ENABLED",
            default=[False],
            tags=["flyitaly", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ADSBX_ENABLED",
            default=[False],
            tags=["adsbx", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_ADSBX_FEEDER_ID",
            default=[""],
            tags="adsbxfeederid",
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_TAT_ENABLED",
            default=[False],
            tags=["tat", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_PLANESPOTTERS_ENABLED",
            default=[False],
            tags=["planespotters", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ADSBFI_ENABLED",
            default=[False],
            tags=["adsbfi", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_AVDELPHI_ENABLED",
            default=[False],
            tags=["avdelphi", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_RADARPLANE_ENABLED",
            default=[False],
            tags=["radarplane", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_HPRADAR_ENABLED",
            default=[False],
            tags=["hpradar", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_IS_ULTRAFEEDER_ALIVE_ENABLED",
            default=[False],
            tags=["alive", "ultrafeeder", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_ULTRAFEEDER_EXTRA_ARGS",
            tags=["ultrafeeder_extra_args"],
        ),
        Env(
            "FEEDER_TAR1090_ENABLE_AC_DB",
            default=True,
            tags=["tar1090_ac_db", "is_enabled"],
        ),
        Env(
            "FEEDER_MLATHUB_DISABLE",
            default=False,
            tags=["mlathub_disable", "is_enabled"],
        ),
        Env(
            "_ADSBIM_STATE_REMOTE_SDR",
            tags=["remote_sdr"],
        ),
        Env(
            "_ADSBIM_STATE_LAST_DNS_CHECK",
            tags=["dns_state", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_FEEDER_IP",
            tags=["feeder_ip", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_UNDER_VOLTAGE",
            tags=["under_voltage", "norestore"],
        ),
        Env(
            "_ADSBIM_STATE_LOW_DISK",
            tags=["low_disk", "norestore"],
        ),
        Env(
            "AF_IS_STAGE2",
            default=False,
            tags=["stage2", "is_enabled"],
        ),
        Env(
            "AF_NUM_MICRO_SITES",
            default=0,
            tags=["num_micro_sites"],
        ),
        Env(  # list with two elements, first is the IP, second the tm it was last accessed
            "_ADSBIM_STATE_LAST_STAGE2_CONTACT",
            default=[""],
            tags=["last_stage2_contact"],
        ),
        Env("AF_MICRO_IP", default=[""], tags=["mf_ip"]),
        Env("AF_MICRO_PORT", default=[""], tags=["mf_port"]),
        Env("AF_MICRO_BROFM", default=[False], tags=["mf_brofm", "is_enabled"]),
        Env(
            "AF_MICRO_BROFM_CAPABLE",
            default=[False],
            tags=["mf_brofm_capable", "is_enabled"],
        ),
        Env("AF_FEEDER_VERSION", default=[""], tags=["mf_version"]),
    }

    # Container images
    # -- these names are magic and are used in yaml files and the structure
    #    of these names is used in scripting around that
    # the version of the adsb-setup app and the containers are linked and
    # there are subtle dependencies between them - so let's not include these
    # in backup/restore

    tag_for_name = {
        "ULTRAFEEDER_CONTAINER": "ultrafeeder",
        "FR24_CONTAINER": "flightradar",
        "FA_CONTAINER": "flightaware",
        "RB_CONTAINER": "radarbox",
        "PF_CONTAINER": "planefinder",
        "AH_CONTAINER": "adsbhub",
        "OS_CONTAINER": "opensky",
        "RV_CONTAINER": "radarvirtuel",
        "PW_CONTAINER": "planewatch",
        "TNUK_CONTAINER": "1090uk",
    }
    with open(data_path / "docker.image.versions", "r") as file:
        for line in file:
            if line.startswith("#"):
                continue
            items = line.replace("\n", "").split("=")
            if len(items) != 2:
                print_err(f"docker.image.versions check line: {line}")
                continue
            key = items[0]
            value = items[1]
            entry = Env(key, tags=[tag_for_name.get(key, key), "container", "norestore"])
            entry.value = value  # always use value from docker.image.versions as definitive source
            _env.add(entry)  # add to _env set

    @property
    def envs_for_envfile(self):

        # read old values from env file so we can debug print only those that have changed
        old_values = read_values_from_env_file()

        def adjust_bool_impl(e, value):
            if "false_is_zero" in e.tags:
                return "1" if is_true(value) else "0"
            if "false_is_empty" in e.tags:
                return "1" if is_true(value) else ""
            return is_true(value)

        def adjust_bool(e, value):
            v = adjust_bool_impl(e, value)
            print_err(f"adjust_bool({e}, {e.tags}) = {v}", level=8)
            return v

        def adjust_heywhatsthat(value):
            enabled = self.env_by_tags(["heywhatsthat", "is_enabled"])._value
            new_value = []
            for i in range(len(value)):
                new_value.append(value[i] if enabled[i] else "")
            return new_value

        ret = {}
        for e in self._env:

            def printChanged(descriptor, envKey, newValue, oldValue):
                # omit state vars as they are never in the env file so we don't know if they changed
                oldValue = str(oldValue)
                newValue = str(newValue)
                if oldValue != newValue and not envKey.startswith("_ADSBIM_STATE"):
                    emptyStringPrint = "''"
                    print_err(
                        f"{descriptor}: {envKey} = {emptyStringPrint if newValue == '' else newValue}",
                        level=2,
                    )

            if type(e._value) == list:
                if e._name == "FEEDER_HEYWHATSTHAT_ID":
                    actual_value = adjust_heywhatsthat(e._value)
                else:
                    actual_value = e._value
                for i in range(len(actual_value)):
                    suffix = "" if i == 0 else f"_{i}"
                    value = actual_value[i]
                    envKey = e._name + suffix
                    newValue = adjust_bool(e, value) if type(value) == bool or "is_enabled" in e.tags else value
                    ret[envKey] = newValue

                    oldValue = old_values.get(envKey)
                    printChanged("ENV_FILE LIST", envKey, newValue, oldValue)

            else:
                envKey = e._name
                newValue = adjust_bool(e, e._value) if type(e._value) == bool else e._value
                ret[envKey] = newValue

                oldValue = old_values.get(envKey)
                printChanged("ENV_FILE OTHR", envKey, newValue, oldValue)

        # add convenience values
        # fmt: off
        ret["AF_FALSE_ON_STAGE2"] = "false" if self.is_enabled(["stage2"]) else "true"
        if self.is_enabled(["stage2"]):
            for i in range(1, self.env_by_tags("num_micro_sites").value + 1):
                ret[f"AF_TAR1090_PORT_{i}"] = int(ret[f"AF_TAR1090_PORT"]) + i * 1000
                ret[f"AF_PIAWAREMAP_PORT_{i}"] = int(ret[f"AF_PIAWAREMAP_PORT"]) + i * 1000
                ret[f"AF_PIAWARESTAT_PORT_{i}"] = int(ret[f"AF_PIAWARESTAT_PORT"]) + i * 1000
                ret[f"AF_FLIGHTRADAR_PORT_{i}"] = int(ret[f"AF_FLIGHTRADAR_PORT"]) + i * 1000
                ret[f"AF_PLANEFINDER_PORT_{i}"] = int(ret[f"AF_PLANEFINDER_PORT"]) + i * 1000
                site_name = self.env_by_tags("site_name").list_get(i)
                ret[f"GRAPHS1090_WWW_TITLE_{i}"] = f"{site_name} graphs1090 stats"
                ret[f"GRAPHS1090_WWW_HEADER_{i}"] = f"Performance Graphs: {site_name}"
        return ret
        # fmt: on

    @property
    def envs(self):
        return {e.name: e._value for e in self._env}

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
        if not tags:
            return None

        # make the list a tuple so it's hashable
        tags = tuple(tags)
        cached = self._env_by_tags_dict.get(tags)
        if cached:
            return cached

        matches = []
        for e in self._env:
            if not e.tags:
                print_err(f"{e} has no tags")
            if all(t in e.tags for t in tags):
                matches.append(e)
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            print_err(f"More than one match for tags {tags}")
            for e in matches:
                print_err(f"  {e}")

        self._env_by_tags_dict[tags] = matches[0]
        return matches[0]

    def _get_enabled_env_by_tags(self, tags):
        # we append is_enabled to tags
        tags.append("is_enabled")
        # stack_info(f"taglist {tags} gets us env {self.env_by_tags(tags)}")
        return self.env_by_tags(tags)

    # helper function to see if something is enabled
    def is_enabled(self, tags):
        if type(tags) != list:
            tags = [tags]
        e = self._get_enabled_env_by_tags(tags)
        if type(e._value) == list:
            ret = e and is_true(e.list_get(0))
            print_err(f"is_enabled called on list: {e}[0] = {ret}")
            return ret
        return e and is_true(e._value)

    # helper function to see if list element is enabled
    def list_is_enabled(self, tags, idx):
        if type(tags) != list:
            tags = [tags]
        e = self._get_enabled_env_by_tags(tags)
        ret = is_true(e.list_get(idx)) if e else False
        print_err(f"list_is_enabled: {e}[{idx}] = {ret}", level=8)
        return ret
