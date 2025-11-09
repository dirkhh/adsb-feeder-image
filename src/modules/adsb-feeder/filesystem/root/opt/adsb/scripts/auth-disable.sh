#!/bin/bash

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

systemctl stop adsb-setup

TMP="$(mktemp config.json.XXXX)"
JSON="/opt/adsb/config/config.json"
SCRIPT='."_ADSBIM_WEB_AUTH_ENABLED" = false | ."_ADSBIM_APP_SECRET" = "" '
SCRIPT+='| ."_ADSBIM_WEB_AUTH_PASSWORD_HASH" = "" | ."_ADSBIM_WEB_AUTH_USERNAME" = ""'
jq < "$JSON" "$SCRIPT" > "$TMP" && mv "$TMP" "$JSON"
sed -i '/_ADSBIM_STATE_IS_SECURE_IMAGE=True/d' /opt/adsb/config/.env

systemctl restart adsb-setup

echo "----------------------"
echo "Authentication DISABLED!"
echo "----------------------"
