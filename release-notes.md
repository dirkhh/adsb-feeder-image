Changes since v1.1.3 include
- add somewhat experimental feature to receive beast_in from a seperate device; this way one could have a resource constrained SBC run with a 1090MHz SDR attached, and then use a differeny system (maybe even a VM) to do the visualization and to feed the aggregators.
- create better names for backup zip files
- warn the user if they use multiple SDRs with the same serial number
- ensure that there are no zombie SDRs in the list in the web UI
- allow multiple SDRs to be assigned 'other' status in the web UI

> [!WARNING]
> Images that start with `adsb-im-iob` can take up to **20 minutes** at first boot. Images without `iob` in their name still can take more than 5 minutes before the web interface is available. Please be patient.

Depending on the target platform, there may be multiple images available.

Some of the images are based on the DietPi Linux distribution and are designed to complete their **install on boot** - those are marked with `iob` in their name and can take a significant time (up to 20 minutes) on first boot as they download and install some of their components at that point (in return, the images are much smaller).

The remaining images have all components pre-installed, but still often take around 5 minutes until the web interface becomes available. Those are based on Raspbian (for the Raspberry Pi boards) or Armbian (all other non-`iob` images)



