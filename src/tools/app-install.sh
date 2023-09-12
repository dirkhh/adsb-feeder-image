#!/bin/bash

# install the adsb-setup app, the config files, and the services for use of
# the adsb-feeder on top of another OS.
# the script assumes that the dependencies are installed by the caller

USAGE="
 $0 arguments
  -s srcdir      # the git checkout parent dir
  -b branch      # the branch to use (default: main)
  -t tag         # alternatively the tag to use
"

APP_DIR="/opt/adsb"
BRANCH=""
CONF_DIR=""
GIT_PARENT_DIR=""
TAG=""

while (( $# ))
do
    case $1 in
        '-s') shift; GIT_PARENT_DIR=$1
            ;;
        '-b') shift; BRANCH=$1
            ;;
        '-t') shift; TAG=$1
            ;;
        *) echo "$USAGE"; exit 1 
    esac
    shift
done

if [[ $GIT_PARENT_DIR == '' ]] ; then
    GIT_PARENT_DIR=$(mktemp -d)
    # shellcheck disable=SC2064
    trap "rm -rf $GIT_PARENT_DIR" EXIT
fi
if [[ $TAG == '' && $BRANCH == '' ]] ; then
    BRANCH="main"
elif [[ $TAG != '' && $BRANCH != '' ]] ; then
    echo "Please set either branch or tag, not both"
    exit 1
fi
if [[ ! -d "$APP_DIR" ]] ; then
    if ! mkdir -p "$APP_DIR" ; then
        echo "failed to create $APP_DIR"
        exit 1
    fi
fi
if [[ $CONF_DIR != "" && ! -d "$CONF_DIR" ]] ; then
    if ! mkdir -p "$CONF_DIR" ; then
        echo "failed to create $CONF_DIR"
        exit 1
    fi
fi

# now that we know that there isn't anything obviously wrong with
# the command line arguments, let's ask the user if the dependencies
# are installed (checking this generically for any Linux distro
# seemd more work than it's likely worth)
MESSAGE="
 App installer for ADS-B Feeder
 ------------------------------

 Please confirm that you have
 - Docker
 - Docker compose module (not the old docker-compose app)
 - Python 3
 - Flask 2
 - git
 installed before continuing
"
QUESTION="(C)ontinue (S)top: "
echo "$MESSAGE"
while true; do
    read -r -p "$QUESTION" ans
    case $ans in
        [Cc]* ) echo ; echo "Continuing install" ; break;;
        [Ss]* ) echo ; echo "Please install missing components with system tools"; exit;;
        * ) echo "Please answer with 'c' or 's'" ;;
    esac
done

# ok, now we should have all we need, let's get started

if ! git clone 'https://github.com/dirkhh/adsb-feeder-image.git' "$GIT_PARENT_DIR"/adsb-feeder ; then
    echo "cannot check out the git repo to ${GIT_PARENT_DIR}"
    exit 1
fi

cd "$GIT_PARENT_DIR"/adsb-feeder

if [[ $BRANCH != '' ]] ; then
    if ! git checkout "$BRANCH" ; then
        echo "cannot check out the branch ${BRANCH}"
        exit 1
    fi
else  # because of the sanity checks above we know that we have a tag
    if ! git checkout "$TAG" ; then
        echo "cannot check out the tag ${TAG}"
        exit 1
    fi
fi

# determine the version
SRC_ROOT="${GIT_PARENT_DIR}/adsb-feeder/src/modules/adsb-feeder/filesystem/root"
cd "$SRC_ROOT" || exit 1
DATE_COMPONENT=$(git log -20 --date=format:%y%m%d --format="%ad" | uniq -c | head -1 | awk '{ print $2"."$1 }')
TAG_COMPONENT=$(git describe --match "v[0-9]*" | cut -d- -f1)
if [[ $BRANCH == '' ]] ; then
    ADSB_IM_VERSION="${TAG_COMPONENT}(main)-${DATE_COMPONENT}"
else
    ADSB_IM_VERSION="${TAG_COMPONENT}(${BRANCH})-${DATE_COMPONENT}"
fi

# copy the software in place
cp -a "${SRC_ROOT}/opt/adsb/"* "${APP_DIR}/"
rm -f "${SRC_ROOT}/usr/lib/systemd/system/adsb-bootstrap.service"
if [[ ${CONF_DIR} != '' && "$CONF_DIR" != "${APP_DIR}/config" ]] ; then
    mkdir -p "$CONF_DIR"
    ln -s "$CONF_DIR" "${APP_DIR}/config"
fi
cp -a "${SRC_ROOT}/usr/lib/systemd/system/"* "/usr/lib/systemd/system/"
rm -rf "${GIT_PARENT_DIR}/adsb-feeder"

# set the 'image name' and version that are shown in the footer of the Web UI
cd "$APP_DIR" || exit 1
if [[ -d /boot/dietpi ]] ; then
    if [[ -f /boot/dietpi/.version ]] ; then
        # shellcheck disable=SC1091
        source /boot/dietpi/.version
        OS="DietPi ${G_DIETPI_VERSION_CORE}.${G_DIETPI_VERSION_SUB}"
    else
        OS="DietPi"
    fi
elif [[ -f /etc/dist_variant ]] ; then
    OS=$(</etc/dist_variant)
elif [[ -f /etc/os-release ]] ; then
    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ $PRETTY_NAME != '' ]] ; then
        OS="$PRETTY_NAME"
    elif [[ $NAME != '' ]] ; then
        OS="$NAME"
    else
        OS="unrecognized OS"
    fi
else
    OS="unrecognized OS"
fi
echo "ADSB Feeder app running on ${OS}" > feeder-image.name
echo "$ADSB_IM_VERSION" > adsb.im.version

# run the final steps of the setup and then enable the services
systemctl daemon-reload
systemctl start adsb-nonimage
systemctl enable --now adsb-docker
systemctl enable --now adsb-setup

echo "done instaling"
