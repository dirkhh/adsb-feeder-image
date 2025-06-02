#!/bin/bash

# acarshub
mkdir -p /opt/adsb/config/acarshub/
zstd -f --compress /run/acars_data/acarshub.rrd -o /opt/adsb/config/acarshub/acarshub.rrd.zst
zstd -f --compress /run/acars_data/messages.db -o /opt/adsb/config/acarshub/messages.db.zst

exit 0
