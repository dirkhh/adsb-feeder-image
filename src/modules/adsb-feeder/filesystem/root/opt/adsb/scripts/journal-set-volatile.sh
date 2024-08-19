#!/bin/bash

if grep -qs -e '^Storage=volatile' /etc/systemd/journald.conf; then
    echo set-volatile.sh: already volatile, no actions performed
    exit 0
fi

# move over the existing log, if it doesn't work so be it
mkdir -p /run/log/journal
if [[ $(du -s "/var/log/journal/$(cat /etc/machine-id)" | cut -f1) < 20000 ]]; then
    cp -f -a "/var/log/journal/$(cat /etc/machine-id)" /run/log/journal/
fi

sed -i -e 's/.*Storage=.*/Storage=volatile/' "/etc/systemd/journald.conf"
# use 1/50th of memory for journal, that's 20 MB per Gigabyte of memory
sed -i -e "s/.*RuntimeMaxUse=.*/RuntimeMaxUse=$(( $(cat /proc/meminfo | grep -i 'memtotal' | grep -o '[[:digit:]]*') / 50 ))K/" "/etc/systemd/journald.conf"

systemctl restart systemd-journald

rm -rf /var/log/journal
