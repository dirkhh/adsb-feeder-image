#!/bin/bash
systemctl stop adsb-setup

systemd-run -u adsb-log echo "FACTORY RESET"

systemd-run -u adsb-log /opt/adsb/docker-compose-adsb down
rm -f /opt/adsb/config/{.env,config.json};
rm -f /opt/adsb/init-complete
systemd-run -u adsb-log docker system prune -a -f

systemd-run -u adsb-log echo "FACTORY RESET DONE"

systemctl enable adsb-bootstrap.service
systemctl stop adsb-docker
systemctl restart adsb-bootstrap adsb-setup adsb-docker
