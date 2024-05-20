#!/bin/bash

# while the user is getting ready, let's try to pull the ultrafeeder docker
# container in the background -- that way startup will feel quicker

# this needs to run as root
if [ $(id -u) != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

# but we only want to run this once
lockFile="/opt/adsb/bootstrap.lock"
if ( set -o noclobber; echo "locked" > "$lockFile") 2> /dev/null; then
	trap 'rm -f "$lockFile"; exit $?' INT TERM EXIT
else
	echo "bootstrap.sh is already running" >&2
	exit
fi

# let's figure out if we have internet access
bash /opt/adsb/scripts/net-or-hotspot.sh

bash /opt/adsb/docker-pull.sh &

# the code below enables the redirection from the my.adsb.im service to the
# local feeder. this only needs to run if things aren't configured, yet
grep "AF_IS_BASE_CONFIG_FINISHED=True" /opt/adsb/config/.env &> /dev/null && exit 0

# get the local IP address
IP=$(ip route get 8.8.8.8 | sed -n '/src/{s/.*src *\([^ ]*\).*/\1/p;q}')

# slightly different approach in the rare cases where the first one fails
[[ -z "$IP" ]] && IP=$(ip route get 8.8.8.8 | sed -nr 's/^.* src ([0-9.]*).*/\1/p;q')

# this gets stopped and disabled by the setup app
while true; do
    curl "https://my.adsb.im/adsb-feeder.html?lip=${IP}" > /dev/null 2>&1
    sleep 60
done &
