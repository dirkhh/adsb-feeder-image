#!/command/with-contenv bash
# shellcheck shell=bash disable=SC2028

# Regular Expressions
# shellcheck disable=SC1112
REGEX_PATTERN_VALID_EMAIL_ADDRESS='^[a-z0-9!#$%&*+=?^_‘{|}~-]+(?:\.[a-z0-9!$%&*+=?^_{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$'
REGEX_PATTERN_FR24_SHARING_KEY='^\+ Your sharing key \((\w+)\) has been configured and emailed to you for backup purposes\.'
REGEX_PATTERN_FR24_RADAR_ID='^\+ Your radar id is ([A-Za-z0-9\-]+), please include it in all email communication with us\.'


# Temp files - created in one dir
TMPDIR_FR24SIGNUP="$(mktemp -d --suffix=.fr24signup)"
TMPFILE_FR24SIGNUP_EXPECT="$TMPDIR_FR24SIGNUP/TMPFILE_FR24SIGNUP_EXPECT"
TMPFILE_FR24SIGNUP_LOG="$TMPDIR_FR24SIGNUP/TMPFILE_FR24SIGNUP_LOG"


#wget https://repo-feed.flightradar24.com/rpi_binaries/fr24feed_1.0.46-1_armhf.tgz -O fr24feed.tgz
#tar xf fr24feed.tgz
#cp fr24feed_armhf/fr24feed /usr/local/bin/fr24feed
# just use the containers binary and hope that works
# if we go back to using a pinned version it will need to be the correct
# architecture as the container doesn't bring qemu anymore

COMMAND="/usr/local/bin/fr24feed --signup --configfile=/tmp/config.txt"
SPAWN_CMD="spawn $COMMAND"


function write_fr24_expectscript() {
    {
        echo '#!/usr/bin/env expect --'
        echo 'set timeout 120'
        echo "${SPAWN_CMD}"
        echo "sleep 3"
        echo 'expect "Step 1.1 - Enter your email address (username@domain.tld)\r\n$:"'
        echo "send -- \"${FR24_EMAIL}\n\""
        echo 'expect "Step 1.2"'
        echo 'expect "$:"'
        echo "send \"\r\""
        echo 'expect "Step 1.3 - Would you like to participate in MLAT calculations? (yes/no)$:"'
        echo "send \"no\r\""
        echo "expect \"Step 3.A - Enter antenna's latitude (DD.DDDD)\r\n\$:\""
        echo "send -- \"${FEEDER_LAT}\r\""
        echo "expect \"Step 3.B - Enter antenna's longitude (DDD.DDDD)\r\n\$:\""
        echo "send -- \"${FEEDER_LONG}\r\""
        echo "expect \"Step 3.C - Enter antenna's altitude above the sea level (in feet)\r\n\$:\""
        echo "send -- \"${FEEDER_ALT_FT}\r\""
        # TODO - Add better error handlin
        # eg: Handle 'Validating email/location information...ERROR'
        # Need some real-world failure logs
        echo 'expect "Would you like to continue using these settings?"'
        echo 'expect "Enter your choice (yes/no)$:"'
        echo "send \"yes\r\""
        echo 'expect "Step 4.1 - Receiver selection"'
        echo 'expect "Enter your receiver type"'
        echo "send \"4\r\""
        echo 'expect "Enter your connection type (1-2)$:"'
        echo "send \"1\r\""
        echo 'expect "$:"'
        echo "send \"127.0.0.1\r\""
        echo 'expect "$:"'
        echo "send \"30005\r\""
        echo 'expect "Step 5.1 - Would you like to enable RAW data feed on port 30334 (yes/*no*)$:"'
        echo "send \"no\r\""
        echo 'expect "Step 5.2 - Would you like to enable Basestation data feed on port 30003 (yes/no)$:"'
        echo "send \"no\r\""
        echo 'expect "Submitting form data...OK"'
        echo 'expect "+ Your sharing key ("'
        echo 'expect "+ Your radar id is"'
        echo 'expect "Saving settings"'
    } > "$TMPFILE_FR24SIGNUP_EXPECT"
}


# ========== MAIN SCRIPT ========== #

# Sanity checks
if ! echo "$FR24_EMAIL" | grep -P "$REGEX_PATTERN_VALID_EMAIL_ADDRESS" > /dev/null 2>&1; then
  echo "ERROR: Please set FR24_EMAIL to a valid email address (currently set to: $FR24_EMAIL)"
  exit 1
fi

# write out expect script
write_fr24_expectscript

echo "Starting signup process ...."

# run expect script & interpret output
if ! expect "$TMPFILE_FR24SIGNUP_EXPECT" 2>&1 | tee "$TMPFILE_FR24SIGNUP_LOG" ; then
  echo "ERROR: Problem running flightradar24 sign-up process :-("
  echo ""
  cat "$TMPFILE_FR24SIGNUP_LOG"
  exit 1
fi

# try to get sharing key
if grep -P "$REGEX_PATTERN_FR24_SHARING_KEY" "$TMPFILE_FR24SIGNUP_LOG" > /dev/null 2>&1; then
  FR24_SHARING_KEY=$(grep -P "$REGEX_PATTERN_FR24_SHARING_KEY" "$TMPFILE_FR24SIGNUP_LOG" | \
    sed -r "s/$REGEX_PATTERN_FR24_SHARING_KEY/\1/")
  echo "FR24_SHARING_KEY=$FR24_SHARING_KEY"
else
  echo "ERROR: Could not find flightradar24 sharing key :-("
  echo ""
  cat "$TMPFILE_FR24SIGNUP_LOG"
  exit 1
fi

# try to get radar ID
if grep -P "$REGEX_PATTERN_FR24_RADAR_ID" "$TMPFILE_FR24SIGNUP_LOG" > /dev/null 2>&1; then
  FR24_RADAR_ID=$(grep -P "$REGEX_PATTERN_FR24_RADAR_ID" "$TMPFILE_FR24SIGNUP_LOG" | \
    sed -r "s/$REGEX_PATTERN_FR24_RADAR_ID/\1/")
  echo "FR24_RADAR_ID=$FR24_RADAR_ID"
else
  echo "ERROR: Could not find flightradar24 radar ID :-("
  echo ""
  cat "$TMPFILE_FR24SIGNUP_LOG"
  exit 1
fi

# clean up
rm -r "$TMPDIR_FR24SIGNUP"
