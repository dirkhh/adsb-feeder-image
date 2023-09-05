#!/bin/bash

# while the user is getting ready, let's try to pull the ultrafeeder docker
# container in the background -- that way startup will feel quicker
mkdir -p /opt/adsb/config
cd /opt/adsb/config
if [ ! -f .env ] ; then
	cp /opt/adsb/docker.image.versions .env
	echo "_ADSBIM_BASE_VERSION=$(cat /opt/adsb/adsb.im.version)" >> .env
	echo "_ADSBIM_CONTAINER_VERSION=$(cat /opt/adsb/adsb.im.version)" >> .env
fi
bash /opt/adsb/docker-pull.sh &

# get the local IP address
IP=$(ip -4 ad li dev $(ip ro li | head -1 | awk '/default/{ print $5 }') up | awk '/inet/{ print $2 }' | cut -d/ -f1 | head -1)

# this gets stopped and disabled by the setup app
while true; do
    curl "https://my.adsb.im/adsb-feeder.html?lip=${IP}" > /dev/null 2>&1
    sleep 60
done &
