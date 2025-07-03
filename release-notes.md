Changes since v2.3.5:
=======
- beta-notes: add contact information for the AcarsDrama team to let them know that you are feeding them data
- beta-notes: additional UI tweaks for visual separation on the home page, button text on the expert page, and removal of a redundant Ko-Fi link
- beta-notes: random changes below will show up in Changelogs as we get ready for release - this is a tooling artifact
- core: add support for additional SDR use cases: ACARS, VDLM2, HFDL, AIS, SONDE
- core: redesign of the SDR setup page with clickable SDR entries that open a modal dialog to edit all the SDR settings in one place
- core: improve SDR handling and explain why a user might get sent back to the SDR Setup page when all they want is the Feeder Homepage
- core: add support for AirspyHF - limited to just a HFDL and AIS
- core: add support for web-888 SDR via hfdlobserver
- core: add SDR feature matrix README
- core: add support for DHT22 temperature sensor on Raspberry Pi boards
- core: show ambient temperature in graphs1090 temperature graph if supported temperature sensor is installed
- core: work around the fact that Flightradar24 appears to believe that emails have to be lowercase
- core: update containers to their current version
- core: /feeder-update-<channel> endpoint: add oldstable option -- this allows downgrade to an earlier, known good 'stable' version after a release
- core: many internal changes to Env variable handling and related code cleanup
- core: better instructions on how to handle compose failure
- hotspot: make hotspot RFC7710 compliant and fix usability issues
- UI: show changelog after update; change the changelog preview from 'button hover' to an explicit Changelog section that the user can easily discover, even on mobile
- UI: significant rework of the UI to accomodate small screens and usage on mobile devices
- UI: add custom status icons for feeder home page
- UI: show warning about potentially too many SDRs
- UI: add UI to allow changing the serial number of an RTLSDR
- UI: add Discord link to the footer
- stage2: additional ultrafeeder arguments: replace SITENUM magic string
- stage2: fix microfeeder edit with old docker compose version
- stage2: fix restore issue connected to rbfeeder cpuinfo files
- stage2 with local SDR: correctly show signal graph when using an airspy

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



