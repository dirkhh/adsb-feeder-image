#!/bin/bash
#
# set up the initial .env file to start from
if [ ! -f .env ] ; then
	cp docker.image.versions .env
fi

# pull the Ultrafeeder container... do this in a loop in case networking isn't
# quite ready, yet.
while :
do
	docker pull $(grep "ULTRAFEEDER_CONTAINER=" docker.image.versions | cut -d\   -f 1) && break
	sleep 5
done

