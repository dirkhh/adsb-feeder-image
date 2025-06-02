#!/bin/bash

# acarshub
mkdir -p /run/acars_data
zstd -f --decompress /opt/adsb/config/acarshub/acarshub.rrd.zst -o /run/acars_data/acarshub.rrd
zstd -f --decompress /opt/adsb/config/acarshub/messages.db.zst -o /run/acars_data/messages.db

exit 0
