#!/bin/bash

# acarshub
if [[ -d /run/acars_data ]] && mkdir -p /opt/adsb/config/acarshub/ && cd /opt/adsb/config/acarshub; then
    zstd -f --compress /run/acars_data/acarshub.rrd -o acarshub.rrd.zst.tmp \
        && mv -f acarshub.rrd.zst.tmp acarshub.rrd.zst
    zstd -f --compress /run/acars_data/messages.db -o messages.db.zst.tmp \
        && mv -f messages.db.zst.tmp messages.db.zst
fi

exit 0
