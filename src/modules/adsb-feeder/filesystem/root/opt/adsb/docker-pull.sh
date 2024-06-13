#!/bin/bash
#
# pull the currently selected images -- simply a convenience wrapper

# this needs to run as root
if [ $(id -u) != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

if ! docker images | grep -qs docker-adsb-ultrafeeder; then
    # pull ultrafeeder if we have no ultrafeeder version yet
    # this is just for the first boot while the user configures the basics
    source /opt/adsb/docker.image.versions
    for i in {1..3}; do
        docker pull "$ULTRAFEEDER_CONTAINER" && break
    done
fi

# do the regular docker compose pull on all activated containers
bash /opt/adsb/docker-compose-adsb pull
