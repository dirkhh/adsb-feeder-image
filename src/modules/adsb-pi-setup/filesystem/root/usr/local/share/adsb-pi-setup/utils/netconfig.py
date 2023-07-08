class NetConfig:
    def __init__(self, adsb_config: str, mlat_config: str, has_policy: bool):
        self.adsb_config = adsb_config
        self.mlat_config = mlat_config
        self.has_policy = has_policy

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
    def normal(self):
        return self.generate(False, None)  # without uuid or mlat privacy flag

    @property
    def domain(self):
        # avdelphi.com -> avdelphi.com
        # feed.adsb.lol -> adsb.lol
        return ".".join(self.adsb_config.split(",")[1].split(".")[-2:])


class NetConfigs:
    def __init__(self):
        self.configs = {
            "adsblol": NetConfig(
                "adsb,feed.adsb.lol,30004,beast_reduce_plus_out",
                "mlat,feed.adsb.lol,31090,39001",
                True,
            ),
            "flyitaly": NetConfig(
                "adsb,dati.flyitalyadsb.com,4905,beast_reduce_plus_out",
                "mlat,dati.flyitalyadsb.com,30100,39002",
                True,
            ),
            "adsbx": NetConfig(
                "adsb,feed1.adsbexchange.com,30004,beast_reduce_plus_out",
                "mlat,feed.adsbexchange.com,31090,39003",
                True,
            ),
            "tat": NetConfig(
                "adsb,feed.theairtraffic.com,30004,beast_reduce_plus_out",
                "mlat,feed.theairtraffic.com,31090,39004",
                False,
            ),
            "ps": NetConfig(
                "adsb,feed.planespotters.net,30004,beast_reduce_plus_out",
                "mlat,mlat.planespotters.net,31090,39005",
                True,
            ),
            "adsbone": NetConfig(
                "adsb,feed.adsb.one,64004,beast_reduce_plus_out",
                "mlat,feed.adsb.one,64006,39006",
                False,
            ),
            "adsbfi": NetConfig(
                "adsb,feed.adsb.fi,30004,beast_reduce_plus_out",
                "mlat,feed.adsb.fi,31090,39007",
                False,
            ),
            "avdelphi": NetConfig(
                "adsb,data.avdelphi.com,24999,beast_reduce_plus_out",
                "",
                True,
            ),
        }

    def get_config(self, key):
        return self.configs.get(key)

    def get_keys(self):
        return self.configs.keys()

class CurrentNetConfig:
    # This checks the current net config and returns the list of keys that are enabled
    # We do this by comparing the current net config to the list of net configs
    # We make a set of the pending return values.
    # For each item separated by ; in the current net config, we check if it is in the list of net configs
    # If it is, we add the key to the set
    # Of course, we ignore the mlat config and the UUID if it is present
    # We also check that the net config is not empty, as some netconfigs do not have MLAT for example.
    def __init__(self, current_net_config: str, net_configs: NetConfigs):
        self.current_net_config = current_net_config
        self.net_configs = net_configs
        self.domain_to_key = {}

        for key in self.net_configs.get_keys():
            self.domain_to_key[self.net_configs.get_config(key).domain] = key


    def _get_enabled_keys(self):
        for item in self.current_net_config.split(";"):
            # If it does not start with adsb, continue.
            if not item.startswith("adsb"):
                continue
            # If it is empty, continue.
            if not item:
                continue
            # If the domain is not in the list of domains, continue.
            domain = ".".join(item.split(",")[1].split(".")[-2:])
            if domain not in self.domain_to_key:
                continue
            # If the net config is empty, continue.
            if not self.net_configs.get_config(self.domain_to_key[domain]).normal:
                continue
            # If we get here, we can add the key to the set.
            self.enabled_keys.add(self.domain_to_key[domain])

    def get_enabled_keys(self):
        self.enabled_keys = set()
        self._get_enabled_keys()
        return self.enabled_keys
