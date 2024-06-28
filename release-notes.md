Changes since v2.1.2 include:
- fixup form value issue with last beta (checkbox value must be 1)
- index page: improve load time
- restarting / logstreamer pages: avoid using readystatechange listener to make sure functions don't run unexpectedly
- if a feeder has working GPS/gpsd that is accessible for the Ultrafeeder container, add option to derive location from the GPS data
- fix zerotier bring up after restore
- make network checks more robust, trying to deal with corner cases where ICMP may be blocked or have extremely high latency
- reduce image sizes some more by removing unnecessary components that were being bundled
- update SDR-E containers
- address security issues around user input potentially being executed
- new experimental Raspbian based Le Potato image that supports WiFi with many USB-WiFi adapters
- many small improvements to logging and debuggability
- set station name as hostname as well

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



