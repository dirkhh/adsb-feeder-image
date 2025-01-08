#!/bin/bash
# CC0 - public domain

set -E
trap 'echo "[ERROR] Error in line $LINENO when executing: $BASH_COMMAND"' ERR

SEPARATOR="
----------------------------------------------------------------------------------------------------------
"
# We read the file
# and also append a bunch of other diagnostic info
SANITIZED_LOG="
important:
$(jq < /opt/adsb/config/config.json '{ version: ._ADSBIM_BASE_VERSION, board: ._ADSBIM_STATE_BOARD_NAME, user_env: ._ADSBIM_STATE_EXTRA_ENV, user_ultrafeeder: ._ADSBIM_STATE_ULTRAFEEDER_EXTRA_ARGS }')
${SEPARATOR}
uname -a:
$(uname -a)
${SEPARATOR}
base_image:
$(cat /opt/adsb/feeder-image.name || echo "probably app install")
${SEPARATOR}
/etc/os-release:
$(cat /etc/os-release)
${SEPARATOR}
"

if ip -6 addr show scope global $(ip -j route get 1.2.3.4 | jq '.[0].dev' -r) | grep -v 'inet6 f' | grep -qs inet6; then
  if timeout 2 curl -sS -o /dev/null -6 https://google.com; then
    SANITIZED_LOG+="IPv6 is enabled and working."
  else
    SANITIZED_LOG+="IPv6 is enabled and BROKEN."
  fi
else
  SANITIZED_LOG+="IPv6 is disabled."
fi

SANITIZED_LOG+="
${SEPARATOR}
dmesg | grep -iE under.?voltage:
$(dmesg | grep -iE under.?voltage || true)
${SEPARATOR}
df:
$(df -h | grep -v overlay)
${SEPARATOR}
top -b -n1 | head -n20:
$(top -b -n1 | head -n20)
${SEPARATOR}
zramctl:
$(zramctl)
${SEPARATOR}
free -h:
$(free -h)
${SEPARATOR}
journal storage:
$( ( systemd-analyze cat-config systemd/journald.conf | grep ^Storage ; echo 'Storage=auto' ) | head -1 | cut -d= -f2)
${SEPARATOR}
cat /etc/docker/daemon.json:
$(cat /etc/docker/daemon.json)
${SEPARATOR}
docker ps:
$(timeout 4 docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}")
${SEPARATOR}
docker images:
$(timeout 4 docker images -a --format "{{.Repository}}:{{.Tag}}")
${SEPARATOR}
docker network ls:
$(timeout 4 docker network ls)
${SEPARATOR}
docker system df:
$(timeout 4 docker system df)
${SEPARATOR}
lsusb -vt:
$(timeout 4 lsusb -vt)
${SEPARATOR}
grep -e sdr_info /run/adsb-feeder-image.log:
$(grep -e sdr_info /run/adsb-feeder-image.log)
${SEPARATOR}
lsusb -v:
$(timeout 4 lsusb -v)
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
"

for oldlog in $(find /opt/adsb/logs -name adsb-setup.log.\* | sort | tail -n2); do

SANITIZED_LOG+="
${oldlog}:
$(zstdcat "$oldlog" || cat "$oldlog")
${SEPARATOR}
"

done

SANITIZED_LOG+="
adsb-setup.log:
$(</run/adsb-feeder-image.log)
${SEPARATOR}
"

# We set vars to empty
SANITIZE_VARS="FEEDER_LAT FEEDER_LONG ADSBLOL_UUID AF_MICRO_IP ULTRAFEEDER_UUID FEEDER_1090UK_API_KEY
FEEDER_ADSBHUB_STATION_KEY FEEDER_FR24_SHARING_KEY FEEDER_FR24_UAT_SHARING_KEY
FEEDER_PLANEWATCH_API_KEY FEEDER_RADARBOX_SHARING_KEY FEEDER_RV_FEEDER_KEY
FEEDER_PIAWARE_FEEDER_ID FEEDER_RADARBOX_SHARING_KEY FEEDER_RADARBOX_SN
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

# simple fixed string replacement using search-replace.py, search and replace strings are given as pairs of command line arguments
simple_replace=()
# regex replacements using perl, this is more consistent than sed due to always different sed versions
replace_args=()

# For each
for VAR in $SANITIZE_VARS; do
  # We get the value of the variable
  MY_VAR=$(grep -e "^${VAR}=" /opt/adsb/config/.env | sed -e 's/[^=]*=//')
  # MY_VAR is empty, and it is one of FEEDER_LAT FEEDER_LONG ADSBLOL_UUID, bail out
  if [ -z "$MY_VAR" ] ; then
    if [[ "$IMPORTANT_VARS" == *"$VAR"* ]]; then
      # If we are here, it means that the variable is empty, and it is one of the important ones
      echo "WARNING: $VAR is empty"
    fi
  else
    #echo "removing all references to ${VAR}"
    case "$MY_VAR" in
        None | True | False )
            continue
            ;;
    esac
    if grep -qs -F -e '$$' <<< "${MY_VAR}"; then
        # for the .env, $ is replaced with $$, undo this replacement
        MY_VAR_UNESCAPED="$(sed 's#\$\$#\$#g' <<< "${MY_VAR}")"
        simple_replace+=("${MY_VAR_UNESCAPED}" "MY_REAL_${VAR}")
    fi
    simple_replace+=("${MY_VAR}" "MY_REAL_${VAR}")
  fi
done
# replace --lat --lon arguments mainly from piaware log
replace_args+='s/--lat.[^ ]*/--lat <redacted>/g;'
replace_args+='s/--lon.[^ ]*/--lon <redacted>/g;'
# replace 'handling ssh_pub' messages
replace_args+='s/handling ssh_pub.*/handling ssh_pub <redacted>/;'
# replace old messages of saing the ssh key to config
replace_args+='s/_ADSB_STATE_SSH_KEY.*/_ADSB_STATE_SSH_KEY <redacted>/;'
# replace sshd pubkey messages
replace_args+='s/Accepted publickey.*/Accepted publickey <redacted>/;'
# replace dropbear pubkey messages
replace_args+='s/Pubkey auth.*/Pubkey auth <redacted>/;'
# now get rid of anything that looks like an IP address
replace_args+='s/((1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])\.){3}(1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])/<hidden-ip-address>/g;'
# finally, replace everything that looks like a uuid
replace_args+='s/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/<hidden-uuid>/g;'

perl -pe "${replace_args}" <<< "${SANITIZED_LOG}" | /opt/adsb/scripts/search-replace.py "${simple_replace[@]}"
