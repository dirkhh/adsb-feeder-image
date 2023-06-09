#!/bin/bash

# while the user is getting ready, let's try to pull the remaining docker containers
# in the background -- that way startup will feel quicker
cd /opt/adsb
bash docker-pull.sh &

# get the local IP address
IP=$(ip -4 ad li dev $(ip ro li | head -1 | awk '/default/{ print $5 }') up | awk '/inet/{ print $2 }' | cut -d/ -f1 | head -1)

# this gets stopped and disabled by the setup app
while true; do
    curl "https://my.adsb.im/adsb-feeder.html?lip=${IP}" > /dev/null 2>&1
    sleep 60
done
