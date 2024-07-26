Changes since v2.1.4 include:
- pin Dozzle and alpine images to reduce unnecessary updates
- fix potential crash if the scripts cannot find a local route
- made micro/nano feeder as an app work again - it seems weird to run this as an app (on port 1099), but maybe there are people who end up doing this reusing an existing DietPi install or something
- add nano feeder mode that tries to even more reduce disk IO and footprint by turning off heatmap, replay, and graphs, as well as moving all logging to memory only (which prevents looking at logs after a crash)
- various code cleanups that resulted in more logical api names, among other things 
- add script to more easily build our images locally - this should allow us to work around the weird GitHub Action issues with Odroid images
- deal with another random change in the airplanes.live status json; at least this change makes things more logical, so I guess I shouldn't complain
- don't unnecessarily add a '_' to the end of a micro feeder site name
- increase size of /run to make sure we don't run out of space for the containers
- add undervoltage and networking issues to the Support Info page
- remove obsolete GitHub Action, references to iob images, and the remainders of the initial attempts to build DietPi images with CustomPiOS
- add several stubs for additional services that aren't fully integrated, but allow managing a pingfail service and integrating CPU/external temperature sensor in the UI template
- fix potential 501 error on startup by avoiding a delayed start of some maintenance tasks

> [!NOTE]
> Based on the available usage information, I have significantly reduced the number of images provided here. If there's one that you need for a different SBC which is supported either by Armbian or DietPi, please post a request on the [Zulip server](https://adsblol.zulipchat.com/#narrow/stream/391168-adsb-feeder-image)

> [!WARNING]
> Images can take more than 5 minutes before the web interface is available. Please be patient.

> [!NOTE]
> Currently the Odroid image and the default LePotato images do NOT support WiFi. For the default Raspberry Pi image (but not the new Raspbian image for LePotato), WiFi can be configured with the Pi Imager when you write the image to SD-card, DietPi based images do support WiFi, but they require editing two files on the DOS partition included with the image BEFORE the first boot. Please look at the [adsb.im FAQ](https://adsb.im/faq) for details.
> Alternatively, if there is no network connection detected, all WiFi enabled images will create a hotspot named `adsb.im-feeder`. You can then connect to that hotspot and set up SSID/password of the access point you want the feeder to connect to.

For Raspberry Pis there are multiple images available. For most users the Raspbian based `adsb-im-raspberrypi64-pi-2-3-4-5-v....img.xz` is likely the best choice, but there are also two DietPi based images available for those who prefer that.



