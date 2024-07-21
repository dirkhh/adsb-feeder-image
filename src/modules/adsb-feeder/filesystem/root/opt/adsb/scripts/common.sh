#!/bin/bash
#
# common set of boilerplate for shell scripts

l_scriptname="$0"

# this needs to run as root
function rootcheck()
{
    if [ $(id -u) != "0" ] ; then
        echo "this command requires superuser privileges - please run as sudo bash $0"
        exit 1
    fi
}

function logparent()
{
    # identify the calling process for better log messages
    PARENTPID=$(ps -cp $$ -o ppid="")
    if kill -0 "$PARENTPID" &> /dev/null ; then
        # shellcheck disable=SC2086 # the ps -q call fails with quotes around the variable
        PARENTPROC=$(ps -q$PARENTPID -o args=)
    else
        PARENTPROC="process $PARENTPID (appears already gone)"
    fi
    echo "$(date -u +"%FT%T.%3NZ") $PARENTPROC called $l_scriptname" "$@" >&2
}
