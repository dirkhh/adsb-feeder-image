#!/bin/bash
#
# based on https://github.com/wiedehopf/adsb-scripts/wiki/pingfail

umask 022

trap "exit" INT TERM
trap "kill 0" EXIT

TEST1="8.8.8.8" # consider making one of these addresses the VPN endpoint you are talking to
TEST2="1.1.1.1"
FAIL="no"

while sleep 300
do
    if ping "$TEST1" -c1 -w5 >/dev/null || ping "$TEST2" -c1 -w5 >/dev/null
    then
        FAIL="no"
    elif [[ "$FAIL" == yes ]]
    then
        if ! ping "$TEST1" -c5 -w20 >/dev/null && ! ping "$TEST2" -c5 -w20 >/dev/null
        then
            echo "$(date): Restarting network, could reach neither $TEST1 nor $TEST2" | tee -a /var/log/pingfail
            systemctl restart networking.service
            sleep 60
            if ! ping "$TEST1" -c5 -w20 >/dev/null && ! ping "$TEST2" -c5 -w20 >/dev/null
            then
                echo "$(date): Rebooting, could reach neither $TEST1 nor $TEST2" | tee -a /var/log/pingfail
                mkdir -p /run/systemd/system/reboot.target.d/
                cat > /run/systemd/system/reboot.target.d/fastreboot.conf <<"EOF"
[Unit]
JobTimeoutSec=60
JobTimeoutAction=reboot-force
EOF
                systemctl daemon-reload
                sync
                reboot
	        fi
        fi
        FAIL="no"
    else
        FAIL="yes"
    fi
done

