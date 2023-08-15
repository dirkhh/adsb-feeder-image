#!/bin/bash
#
# update the docker images to latest instead of the pinned versions

NOW=$(date -Iseconds)
cd /opt/adsb
cp .env "env.${NOW}"
cp docker.image.versions "docker.image.versions.${NOW}"
for container_line in $(grep "_CONTAINER=" .env); do
	image=$(echo $container_line | cut -d= -f2)
	latest="$(echo $image | cut -d@ -f1):latest"
	docker pull $latest >> docker-pull.log 2>&1
	new_container=$(docker inspect --format='{{.RepoDigests}}' $latest)
	new_container_line="${new_container:1:-1}"
	echo "->  $new_container_line"
	sed -i "s|${image}|${new_container_line}|" .env
	sed -i "s|${image}|${new_container_line}|" docker.image.versions
done

