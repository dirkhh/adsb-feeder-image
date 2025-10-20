#!/bin/bash

echo
echo RUNNING COMPOSE DOWN
echo

/opt/adsb/docker-compose-adsb down
docker system prune -a

DEV=eth0
if [[ -n $1 ]]; then
    DEV=$1
fi

echo
echo "pulling each container and printing how much RX occured on interface $DEV"
echo

function test_image () {
    image=$1
    bytes_before=$(grep </proc/net/dev $DEV | awk '{print $2}')
    docker pull -q $image &>/dev/null || echo ERROR
    bytes_after=$(grep </proc/net/dev $DEV | awk '{print $2}')
    echo "$image $(( (bytes_after - bytes_before) / 1024 ))" | awk '{printf("%-80s %7.3f MBytes\n", $1, $2 / 1024.0)}'
}
for image in $(cat /opt/adsb/docker.image.versions | head -n-2 | cut -d= -f2); do
    #echo $image; docker inspect $image -f '{{json .RootFS.Layers}}' | jq '.[]' | grep ce368d
    test_image $image
done
echo
echo "printing SHA for the 2nd layer of each container (should be the same for most SDR-E containers)"
echo

# check if baseimage layer is the same for all:
for image in $(cat /opt/adsb/docker.image.versions | head -n-2 | cut -d= -f2); do echo $image; docker inspect $image -f '{{json .RootFS.Layers}}' | jq '.[1]'; done


/opt/adsb/docker-compose-adsb up -d
