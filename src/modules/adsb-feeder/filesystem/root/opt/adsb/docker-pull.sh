#!/bin/bash
#
# pull the currently selected images
cd /opt/adsb
for image in $(grep "_CONTAINER=" .env); do
	pref=$(echo $image | cut -d_ -f1)
	if [ "$pref" = "ULTRAFEEDER" ] ; then
		docker pull $(echo $image | cut -d= -f2) >> docker-pull.log 2>&1
	else
		if grep "$pref=1" .env > /dev/null 2>&1 ; then
			docker pull $(echo $image | cut -d= -f2) >> docker-pull.log 2>&1
		fi
	fi
done
