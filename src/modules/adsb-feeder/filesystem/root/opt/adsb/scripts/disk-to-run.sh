#!/bin/bash

# acarshub
mkdir -p /run/acars_data
if cd /run/acars_data; then
    ! [[ -f acarshub.rrd ]] && [[ -f /opt/adsb/config/acarshub/acarshub.rrd.zst ]] \
        && zstd -f --decompress /opt/adsb/config/acarshub/acarshub.rrd.zst -o acarshub.rrd.tmp \
        && mv -f acarshub.rrd.tmp acarshub.rrd
    if ! [[ -f messages.db ]]; then
        if [[ -f /opt/adsb/config/acarshub/messages.db ]]; then
            # restore current to-disk method of using vacuum into without compression
            cp /opt/adsb/config/acarshub/messages.db messages.db.tmp \
                && mv -v -f messages.db.tmp messages.db
        elif [[ -f /opt/adsb/config/acarshub/messages.db.zst ]]; then
            # restore old to-disk method of just copying an active DB which was pretty bad really
            zstd -f --decompress /opt/adsb/config/acarshub/messages.db.zst -o messages.db.tmp \
                && mv -f messages.db.tmp messages.db
        fi
    fi
    # remove temporary files in case the decompression failed half way
    rm -f messages.db.tmp
    rm -f acarshub.rrd.tmp
fi

exit 0
