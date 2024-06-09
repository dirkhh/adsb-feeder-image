#!/bin/bash

# dietpi deletes and creates a new /etc/machine-id after systemd-journald starts up
# thus systemd-journald is writing to /var/log/journal/<old-machine-id>
# journalctl on the other hand tries to read from /var/log/journal/<new-machine-id>
# the log in the <old-machine-id> will be hard to access
# optimally this would be somehow patched into dietpi but let's do this workaround for now
# this workaround expects the journal to already be in /var/log and not in /run
# there should only be 1 folder in /var/log/journal in the unexpected case of multiple, just take a guess
mv "/var/log/journal/$(ls /var/log/journal/ | head -n1)" "/var/log/journal/$(cat /etc/machine-id)"
systemctl restart systemd-journald

# install chrony for better time synchronization compared to systemd-timesyncd
# when chrony is installed it's imperative that CONFIG_NTP_MODE=0
# (custom/disabled) is set in dietpi.txt to avoid breakage of dietpi-update
/boot/dietpi/func/dietpi-set_software ntpd-mode 0
apt install -y --no-install-recommends chrony

# copy the blocklisting code from Ramon Kolb's install-docker.sh script
# DOCKER-INSTALL.SH -- Installation script for the Docker infrastructure on a Raspbian or Ubuntu system
# Usage: source <(curl -s https://raw.githubusercontent.com/sdr-enthusiasts/docker-install/main/docker-install.sh)
#
# Copyright 2021-2023 Ramon F. Kolb (kx1t)- licensed under the terms and conditions
# of the MIT license. The terms and conditions of this license are included with the Github
# distribution of this package.


    BLOCKED_MODULES=("rtl2832_sdr")
    BLOCKED_MODULES+=("dvb_usb_rtl2832u")
    BLOCKED_MODULES+=("dvb_usb_rtl28xxu")
    BLOCKED_MODULES+=("dvb_usb_v2")
    BLOCKED_MODULES+=("r820t")
    BLOCKED_MODULES+=("rtl2830")
    BLOCKED_MODULES+=("rtl2832")
    BLOCKED_MODULES+=("rtl2838")
    BLOCKED_MODULES+=("dvb_core")
    echo -n "Getting the latest UDEV rules... "
    mkdir -p /etc/udev/rules.d /etc/udev/hwdb.d
    # First install the UDEV rules for RTL-SDR dongles
    curl -sL -o /etc/udev/rules.d/rtl-sdr.rules https://raw.githubusercontent.com/wiedehopf/adsb-scripts/master/osmocom-rtl-sdr.rules
    curl -sL -o /etc/udev/rules.d/dump978-fa.rules https://raw.githubusercontent.com/flightaware/dump978/master/debian/dump978-fa.udev
    # Now install the UDEV rules for SDRPlay devices
    curl -sL -o /etc/udev/rules.d/66-mirics.rules https://raw.githubusercontent.com/sdr-enthusiasts/install-libsdrplay/main/66-mirics.rules
    curl -sL -o /etc/udev/hwdb.d/20-sdrplay.hwdb https://raw.githubusercontent.com/sdr-enthusiasts/install-libsdrplay/main/20-sdrplay.hwdb
    # Next, exclude the drivers so the dongles stay accessible
    echo -n "Excluding and unloading any competing RTL-SDR drivers... "
    UNLOAD_SUCCESS=true
    for module in "${BLOCKED_MODULES[@]}"
    do
        if ! grep -q "$module" /etc/modprobe.d/exclusions-rtl2832.conf
        then
          echo blacklist "$module" >>/etc/modprobe.d/exclusions-rtl2832.conf
          echo install "$module" /bin/false >>/etc/modprobe.d/exclusions-rtl2832.conf
          modprobe -r "$module" 2>/dev/null || UNLOAD_SUCCESS=false
        fi
    done
    # Rebuild module dependency database factoring in blacklists
    which depmod >/dev/null 2>&1 && depmod -a  >/dev/null 2>&1 || UNLOAD_SUCCESS=false
    # On systems with initramfs, this needs to be updated to make sure the exclusions take effect:
    which update-initramfs >/dev/null 2>&1 && update-initramfs -u  >/dev/null 2>&1 || true

    if [[ "${UNLOAD_SUCCESS}" == false ]]; then
      echo "INFO: Although we've successfully excluded any competing RTL-SDR drivers, we weren't able to unload them. This will remedy itself when you reboot your system after the script finishes."
    fi

    echo "Deactivating biastees possibly turned on by kernel driver, device not found errors are expected:"
    for i in 0 1 2 3; do rtl_biast -d "$i" -b 0; done
    echo "Deactivation of biastees completed."


#
# End of Ramon Kolb's docker-install.sh
#
git clone 'https://github.com/dirkhh/adsb-feeder-image.git' /tmp/adsb-feeder
cd /tmp/adsb-feeder
git checkout GIT_COMMIT_SHA  # <- gets replaced before use
mv -v /tmp/adsb-feeder/src/modules/adsb-feeder/filesystem/root/usr/lib/systemd/system/* /usr/lib/systemd/system/
mv -v /tmp/adsb-feeder/src/modules/adsb-feeder/filesystem/root/opt/adsb /opt/
cd /opt/adsb
rm -rf /tmp/adsb-feeder
echo "FEEDER_IMAGE_NAME" > /opt/adsb/feeder-image.name  # <- gets replaced before use
echo "FEEDER_IMAGE_VERSION" > /opt/adsb/adsb.im.version # <- gets replaced before use
touch /opt/adsb/os.adsb.feeder.image
touch /opt/adsb/adsb.im.passwd.and.keys
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
systemctl enable --now adsb-setup.service
systemctl enable --now adsb-docker.service
systemctl enable --now adsb-update.timer

# make sure the VPN services are stopped and disabled
systemctl stop zerotier-one.service
systemctl stop tailscaled.service
systemctl disable zerotier-one.service
systemctl disable tailscaled.service

