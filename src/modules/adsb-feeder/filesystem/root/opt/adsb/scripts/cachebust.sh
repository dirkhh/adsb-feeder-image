#!/bin/bash

set -e
trap 'echo "[ERROR] Error in line $LINENO when executing: $BASH_COMMAND"' ERR

if [[ -f /opt/adsb/.cachebust_done ]]; then
    # cachebust has already run
    exit 0
fi

ORIG=/opt/adsb-feeder-update/adsb-feeder-image/src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/
if ! [[ -d "$ORIG" ]]; then
    # if this is not an update, use the original files
    ORIG=/opt/adsb/adsb-setup/
fi
# move unmodified files to staging directories
cp -T -f -a "$ORIG/static" /opt/adsb/adsb-setup/static-staging
cp -T -f -a "$ORIG/templates" /opt/adsb/adsb-setup/templates-staging

# ignore woff2 files they should not change anyhow, this makes this code simpler as the woff2 files
# are referred to from a css file
STATIC="$(find /opt/adsb/adsb-setup/static-staging/ -type f |  grep -v -e '\.License$' -e '\.ico$' -e '\.map$' -e '\.woff2$')"

sedreplaceargs=()

while read -r FILE; do
    md5sum=$(md5sum "$FILE" | cut -d' ' -f1)
    dir="$(dirname $FILE)"
    base="$(basename $FILE)"
    prefix="${base%.*}"
    postfix="${base##*.}"
    newname="${prefix}.${md5sum}.${postfix}"
    mv "$FILE" "$dir/$newname"
    sedreplaceargs+=("-e" "s#${base}#${newname}#")
done <<< "$STATIC"

#echo "${sedreplaceargs[@]}"
for FILE in /opt/adsb/adsb-setup/templates-staging/*.html; do
    sed -i "${sedreplaceargs[@]}" "$FILE"
done

rm -rf /opt/adsb/adsb-setup/static-old /opt/adsb/adsb-setup/templates-old

mv /opt/adsb/adsb-setup/static /opt/adsb/adsb-setup/static-old
mv /opt/adsb/adsb-setup/static-staging /opt/adsb/adsb-setup/static

mv /opt/adsb/adsb-setup/templates /opt/adsb/adsb-setup/templates-old
mv /opt/adsb/adsb-setup/templates-staging /opt/adsb/adsb-setup/templates

rm -rf /opt/adsb/adsb-setup/static-old /opt/adsb/adsb-setup/templates-old
