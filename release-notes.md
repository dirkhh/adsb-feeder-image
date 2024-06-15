Changes since v2.1.0 include:
- hotspot dietpi: join the network much quicker
- hotspot raspbian: avoid possible race condition that would stop the hotspot from starting
- hotspot: be more patient with slow networks, use channel 6 instead of 1
- internal code changes, workaround for gateway not responding to ping
- lots of hotspot code tweaks to make it more consistent (hopefully)
- update ultrafeeder to latest version
- fix two small bugs in beta.1
- add secondary .local name for the image once configured, based on the site name (e.g. mysite.local)
- hotspot: fix several issues where hotspot wouldn't work in updated images, after a reboot, in certain situations where WiFi passwords changed
- app: avoid several problems during updates; more robust install
- improved logging behavior with more information, better log rotation
- stage2: reduce memory consumption when importing full data from micro feeder

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.
>
> Not all images support WiFi, DietPi based images that do support WiFi (e.g. DietPi images for Raspberry Pi) require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.

Depending on the target platform, there may be multiple images available.

Some of the images are based on the DietPi Linux distribution and are designed to complete their **install on boot** - those are marked with `iob` in their name and can take a significant time (up to 20 minutes) on first boot as they download and install some of their components at that point (in return, the images are much smaller).

The remaining images have all components pre-installed, but still often take around 5 minutes until the web interface becomes available. Those are based on Raspbian (for the Raspberry Pi boards) or Armbian (all other non-`iob` images)



