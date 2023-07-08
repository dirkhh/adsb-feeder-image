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
        print(f"Ready line: {adsb_line};{mlat_line}")
        return f"{adsb_line};{mlat_line}"

    @property
    def normal(self):
        return self.generate(False, None)  # without uuid or mlat privacy flag


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
