#!/bin/bash

function test_network() {
    gateway="$(ip route get 1.2.3.4 | awk '/via/ { print $3 }')"
    if ping -i 0 -c2 -w5 "${gateway}" &>/dev/null; then
        echo "gateway reachable via ping: ${gateway}"
        return 0
    fi
    if ping -c2 -w5 8.8.8.8 &>/dev/null; then
        echo "8.8.8.8 reachable via ping, ${gateway} not reachable via ping"
        return 0
    fi
    if curl --max-time 5 akamai.com &>/dev/null; then
        echo "akamai.com reachable via curl, 8.8.8.8 not reachable via ping, ${gateway} not reachable via ping"
        return 0
    fi
    return 1
}

FAILS=0

while sleep 120; do
    # don't check when adsb-hotspot is running
    HOTSPOT=$(systemctl is-active adsb-hotspot)
    if [[ "$HOTSPOT" == "activating" ]]; then
        continue
    fi

    if test_network; then
        # network is working, reset failure count
        FAILS=0
        continue
    fi

    # network is down!

    FAILS=$(( FAILS + 1 ))

    echo "Network doesn't seem to be working! Successive Failures: $FAILS"
    if (( FAILS >= 6 )); then
        echo "Rebooting"
        echo "$(date --rfc-3339=seconds): Rebooting after ${FAILS} failed attempts" >> /opt/adsb/logs/netdog.log
        reboot
    elif (( FAILS == 3 )); then
        if systemctl is-enabled NetworkManager &>/dev/null; then
            echo "Restarting NetworkManager"
            systemctl restart NetworkManager
        else
            echo "Restarting networking"
            systemctl restart networking
        fi
    fi
done
