#!/bin/bash

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

function test_network() {
    # is there a gateway?
    gateway=$(ip route | awk '/default/ { print $3 }')
    if [[ $gateway == "" ]]; then
       return 1
    fi
    if ping -c 1 -W 0.5 "$gateway" &> /dev/null ; then
        return 0
    fi
    if ping -c 1 -W 0.5 8.8.8.8 &> /dev/null ; then
        return 0
    fi
    return 1
}
function check_network() {
    for i in {1..20}; do
        sleep 1 &
        if test_network; then
            return 0
        fi
        wait
    done
    return 1
}

if check_network; then
    echo "we are able to ping ${gateway} or 8.8.8.8, no need to start an access point"
    exit 0
fi

# that's not good, let's try to start an access point

wlan=$(iw dev | grep Interface | cut -d' ' -f2)
if [[ $wlan == "" ]] ; then
    echo "No wireless interface detected, giving up"
    exit 1
fi

cp /opt/adsb/accesspoint/hostapd.conf /etc/hostapd/hostapd.conf
cp /opt/adsb/accesspoint/dhcpd.conf /etc/dhcp/dhcpd.conf
cp /opt/adsb/accesspoint/isc-dhcp-server /etc/default/isc-dhcp-server

if [[ $wlan != "wlan0" ]] ; then
    sed -i "s/wlan0/$wlan/g" /etc/default/isc-dhcp-server
    sed -i "s/wlan0/$wlan/g" /etc/hostapd/hostapd.conf
fi

systemctl unmask hostapd.service isc-dhcp-server.service
for service in hostapd.service isc-dhcp-server.service; do
    if systemctl is-enabled "$service"; then
        systemctl disable "$service"
    fi
done

while true; do
    echo "No internet connection detected, starting access point"
    python3 /opt/adsb/adsb-setup/hotspot-app.py "$wlan"

    if check_network; then
        # break outer loop as well if network tests good
        break
    fi
done

# systemctl disable takes 8 seconds for these 2 services,
# stopping them and masking them is sufficient to stop them from starting so do that instead
systemctl stop hostapd.service isc-dhcp-server.service
systemctl mask hostapd.service isc-dhcp-server.service

echo "successfully connected to network"
