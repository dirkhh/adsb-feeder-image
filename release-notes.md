Changes since v2.3.5:
=======
- beta-notes: add custom icons for the nav buttons
- beta-notes: fix status icons for container starting / container down
- add support for web-888 SDR via hfdlobserver
- beta-notes: label acars2pos 'white planes' as ACARS in tar1090
- beta-notes: even more improvements for small and very small screens
- beta-notes; allow 'auto-verbose' for ads-b RTLSDR autogain with logging
- beta-notes: instead of auto-enabling acars2pos, make this a user selectable option on the expert screen
- add Discord link to the footer
- update almost all containers to their current version
- rework UI to change button style and font size to support even smaller screen sizes
- /feeder-update-<channel> endpoint: add oldstable option -- this allows downgrade to an earlier, known good 'stable' version after a release
- beta-notes: actually enable acars2pos
- rework the navigation bar to be smarter about which buttons to show, depending on screen width
- add custom status icons for feeder home page
- beta-notes: correct the protocols offered for each SDR type -- this continues to be WIP
- beta-notes: support autogain for Airspy and HFDL
- beta-notes: update several containers, and with that correctly support Airspy for acars
- beta-notes: small UI clean-ups
- beta-notes: add acars feed option for adsb.lol
- beta-notes: attempt to support AirspyHF - this is untested, especially the gain values supported are unclear
- beta-notes: fix HFDL feeding to airframes.io
- beta-notes: write acarshub data to disk every hour
- beta-notes: support -10 for RTLSDR autogain in ACARS
- add SDR feature matrix README
- beta-notes: allow disabling non-adsb protocols without first setting a feed ID
- beta-notes: image only: increase usbfs memory to 128M to accomodate more SDRs
- beta-notes: only show biastee option if the underlying container supports that for this SDR type
- beta-notes: fixup ACARS feeds / more consistently handle acars_router feed strings
- beta-notes: improve matching of acars notifications on the live map
- beta-notes: improve comments and placeholders on expert page based on user feedback
- beta-notes: feed VDLM2 to airframes.io on TCP
- beta-notes: show warning about potentially too many SDRs
- beta-notes: update Shipfeeder container
- beta-notes: change SDR Setup user experience; clicking OK in the modal dialog only stores the updates in the browser; only after clicking Apply Settings are all the changes handed to the backend
- beta-notes: show better gain guidance in the SDR Settings UI - depending on the SDR model and the decoder used
- beta-notes: return to the SDR Setup page after making changes
- beta-notes: add user configurable Env variables to the non-ADS-B containers
- beta-notes: fix main page error when non-adsb option is enabled
- beta-notes: handle aggregator choices for the various protocols accordingly and notify the user when a protocol is enabled with no aggregators
- beta-notes: make the feed IDs for the various non-ADS-B services required
- beta-notes: improve the setup flow for non-ADS-B users
- beta-notes: fix acars2pos to ingest VDL2 and HFDL as well
- beta-notes: fix feeding AIS to sdrmap.org and PocketMariner/BoatBeacon
- beta-notes: improvements to the non-ADS-B user experience, trying to make things less ADS-B centric
- beta-notes: move non-ADS-B aggregators to Data Sharing page and add more aggregators
- beta-notes: stage2: aggregator display fix for main page (introduced in beta.6)
- beta-notes: stage2: fixup config for bug in beta.4
- beta-notes: unbreak stage 2 (bug introduced in beta.4)
- beta-notes: validate the given frequency ranges for ACARS and VDLM2 to make sure they fit in 2MHz
- beta-notes: add more AIS aggregators
- beta-notes: make ACARS data survive a controlled reboot (but not power failure)
- beta-notes: better ACARS default frequencies for acarsdec (with less common ones mostly in acarsdec2)
- beta-notes: fix homepage refresh failure in cases with no ADSB SDRs
- beta-notes: fix bug that sometimes prevented turning on biastee in the UI
- beta-notes: enforce new serial to be at least two and at most eight characters
- beta-notes: add UI link to change RTLSDR serial number
- beta-notes: fix bug when adding stage2 site
- beta-notes: sdr serial change: use longer timeout to stop containers
- update all of the containers to the current releases
- core: add UI to allow changing the serial number of an RTLSDR
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



