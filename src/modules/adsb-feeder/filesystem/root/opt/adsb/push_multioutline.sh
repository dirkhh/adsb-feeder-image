#!/bin/bash

# all errors will show a line number and the command used to produce the error
# shellcheck disable=SC2148,SC2164
SCRIPT_PATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd)/$(basename "$0")"
trap 'echo -e "[ERROR] $SCRIPT_PATH in line $LINENO when executing: $BASH_COMMAND"' ERR

# this needs to run as root
if [ "$(id -u)" != "0" ] ; then
    echo "this command requires superuser privileges - please run as sudo bash $0"
    exit 1
fi

# let's make sure we have shapely installed (it's not in the image by default since
# it's a huge dependency and only needed for the relatively rare stage 2 case)
python3 -c "import shapely" &>/dev/null || apt install -y python3-shapely

exec python3 /opt/adsb/adsb-setup/push_multioutline.py "$@"
