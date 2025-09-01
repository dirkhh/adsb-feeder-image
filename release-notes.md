Changes since v3.0.1
=======
- adsbexchange map / stats link: reliably retrieve for stage2 / multiple feeds on same IP
- expert page: correctly handle enter in various text input fields to update the corresponding values
- up acars_router version so docker bridge ipv6 no longer breaks acars
- up fr24 version to fix an error ('use new version' .. version is out less than a week)
- improve log-sanitizer / share diagnostics (was apparently truncating the log on some systems)
- fix the acarshub data loss on power loss (probably)
- fix biastee not showing for acars and acars2 (rtl-sdr and airspy)
- fix MLAT displaying as disconnected when it's actually disabled
- remove unicode symbols from internal API for feeder status
- add option on expert page to enable ipv6 for the docker bridge network, name now adsb_im_bridge (was config_default)
- fix: some temperature sensor corner cases

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



