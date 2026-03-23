Changes since v3.0.8
=======
- beta-notes: update acarshub to v4.1.5-beta.3
- update airplanes live map link
- stage2: add feeder links to home page table
- update theairtraffic status link
- ensure that my.adsb.im has accurate information to forward the user to the local feeder
- share diagnostics page: small tweaks
- beta-notes: update acarshub to v4.1.5-beta.2
- OS Update: fix unattended apt upgrade on Raspbian
- beta-notes: update acarshub to v4.1.5-beta.1
- beta-notes: another round of container version updates
- beta-notes: update acarshub to v4.1.4-beta.2 and update ultrafeeder
- NOTE: if acarshub does not work immediately, wait 10 minutes for possible migrations to finish
- beta-notes: update acarshub to 4.1.3
- beta-notes: update acarshub to 4.1.1
- NOTE: if this update does not work, your docker --version is 20 or lower (update via get.docker.com)
- sonde: optionally enable web control
- sdrmap: add status link
- update docker containers to current versions (WARNING: potentially long update time)

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



