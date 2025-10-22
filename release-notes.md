Changes since v3.0.5
=======
- infrastructure: add automated boot test / basic functionality test support
- beta-notes: security: fix potential command injection vulnerability in FlightRadar24 signup
- beta-notes: security: add input validation to prevent path traversal attacks
- beta-notes: core: improve error logging for missing container version file
- beta-notes: infrastructure: comprehensive code quality improvements (type hints, test coverage, modernized architecture)
- beta-notes: fix compose up failure related to docker network creation
- beta-notes: fix SDRPlay SDR Setup for 1090 bug
- beta-notes: update Skystats to v0.1.11
- add ability to backup Skystats database. NOTE: no restore from the UI (yet)
- beta-notes: small updates to the README
- beta-notes: update Skystats to v0.1.10
- beta-notes: update ultrafeeder and telegraf containers to fix Mode-S Beast message counting issue
- acarshub: make sure /run size is increased before restoring data from disk
- acarshub: use index optimization setting to prevent the DB growing unnecessarily
- beta-notes: redoing the internal changes, this time hopefully without breaking things - tested on Python 3.9
- beta-notes: revert some internal changes that need more careful planning as they introduced bugs in a number of scenarios, including for systems with older Python versions
- add recovery service to the image (not the app): go to http://<IP>:1089 and be offered to go back to the previous version - or go to a specific version or branch with http://<IP>:1089/recover-to/<tag-or-branch>
- beta-notes: fix two stupid bugs introduced in the last beta
- UI: consistent wording of button text to apply changes
- beta-notes: update Skystats to v0.1.8
- ais-catcher: update container to make sure biastee is set to off on startup if not enabled
- beta-notes: fix showing CPU temperature and allow manual configuration of the correct sensor
- core: add Skystats for extended statistics - tuned for low disk IO
- UI: always show the CPU temperature in the title bar, even without a temperature sensor
- UI: split Expert settings into an Advanced page and the existing Expert page, making the user experience a bit easier to explore
- app install: prompt to install docker via get.docker.com in some cases
- add support for openfreemap offline map (not included)
- healthcheck: improve wording when decoders are not running
- update containers


> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



