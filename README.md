# ADS-B Feeder Image

Easy to use turn-key SD card image for a number of single board computers (or to run in an x86 VM).
Currently we are building images for
- Raspberry Pi Zero 2, 3a/b, and 4 (tested on Zero 2W, 3a, and 4 - note that Pi Zero W will NOT work)
- Asus Tinkerboard (tested)
- Libre Computing Le Potato (tested) and Renegade (tested)
- Orange Pi 3LTS (tested - no wifi support), 4LTS, 5, and 5plus (tested)
- Banana Pi M5 / M2P
- Odriod C4
- Rockpi 4 (tested)
- NanoPi NEO3 (tested)

- VM setup under VirtualBox (easy), VMware (almost as easy), or Proxmox (advanced users) -- note that when running in VMs, there are known issues that are outside of the control of the image with USB timing that frequently lead to MLAT issues.

The idea is to create a "complete" ADS-B feeder that feeds pretty much all of the ADS-B flight trackers / aggregators.

These aggregators have a comittment to open data ([daily release of the data](https://github.com/adsblol/globe_history)); they also share with each other the data fed to them (in order to improve mlat coverage, it still makes sense to feed all of them):
- [adsb.lol](https://adsb.lol)
- [Fly Italy Adsb](https://flyitalyadsb.com)
- [TheAirTraffic](http://theairtraffic.com)

These aggregators are also supported:
- [adsb.fi](https://adsb.fi)
- [ADS-B Exchange](https://adsbexchange.com)
- [ADSBHub](https://adsbhub.org)
- [ADS-B One](https://adsb.one)
- [airplanes.live](https://airplanes.live)
- [AVDelphi](https://www.avdelphi.com)
- [FlightAware](https://flightaware.com)
- [FlightRadar24](https://www.flightradar24.com)
- [FLYOVR.io](https://www.flyovr.io/)
- [hpradar](https://skylink.hpradar.com/)
- [OpenSky Network](https://opensky-network.org)
- [Plane.watch](https://plane.watch)
- [Plane Finder](https://planefinder.net)
- [Planespotters.net](http://planespotters.net)
- [RadarBox](https://www.radarbox.com)
- [RadarPlane](https://radarplane.com/)
- [Radar Virtuel](https://www.radarvirtuel.com)

### Home page of an installed ADS-B Feeder Image

![ADS-B Feeder home page](/../screenshots/screenshots/ADSB-im-v0.16.0.png "Feeder Home Page")

### The goal of this project is to make things as simple as possible for the non-technical user.

## Feed from a Single Board Computer (like the Raspberry Pi)
- buy one of the supported boards (at least the Le Potato seems to be easily and cheaply available in most places)
- invest in a decent power supply - while many of these can be driven from a powered hub or a cheap 'charger' plug, not having a stable 5V power
source tends to be the biggest cause of issues with these SBC
- get an SDR and antenna. There are many many choices. Availability may differ depending on where you are. But often the 'green' RadarBox SDR and
an indoor or (much better) outdoor antenna is all you need. More detail on the [ADSB.im website](https://adsb.im/supported).
- download the current release from the [Release section](https://github.com/dirkhh/adsb-feeder-image/releases/latest)
- use a tool like the [Raspberry Pi Imager](https://github.com/raspberrypi/rpi-imager/releases) to write the image to a µSD card on your computer
- if doing this with the RPi image, only use the 'wifi setup' option to make sure the image can connect to your wifi - everything else should be
- using a DietPi or non-Raspberry image, WiFi is either unsupported (non-Raspberry boards) or needs to be setup using a text editor making changes to two files on the mountable partifion of the feeder image. There's a README file with instructions in the same folder.
- boot from the image
- wait a couple of minutes for the initial boot to complete, then connect to the [ADSB-PI Setup Page](http://adsb-feeder.local) -- this link
_should_ work to find the freshly booted system on your local network - assuming you have a reasonably standard setup with mDNS enabled. If this fails. got to the [adsb.im redirector](http://my.adsb.im) - which should forward you to the right local address on your network. In the rare case where this fails as well you'll need to manually find the board's IP address - either using a connected keyboard / monitor, or via your router or other source of local IP addresses.
- on the setup website enter the latitude, longitude, and elevation of your receiver as well as a name.
- there's a convenient button to get the correct time zone from your browser
- finally there's a quick selection of the 'semi anonymous' aggregators to submit data to - the ones where you need accounts are on a separate config page
- click on Submit and then be patient while everything gets installed and setup - depending on your internet speed this could take several minutes
- there are two more pages to choose some options and decide which aggregators to feed
- once the setup is completed, you'll be forwarded to your feeder home page from where you can go to all of the various pages that your feeder offers. Usually a good one to start with is the TAR1090 Map at the top.

## Feed from an x86 virtual machine

### for VirtualBox or VMware Workstation / Fusion

Download the `adsb-im-iob-x86-64-vm-*.ova` for the latest release. Double click on the OVA (which should open your virtualization software). Finish the import (under VMware you'll get a warning about a compatibility issue, simply clicking retry should get you past that). Before you start the VM, pass your SDR (which should be connected to a USB port of your PC or Mac) through to that VM. How this is done varries by product and the OS you are running on (Windows, macOS, Linux), but basically in all cases there is an option to pass a USB device to a VM - select your SDR in that list.

Now boot the image and wait a brief while until the console screen stops scrolling and shows a DietPi startup screen that below the two yellow lines presents you with an IP address. Connect to this IP address from your browser and you'll be able to set up the feeder and start sending data to the aggregators of your choice.

As mentioned above, there are known issues with USB timing when accessing an SDR from within a VM - these are unrelated to the ADS-B Feeder image but instead based in the implementation details of most hypervisors. As a result, it is not uncommon to see MLAT issues with feeders running in a VM.

### for advanced users wanting to run this image on x86 under Proxmox

You need to be able to ssh into your Proxmox system with the root account.
- download the x86-64-vm proxmox image
- copy it to the proxmox server: `scp adsb-im-iob-x86-64-vm*.tar.xz root@<proxmox-ip or name>`
- unpack the image on the server and create a fresh VM: `ssh root@<proxmox-ip or name> "tar xJf adsb-im-iob-x86-64-vm*.tar.xz && bash ./pve-vmcreate.sh -s 16G"`
- after this process completes, you should see the new VM in the Proxmox web UI
- start the VM, wait for the first boot to complete, and then connect to it's web interface as usual
- remember to pass through the SDR USB device to the VM before trying to configure the feeder


## Feed from most Linux systems

You can also install this software stack as an app on an existing Linux system. If you are running DietPi as the Linux OS on your system, you can simply install it using `dietpi-software` (it's app 141). Otherwise you can run a small [install script](https://raw.githubusercontent.com/dirkhh/adsb-feeder-image/main/src/tools/app-install.sh). For the trusting kinda people, all you need to do is
```
curl https://raw.githubusercontent.com/dirkhh/adsb-feeder-image/main/src/tools/app-install.sh | sudo bash
```
Or you could do the more sensible thing of downloading the script, reading it, and then executing it.

# for developers

This repo actually contains the scripting to create the SD card image for some common SBCs to run an ADS-B feeder. And as 'releases' it publishes such images.

This requires [CustomPiOS](https://github.com/guysoft/CustomPiOS) - unpack this next to the `CustomPiOS` folder in order for the scripts to work.

## python app

If you are looking for the sources to the adsb-setup app, they are at [src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup](https://github.com/dirkhh/adsb-feeder-image/tree/master/src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup)
