#!/bin/bash

# is there a gateway?
exec > >(tee -a /opt/adsb/bootstrap.log) 2>&1
set -x
gateway=$(ip route | awk '/default/ { print $3 }')

if [[ $gateway == "" ]] || ! ping -c 1 -W 1 "$gateway" &> /dev/null ; then
    # that's not good, let's start an access point
    echo "No internet connection detected, starting access point"
    systemctl unmask hostapd.service
    wlan=$(iw dev | grep Interface | cut -d' ' -f2)
    if [[ $wlan == "" ]] ; then
        echo "No wireless interface detected, giving up"
    exit 1
    fi
    if [[ $wlan != "wlan0" ]] ; then
        sed -i "s/wlan0/$wlan/g" /etc/default/isc-dhcp-server
        sed -i "s/wlan0/$wlan/g" /etc/hostapd/hostapd.conf
    fi
    ip li set "$wlan" up
    ip ad add 192.168.199.1/24 broadcast 192.168.199.255 dev "$wlan"
    cp /opt/adsb/accesspoint/hostapd.conf /etc/hostapd/hostapd.conf
    cp /opt/adsb/accesspoint/dhcpd.conf /etc/dhcp/dhcpd.conf
    cp /opt/adsb/accesspoint/isc-dhcp-server /etc/default/isc-dhcp-server
    systemctl start hostapd.service
    systemctl start isc-dhcp-server.service
    while true ; do sleep 60 ; done
fi
