#!/bin/bash

# this needs to run as root
if [ $(id -u) != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

# time for the radarbox hacks
# the rb container is setup to run on a Raspberry Pi and it reacts poorly (crashes)
# if it can't find certain information in the filesystem
# this is adapted from
# https://github.com/sdr-enthusiasts/docker-radarbox/blob/main/version_0.4.3_workarounds.md#version-043-workarounds
mkdir -p /opt/adsb/rb/thermal_zone0
if grep -i serial /proc/cpuinfo ; then
	sed -i '/FEEDER_RB_CPUINFO_HACK/d' /opt/adsb/config/.env
else
	if [ ! -f /opt/adsb/rb/cpuinfo ] ; then
		cat /proc/cpuinfo > /opt/adsb/rb/cpuinfo
		echo -e "Serial\t\t: $(echo $RANDOM$RANDOM $RANDOM$RANDOM | awk '{printf "%08x%08x", $1, $2 }')" >> /opt/adsb/rb/cpuinfo
	fi
	if ! grep FEEDER_RB_CPUINFO_HACK=/proc/cpuinfo /opt/adsb/config/.env &> /dev/null ; then
		sed -i '/FEEDER_RB_CPUINFO_HACK/d' /opt/adsb/config/.env
		echo "FEEDER_RB_CPUINFO_HACK=/proc/cpuinfo" >> /opt/adsb/config/.env
	fi
fi
if [ -f /sys/class/thermal/thermal_zone0/temp ] ; then
	sed -i "/FEEDER_RB_THERMAL_HACK/d" /opt/adsb/config/.env
else
	if [ ! -f /opt/adsb/rb/thermal_zone0/temp ] ; then
		echo 12345 > /opt/adsb/rb/thermal_zone0/temp
	fi
	if ! grep 'FEEDER_RB_THERMAL_HACK=/sys/class/thermal$' /opt/adsb/config/.env &> /dev/null ; then
		sed -i "/FEEDER_RB_THERMAL_HACK/d" /opt/adsb/config/.env
		echo "FEEDER_RB_THERMAL_HACK=/sys/class/thermal" >> /opt/adsb/config/.env
	fi
fi
