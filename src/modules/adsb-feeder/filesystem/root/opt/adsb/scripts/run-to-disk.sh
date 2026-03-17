#!/bin/bash

# acarshub
if [[ -d /run/acars_data ]] && mkdir -p /opt/adsb/config/acarshub/ && cd /opt/adsb/config/acarshub; then
    if [[ -f /run/acars_data/acarshub.rrd ]]; then
        zstd -f --compress /run/acars_data/acarshub.rrd -o acarshub.rrd.zst.tmp \
            && mv -v -f acarshub.rrd.zst.tmp acarshub.rrd.zst
    fi
    if ! command -v sqlite3 &>/dev/null; then
        apt update
        apt install --no-install-recommends --no-install-suggests -y sqlite3
    fi
    rm -f messages.db.tmp
    # backup using vacuum into
    if [[ -f /run/acars_data/messages.db ]]; then
        sqlite3 /run/acars_data/messages.db "vacuum into 'messages.db.tmp';" \
            && mv -v -f messages.db.tmp messages.db
    fi
    # delete backup file used by previous iteration of this code
    rm -f messages.db.zst
fi

exit 0
