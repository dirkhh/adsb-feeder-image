#!/bin/bash
#
# pull the currently selected images

# this needs to run as root
if [ $(id -u) != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

cd /opt/adsb/config
[ "$1" = "-a" ] && ALL="1"

function pull() {
    echo -n "$(date -u +"%FT%T.%3NZ") docker pull $@"
    docker pull -q "$@" 2>&1
}

# first get the two we always need:
pull amir20/dozzle:latest
pull alpine:latest

# then check if any other are enabled (but always get ULTRAFEEDER)
for image in $(grep "_CONTAINER=" .env); do
	pref=$(echo $image | cut -d_ -f1)
	if [ ! -z $ALL ] || [ "$pref" = "ULTRAFEEDER" ] ; then
		pull $(echo $image | cut -d= -f2)
	else
		if grep "$pref=True" .env > /dev/null 2>&1 ; then
			pull $(echo $image | cut -d= -f2)
		fi
	fi
done
