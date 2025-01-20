Changes since v2.2.5 include:
- ensure that the Docker network doesn't conflict with any network that the user is already connected to
- update Dozzle container to current version
- don't show the 'upgrade to stable' button on the home page when this is actually a downgrade. Still offer that ability on the system management page.
- stage2: avoid potential data consistency issues when manipulating micro feeders
- stage2: allow reordering of micro feeders
- update containers - this will cause the update to take a bit longer
- only run nightly update if there actually is a newer version available in the active channel
- significantly increase the number of warnings / issues that are communicated to the user via the web UI
- log-sanitizer: improve search and replace
- improve implementation of ssh password/keys and ensure that sshd is running
- always have a single SDR default to ADS-B, even if its serial number is 978
- replace the language of semi-anonymous / commercial aggregators with account-less / account-based
- update the README to reflect the current state of the project
- better handling of broken IPv6 environments when collecting support info


> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



