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
    def __init__(self, constants):
        self._constants = constants

    @property
    def enabled_aggregators(self):
        aggregator_selection = self._constants.env_by_tags("aggregators").value
        return {
            name: value
            for name, value in self._constants.netconfigs.items()
            if (
                aggregator_selection == "all"
                or aggregator_selection == "privacy"
                and self._constants.netconfigs[name].has_policy
                or aggregator_selection == "individual"
                and self._constants.is_enabled("ultrafeeder", name)
            )
        }

    def generate(self):
        mlat_privacy = self._constants.is_enabled("mlat_privacy")
        ret = set()
        for name, netconfig in self.enabled_aggregators.items():
            uuid = self._constants.env_by_tags("ultrafeeder_uuid").value
            if name == "adsblol":
                uuid = self._constants.env_by_tags("adsblol_uuid").value
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

        return ";".join(ret)
