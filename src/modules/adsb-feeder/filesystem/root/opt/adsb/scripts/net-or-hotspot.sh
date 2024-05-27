#!/bin/bash

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

# is there a gateway?
gateway=$(ip route | awk '/default/ { print $3 }')

if [[ $gateway == "" ]] || ! ping -c 1 -W 1 "$gateway" &> /dev/null ; then
    # that's not good, let's try to start an access point
    wlan=$(iw dev | grep Interface | cut -d' ' -f2)
    if [[ $wlan == "" ]] ; then
        echo "No wireless interface detected, giving up"
        exit 1
    fi
    echo "No internet connection detected, starting access point"
    systemctl unmask hostapd.service
    systemctl unmask isc-dhcp-server.service
    if [[ $wlan != "wlan0" ]] ; then
        sed -i "s/wlan0/$wlan/g" /etc/default/isc-dhcp-server
        sed -i "s/wlan0/$wlan/g" /etc/hostapd/hostapd.conf
    fi
    while [[ ! -f /opt/adsb/continueboot ]]; do
        cp /opt/adsb/accesspoint/hostapd.conf /etc/hostapd/hostapd.conf
        cp /opt/adsb/accesspoint/dhcpd.conf /etc/dhcp/dhcpd.conf
        cp /opt/adsb/accesspoint/isc-dhcp-server /etc/default/isc-dhcp-server
        python3 /opt/adsb/adsb-setup/hotspot-app.py "$wlan"
    done
    # the hotspot creates that file to indicate we should continue, let's clean it up
    rm -f /opt/adsb/continueboot
    echo "successfully connected to network"
else
    echo "we are able to ping ${gateway}, no need to start an access point"
fi
