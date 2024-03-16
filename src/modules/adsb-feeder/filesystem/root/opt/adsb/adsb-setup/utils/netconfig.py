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
    def __init__(self, constants, micro: str = ""):
        self._micro = micro
        self._constants = constants

    @property
    def enabled_aggregators(self):
        aggregator_selection = self._constants.env_by_tags("aggregators").value
        if aggregator_selection == "micro":
            return {}
        # be careful to set the correct values for the individual aggregators;
        # these values are used in the main landing page for the feeder to provide
        # additional links for the enabled aggregators
        for name in self._constants.netconfigs.keys():
            aggregator_env = self._constants.env_by_tags(
                [name, "ultrafeeder", "is_enabled"]
            )
            if not aggregator_env:
                print_err(f"netconfigs references tag {name} with no associated env")
                continue
            if aggregator_selection == "all":
                aggregator_env.value = True
            elif aggregator_selection == "privacy":
                aggregator_env.value = self._constants.netconfigs[name].has_policy
        return {
            name: value
            for name, value in self._constants.netconfigs.items()
            if (self._constants.is_enabled("ultrafeeder", name))
        }

    def generate(self):
        is_stage2 = self._constants.is_enabled("stage2")
        micro = int(self._micro[1:]) if self._micro else -1
        num_micro = self._constants.env_by_tags("num_micro_sites").value
        # when not in stage2 mode, no point in setting up the others
        if micro >= 0 and not is_stage2:
            return ""
        # in stage2 mode, don't feed from the internal aggregator, don't set up more
        # proxy ultrafeeders than are configured
        if is_stage2 and (micro == -1 or micro >= num_micro):
            return ""
        print_err(
            f"generating netconfigs for {f'micro site {micro}' if micro >= 0 else 'Ultrafeeder'}"
        )
        mlat_privacy = self._constants.is_enabled("mlat_privacy")
        ret = set()
        for name, netconfig in self.enabled_aggregators.items():
            uuid = self._constants.env_by_tags(f"ultrafeeder_uuid{self._micro}").value
            if name == "adsblol":
                uuid = self._constants.env_by_tags(f"adsblol_uuid{self._micro}").value
            ret.add(netconfig.generate(mlat_privacy=mlat_privacy, uuid=uuid))
        ret.discard("")
        # now we need to add the two internal inbound links (if needed)
        if self._constants.is_enabled("uat978"):
            ret.add("adsb,dump978,30978,uat_in")
        if self._constants.is_enabled("airspy"):
            ret.add("adsb,airspy_adsb,30005,beast_in")
        # finally, add user provided things
        ultrafeeder_extra_args = self._constants.env_by_tags(
            "ultrafeeder_extra_args"
        ).value
        if ultrafeeder_extra_args:
            ret.add(ultrafeeder_extra_args)
        remote_sdr = self._constants.env_by_tags("remote_sdr").value
        if self._micro:
            # this is one of the proxies - so it also should feed the aggregate map
            ret.add("adsb,ultrafeeder,30004,beast_out")
        if remote_sdr:
            if remote_sdr.find(",") == -1:
                remote_sdr += ",30005"
            ret.add(f"adsb,{remote_sdr.replace(' ', '')},beast_in")

        print_err(f"ended up with Ultrafeeder args {ret}")

        return ";".join(ret)
