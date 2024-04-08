#!/usr/bin/env bash

function show_branch() {
    BETA=$(echo "$1" | grep "beta")
    ALPHA=$(echo "$1" | grep "alpha")
    if [[ -n "$BETA" ]] ; then
        BRANCH_COMPONENT="(beta)"
    elif [[ -n "$ALPHA" ]] ; then
        BRANCH_COMPONENT="(alpha)"
    else
        BRANCH_COMPONENT="(stable)"
    fi
    echo "$BRANCH_COMPONENT"
}
# are we running in a GitHub Action?
if [ "$GH_REF_TYPE" != "" ] ; then
    # echo "running in GitHub Action, triggered by push to $GH_REF_TYPE with value $GH_TRGT_REF"
    # create our elaborate version info
    if [ "$GH_REF_TYPE" = "tag" ] ; then
        TAG_COMPONENT="$GH_TRGT_REF"
        BRANCH_COMPONENT=$(show_branch "$TAG_COMPONENT")
    else
        TAG_COMPONENT=$(git describe --match "v[0-9]*" --long | sed "s/-[0-9]*-g[0-9a-f]*//")
        BRANCH_COMPONENT="($GH_TRGT_REF)"
    fi
else
    TAG_COMPONENT=$(git describe --match "v[0-9]*" --long | sed "s/-[0-9]*-g[0-9a-f]*//")
    BRANCH_COMPONENT="($(git branch --no-color --show-current))"
    if [ "$BRANCH_COMPONENT" = "()" ] ; then
        BRANCH_COMPONENT=$(show_branch "$TAG_COMPONENT")
    fi
fi
BRANCH_COMPONENT=${BRANCH_COMPONENT//(main)/(stable)}
DESCRIBE=$(git describe --match "v[0-9]*")
SHA_COMPONENT=${DESCRIBE//$TAG_COMPONENT/}
echo -n "${TAG_COMPONENT}${BRANCH_COMPONENT}${SHA_COMPONENT}"
