#!/bin/bash
#
# pull the currently selected images -- simply a convenience wrapper

# this needs to run as root
if [ $(id -u) != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

# docker compose pull on all activated containers (and ultrafeeder even if not configured yet)
bash /opt/adsb/docker-compose-adsb pull &>>/opt/adsb/adsb-setup.log
