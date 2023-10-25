Changes since v1.0.1 include
- switch to new RadarVirtuel container that fixes an issue with newer keys
- show available update options on the feeder homepage
- if there are updates available, allow triggering them from the feeder homepage
- add Plane.watch status indication to the feeder home page
- several small changes to the container config to help with stability and autogain behavior when close to an airport

> [!WARNING]
> Images that start with `adsb-im-iob` can take up to **20 minutes** at first boot. Images without `iob` in their name still can take more than 5 minutes before the web interface is available. Please be patient.

Depending on the target platform, there may be multiple images available.

Some of the images are based on the DietPi Linux distribution and are designed to complete their **install on boot** - those are marked with `iob` in their name and can take a significant time (up to 20 minutes) on first boot as they download and install some of their components at that point (in return, the images are much smaller).

The remaining images have all components pre-installed, but still often take around 5 minutes until the web interface becomes available. Those are based on Raspbian (for the Raspberry Pi boards) or Armbian (all other non-`iob` images)



