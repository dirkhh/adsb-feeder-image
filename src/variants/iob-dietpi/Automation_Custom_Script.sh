#!/bin/bash

# set up ADS-B Feeder as image (and not just as app)
# this only ever gets used on bookwork (or later)
apt install -y --no-install-recommends python3-flask python3-requests

# install chrony for better time synchronization compared to systemd-timesyncd
# when chrony is installed it's imperative that CONFIG_NTP_MODE=0
# (custom/disabled) is set in dietpi.txt to avoid breakage of dietpi-update
apt install -y --no-install-recommends chrony

git clone 'https://github.com/dirkhh/adsb-feeder-image.git' /tmp/adsb-feeder
cd /tmp/adsb-feeder
git checkout GIT_COMMIT_SHA  # <- gets replaced before use
mv /tmp/adsb-feeder/src/modules/adsb-feeder/filesystem/root/usr/lib/systemd/system/* /etc/systemd/system/
mv /tmp/adsb-feeder/src/modules/adsb-feeder/filesystem/root/opt/adsb /opt/
cd /opt/adsb
rm -rf /tmp/adsb-feeder
echo "FEEDER_IMAGE_NAME" > /opt/adsb/feeder-image.name  # <- gets replaced before use
echo "FEEDER_IMAGE_VERSION" > /opt/adsb/adsb.im.version # <- gets replaced before use
touch /opt/adsb/os.adsb.feeder.image
touch /opt/adsb/adsb.im.passwd.and.keys
cp ~root/.ssh/authorized_keys ~root/.ssh/adsb.im.installkey

# make sure all the ADS-B Feeder services are enabled and started
systemctl enable --now adsb-bootstrap.service
systemctl enable --now adsb-setup.service
systemctl enable --now adsb-docker.service
systemctl enable --now adsb-update.timer

# make sure the VPN services are stopped and disabled
systemctl stop zerotier-one.service
systemctl stop tailscaled.service
systemctl disable zerotier-one.service
systemctl disable tailscaled.service

