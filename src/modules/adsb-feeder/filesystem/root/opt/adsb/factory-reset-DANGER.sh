#!/bin/bash
systemctl stop adsb-setup

echo "FACTORY RESET" >> /run/adsb-feeder-image.log

/opt/adsb/docker-compose-adsb down
rm -f /opt/adsb/config/{.env,config.json};
rm -f /opt/adsb/init-complete
docker system prune -a -f

echo "FACTORY RESET DONE" >> /run/adsb-feeder-image.log

systemctl enable adsb-bootstrap.service
systemctl stop adsb-docker
systemctl restart adsb-bootstrap adsb-setup adsb-docker
