#!/bin/bash
#
# this script can do some housekeeping tasks before the adsb-setup
# is (re)started

if [[ -f "/opt/adsb/finish-update.done" ]]; then
	# so we have completed one of the 'post 0.15' updates already.
	# let's see if the version changed (i.e. if this is another new update)
	# if not, then we ran this script already and can exit
	cmp /opt/adsb/finish-update.done /opt/adsb/adsb.im.version > /dev/null 2>&1 && exit 0
fi

# if we updated from a fairly old version, the feeder-update script will have written
# the new version into /etc, not /opt/adsb - if that's the case, simply move it
[[ -f /etc/adsb.im.version && ! -f /opt/adsb/adsb.im.version ]] && mv -f /etc/adsb.im.version /opt/adsb/adsb.im.version

NEW_VERSION=$(</opt/adsb/adsb.im.version)
echo "final housekeeping for the update to $NEW_VERSION" >> /var/log/adsb-setup.log

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
[[ -f /opt/adsb/config/.env ]] || cp /opt/adsb/.env /opt/adsb/config
# last resort
touch /opt/adsb/config/.env

# remember that we handled the housekeeping for this version
cp /opt/adsb/adsb.im.version /opt/adsb/finish-update.done
