Changes since v1.3.0 include
- fix order of execution issue when upgrading from v1.2.3 or older to v1.3.0 or newer that lead to only some of the containers restarting

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)
>
> [!WARNING]
> Images that start with `adsb-im-iob` can take up to **20 minutes** at first boot. Images without `iob` in their name still can take more than 5 minutes before the web interface is available. Please be patient.
>
> Not all images support WiFi, DietPi based images that do support WiFi (e.g. DietPi images for Raspberry Pi) require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.

Depending on the target platform, there may be multiple images available.

Some of the images are based on the DietPi Linux distribution and are designed to complete their **install on boot** - those are marked with `iob` in their name and can take a significant time (up to 20 minutes) on first boot as they download and install some of their components at that point (in return, the images are much smaller).

The remaining images have all components pre-installed, but still often take around 5 minutes until the web interface becomes available. Those are based on Raspbian (for the Raspberry Pi boards) or Armbian (all other non-`iob` images)



