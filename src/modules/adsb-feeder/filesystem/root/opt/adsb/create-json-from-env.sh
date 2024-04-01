#!/bin/bash
#
# if there is no config.json file in /opt/adsb/config, then we need to
# piece one together...

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
	echo "this command requires superuser privileges - please run as sudo bash $0"
	exit 1
fi

# identify the calling process for better log messages
PARENTPID=$(ps -cp $$ -o ppid="")
if kill -0 "$PARENTPID" &> /dev/null ; then
	# shellcheck disable=SC2086 # the ps -q call fails with quotes around the variable
	PARENTPROC=$(ps -q$PARENTPID -o args=)
else
	PARENTPROC="process $PARENTPID (appears already gone)"
fi
echo "$PARENTPROC called $0" "$@" >> /opt/adsb/adsb-setup.log

if [ ! -f /opt/adsb/config/config.json ] ; then
    echo "create config.json file from scratch" >> /opt/adsb/adsb-setup.log
    source /opt/adsb/docker.image.versions
    _ADSBIM_BASE_VERSION=$(cat /opt/adsb/adsb.im.version)
	_ADSBIM_CONTAINER_VERSION=$(cat /opt/adsb/adsb.im.version)
    echo " \
    { \
    \"ULTRAFEEDER_CONTAINER\": \"$ULTRAFEEDER_CONTAINER\", \
    \"UAT978_CONTAINER\": \"$UAT978_CONTAINER\", \
    \"FR24_CONTAINER\": \"$FR24_CONTAINER\", \
    \"FA_CONTAINER\": \"$FA_CONTAINER\", \
    \"RB_CONTAINER\": \"$RB_CONTAINER\", \
    \"RV_CONTAINER\": \"$RV_CONTAINER\", \
    \"OS_CONTAINER\": \"$OS_CONTAINER\", \
    \"PF_CONTAINER\": \"$PF_CONTAINER\", \
    \"AH_CONTAINER\": \"$AH_CONTAINER\", \
    \"PW_CONTAINER\": \"$PW_CONTAINER\", \
    \"AIRSPY_CONTAINER\": \"$AIRSPY_CONTAINER\", \
    \"TNUK_CONTAINER\": \"$TNUK_CONTAINER\", \
    \"SDRPLAY_CONTAINER\": \"$SDRPLAY_CONTAINER\", \
    \"_ADSBIM_BASE_VERSION\": \"$_ADSBIM_BASE_VERSION\", \
    \"_ADSBIM_CONTAINER_VERSION\": \"$_ADSBIM_BASE_VERSION\" \
    }" > /opt/adsb/config/config.json
fi
