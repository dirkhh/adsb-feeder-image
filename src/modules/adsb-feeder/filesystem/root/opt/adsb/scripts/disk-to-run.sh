#!/bin/bash

# acarshub
mkdir -p /run/acars_data
if cd /run/acars_data; then
    ! [[ -f acarshub.rrd ]] && [[ -f /opt/adsb/config/acarshub/acarshub.rrd.zst ]] \
        && zstd -f --decompress /opt/adsb/config/acarshub/acarshub.rrd.zst -o acarshub.rrd.tmp \
        && mv -f acarshub.rrd.tmp acarshub.rrd
    ! [[ -f messages.db ]] && [[ -f /opt/adsb/config/acarshub/messages.db.zst ]] \
        && zstd -f --decompress /opt/adsb/config/acarshub/messages.db.zst -o messages.db.tmp \
        && mv -f messages.db.tmp messages.db
    # remove temporary files in case the decompression failed half way
    rm -f messages.db.tmp
    rm -f acarshub.rrd.tmp
fi

exit 0
