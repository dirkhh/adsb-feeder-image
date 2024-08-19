#!/bin/bash

if grep -qs -e '^Storage=persistent' /etc/systemd/journald.conf; then
    echo set-persistent.sh: already persistent, no actions performed
    exit 0
fi

# move over the existing log, if it doesn't work so be it
VARDIR="/var/log/journal/$(cat /etc/machine-id)"
mkdir -p "$VARDIR"
systemctl stop systemd-journald
cp -v -f -a "/run/log/journal/$(cat /etc/machine-id)"/system.journal "$VARDIR"

sed -i -e 's/.*Storage=.*/Storage=persistent/' "/etc/systemd/journald.conf"
sed -i -e 's/.*SystemMaxUse=.*/SystemMaxUse=128M/' /etc/systemd/journald.conf

systemctl restart systemd-journald

rm -rf /run/log/journal
