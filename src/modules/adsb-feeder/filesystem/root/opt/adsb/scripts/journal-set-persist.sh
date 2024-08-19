#!/bin/bash

if grep -qs -e '^Storage=persistent' /etc/systemd/journald.conf; then
    echo set-persistent.sh: already persistent, no actions performed
    exit 0
fi

# move over the existing log, if it doesn't work so be it
mkdir -p /var/log/journal
cp -f -a "/run/log/journal/$(cat /etc/machine-id)" /var/log/journal/

sed -i -e 's/.*Storage=.*/Storage=persistent/' "/etc/systemd/journald.conf"
sed -i -e 's/.*SystemMaxUse=.*/SystemMaxUse=128M/' /etc/systemd/journald.conf

systemctl restart systemd-journald

rm -rf /run/log/journal
