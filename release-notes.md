Changes since v2.3.5:
=======
- beta-notes: sdr serial change: use longer timeout to stop containers
- update all of the containers to the current releases
- core: add UI to allow changing the serial number of an RTLSDR; right now this is only made available if there's a duplicate serial number.
- core: warn user when they navigate away from SDR setup without applying the changes
- core: redesign of the SDR setup page with clickable SDR entries that open a modal dialog to edit all the SDR settings in one place
- non-adsb: initial support for additional SDR use cases: ACARS, VDLM2, HFDL, AIS, SONDE
- core: many internal changes to Env variable handling and related code cleanup
- hotspot: make hotspot RFC7710 compliant and fix a bug where it would respond to random web requests, making it hard to use if your computer / phone sends out a lot of web requests once you connect (and before you can enter the SSID/password)
- stage2: additional ultrafeeder arguments: replace SITENUM magic string
- stage2: fix microfeeder edit with old docker compose version
- stage2: fix restore issue connected to rbfeeder cpuinfo files
- better instructions on how to handle compose failure

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



