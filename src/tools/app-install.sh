#!/bin/bash

# install the adsb-setup app, the config files, and the services for use of
# the adsb-feeder on top of another OS.
# the script assumes that the dependencies are installed by the caller

USAGE="
 $0 arguments
  -s srcdir      # the git checkout parent dir
  -b branch      # the branch to use (default: main)
  -t tag         # alternatively the tag to use
  -d appdir      # where do the app files go (default: /opt/adsb)
  -c confdir     # where do the yml files and .env go (default: ${APP_DIR}/config)
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
        '-d') shift; APP_DIR=$1
            ;;
        '-c') shift; CONF_DIR=$1
            ;;
        *) echo "$USAGE"; exit 1 
    esac
    shift
done

if [ -z ${GIT_PARENT+x} ] ; then
    GIT_PARENT=$(mktemp -d)
    trap rm -rf "$GIT_PARENT" EXIT
fi
# shellcheck disable=SC2236
if [[ -z ${TAG+x} && -z ${BRANCH+x} ]] ; then
    BRANCH="main"
elif [[ ! -z ${TAG+x} && ! -z ${BRANCH+x} ]] ; then
    echo "Please set either branch or tag, not both"
    exit 1
fi
if [ ! -d "$APP_DIR" ] ; then
    if ! mkdir -p "$APP_DIR" ; then
        echo "failed to create $APP_DIR"
        exit 1
    fi
fi
# shellcheck disable=SC2236
if [[ ! -z ${CONFIG_DIR+x} && ! -d "$CONFIG_DIR" ]] ; then
    if ! mkdir -p "$CONFIG_DIR" ; then
        echo "failed to create $CONFIG_DIR"
        exit 1
    fi
fi

# now that we know that there isn't anything obviously wrong with
# the command line arguments, let's start by checking out the repo
if ! git clone 'https://github.com/dirkhh/adsb-feeder-image.git' "$GIT_PARENT_DIR"/adsb-feeder ; then
    echo "cannot check out the git repo to ${GIT_PARENT_DIR}"
    exit 1
fi
# shellcheck disable=SC2236
if [ ! -z ${BRANCH+x} ] ; then
    if ! git checkout "$BRANCH" ; then
        echo "cannot check out the branch ${BRANCH}"
        exit 1
    fi
else  # because of the sanity checks above we know that we have a tag
    if ! git checkout -b "$TAG" "$TAG" ; then
        echo "cannot check out the tag ${TAG}"
        exit 1
    fi
fi

# determine the version
SRC_ROOT="${GIT_PARENT_DIR}/adsb-feeder/src/modules/adsb-feeder/filesystem/root"
cd "$SRC_ROOT" || exit 1
DATE_COMPONENT=$(git log -20 --date=format:%y%m%d --format="%ad" | uniq -c | head -1 | awk '{ print $2"."$1 }')
TAG_COMPONENT=$(git describe --match "v[0-9]*" | cut -d- -f1)
if [ -z ${BRANCH+x} ] ; then
    VERSION="${TAG_COMPONENT}(main)-${DATE_COMPONENT}"
else
    VERSION="${TAG_COMPONENT}(${BRANCH})-${DATE_COMPONENT}"
fi

# copy the software in place
cp -a /adsb-feeder/src/modules/adsb-feeder/filesystem/root/opt/adsb /opt
cp -a "${SRC_ROOT}/opt/adsb/*" "${APP_DIR}/"
rm -rf "${SRC_ROOT}/usr/lib/systemd/system/adsb-bootstrap.service"
# shellcheck disable=SC2236
if [[ ! -z ${CONF_DIR+x} && "$CONF_DIR" != "${APP_DIR}/config" ]] ; then
    mkdir -p "$CONF_DIR"
    ln -s "$CONF_DIR" "${APP_DIR}/config"
fi
mkdir -p "${APP_DIR}/services"
cp -a "${SRC_ROOT}/usr/lib/systemd/system/*" "${APP_DIR}/services/"
cd "$APP_DIR" || exit 1
rm -rf "${GIT_PARENT_DIR}/adsb-feeder"

# set the 'image name' and version that are shown in the footer of the Web UI
if [ -d /boot/dietpi ] ; then
    if [ -f /boot/dietpi/.version ] ; then
        source /boot/dietpi/.version
        OS="DietPi ${G_DIETPI_VERSION_CORE}.${G_DIETPI_VERSION_SUB}"
    else
        OS="DietPi"
    fi
elif [ -f /etc/dist_variant ] ; then
    OS=$(</etc/dist_variant)
elif [ -f /etc/os-release ] ; then
    source /etc/os-release
    # shellcheck disable=SC2236
    if [ ! -z ${PRETTY_NAME+x} ] ; then
        OS="$PRETTY_NAME"
    elif [ ! -z ${NAME+x} ] ; then
        OS="$NAME"
    else
        OS="unrecognized OS"
    fi
else
    OS="unrecognized OS"
fi
echo "ADSB Feeder app running on ${OS}" > feeder-image.name
echo "$VERSION" > adsb.im.version
