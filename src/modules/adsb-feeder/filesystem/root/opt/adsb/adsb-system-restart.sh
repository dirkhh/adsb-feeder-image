#!/bin/bash

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

(
	if [[ ! -f /opt/adsb/init-complete && -f /opt/adsb/os.adsb.feeder.image ]] ; then
		# first time we do this on a Feeder Image, we need to do some more housekeeping
		echo "first time adsb-system-restart: restart docker and stop bootstrap" 2>&1
		touch /opt/adsb/init-complete
		/usr/bin/systemctl daemon-reload
		/usr/bin/systemctl restart adsb-docker
		/usr/bin/systemctl disable adsb-bootstrap
		/usr/bin/systemctl stop adsb-bootstrap
	else
		# if this isn't the first time we do a restart, or we are running as an app,
		# things are simpler (we are touching the flag file every time to make this
		# work both for the Feeder Image and when used as an app)
		touch /opt/adsb/init-complete
		echo "adsb-system-restart: trigger docker compose up" 2>&1
		/opt/adsb/docker-compose-start 2>&1
	fi
) | tee -a /opt/adsb/adsb-setup.log
