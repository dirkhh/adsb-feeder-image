#!/bin/bash

if dpkg -s netbird | grep -qs '^Status: install ok installed' ; then
    echo netbird already installed
    exit 0
fi

# install and disable
# will be enabled by app.sh

DEBIAN_DISTRO=$(grep /etc/os-release -e VERSION_CODENAME | cut -d= -f2)

curl -fsSL "https://pkgs.netbird.io/debian/public.key" | sudo gpg --dearmor -o /usr/share/keyrings/netbird-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/netbird-archive-keyring.gpg] https://pkgs.netbird.io/debian stable main" > /etc/apt/sources.list.d/netbird.list

export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none

apt-get update
apt-get install -y -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef netbird &
wait
systemctl disable --now netbird
rm -f /etc/systemd/system/netbird.service
