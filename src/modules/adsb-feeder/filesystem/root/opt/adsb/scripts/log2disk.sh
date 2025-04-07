#!/bin/bash

if [[ -f /run/adsb-feeder-image.log ]]; then
    TIMESTAMP=$(date +%Y-%m-%d+%H:%M:%S)
    mkdir -p /opt/adsb/logs
    zstd /run/adsb-feeder-image.log -o /opt/adsb/logs/adsb-setup.log."$TIMESTAMP".zst
    truncate -s 0 /run/adsb-feeder-image.log
    find /opt/adsb/logs -name adsb-setup.log.\* -ctime +7 | xargs rm -f
fi
