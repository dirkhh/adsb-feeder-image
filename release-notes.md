Changes since v3.0.6
=======
- beta-notes: auth - add help text to explain to people how to recover / when to re-image
- acarshub: improve method of saving data to disk to avoid DB corruption
- beta-notes: update planefinder container - radar stick now works with MLAT
- beta-notes: suggest having ssh working before turning on authentication
- beta-notes: don't allow setting up auth on a secured image
- web UI: simple http authentication
- hotfix: revert to older multi-outline code - this will fix CPU usage / random tar1090 hangs for large stage2 systems
- infrastructure: add automated boot test / basic functionality test support
- security: fix potential command injection vulnerability in FlightRadar24 signup
- security: add input validation to prevent path traversal attacks
- core: improve error logging for missing container version file
- core: comprehensive code quality improvements (type hints, test coverage, modernized architecture)
- systemd services: define active services in one place so this doesn't get out of sync (again)
- initial support for planefinder radar stick, no MLAT yet, PF data sharing needs to be enabled
- stage2: multioutline: don't launch another script instance if previous one is still running
- stage2: multioutline: log CPU time used when it takes more than 30 seconds
- stage2: multioutline: don't regenerate combined heywhatsthat if source data stays the same
- support WiFi networks with protected management frames on DietPi
- fix Mode S Beast healthcheck
- fix app install / DietPi install issue


> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



