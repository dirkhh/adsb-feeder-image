Changes since v2.3.5:
=======
- beta-notes: add button for Sonde and redo all the UI logic to allow for up to four buttons
- beta-notes: remove virtualradar.nl again as their service appears to be continuously down -- possibly not ready for prime time
- beta-notes: fixup inability to deselect individual aggregators when aggregator choice is currently all or privacy
- stage2 with local SDR: correctly show signal graph when using an airspy
- beta-notes: UI: make the choice of whether AIS ships are shown on tar1090 live map user configurable on the expert page
- beta-notes: UI: restyle the page footer
- beta-notes: UI: add hover effect to SDR table
- beta-notes: UI: another rewrite of the SDR Setup, this time with focus to responsiveness and good user experience on small screens
- beta-notes: UI: make stage 2 setup screen more usable on small / mobile screens
- beta-notes: clean up handling of SVG icons
- beta-notes: clean up, reorder, and organize release notes as we get ready for the first v3.0 release
- beta-notes: all changes below are just artifacts of the release notes cleanup
- core: add support for additional SDR use cases: ACARS, VDLM2, HFDL, AIS, SONDE
- core: redesign of the SDR setup page with clickable SDR entries that open a modal dialog to edit all the SDR settings in one place
- core: improve SDR handling and explain why a user might get sent back to the SDR Setup page when all they want is the Feeder Homepage
- core: add support for AirspyHF - limited to just a HFDL and AIS
- core: add support for web-888 SDR via hfdlobserver
- core: add SDR feature matrix README
- core: add support for DHT22 temperature sensor on Raspberry Pi boards
- hotspot: make hotspot RFC7710 compliant and fix a bug where it would respond to random web requests, making it hard to use if your computer / phone sends out a lot of web requests once you connect (and before you can enter the SSID/password)
- UI: add Discord link to the footer
- UI: rework UI to change button style and font size to support even smaller screen sizes
- UI: add custom status icons for feeder home page
- UI: show warning about potentially too many SDRs
- UI: add UI to allow changing the serial number of an RTLSDR
- core: update containers to their current version
- core: /feeder-update-<channel> endpoint: add oldstable option -- this allows downgrade to an earlier, known good 'stable' version after a release
- core: many internal changes to Env variable handling and related code cleanup
- core: better instructions on how to handle compose failure
- stage2: additional ultrafeeder arguments: replace SITENUM magic string
- stage2: fix microfeeder edit with old docker compose version
- stage2: fix restore issue connected to rbfeeder cpuinfo files

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



