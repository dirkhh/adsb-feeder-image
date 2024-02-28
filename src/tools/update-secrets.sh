#!/bin/bash

# this is hacky and not at all secure - but it's better than nothing

# little helper
function croak {
    >&2 echo "$@"
    exit 1
}

# run from the top directory
cd "$(dirname "${BASH_SOURCE[0]}")"/../.. || croak "cannot cd to top-level directory"

d="$HOME/.adsb.im.secrets"
mkdir -p "$d"

v=$(bash ./src/get_version.sh | sed 's/([^)]*)//g')
pu=$(openssl rand -base64 18 | tr -d /=+ | cut -c -16)
pr=$(openssl rand -base64 18 | tr -d /=+ | cut -c -16)
pk=$(openssl rand -base64 18 | tr -d /=+ | cut -c -16)
ssh-keygen -q -t ed25519 -C "adsb.im $v" -f "$d/$v" -N "$pk"
cat <<EOF > "$d/$v-secrets"
PU=${pu}
PR=${pr}
PK=${pk}
EOF

gh secret set ROOT_PASSWORD --app actions -r dirkhh/adsb-feeder-image -b "$pr"
gh secret set USER_PASSWORD --app actions -r dirkhh/adsb-feeder-image -b "$pu"
gh secret set SSH_KEY --app actions -r dirkhh/adsb-feeder-image < "$d/$v.pub"
