#!/bin/bash


# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

systemctl stop adsb-setup

sed -i '/_ADSBIM_STATE_IS_SECURE_IMAGE=True/d' /opt/adsb/config/.env
rm -f /opt/adsb/adsb.im.secure_image

systemctl restart adsb-setup

echo "----------------------"
echo "Secure Image DISABLED!"
echo "----------------------"
