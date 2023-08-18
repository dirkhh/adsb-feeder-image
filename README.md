# adsb-feeder-image

Easy to use turn-key SD card image for a number of single board computers.
Currently we are building images for
- Raspberry Pi Zero 2, 3a/b, and 4 (tested on Zero 2W, 3a, and 4 - note that Pi Zero W will NOT work)
- Asus Tinkerboard (tested)
- Libre Computing Le Potato (tested) and Renegade (tested)
- Orange Pi 3LTS (tested - no wifi support), 4LTS, and 5
- Banana Pi M5 / M2P
- Odriod C4
- Rockpi 4 (tested)

The idea is to create a "complete" ADS-B feeder that feeds pretty much all of the ADS-B flight trackers / aggregators.

These aggregators have a comittment to open data ([daily release of the data](https://github.com/adsblol/globe_history)):
- [adsb.lol](https://adsb.lol)
- [Fly Italy Adsb](https://flyitalyadsb.com)
- [TheAirTraffic](http://theairtraffic.com)

These aggregators are also supported:
- [adsb.fi](https://adsb.fi)
- [ADS-B Exchange](https://adsbexchange.com)
- [ADSBHub](https://adsbhub.org)
- [ADS-B One](https://adsb.one)
- [AVDelphi](https://www.avdelphi.com)
- [FlightAware](https://flightaware.com)
- [FlightRadar24](https://www.flightradar24.com)
- [FLYOVR.io](https://www.flyovr.io/)
- [OpenSky Network](https://opensky-network.org)
- [Plane.watch](https://plane.watch)
- [Plane Finder](https://planefinder.net)
- [Planespotters.net](http://planespotters.net)
- [RadarBox](https://www.radarbox.com)
- [RadarPlane](https://radarplane.com/)
- [Radar Virtuel](https://www.radarvirtuel.com)

The goal of this project is to make things as simple as possible for the non-technical user.

- buy one of the supported boards (at least the Le Potato seems to be easily and cheaply available in most places)
- invest in a decent power supply - while many of these can be driven from a powered hub or a cheap 'charger' plug, not having a stable 5V power
source tends to be the biggest causes of issues with these SBC
- get an SDR and antenna. There are many many choices. Availability may differ depending on where you are. But often the 'green' RadarBox SDR and
an indoor or (much better) outdoor antenna is all you need
- download the current release from the [Release section](https://github.com/dirkhh/adsb-feeder-image/releases/latest)
- use a tool like the [Raspberry Pi Imager](https://github.com/raspberrypi/rpi-imager/releases) to write the image to a µSD card on your computer
- if doing this with the RPi image, only use the 'wifi setup' option to make sure the image can connect to your wifi - everything else should be
kept unchanged
- boot from the image
- wait a couple of minutes for the initial boot to complete, then connect to the [ADSB-PI Setup Page](http://adsb-feeder.local) -- this link
_should_ work to find the freshly booted system on your local network - assuming you have a reasonably standard setup with mDNS enabled. If this fails. got to the [adsb.im redirector](http://my.adsb.im) - which should forward you to the right local address on your network.
- on the setup website enter the latitude, longitude, and elevation of your receiver as well as a name.
- there's a convenient button to get the correct time zone from your browser
- finally there's a quick selection of the 'semi anonymous' aggregators to submit data to - the ones where you need accounts are on a separate config page
- click on Submit and then be patient while everything gets installed and setup - depending on your internet speed this could take several minutes
- there are two more pages to choose some options and decide which aggregators to feed
- once the setup is completed, you'll be forwarded to your feeder home page from where you can go to all of the various pages that your feeder offers. Usually a good one to start with is the TAR1090 Map at the top.

# for advanced users wanting to run this image on x86 under Proxmox

You need to be able to ssh into your Proxmox system with the root account.
- download the VM-x86_64 image
- copy it to the proxmox server: `scp adsb-feeder-dietpi-x86-64-vm*.tar.xz root@<proxmox-ip or name>`
- unpack the image on the server and create a fresh VM: `ssh root@<proxmox-ip or name> "tar xJf adsb-feeder-dietpi-x86-64-vm*.tar.xz && bash ./pve-vmcreate.sh -s 16G"`
- after this process completes, you should see the new VM in the Proxmox web UI
- start the VM, wait for the first boot to complete, and then connect to it's web interface as usual
- remember to pass through the SDR USB device to the VM before trying to configure the feeder

# for developers

This repo actually contains the scripting to create the SD card image for some common SBCs to run an ADS-B feeder. And as 'releases' it publishes such images.

This requires [CustomPiOS](https://github.com/guysoft/CustomPiOS) - unpack this next to the `CustomPiOS` folder in order for the scripts to work.
