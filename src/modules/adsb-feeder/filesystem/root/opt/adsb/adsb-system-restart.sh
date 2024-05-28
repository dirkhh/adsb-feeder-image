#!/bin/bash

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

(
	if [[ ! -f /opt/adsb/init-complete ]]; then
        if [[ -f /opt/adsb/os.adsb.feeder.image ]] ; then
            echo "feeder image first time adsb-system-restart: stop bootstrap"
            systemctl disable adsb-bootstrap
            systemctl stop adsb-bootstrap
        fi
		touch /opt/adsb/init-complete
    fi
    echo "adsb-system-restart: trigger docker compose up"
    /opt/adsb/docker-compose-start
) 2>&1 | tee -a /opt/adsb/adsb-setup.log
