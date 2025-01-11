#!/bin/bash
# CC0 - public domain

set -E
trap 'echo "[ERROR] Error in line $LINENO"' ERR

SEPARATOR="
----------------------------------------------------------------------------------------------------------
"
# We read the file
# and also append a bunch of other diagnostic info
SANITIZED_LOG="
important:
$(jq '{ version: ._ADSBIM_BASE_VERSION, board: ._ADSBIM_STATE_BOARD_NAME, user_env: ._ADSBIM_STATE_EXTRA_ENV, user_ultrafeeder: ._ADSBIM_STATE_ULTRAFEEDER_EXTRA_ARGS }' /opt/adsb/config/config.json 2>&1)
${SEPARATOR}
uname -a:
$(uname -a)
${SEPARATOR}
base_image:
$(cat /opt/adsb/feeder-image.name 2>/dev/null || echo "probably app install")
${SEPARATOR}
/etc/os-release:
$(cat /etc/os-release 2>&1)
${SEPARATOR}
"

if ip -6 addr show scope global $(ip -j route get 1.2.3.4 | jq '.[0].dev' -r) | grep -v 'inet6 f' | grep -qs inet6; then
  if timeout 2 curl -sS -o /dev/null -6 https://google.com; then
    SANITIZED_LOG+="IPv6: working"
  else
    SANITIZED_LOG+="IPv6: BROKEN"
  fi
else
  if timeout 2 curl -sS -o /dev/null -6 https://google.com; then
    SANITIZED_LOG+="IPv6: working (but no global ipv6 address on primary route interface found)"
  else
    SANITIZED_LOG+="IPv6: no global address or disabled"
  fi
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
$(zramctl 2>&1)
${SEPARATOR}
free -h:
$(free -h 2>&1)
${SEPARATOR}
journal storage:
$( ( systemd-analyze cat-config systemd/journald.conf | grep ^Storage ; echo 'Storage=auto' ) | head -1 | cut -d= -f2 2>&1)
${SEPARATOR}
cat /etc/docker/daemon.json:
$(cat /etc/docker/daemon.json 2>&1)
${SEPARATOR}
docker ps:
$(timeout 4 docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" 2>&1)
${SEPARATOR}
docker images:
$(timeout 4 docker images -a --format "{{.Repository}}:{{.Tag}}" 2>&1)
${SEPARATOR}
docker network ls:
$(timeout 4 docker network ls 2>&1)
${SEPARATOR}
docker system df:
$(timeout 4 docker system df 2>&1)
${SEPARATOR}
lsusb -vt:
$(timeout 4 lsusb -vt 2>&1)
${SEPARATOR}
grep -e sdr_info /run/adsb-feeder-image.log:
$(grep -e sdr_info /run/adsb-feeder-image.log 2>&1)
${SEPARATOR}
lsusb -v:
$(timeout 4 lsusb -v 2>&1)
${SEPARATOR}
config.json:
$(cat /opt/adsb/config/config.json 2>&1)
${SEPARATOR}
.env:
$(cat /opt/adsb/config/.env 2>&1)
${SEPARATOR}
journalctl -e -n3000:
$(journalctl -e -n3000 2>&1)
${SEPARATOR}
"

for oldlog in $(find /opt/adsb/logs -name adsb-setup.log.\*zst | sort | tail -n2); do

SANITIZED_LOG+="
${oldlog}:
$(zstdcat "$oldlog" 2>&1)
${SEPARATOR}
"

done

SANITIZED_LOG+="
adsb-setup.log:
$(cat /run/adsb-feeder-image.log 2>&1)
${SEPARATOR}
"

# config variable replacement now done in search-replace.py
# search-replace also accepts argument pairs for search replace

# regex replacements using perl, this is more consistent than sed due to always different sed versions
replace_args=()

# replace --lat --lon arguments mainly from piaware log
replace_args+='s/--lat.[^ ]*/--lat <redacted>/g;'
replace_args+='s/--lon.[^ ]*/--lon <redacted>/g;'
# remove FA name from piaware log
replace_args+='s#flightaware.com/adsb/stats/user.*#flightaware.com/adsb/stats/user/<redacted>#g;'
replace_args+='s/FlightAware as user .*/FlightAware as user <redacted>/g;'
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

perl -pe "${replace_args}" <<< "${SANITIZED_LOG}" | /opt/adsb/scripts/search-replace.py "$(hostname)" HOSTNAME
