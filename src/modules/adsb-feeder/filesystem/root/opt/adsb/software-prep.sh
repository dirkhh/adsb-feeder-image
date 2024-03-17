#!/bin/bash

# this needs to run as root
if [ $(id -u) != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

# this is the script that replaces part of the bootstrap code in the feeder image.
# let's first make sure that we mark this as an app, not an image:
touch /opt/adsb/app.adsb.feeder.image

# the original install code didn't setup Python requests
# so let's cheat and do that here
source /etc/os-release
if (( $VERSION_ID < 12 )) ; then
	pip3 install -U requests
else
	apt-get install -y python3-requests
fi

cd /opt/adsb/config
cat /opt/adsb/docker.image.versions >> .env
echo "_ADSBIM_BASE_VERSION=$(cat /opt/adsb/adsb.im.version)" >> .env
echo "_ADSBIM_CONTAINER_VERSION=$(cat /opt/adsb/adsb.im.version)" >> .env
echo "AF_WEBPORT=1099" >> .env
echo "AF_TAR1090_PORT=1090" >> .env
echo "AF_UAT978_PORT=1091" >> .env
echo "AF_PIAWAREMAP_PORT=1092" >> .env
echo "AF_PIAWARESTAT_PORT=1093" >> .env
echo "AF_DAZZLE_PORT=1094" >> .env

if [ ! -f /opt/adsb/feeder-image.name ] ; then
	echo "ADS-B Feeder app" > /opt/adsb/feeder-image-name
fi

# while the user is getting ready, let's try to pull the ultrafeeder docker
# container in the background -- that way startup will feel quicker
bash /opt/adsb/docker-pull.sh &

# finally, turn off this service
systemctl disable adsb-nonimage.service
