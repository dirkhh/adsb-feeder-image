#!/bin/bash
systemctl stop adsb-setup

echo "FACTORY RESET" >> /opt/adsb/adsb-setup.log

/opt/adsb/docker-compose-adsb down
rm -f /opt/adsb/config/{.env,config.json};
rm -f /opt/adsb/init-complete
docker system prune -a -f

echo "FACTORY RESET DONE" >> /opt/adsb/adsb-setup.log

systemctl enable adsb-bootstrap.service
systemctl stop adsb-docker
systemctl restart adsb-bootstrap adsb-setup adsb-docker
