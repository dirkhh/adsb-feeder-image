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
fi

host_name="$1"
host_name_no_dash="${host_name//-/}"
# ensure that the local hosts file includes the hostname
if ! grep -q "$host_name" /etc/hosts ; then
    echo "127.0.2.1 $host_name" >> /etc/hosts
fi

names=("${host_name}.local" "${host_name_no_dash}.local" "adsb-feeder.local")
echo "set up mDNS aliases: ${names[@]}"
service_names=()
for name in "${names[@]}"; do
    service_name="adsb-avahi-alias@${name}.service"
    service_names+=("${service_name}")
    # is-active returns true when the service is started, in that case we don't need to do anything
    if ! systemctl is-active --quiet "${service_name}" ; then
        systemctl enable "${service_name}"
        systemctl restart "${service_name}"
    fi
done

systemctl list-units | grep '^\s*adsb-avahi-alias@' | awk '{print $1}' | \
    while read -r unit; do
        wanted="no"
        for service_name in "${service_names[@]}"; do
            if [[ "${service_name}" == "${unit}" ]]; then
                wanted="yes"
            fi
        done
        if [[ "${wanted}" == "no" ]]; then
            # unit no longer needed, disable it
            systemctl disable --now "${unit}"
        fi
    done
