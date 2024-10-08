Changes since v2.1.6 include:
- almost all docker images have been updated since v2.1.6 (but not since the last beta). Expect a relatively slow update if coming from 2.1.7-beta.1 or earlier.
- many memory tweaks so raspbian systems with less than 4G of memory have more available
- raspbian image build: reduce gpu memory / disable bluetooth
- app install first run: fix wrong redirects
- fix stage2 local receiver with userland proxy disabled
- airspy container: avoid need for restart after hotplug
- additional aggregator links: add FlightAware and airplanes.live links
- reimplement beast and mlat status for Ultrafeeder based aggregators; this adds more status details
- don't require 1.8G of memory for stage2, only warn about recommended memory per microsite
- image: enable swap via zram
- eliminate minor disk writes by fa / fr24 containers
- disable userland proxy in the docker config for new images
- fix long load for expert page for rare circumstances
- fix tar1090 config link port when restoring app install <-> image

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



