#!/bin/bash

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

# only ever run this if this is an adsb.im feeder image - not when this is an app
if [[ ! -f /opt/adsb/os.adsb.feeder.image ]] ; then
    echo "don't run the avahi service when installed as app"
    exit 1
fi
if [ "$1" = "" ] ; then
    echo "usage: $0 <hostname>"
    exit 1
else
    host_name="$1"
    # ensure that the local hosts file includes the hostname
    if ! grep -q "$host_name" /etc/hosts ; then
        echo "127.0.2.1 $host_name" >> /etc/hosts
    fi
    echo "set up mDNS alias for $host_name"
    if systemctl is-active --quiet "adsb-avahi-alias@${host_name}.local.service" ; then
        systemctl restart "adsb-avahi-alias@${host_name}.local.service"
    else
        systemctl enable --now "adsb-avahi-alias@${host_name}.local.service"
    fi
fi
