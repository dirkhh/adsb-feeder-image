#!/bin/bash
#
# if there is no config.json file in /opt/adsb/config, then we need to
# piece one together...

if [ ! -f /opt/adsb/scripts/common.sh ]
then
    echo "missing /opt/adsb/scripts/common.sh -- that's generally a bad sign"
else
    . /opt/adsb/scripts/common.sh
    rootcheck
    logparent
fi

if [ ! -f /opt/adsb/config/config.json ] ; then
    echo "create config.json file from scratch" >> /run/adsb-feeder-image.log
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
    \"_ADSBIM_CONTAINER_VERSION\": \"$_ADSBIM_BASE_VERSION\", \
    \"_ADSBIM_SEEN_CHANGELOG\": \"$_ADSBIM_SEEN_CHANGELOG\", \
    \"_ADSBIM_SHOW_CHANGELOG\": \"$_ADSBIM_SHOW_CHANGELOG\" \
    }" > /opt/adsb/config/config.json
fi
