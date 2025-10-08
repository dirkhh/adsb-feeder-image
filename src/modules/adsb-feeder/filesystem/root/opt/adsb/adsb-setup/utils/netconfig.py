from uuid import uuid4
from utils.util import is_true, print_err, mf_get_ip_and_triplet


class NetConfig:
    def __init__(self, adsb_config: str, mlat_config: str, has_policy: bool):
        self.adsb_config = adsb_config
        self.mlat_config = mlat_config
        self._has_policy = has_policy

    def generate(self, mlat_privacy: bool = True, uuid: str = None, mlat_enable: bool = True):
        adsb_line = self.adsb_config
        mlat_line = self.mlat_config

        if uuid and len(uuid) == 36:
            adsb_line += f",uuid={uuid}"
            if mlat_line:
                mlat_line += f",uuid={uuid}"
        if mlat_line and mlat_privacy:
            mlat_line += ",--privacy"
        if mlat_enable:
            return f"{adsb_line};{mlat_line}"
        else:
            return f"{adsb_line}"

    @property
    def has_policy(self):
        return self._has_policy


class UltrafeederConfig:
    def __init__(self, data, micro=0):
        # 0means this is either standalone or the aggregator Ultrafeeder
        self._micro = micro
        self._d = data

    @property
    def enabled_aggregators(self):
        ret = {}
        # neither a micro feeder nor the aggregating Ultrafeeder on stage2
        # should feed any aggregators themselves
        aggregator_selection = self._d.env_by_tags("aggregator_choice").value
        print_err(
            f"enabled_aggregators for {self._micro} with agg_sel {aggregator_selection} and stage2 {self._d.is_enabled('stage2')}",
            level=8,
        )
        # be careful to set the correct values for the individual aggregators;
        # these values are used in the main landing page for the feeder to provide
        # additional links for the enabled aggregators

        for name, value in self._d.netconfigs.items():
            aggregator_env = self._d.env_by_tags([name, "ultrafeeder", "is_enabled"])
            if not aggregator_env:
                print_err(f"netconfigs references tag {name} with no associated env")
                continue
            if aggregator_selection in ["micro", "nano"] or (self._d.is_enabled("stage2") and self._micro == 0):
                aggregator_env.list_set(self._micro, False)
            elif aggregator_selection == "all":
                aggregator_env.list_set(self._micro, True)
            elif aggregator_selection == "privacy":
                aggregator_env.list_set(
                    self._micro,
                    self._d.netconfigs[name].has_policy,
                )
            if is_true(aggregator_env.list_get(self._micro)):
                ret[name] = value
        return ret

    def generate(self):
        is_stage2 = self._d.is_enabled("stage2")
        num_micro = self._d.env_by_tags("num_micro_sites").value
        # when not in stage2 mode, no point in setting up the others
        if self._micro > 0 and not is_stage2:
            return ""
        # in stage2 mode, don't set up more proxy ultrafeeders than are configured
        if is_stage2 and self._micro > num_micro:
            return ""
        print_err(f"generating netconfigs for {f'micro site {self._micro}' if self._micro > 0 else 'Ultrafeeder'}")
        mlat_privacy = self._d.list_is_enabled("mlat_privacy", self._micro)
        mlat_enable = self._d.list_is_enabled("mlat_enable", self._micro)
        ret = set()
        # let's grab the values, depending on the mode
        if not is_stage2 or self._micro > 0:
            for name, netconfig in self.enabled_aggregators.items():
                uuid_tag = "adsblol_uuid" if name == "adsblol" else "ultrafeeder_uuid"
                uuid = self._d.env_by_tags(uuid_tag).list_get(self._micro)
                if not uuid:
                    uuid = str(uuid4())
                    self._d.env_by_tags(uuid_tag).list_set(self._micro, uuid)
                ret.add(netconfig.generate(mlat_privacy=mlat_privacy, uuid=uuid, mlat_enable=mlat_enable))
        ret.discard("")

        # now we need to add the inbound links (if needed)

        mf_ip = None
        # add primary data input for microproxy
        if is_stage2 and self._micro > 0:
            mf_ip = self._d.env_by_tags("mf_ip").list_get(self._micro)
            stage2_nano = mf_ip in ["local", "local2"]
            ip, triplet = mf_get_ip_and_triplet(mf_ip)
            # is_user_triplet: microfeeder was specified by user as triplet
            is_user_triplet = mf_ip != ip
            if mf_ip == ip and self._d.env_by_tags("mf_brofm").list_get(self._micro):
                ret.add(f"adsb,{ip},30006,beast_in")
            else:
                ret.add(f"adsb,{triplet}")
            # this is required for the UAT replay
            # the stage2 will be getting the UAT data twice
            # once via the normal beast connection to the microfeeder and via this uat_in
            # but that shouldn't cause issues besides double 978 message rate in the graphs
            # a possible fix would be not to ingest the 978 into ultrafeeder on the microfeeder
            # but that would mean the local microfeeder display / graphs will be lacking 978
            if self._d.list_is_enabled("uat978", self._micro) and not stage2_nano:
                # or the UAT port on the micro feeder
                ret.add(f"adsb,{ip},30978,uat_in")

            if not stage2_nano and not is_user_triplet:
                # while a rare usecase, people might run feed clients on the
                # microfeeder (technically not a microfeeder then) and then use
                # stage2 just for aggregation of the data
                # always get MLAT results to accomodate this
                ret.add(f"mlathub,{ip},31005,beast_in,silent_fail")

        if not is_stage2:
            if self._d.list_is_enabled("uat978", self._micro):
                # the dump978 container if this is an integrated feeder
                ret.add("adsb,dump978,30978,uat_in")

            remote_sdr = self._d.env_by_tags("remote_sdr").value
            # make sure we only ever use 1 SDR / network input for ultrafeeder
            if self._d.env_by_tags("readsb_device_type").value != "":
                pass
            elif self._d.is_enabled("airspy"):
                ret.add("adsb,airspy_adsb,30005,beast_in")
            elif self._d.is_enabled("sdrplay"):
                ret.add("adsb,sdrplay-beast1090,30005,beast_in")
            elif remote_sdr:
                if remote_sdr.find(",") == -1:
                    remote_sdr += ",30005"
                ret.add(f"adsb,{remote_sdr.replace(' ', '')},beast_in")

        # bypass nanofeeder for stage2_nano, ingest airspy / sdrplay / 978 data directly into the local microsite
        if mf_ip == "local":
            if self._d.is_enabled("airspy"):
                ret.add("adsb,airspy_adsb,30005,beast_in")
            elif self._d.is_enabled("sdrplay"):
                ret.add("adsb,sdrplay-beast1090,30005,beast_in")

            if self._d.list_is_enabled("uat978", self._micro):
                ret.add(f"adsb,dump978,30978,uat_in")

        # finally, add user provided things
        ultrafeeder_extra_args = self._d.env_by_tags("ultrafeeder_extra_args").value
        ultrafeeder_extra_args_microsites = self._d.env_by_tags("ultrafeeder_extra_args_microsites").value
        if ultrafeeder_extra_args:
            if not is_stage2:
                ret.add(ultrafeeder_extra_args)
            if is_stage2 and self._micro == 0:
                ret.add(ultrafeeder_extra_args)
        if ultrafeeder_extra_args_microsites:
            if is_stage2 and self._micro != 0:
                ret.add(ultrafeeder_extra_args_microsites.replace("SITENUM", f"{self._micro:02}"))

        if self._micro > 0:
            # this is one of the proxies - so it also should feed the aggregate map
            ret.add("adsb,ultrafeeder,30004,beast_out")
            # push mlat results into central mlathub (possibly useful to separately process / forward mlat data)
            ret.add("mlathub,ultrafeeder,31004,beast_out")

        if self._d.is_enabled("use_gpsd") and self._micro == 0:
            ret.add("gpsd,host.docker.internal,2947")

        # generate sorted listed for deterministic env var (avoid unnecessary container recreation by docker compose)
        ret = sorted(ret)

        print_err(f"ended up with Ultrafeeder args {ret}")

        return ";".join(ret)
