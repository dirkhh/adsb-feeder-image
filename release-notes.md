Changes since v2.2.6 include:
- nicely cache static files in the browser for faster page load times
- beta fix: race condition sometimes result in 'site unreachable' during feeder update
- beta fix: inadvertantly broken 'waiting' app (that's needed by feeder update)
- UI: improve SDR page for small displays
- UI: dark mode improvements
- chart: support shift-click to remove a microfeeder from the chart when all microdfeeders are shown (default)
- update all containers to current versions
- stage 2: correctly align stats for recently added microfeeders
- add support for Mode-S Beast and other less common SDRs
- improve Proxmox instructions
- add missing usbutils(lsusb) dependency for app install
- improve proxmox instructions in the README
- stage 2: radical UI change, removing nested dropdowns using buttons to pick the target micro feeder
- fix remaining broken statistics link on Stage 2 home page
- stage 2: allow selecting the feeders shown in the statistics chart by clicking on the legend
- improve colors and date display for the statistics chart
- add chart of planes seen for up to the last two weeks (this will take time to populate data as it requires the new statistics just added)
- stage 2: make number of planes available as part of stage2_stats API
- several consistency and user interaction improvements for the UI, especially for Stage 2 systems
- fix AirNav support in stage 2 scenarios
- remove RadarPlane (which has been defunct for a while) plus remnants of some other defunct aggregators
- stage 2: allow updating time zone
- Basic setup: allow altitude entry with unit, including conversion from ft to m
- Make it explicit which branch is used for automated nightly updates
- Don't show beta/stable channel indicator in the version shown on feeder home page
- Don't show live map link until feeder is configured


> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



