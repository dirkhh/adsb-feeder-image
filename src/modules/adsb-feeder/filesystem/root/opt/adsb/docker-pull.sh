#!/bin/bash
#
# pull the currently selected images -- simply a convenience wrapper

# this needs to run as root
if [ $(id -u) != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

# wait for chrony to sync so this doesn't fail due to certs
chronyc waitsync

# docker compose pull on all activated containers (and ultrafeeder even if not configured yet)
bash /opt/adsb/docker-compose-adsb pull &>>/run/adsb-feeder-image.log
