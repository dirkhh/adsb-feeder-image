Changes since v2.0.0 include:
- make heatmap shown consistent regardless from where you get to it
- ultrafeeder/rtlsdr: on the fly gain changes without restarting the decoder or container
- make logs less verbose and improve the diagnostic uploader
- add ready to go VM images, drop the iob builds, drop the 32bit Pi3 build
- fix autogain reset for UAT SDRs
- fix out of space build error preventing some images from getting built
- further improvements of boot time for DietPi images
- add missing Env variable that broke the option to remove the config link from the map
- add a second set of DietPi images that should boot much quicker as most of the dependencies are installed at build time
- make initial autogain adjustment quicker / no more restarting the decoder to change gain
- fix dump978 when using rtl-sdr blog v4 SDR
- add an option to remove the config link from the map
- change the file name extension of backups from .zip to .backup
- disable docker healthcheck for all containers (hopefully improve MLAT on pi3)
- add micro feeder status info to index and stage2 settings page
- work around broken PlaneFinder container on RPi5
- re-enable tar1090 update at start
- add multi-outline for stage 2 maps
- various small UI adjustments


> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images that start with `adsb-im-iob` can take up to **20 minutes** at first boot. Images without `iob` in their name still can take more than 5 minutes before the web interface is available. Please be patient.
>
> Not all images support WiFi, DietPi based images that do support WiFi (e.g. DietPi images for Raspberry Pi) require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.

Depending on the target platform, there may be multiple images available.

Some of the images are based on the DietPi Linux distribution and are designed to complete their **install on boot** - those are marked with `iob` in their name and can take a significant time (up to 20 minutes) on first boot as they download and install some of their components at that point (in return, the images are much smaller).

The remaining images have all components pre-installed, but still often take around 5 minutes until the web interface becomes available. Those are based on Raspbian (for the Raspberry Pi boards) or Armbian (all other non-`iob` images)



