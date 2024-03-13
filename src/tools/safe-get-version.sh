#!/bin/bash

# get the latest version for the branch "$1"

# this will not be an issue with a single person using the sources,
# but a server backend might run this many times in parallel, so we
# need to make sure it's synchronized.

# this is designed to run on Linux (or in a container most likely),
# so we assume that a /data directory exists or can be created
# sorry - this doesn't work on macOS :)

if [[ -z "$1" ]] ; then
     >&2 echo "$0 requires an argument indicating the branch to check"
    exit 1
fi

if [[ -d /data ]] && touch "/data/t.$BASHPID" &> /dev/null ; then
    rm -f "/data/t.$BASHPID"
else
    >&2 echo "$0 requires write access to /data"
    exit 1
fi

lockdir=/data/adsb-version.lock
while true
do
    if mkdir -- "$lockdir" &> /dev/null
    then
        # the floor is ours
        # remove lock when this scripts exits for any reason
        trap 'rm -rf -- "$lockdir"' 0
        break
    else
        # someone else is here, let's wait and try again
        sleep "0.$RANDOM"
    fi
done

# finally, do the actual work
if ! cd /data/adsb-feeder-image &> /dev/null ; then
    cd /data || exit 1
    git clone https://github.com/dirkhh/adsb-feeder-image
    cd adsb-feeder-image || exit 1
fi
(
    git checkout "$1"
    git reset --hard HEAD~50
    git fetch --tags -f
    git pull
) > /dev/null 2>&1
bash src/get_version.sh | sed 's/)-.*/)/'
