#!/bin/bash
#
# update the docker images to the latest "latest-build-xxx" instead of the pinned versions

NOW=$(date -Iseconds)
cd /opt/adsb || { echo "can't cd to /opt/adsb"; exit 1; }
cp docker.image.versions "docker.image.versions.${NOW}"
cd /opt/adsb/config || { echo "can't cd to /opt/adsb/config"; exit 1; }
cp .env "env.${NOW}"

for container_line in $(grep "_CONTAINER=" /opt/adsb/config/.env); do
	image=$(echo $container_line | cut -d= -f2 | cut -d: -f1)
	(echo "$image" | {
		IFS='/' read -r x user container
		if [[ $user == "sdr-enthusiasts" ]] ; then
			package_url="https://github.com/${user}/${container}/pkgs/container/{$container}/versions?filters%5Bversion_type%5D=tagged"
			latestbuild=$(curl -s "$package_url" | grep latest-build- | sed -E 's/.*tag=(latest-build-[0-9]+)".*/\1/' | sort | tail -1)
			sed -i "s|${image}|ghcr.io/${user}/${container}:${latestbuild}|" /opt/adsb/config/.env
			sed -i "s|${image}.*|ghcr.io/${user}/${container}:${latestbuild}|" /opt/adsb/docker.image.versions
			echo "ghcr.io/sdr-enthusiasts/$container:$latestbuild"
		fi
	})
done
