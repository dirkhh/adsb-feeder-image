#!/bin/bash
#
# set up the initial .env file to start from
cd /opt/adsb
if [ ! -f .env ] ; then
	cp docker.image.versions .env
	echo "_ADSBIM_BASE_VERSION=$(cat /etc/adsb.im.version)" >> .adsbim.env
	echo "_ADSBIM_CONTAINER_VERSION=$(cat /etc/adsb.im.version)" >> .adsbim.env
fi

# pull the Ultrafeeder container... do this in a loop in case networking isn't
# quite ready, yet.
while :
do
	docker pull $(grep "ULTRAFEEDER_CONTAINER=" docker.image.versions | cut -d= -f 2) && break
	sleep 5
done

