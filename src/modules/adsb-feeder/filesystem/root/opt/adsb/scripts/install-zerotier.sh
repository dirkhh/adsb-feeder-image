#!/bin/bash

if dpkg -s zerotier-one | grep -qs '^Status: install ok installed' ; then
    echo zerotier-one already installed
    exit 0
fi

# install and disable
# will be enabled by app.sh

DEBIAN_DISTRO=$(grep /etc/os-release -e VERSION_CODENAME | cut -d= -f2)

echo "deb http://download.zerotier.com/debian/${DEBIAN_DISTRO} ${DEBIAN_DISTRO} main" > /etc/apt/sources.list.d/zerotier.list

export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none

apt-get update
apt-get install -y -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef zerotier-one &
wait
systemctl disable --now zerotier-one
systemctl mask zerotier-one

# avoid unnecessary diskwrites by zerotier
ln -sf /dev/null /var/lib/zerotier-one/metrics.prom

