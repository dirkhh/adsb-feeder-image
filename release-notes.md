Changes since v1.3.1 include
- don't restore the container versions from the backup
- fix install issue that prevented SDRplay devices from working out of the box
- prevent users from inadvertantly locking themselves out of a freshly installed system by restoring from a system with secure-image enabled
- fix issue with recent iob builds potentially not successfully completing that first install due to CONFIG_NTP_MODE being set to 0
- attempt to deal better with SDRs without serial number
- intial experimental support of SDRplay devices
- backup: generate zipfile on the fly; this gets us immediate UI response to clicking the backup button and less wear and tear on the SD card
- more backup/restore fixes
- update to the latest version of the udev rules and module blocklist from Ramon Kolb's docker-install.sh; add the same code to the DietPi builds (where it was missing before)
- switch to chrony for time synchronization on all images
- enable backup/restore with the config.json setup - this has received some testing, could benefit from more scrutiny 
- upgrade Airspy container
- improve the shutdown behavior of the containers to shorten the restart time after config changes

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



