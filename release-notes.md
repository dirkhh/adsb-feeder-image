Changes since v2.3.2 include:
- Show waiting app on second boot of DietPi on initial install
- Update Raspberry Pi OS Lite base image
- beta changelog: don't show SDR setup when SDRs configured as 'other' are removed
- beta changelog: correctly restart netdog if script changed
- beta changelog: address unnecessary SDR Setup when upgrading and using an Airspy
- refinement of detection of SDR plug/unplug events as well as under-voltage events
- include netdog reboots in support info and shared diagnostics
- SDR setup page: improve logic for automatically showing SDR setup page when SDRs are not yet configured
- beta changelog: sdrmap update: fix cpu model displayed for rpi
- beta changelog: small but important adjustment to the changes in beta.10
- add network and system watchdogs that should restart networking / reboot system when networking goes down (or the system hangs for boards with hardware watchdog)
- beta changelog: another new ultrafeeder with small readsb improvements
- beta changelog: send sysinfo to sdrmap
- ultrafeeder: readsb: avoid data loops when pihole returns :: or 0.0.0.0
- plane count statistics: more robust / keep stats when system off over midnight
- address some odd DNS edge cases
- beta changelog: update ultrafeeder / sdrmap containers
- experimental support for sdrmap.org (updated)
- readsb bandwith reduction: will not throttle all aggregators if there is a bad connection to one of them
- fix rare FR24 connection issues (docker incorrectly using DNS search domain, fr24 mishandling DNS replies)
- fix several network related issues on DietPi, speeding up reboot and enabling switching to Ethernet once WiFi was enabled
- add UI capability to change WiFi network (only for feeder image, not for app installs)
- update containers to latest versions
- make ADS-B Feeder Image logo slightly higher contrast
- webinterface: fix potential hang in the chart code for the feeder homepage
- webinterface: more consistent handling of task suspension
- chrony: always step the clock for offsets > 0.5s, not only on startup (helps with suspended VMs)
- tailscale: improve handling of unlikely states / webinterface consistency
- share diagnostics / log-sanitizer: remove stray curl error due to IPv6 check
- explain how to disable secure image mode when it is enabled
- feeder-update: various speedups
- webinterface: fix shading of top bar for 'please wait' screen
- system managent page: add spinners for various actions, load page faster
- webinterface: restarting / streamlog: improve consistency


> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



