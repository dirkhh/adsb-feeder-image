#!/bin/bash

# while the user is getting ready, let's try to pull the docker container;
# that way startup will feel quicker
cd /opt/adsb
docker pull ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder > docker-pull.log 2>&1 &

# get the local IP address
IP=$(ip -4 ad li dev $(ip ro li | awk '/default/{ print $5 }') up | awk '/inet/{ print $2 }' | cut -d/ -f1)

skipcount=0
while true; do
    skipcount=$((skipcount + 1))
    if [ "1" = $((skipcount % 12)) ]; then  # about every minute...
        curl "http://adsb.khh.im/adsb-feeder.html?lip=${IP}" > /dev/null 2>&1
    fi
    if [ -f .web-setup.env ] ; then
        # yay - we have been configured - let's disable this service
        # and enable the docker app
        /usr/bin/systemctl disable adsb-bootstrap.service
        /usr/bin/systemctl enable adsb-docker.service
        /usr/bin/systemctl start adsb-docker.service
        break
    fi
    sleep 5
done
