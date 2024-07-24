#!/bin/bash

systemctl stop adsb-docker docker docker.socket
rm -rf /mnt/dietpi_userdata/docker-data /var/lib/docker
systemctl restart docker docker.socket adsb-docker


echo "Done."
echo "If you want to view the progress of container recreation, use this command:"
echo "tail -f /run/adsb-feeder-image.log"
