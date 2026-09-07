#!/bin/bash

# thanks to iburakov on the dietpi forum for this script (used here slightly modified)
# https://dietpi.com/forum/t/using-ethernet-wlan-interfaces-not-at-the-same-time-in-v6-30/4251/6

ip link set eth0 up || echo "failed to bring eth0 up after boot"

LAST_CARRIER="0"
while sleep 3; do
	CARRIER=$(< /sys/class/net/eth0/carrier) || continue
	[[ "$CARRIER" == "$LAST_CARRIER" ]] && continue
	LAST_CARRIER="$CARRIER"
	if [ "$CARRIER" = "0" ]; then
		echo "carrier lost, running ifdown eth0"
		/sbin/ifdown eth0 --force 2>/dev/null
		ip link set eth0 up
		# ^ keep admin link state UP to detect re-insertion
		echo "down complete"
	else
		echo "carrier up, running ifup eth0"
		/sbin/ifup eth0 --force 2>/dev/null
		echo "up complete"
	fi
done
