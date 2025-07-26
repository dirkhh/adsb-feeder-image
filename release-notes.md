Changes since v3.0.0
=======
- fix use of 'integrated' as default for ADS-B
- remove broken attempt to support DHT22 on non-Raspberry boards
- fix enabling non-DHT22 sensors and prevent menu bar wrapping on small displays if temperature is enabled
- while 'secure image' is activated, wifi config hotspot will remain disabled
- add setting to disable wifi config hotspot
- update containers to latest version
- data sharing: add some visual separation / grouping to this rather busy page
- adsb: move MLAT privacy to be part of the account less aggregator setup (where it belongs)
- setup: complete overhaul of the UI flow to be less ADS-B centric
- setup: ask the user for their initials and provide a feed id that matches the proposed pattern if the user doesn't provide their own
- setup: show closest airport on basic setup page, based on lat/long data entered (this should help detect mistakes when entering the location)
- ais: fix incorrect HPRadar feed setup
- UI: allow the user to show the temperature in Fahrenheit
- UI: don't offer to update the WiFi connection when running in a VM
- UI: adjust temperature block colors for dark mode and fade them more slowly as the temperature information ages
- UI: allow the user to choose the temperature sensor that they have and specify the GPIO that it is connected to (for DHT11/22)
- core: allow the DHT22 to be used on OrangePi Zero3
- core: add support for TEMPer USB temperature sensors on all platforms
- hfdl/SDRplay: correct the acceptable gain values
- vdl2: allow specifying frequencies as list of space separated MHz values
- acars/vdl2: changes to sample rates used and therefore frequency spread supported
- acars: support biastee with RTLSDR
- acars/vdl2: use librtlsdr instead of soapy for RTLSDR support
- core: restrict temperature sensor support to feeder image mode only (so not in app mode) and install dependencies if missing
- core: improve temperature sensor support with full support on the Raspberry Pi 5 and some support for the DHT11 and experimental support for the BME280
- UI: improve styling and consistency of system management and hotspot UI
- core: add WiFi scanning to system management (similar to hotspot functionality)

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



