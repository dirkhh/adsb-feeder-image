#!/bin/bash

# while the user is getting ready, let's try to pull the docker container;
# that way startup will feel quicker
cd /opt/adsb
docker pull ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder > docker-pull.log 2>&1 &

# get the local IP address
IP=$(ip -4 ad li dev $(ip ro li | head -1 | awk '/default/{ print $5 }') up | awk '/inet/{ print $2 }' | cut -d/ -f1 | head -1)

# this gets stopped and disabled by the setup app
while true; do
    curl "https://my.adsb.im/adsb-feeder.html?lip=${IP}" > /dev/null 2>&1
    sleep 60
done
