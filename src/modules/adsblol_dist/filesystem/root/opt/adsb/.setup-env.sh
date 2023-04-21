#!/bin/bash

WORKING_DIR="$(dirname -- "${BASH_SOURCE[0]}")"
WORKING_DIR="$(cd -- "$WORKING_DIR" && pwd)"
if [ ! -f "$WORKING_DIR"/.env ] && [ -f /boot/adsblol.env ]; then
	cp /boot/adsblol.env "$WORKING_DIR"/.env
fi

if grep -q 00000000-0000-0000-0000-000000000000 "$WORKING_DIR"/.env ; then
	sed -i "s|^.*UUID=00000000-0000-0000-0000-000000000000|UUID=$(cat /proc/sys/kernel/random/uuid)|" "$WORKING_DIR"/.env
fi
