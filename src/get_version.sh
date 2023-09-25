#!/usr/bin/env bash
# are we running in a GitHub Action?
if [ "$GH_REF_TYPE" != "" ] ; then
    # echo "running in GitHub Action, triggered by push to $GH_REF_TYPE with value $GH_TRGT_REF"
    # create our elaborate version info
    if [ "$GH_REF_TYPE" = "tag" ] ; then
        TAG_COMPONENT="$GH_TRGT_REF"
        BRANCH_COMPONENT=""
    else
        TAG_COMPONENT=$(git describe --match "v[0-9]*" | cut -d- -f1)
        BRANCH_COMPONENT="($GH_TRGT_REF)"
    fi
else
    TAG_COMPONENT=$(git describe --match "v[0-9]*" | cut -d- -f1)
    BRANCH_COMPONENT="($(git branch --no-color --show-current))"
fi

DATE_COMPONENT=$(git log -30 --date=format:%y%m%d --format="%ad" | uniq -c | head -1 | awk '{ print $2"."$1 }')
echo -n "${TAG_COMPONENT}${BRANCH_COMPONENT}-${DATE_COMPONENT}"
