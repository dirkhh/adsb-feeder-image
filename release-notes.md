Changes since v2.3.4:
- fix issues on systems with more than 4 SDRs present
- stage2: better decode ground positions far from stage2 center (readsb change)
- additional improvement of readsb memory consumption
- visual changes to make the checkmarks in the aggregator grid more easily distinguishable
- support wifi networks with an empty password
- support for running two SDRs for ADS-B on the same device (usually low + high gain, requires stage2)
- clarify UI for setting ssh key and switching to 'secure' mode
- minor changes for corner cases in the daily reported planes statistics
- update containers to their current versions
- address container name confusion for the uk1090 service which prevented restarting that container from the web UI
- show the option to do nightly feeder software updates in the case of an app install
- notify user if a feeder has no data source and point them to the SDR Setup page to address the issue
- refuse to do OS updates unless this is acually an ADS-B Feeder Image
- avoid potential fast spinning infinite loop when installed in unsupported environments where dmesg is non-functional

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



