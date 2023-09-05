#!/bin/bash
#
# pull the currently selected images
cd /opt/adsb/config
[ "$1" = "-a" ] && ALL="1"

# first get the two we always need:
docker pull amir20/dozzle:latest >> docker-pull.log 2>&1
docker pull apline:latest >> docker-pull.log 2>&1

# then check if any other are enabled (but always get ULTRAFEEDER)
for image in $(grep "_CONTAINER=" .env); do
	pref=$(echo $image | cut -d_ -f1)
	if [ ! -z $ALL ] || [ "$pref" = "ULTRAFEEDER" ] ; then
		docker pull $(echo $image | cut -d= -f2) >> docker-pull.log 2>&1
	else
		if grep "$pref=True" .env > /dev/null 2>&1 ; then
			docker pull $(echo $image | cut -d= -f2) >> docker-pull.log 2>&1
		fi
	fi
done
