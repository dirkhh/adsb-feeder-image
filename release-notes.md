Changes since v3.0.12
=======
- ultrafeeder extra args: deal with \r
- new aggs: flightdeck, adsbitalia
- cleanup: improve error and debug messages in logs
- add new aggregators, ADSBiq, RealTraffic, Dataero, and FlyOverhead
- webUI: completely rethink and redo the data sharing page
- healthcheck: properly identify container down (instead of wrongly assuming the SDR is down)
- healthcheck: add experimental feature to force automatic reboots when a configured SDR disappears
- temperature: improve handling of BM280 sensors
- update RadarVirtuel container and setup
- beta-notes: stage2 minor piaware link fix on data sharing page
- stage2: support well more than 40 sites (resources permitting)

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the default LePotato images does NOT support WiFi. For the other images, we recommend against configuring WiFi with the Pi Imager when you write the image to SD-card. Instead use the automatic hotspot to set up WiFi: if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



