from uuid import uuid4
from utils.util import print_err


class NetConfig:
    def __init__(self, adsb_config: str, mlat_config: str, has_policy: bool):
        self.adsb_config = adsb_config
        self.mlat_config = mlat_config
        self._has_policy = has_policy

    def generate(self, mlat_privacy: bool = True, uuid: str = None):
        adsb_line = self.adsb_config
        mlat_line = self.mlat_config

        if uuid and len(uuid) == 36:
            adsb_line += f",uuid={uuid}"
            if mlat_line:
                mlat_line += f",uuid={uuid}"
        if mlat_line and mlat_privacy:
            mlat_line += ",--privacy"
        return f"{adsb_line};{mlat_line}"

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
        aggregator_selection = self._d.env_by_tags("aggregators").value
        if aggregator_selection == "micro":
            return {}
        if self._d.is_enabled("stage2") and self._micro == 0:
            return {}
        # be careful to set the correct values for the individual aggregators;
        # these values are used in the main landing page for the feeder to provide
        # additional links for the enabled aggregators

        for name, value in self._d.netconfigs.items():
            aggregator_env = self._d.env_by_tags([name, "ultrafeeder", "is_enabled"])
            if not aggregator_env:
                print_err(f"netconfigs references tag {name} with no associated env")
                continue
            if aggregator_selection == "all":
                aggregator_env.list_set(self._micro, True)
            elif aggregator_selection == "privacy":
                aggregator_env.list_set(
                    self._micro,
                    self._d.netconfigs[name].has_policy,
                )
            if aggregator_env.list_get(self._micro):
                ret[name] = value
        return ret

    def generate(self):
        is_stage2 = self._d.is_enabled("stage2")
        num_micro = self._d.env_by_tags("num_micro_sites").value
        # when not in stage2 mode, no point in setting up the others
        if self._micro > 0 and not is_stage2:
            return ""
        # in stage2 mode, don't feed from the internal aggregator, don't set up more
        # proxy ultrafeeders than are configured
        if is_stage2 and (self._micro == 0 or self._micro > num_micro):
            return ""
        print_err(
            f"generating netconfigs for {f'micro site {self._micro}' if self._micro > 0 else 'Ultrafeeder'}"
        )
        mlat_privacy = self._d.is_enabled("mlat_privacy")
        ret = set()
        # let's grab the values, depending on the mode
        for name, netconfig in self.enabled_aggregators.items():
            uuid_tag = "adsblol_uuid" if name == "adsblol" else "ultrafeeder_uuid"
            uuid = self._d.env_by_tags(uuid_tag).list_get(self._micro)
            if not uuid:
                uuid = str(uuid4())
                self._d.env_by_tags(uuid_tag).list_set(self._micro, uuid)
            ret.add(netconfig.generate(mlat_privacy=mlat_privacy, uuid=uuid))
        ret.discard("")
        # now we need to add the internal inbound links (if needed)
        if self._d.is_enabled("uat978"):
            ret.add("adsb,dump978,30978,uat_in")
        if self._d.is_enabled("airspy"):
            ret.add("adsb,airspy_adsb,30005,beast_in")
        if self._d.is_enabled("sdrplay"):
            ret.add("adsb,sdrplay-beast1090,30005,beast_in")
        # finally, add user provided things
        ultrafeeder_extra_args = self._d.env_by_tags("ultrafeeder_extra_args").value
        if ultrafeeder_extra_args:
            ret.add(ultrafeeder_extra_args)
        remote_sdr = self._d.env_by_tags("remote_sdr").value
        if self._micro > 0:
            # this is one of the proxies - so it also should feed the aggregate map
            ret.add("adsb,ultrafeeder,30004,beast_out")
            ret.add("mlathub,ultrafeerder,30004,beast_out")
        if remote_sdr:
            if remote_sdr.find(",") == -1:
                remote_sdr += ",30005"
            ret.add(f"adsb,{remote_sdr.replace(' ', '')},beast_in")

        print_err(f"ended up with Ultrafeeder args {ret}")

        return ";".join(ret)
