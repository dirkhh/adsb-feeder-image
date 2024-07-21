#!/bin/bash

if [ ! -f /opt/adsb/scripts/common.sh ]
then
    echo "missing /opt/adsb/scripts/common.sh -- that's generally a bad sign"
else
    . /opt/adsb/scripts/common.sh
    rootcheck
    logparent
fi

if [ -L /opt/adsb/adsb-setup.log ] && [ -e /opt/adsb/adsb-setup.log ]
then
    # this is already a symlink, so likely this is redundant
    target=$(realpath /opt/adsb/adsb-setup.log)
    if [ "$target" = "/run/adsb-feeder-image/adsb-setup.log" ]
    then
        echo "looks like we already switched to logging to /run"
        exit 0
    else
        echo "logfile is symlink to $target, giving up"
        exit 1
    fi
else
    TIMESTAMP=$(date +%Y-%m-%d+%H:%M)
    # stop both adsb-setup and the adsb-setup-proxy
    systemctl stop adsb-setup
    /opt/adsb/docker-compose-adsb stop adsb-setup-proxy
    # copy the log file and create a symlink to tmpfs log
    mkdir -p /run/adsb-feeder-image
    if [ -f /run/adsb-feeder-image/adsb-setup.log ]
    then
        cp /run/adsb-feeder-image/adsb-setup.log /run/adsb-feeder-image/adsb-setup.log."$TIMESTAMP"
    fi
    cp /opt/adsb/adsb-setup.log /opt/adsb/adsb-setup.log."$TIMESTAMP"
    truncate -s 0 /run/adsb-feeder-image/adsb-setup.log
    ln -sf /run/adsb-feeder-image/adsb-setup.log /opt/adsb/adsb-setup.log
    systemctl start adsb-setup
    /opt/adsb/docker-compose-adsb start adsb-setup-proxy
fi
