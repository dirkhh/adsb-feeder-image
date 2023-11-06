Changes since v1.0.5 include
- update Raspbian images so that Dozzle can show memory use of the containers
- support zero-padded serial number when trying to find "obvious" SDR assignments (thanks to @YipYup)
- always show the SDR assignment on the advanced page, even if there's just one SDR with an "obvious" assignment
- make the parsing of the status checks with the aggregators significantly more robust
- rewrite of the UI code; the overall look and feel hasn't changed dramatically, but this is now based on the free version of Material Design for Bootstrap 5, which gives us a more modern and easier to maintain code baseA

> [!WARNING]
> Images that start with `adsb-im-iob` can take up to **20 minutes** at first boot. Images without `iob` in their name still can take more than 5 minutes before the web interface is available. Please be patient.

Depending on the target platform, there may be multiple images available.

Some of the images are based on the DietPi Linux distribution and are designed to complete their **install on boot** - those are marked with `iob` in their name and can take a significant time (up to 20 minutes) on first boot as they download and install some of their components at that point (in return, the images are much smaller).

The remaining images have all components pre-installed, but still often take around 5 minutes until the web interface becomes available. Those are based on Raspbian (for the Raspberry Pi boards) or Armbian (all other non-`iob` images)



