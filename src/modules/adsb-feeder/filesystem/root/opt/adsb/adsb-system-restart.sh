
#!/bin/bash

if [ ! -f /opt/adsb/init-complete ] ; then
	echo "first time adsb-system-restart: restart docker and stop bootstrap" 1>&2
	touch /opt/adsb/init-complete
	/usr/bin/systemctl daemon-reload
	/usr/bin/systemctl restart adsb-docker
	/usr/bin/systemctl disable adsb-bootstrap
	/usr/bin/systemctl disable adsb-init
	/usr/bin/systemctl stop adsb-bootstrap
	/usr/bin/systemctl stop adsb-init
else
	echo "adsb-system-restart: trigger docker compose up" 1>&2
	/opt/adsb/docker-compose-start
fi

