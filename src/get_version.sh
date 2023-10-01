#!/usr/bin/env bash
# are we running in a GitHub Action?
if [ "$GH_REF_TYPE" != "" ] ; then
    # echo "running in GitHub Action, triggered by push to $GH_REF_TYPE with value $GH_TRGT_REF"
    # create our elaborate version info
    if [ "$GH_REF_TYPE" = "tag" ] ; then
        TAG_COMPONENT="$GH_TRGT_REF"
        BETA=$(echo "$TAG_COMPONENT" | grep "beta")
        if [[ -n "$BETA" ]] ; then
            BRANCH_COMPONENT="(beta)"
        else
            BRANCH_COMPONENT="(stable)"
        fi
    else
        TAG_COMPONENT=$(git describe --match "v[0-9]*" --long | sed "s/-[0-9]*-g[0-9a-f]*//")
        BRANCH_COMPONENT="($GH_TRGT_REF)"
    fi
else
    TAG_COMPONENT=$(git describe --match "v[0-9]*" --long | sed "s/-[0-9]*-g[0-9a-f]*//")
    BRANCH_COMPONENT="($(git branch --no-color --show-current))"
    if [ "$BRANCH_COMPONENT" = "()" ] ; then
        BETA=$(echo "$TAG_COMPONENT" | grep "beta")
        if [[ -n "$BETA" ]] ; then
            BRANCH_COMPONENT="(beta)"
        else
            BRANCH_COMPONENT="(stable)"
        fi
    fi
fi
BRANCH_COMPONENT=${BRANCH_COMPONENT//(main)/(stable)}
DATE_COMPONENT=$(git log -30 --date=format:%y%m%d --format="%ad" | uniq -c | head -1 | awk '{ print $2"."$1 }')
echo -n "${TAG_COMPONENT}${BRANCH_COMPONENT}-${DATE_COMPONENT}"
