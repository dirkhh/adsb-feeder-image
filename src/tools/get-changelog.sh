#!/bin/bash

# get the changelog between $1 and $2 (we return this to the feeder so it
# can be displayed to the user)
if [ -d /data/changelogs ] ; then
    if [ -f "/data/changelogs/${1}-${2}" ] ; then
        cat "/data/changelogs/${1}-${2}"
        exit 0
    fi
else
    mkdir -p /data/changelogs
fi

# ok, so we don't have this one yet, no biggie, let's create it.
# for this we need to own the lock so we can modify the git tree
# this is designed to run on Linux (or in a container most likely)
# and plays well with the safe-get-version.sh script
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
        sleep "1.$RANDOM"
    fi
done

# finally, do the actual work
if ! cd /data/adsb-feeder-image &> /dev/null ; then
    cd /data || exit 1
    git clone https://github.com/dirkhh/adsb-feeder-image
    cd adsb-feeder-image || exit 1
fi
(
    git checkout beta
    git reset --hard HEAD~50
    git fetch --tags -f
    git pull
) > /dev/null 2>&1
bash src/tools/create-changelog.sh "$1" "$2" > "/data/changelogs/${1}-${2}"
cat "/data/changelogs/${1}-${2}"
