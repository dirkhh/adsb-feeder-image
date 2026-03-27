#!/bin/bash

# while the user is getting ready, let's try to pull the ultrafeeder docker
# container in the background -- that way startup will feel quicker

# this needs to run as root
if [ $(id -u) != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

# but we only want to run this once
lockFile="/opt/adsb/bootstrap.lock"
if ( set -o noclobber; echo "locked" > "$lockFile") 2> /dev/null; then
    trap 'rm -f "$lockFile"; exit $?' INT TERM EXIT
else
    echo "bootstrap.sh is already running" >&2
    exit
fi

systemd-run -u adsb-docker-pull bash /opt/adsb/docker-pull.sh

