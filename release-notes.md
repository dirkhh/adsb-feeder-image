Changes since v2.1.0 include:
- logsanitizer: fix for stage2, add journalctl
- heywhatsthat outline: fix disable via checkbox
- first boot / first configuration: avoid interrupting docker pull to eliminate extra downloading
- Basic Setup: don't force the user to go through the data sharing page if they pick "all" or "privacy" during basic setup
- DietPi builds: don't clone the feeder image on first boot - we use custom DietPi images that have the correct version pre-installed
- hotspot dietpi: join the network much quicker
- hotspot raspbian: avoid possible race condition that would stop the hotspot from starting
- hotspot: be more patient with slow networks, use channel 6 instead of 1
- internal code changes, workaround for gateway not responding to ping
- lots of hotspot code tweaks to make it more consistent (hopefully)
- update ultrafeeder to latest version
- fix two small bugs in beta.1
- add secondary .local name for the image once configured, based on the site name (e.g. mysite.local)
- hotspot: fix several issues where hotspot wouldn't work in updated images, after a reboot, in certain situations where WiFi passwords changed
- app: avoid several problems during updates; more robust install
- improved logging behavior with more information, better log rotation
- stage2: reduce memory consumption when importing full data from micro feeder

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid and LePotato images do NOT support WiFi. For Raspbian images, WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



