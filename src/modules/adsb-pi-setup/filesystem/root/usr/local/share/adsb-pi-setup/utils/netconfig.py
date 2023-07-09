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
