#!/usr/bin/env python3

import sys
import json

config = json.load(open("/opt/adsb/config/config.json", "r"))

sr = []

if (len(sys.argv) - 1) % 2 != 0:
    print("ERROR: even number of search replace pairs required!")
    sys.exit(1)

for i in range(int((len(sys.argv) - 1) / 2)):
    sr.append((sys.argv[2 * i + 1], sys.argv[2 * i + 2]))
    #print(f"{sr[-1]}")

sanitize_vars = [
    "FEEDER_LAT",
    "FEEDER_LONG",
    "MLAT_SITE_NAME",
    "MLAT_SITE_NAME_SANITIZED",
    "ADSBLOL_UUID",
    "AF_MICRO_IP",
    "ULTRAFEEDER_UUID",
    "FEEDER_1090UK_API_KEY",
    "ADSBLOL_LINK",
    "_ADSBIM_STATE_ALIVE_MAP_LINK",
    "_ADSBIM_STATE_ADSBX_FEEDER_ID",
    "FEEDER_ADSBHUB_STATION_KEY",
    "FEEDER_FR24_SHARING_KEY",
    "FEEDER_FR24_UAT_SHARING_KEY",
    "FEEDER_PLANEWATCH_API_KEY",
    "FEEDER_RADARBOX_SHARING_KEY",
    "FEEDER_RV_FEEDER_KEY",
    "FEEDER_PIAWARE_FEEDER_ID",
    "FEEDER_RADARBOX_SHARING_KEY",
    "FEEDER_RADARBOX_SN",
    "_ADSBIM_STATE_FEEDER_RADARBOX_SN_KEY",
    "FEEDER_PLANEFINDER_SHARECODE",
    "FEEDER_OPENSKY_USERNAME",
    "FEEDER_OPENSKY_SERIAL",
    "FEEDER_HEYWHATSTHAT_ID",
    "_ADSBIM_STATE_ZEROTIER_KEY",
    "_ADSBIM_STATE_TAILSCALE_LOGIN_LINK",
    "_ADSBIM_STATE_TAILSCALE_NAME",
    "FEEDER_SM_USERNAME",
    "FEEDER_SM_PASSWORD",
    "SKYSTATS_DB_PASSWORD",
]

for name in sanitize_vars:
    item = config[name]
    pairs = []
    if type(item) == list:
        count = 0
        for entry in item:
            pairs.append((entry, f"{name}_{count}"))
            count += 1
    else:
        pairs.append((item, name))

    for search, replace in pairs:
        if not search or search == True or search == False:
            continue
        search = str(search).strip()
        if not search:
            continue
        #print(f"{search} {replace}")
        sr.append((search, replace))
        # in the .env file, $ is escaped with $$, in the json $ is not escaped
        # thus in addition to the above replacement, we also need to replace
        # the escaped version if there is a $ in the string
        if "$" in search:
            search = search.replace("$", "$$")
            sr.append((search, replace))

for line in sys.stdin:
    for search, replace in sr:
        line = line.replace(search, replace)
    sys.stdout.write(line)

