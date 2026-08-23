#!/bin/bash

if dpkg -s tailscale | grep -qs '^Status: install ok installed'; then
    echo tailscale already installed
    exit 0
fi

# install and disable
# will be enabled by app.sh

DEBIAN_DISTRO=$(grep /etc/os-release -e VERSION_CODENAME | cut -d= -f2)

curl -fsSL "https://pkgs.tailscale.com/stable/debian/${DEBIAN_DISTRO}.noarmor.gpg" | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL "https://pkgs.tailscale.com/stable/debian/${DEBIAN_DISTRO}.tailscale-keyring.list" | sudo tee /etc/apt/sources.list.d/tailscale.list

export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none

apt-get update
apt-get install -y -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef tailscale &
wait
systemctl disable --now tailscaled
systemctl mask tailscaled

# Disable telemetry for tailscale
# but only if it's not already there
if ! grep -q -- "^FLAGS=\"--no-logs-no-support" /etc/default/tailscaled; then
	sed -i 's/FLAGS=\"/FLAGS=\"--no-logs-no-support /' /etc/default/tailscaled
fi

