#!/bin/bash
# CC0 - public domain

SEPARATOR="
----------------------------------------------------------------------------------------------------------
"
# We read the file
# and also append a bunch of other diagnostic info
SANITIZED_LOG="
important:
$(jq < /opt/adsb/config/config.json '{ version: ._ADSBIM_BASE_VERSION, board: ._ADSBIM_STATE_BOARD_NAME, base: ._ADSBIM_BASE_VERSION, user_env: ._ADSBIM_STATE_EXTRA_ENV, user_ultrafeeder: ._ADSBIM_STATE_ULTRAFEEDER_EXTRA_ARGS }')
${SEPARATOR}
uname -a:
$(uname -a)
${SEPARATOR}
df:
$(df -h | grep -v overlay)
${SEPARATOR}
free -h:
$(free -h)
${SEPARATOR}
docker ps:
$(docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}")
${SEPARATOR}
docker images:
$(docker images -a --format "{{.Repository}}:{{.Tag}}")
${SEPARATOR}
docker network ls:
$(docker network ls)
${SEPARATOR}
docker system df:
$(docker system df)
${SEPARATOR}
lsusb -vt:
$(lsusb -vt)
${SEPARATOR}
lsusb -v:
$(lsusb -v)
${SEPARATOR}
config.json:
$(</opt/adsb/config/config.json)
${SEPARATOR}
.env:
$(</opt/adsb/config/.env)
${SEPARATOR}
journalctl -e -n3000:
$(journalctl -e -n3000)
${SEPARATOR}
adsb-setup.log:
$(</opt/adsb/adsb-setup.log)
${SEPARATOR}
"

# We set vars to empty
SANITIZE_VARS="FEEDER_LAT FEEDER_LONG ADSBLOL_UUID AF_MICRO_IP ULTRAFEEDER_UUID FEEDER_1090UK_API_KEY
FEEDER_ADSBHUB_STATION_KEY FEEDER_FR24_SHARING_KEY FEEDER_FR24_UAT_SHARING_KEY
FEEDER_PLANEWATCH_API_KEY FEEDER_RADARBOX_SHARING_KEY FEEDER_RV_FEEDER_KEY
_ADSB_STATE_SSH_KEY FEEDER_PIAWARE_FEEDER_ID FEEDER_RADARBOX_SHARING_KEY FEEDER_RADARBOX_SN
FEEDER_PLANEFINDER_SHARECODE FEEDER_OPENSKY_USERNAME FEEDER_OPENSKY_SERIAL FEEDER_HEYWHATSTHAT_ID"

# We set vars that cannot be empty, have to be stripped
IMPORTANT_VARS="FEEDER_LAT FEEDER_LONG AF_MICRO_IP"

NUM_MICRO_SITES=$(grep -e "^AF_NUM_MICRO_SITES=" /opt/adsb/config/.env | cut -d'=' -f2)


SANITIZE_VARS_ORIG="$SANITIZE_VARS"
IMPORTANT_VARS_ORIG="$IMPORTANT_VARS"

for i in $(seq $NUM_MICRO_SITES); do
    for VAR in $SANITIZE_VARS_ORIG; do
        SANITIZE_VARS+=" ${VAR}_${i}"
    done
    for VAR in $IMPORTANT_VARS_ORIG; do
        IMPORTANT_VARS+=" ${VAR}_${i}"
    done
done

# For each
for VAR in $SANITIZE_VARS; do
  # We get the value of the variable
  MY_VAR=$(grep -e "^${VAR}=" /opt/adsb/config/.env | cut -d'=' -f2)
  # MY_VAR is empty, and it is one of FEEDER_LAT FEEDER_LONG ADSBLOL_UUID, bail out
  if [ -z "$MY_VAR" ] ; then
    if [[ "$IMPORTANT_VARS" == *"$VAR"* ]]; then
      # If we are here, it means that the variable is empty, and it is one of the important ones
      echo "WARNING: $VAR is empty, this is a critical variable, exiting"
    fi
  else
    echo "removing all references to ${VAR}"
    SANITIZED_LOG=$(echo "$SANITIZED_LOG" | sed "s/${MY_VAR}/MY_REAL_${VAR}/g")
    # Otherwise we just strip it out, and put it back into SANITIZED_LOG
  fi
done
# print a new line do delineate our debug output above
echo
# now get rid of anything that looks like an IP address
SANITIZED_LOG=$(sed -r 's/((1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])\.){3}(1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])/<hidden-ip-address>/g' <<< $SANITIZED_LOG)
# finally, replace everything that looks like a uuid
SANITIZED_LOG=$(sed -r 's/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/<hidden-uuid>/g' <<< $SANITIZED_LOG)
#
# Then we echo the sanitised log
echo "$SANITIZED_LOG"

