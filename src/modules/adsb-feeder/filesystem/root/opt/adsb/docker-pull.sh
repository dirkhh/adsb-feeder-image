#!/bin/bash
#
# pull the currently selected images -- simply a convenience wrapper

# this needs to run as root
if [ $(id -u) != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

bash /opt/adsb/docker-compose-adsb pull

# pull ultrafeeder if we have no ultrafeeder version yet
# this is just for the first boot while the user configures the basics
if ! docker images | grep -qs docker-adsb-ultrafeeder; then
    source /opt/adsb/docker.image.versions
    docker pull "$ULTRAFEEDER_CONTAINER"
fi
