#!/bin/bash

# DEPRECATED

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

/opt/adsb/docker-compose-start
