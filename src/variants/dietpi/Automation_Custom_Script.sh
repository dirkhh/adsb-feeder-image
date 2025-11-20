#!/bin/bash

# start waiting app in case this is after a kernel upgrade reboot during first boot
# if it's already running because the kernel wasn't updated,
# it will simply fail to grab the port and exit
python3 /opt/adsb/adsb-setup/waiting-app.py 80 /var/tmp/dietpi/logs/dietpi-firstrun-setup.log "Second boot of" &>>/run/adsb-feeder-image.log &

# avoid unnecessary diskwrites by zerotier
ln -sf /dev/null /var/lib/zerotier-one/metrics.prom

# override daemon.json with the options we want
cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "journald",
  "log-level": "warn",
  "userland-proxy": false,
  "debug": false
}
EOF

cat >> /etc/systemd/system.conf <<EOF
RuntimeWatchdogSec=15
RebootWatchdogSec=10min
EOF

# set random password for dietpi user
echo "dietpi:$(head -c 20 /dev/urandom | base64)" | chpasswd

# dietpi deletes and creates a new /etc/machine-id after systemd-journald starts up
# thus systemd-journald is writing to /var/log/journal/<old-machine-id>
# journalctl on the other hand tries to read from /var/log/journal/<new-machine-id>
# the log in the <old-machine-id> will be hard to access
# optimally this would be somehow patched into dietpi but let's do this workaround for now
# this workaround expects the journal to already be in /var/log and not in /run
# there should only be 1 folder in /var/log/journal in the unexpected case of multiple, just take a guess
systemctl stop systemd-journald
mkdir -p /var/log/journal
mv -v "/var/log/journal/$(ls /var/log/journal/ | head -n1)" "/var/log/journal/$(cat /etc/machine-id)"
systemctl restart systemd-journald && echo "journal should now be persistent"

# install chrony for better time synchronization compared to systemd-timesyncd
# when chrony is installed it's imperative that CONFIG_NTP_MODE=0
# (custom/disabled) is set in dietpi.txt to avoid breakage of dietpi-update
# to speed up the process, the other necessary image creation type installs
# are included here as well; the Python cryptography module is a bit of the odd one
# out, but having it here should work.
/boot/dietpi/func/dietpi-set_software ntpd-mode 0
apt install -y --no-install-recommends chrony ifplugd ifmetric python3-cryptography

# ifmetric ensures proper precedence for local network connections
# dhclient applies the metric setting from interfaces only to the default
# routes not to the other routes
#
# ifplugd will trigger on link state and up or down the interface
# ifplugd is required so ethernet works when the link is established after boot
sed -i  /etc/default/ifplugd \
    -e 's/^INTERFACES=.*/INTERFACES="eth0"/' \
    -e 's/^ARGS=.*/ARGS="-q -f -u2 -d2 -w -I --initial-down"/'
systemctl restart --no-block ifplugd

# ifplugd will handle eth0, not necessary for networking service to bring it up
sed -i -e 's/^allow-hotplug\s*eth0/#\0/' /etc/network/interfaces

# if no network is configured in wpa_supplicant.conf, disable wifi
# it will be re-enabled by the hotspot or in the webinterface (wifi.py)
if ! grep -qs -e 'network=' /etc/wpa_supplicant/wpa_supplicant.conf; then
    sed -i -e 's/^allow-hotplug\s*wlan0/#\0/' /etc/network/interfaces
fi

# instead of only allowing stepping the clock for 3 updates after startup,
# always step the clock if it's off by more than 0.5 seconds
sed -i -e 's/^makestep.*/makestep 0.5 -1/' /etc/chrony/chrony.conf
systemctl restart chrony

# most of the feeder image is already installed, we just do a few final steps that need
# to happen after first boot
cp ~root/.ssh/authorized_keys ~root/.ssh/adsb.im.installkey

# create a symlink so the config files reside where they should be in /mnt/dietpi_userdata/adsb-feeder
mkdir -p /mnt/dietpi_userdata/adsb-feeder/config
ln -s /mnt/dietpi_userdata/adsb-feeder/config /opt/adsb/

# move the services in place
mv -v /opt/adsb/usr/lib/systemd/system/* /usr/lib/systemd/system

ENV_FILE=/opt/adsb/config/.env
cp /opt/adsb/docker.image.versions "$ENV_FILE"
echo "_ADSBIM_BASE_VERSION=$(cat /opt/adsb/adsb.im.version)" >> "$ENV_FILE"
echo "_ADSBIM_CONTAINER_VERSION=$(cat /opt/adsb/adsb.im.version)" >> "$ENV_FILE"

# make sure all the ADS-B Feeder services are enabled and started
systemctl enable --now adsb-bootstrap.service

readarray -t services_enable < /opt/adsb/misc/services
readarray -t services_image < /opt/adsb/misc/services_image
services_enable+=( "${services_image[@]}" )
systemctl enable --now "${services_enable[@]}"
