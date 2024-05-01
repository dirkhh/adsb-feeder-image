#!/bin/bash
# CC0 - public domain

# We read the file
SANITISED_LOG=$(</opt/adsb/adsb-setup.log)

# We set vars to empty
SANITISE_VARS="FEEDER_LAT FEEDER_LONG ADSBLOL_UUID AF_MICRO_IP ULTRAFEEDER_UUID FEEDER_1090UK_API_KEY
FEEDER_ADSBHUB_STATION_KEY FEEDER_FR24_SHARING_KEY FEEDER_FR24_UAT_SHARING_KEY
FEEDER_PLANEWATCH_API_KEY FEEDER_RADARBOX_SHARING_KEY FEEDER_RV_FEEDER_KEY
_ADSB_STATE_SSH_KEY FEEDER_PIAWARE_FEEDER_ID FEEDER_RADARBOX_SHARING_KEY FEEDER_RADARBOX_SN
FEEDER_PLANEFINDER_SHARECODE FEEDER_OPENSKY_USERNAME FEEDER_OPENSKY_SERIAL FEEDER_HEYWHATSTHAT_ID"

# We set vars that cannot be empty, have to be stripped
IMPORTANT_VARS="FEEDER_LAT FEEDER_LONG AF_MICRO_IP"

# For each
for VAR in $SANITISE_VARS; do
  # We get the value of the variable
  MY_VAR=$(grep ^$VAR= /opt/adsb/config/.env | cut -d'=' -f2)
  # MY_VAR is empty, and it is one of FEEDER_LAT FEEDER_LONG ADSBLOL_UUID, bail out
  if [ -z "$MY_VAR" ] ; then
    if [[ "$IMPORTANT_VARS" == *"$VAR"* ]]; then
      # If we are here, it means that the variable is empty, and it is one of the important ones
      echo "WARNING: $VAR is empty, this is a critical variable, exiting"
    fi
  else
    echo "handling ${MY_VAR} for ${VAR}"
    SANITISED_LOG=$(echo "$SANITISED_LOG" | sed "s/${MY_VAR}/MY_REAL_${VAR}/g")
    # Otherwise we just strip it out, and put it back into SANITISED_LOG
  fi
done
# now get rid of anything that looks like an IP address
SANITISED_LOG=$(sed -r 's/((1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])\.){3}(1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])/<hidden-ip-address>/g' <<< $SANITISED_LOG)
# finally, replace everything that looks like a uuid
SANITISED_LOG=$(sed -r 's/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/<hidden-uuid>/g' <<< $SANITISED_LOG)
#
# Then we echo the sanitised log
echo "$SANITISED_LOG"

