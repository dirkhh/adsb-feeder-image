#!/bin/bash
#
# pull the currently selected images
for image in $(grep "_CONTAINER=" .env); do
	docker pull $(echo $image | cut -d= -f2) >> docker-pull.log 2>&1
done
