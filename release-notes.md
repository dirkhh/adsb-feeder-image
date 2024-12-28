Changes since v2.2.4 include:
- deal with the RadarBox -> AirNav Radar rebranding
- small wording changes to several pages that hopefully improve the user experience
- system management page: don't offer an incorrect / non-existent 'origin/' channel for updates
- feeder homepage: small changes to declutter the page
- dietpi: new images support using ethernet with wifi configured (still needs reboot for ethernet to activate)
- statistics: send old version to adsb.im after update
- dietpi: fix os update from webinterface producing a bad state requiring reboot
- fix range outline reset not working in many cases
- fix up base image reporting in log sanitizer
- vm images / dietpi: shutdown on ACPI shutdown / power button pressed
- after initial setup only change SDR assignments when explicitely requested
- improve multiOutline robustness


> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



