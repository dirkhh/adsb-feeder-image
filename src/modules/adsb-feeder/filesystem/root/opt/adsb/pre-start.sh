#!/bin/bash
#
# this script can do some housekeeping tasks before the adsb-setup
# is (re)started

if [ -f /opt/adsb/verbose ] ; then
	mkdir -p /opt/adsb/config
	mv /opt/adsb/verbose /opt/adsb/config/verbose
fi

ACTION="update to"
if [[ -f "/opt/adsb/finish-update.done" ]]; then
	# so we have completed one of the 'post 0.15' updates already.
	# let's see if the version changed (i.e. if this is another new update)
	# if not, then we ran this script already and can exit
	cmp /opt/adsb/finish-update.done /opt/adsb/adsb.im.version > /dev/null 2>&1 && exit 0
else
	ACTION="initial install of"
fi

# if we updated from a fairly old version, the feeder-update script will have written
# the new version into /etc, not /opt/adsb - if that's the case, simply move it
[[ -f /etc/adsb.im.version && ! -f /opt/adsb/adsb.im.version ]] && mv -f /etc/adsb.im.version /opt/adsb/adsb.im.version

NEW_VERSION=$(</opt/adsb/adsb.im.version)
echo "final housekeeping for the $ACTION $NEW_VERSION" >> /opt/adsb/adsb-setup.log

# remove any left-over apps and files from previous versions
USR_BIN_APPS=('docker-compose-start' 'docker-compose-adsb' 'docker-update-adsb-im' \
              'nightly-update-adsb-im' 'secure-image' 'identify-airspt' 'feeder-update')

for app in "${USR_BIN_APPS[@]}"; do
	[[ -f "/usr/bin/$app" ]] || continue
	[[ -f "/opt/adsb/$app" ]] && rm -f "/usr/bin/$app"
done

[[ -f /etc/adsb.im.version ]] && rm -f /etc/adsb.im.version

# make sure that we have a .env file so the setup app will start
# first make sure we have an /opt/adsb/config directory (or a link to one)
# once we have those two things in place, the setup app will successfully
# start and finish the rest of the work
[[ -d /opt/adsb/config ]] || mkdir -p /opt/adsb/config
cd /opt/adsb/config
if [ ! -f .env ] ; then
	cp /opt/adsb/docker.image.versions .env
	echo "_ADSBIM_BASE_VERSION=$(cat /opt/adsb/adsb.im.version)" >> .env
	echo "_ADSBIM_CONTAINER_VERSION=$(cat /opt/adsb/adsb.im.version)" >> .env
fi
if [ ! -f config.json ] ; then
	bash /opt/adsb/create-json-from-env.sh
fi

# remember that we handled the housekeeping for this version
cp /opt/adsb/adsb.im.version /opt/adsb/finish-update.done
