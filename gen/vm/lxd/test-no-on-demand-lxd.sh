#!/usr/bin/env bash
# The lab VM's provision step keeps Ubuntu's on-demand LXD installer out of the way: it is
# masked before the first apt-get, an install it already started finishes first, and an LXD
# it installed from its own channel is moved to the lab's.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
script=$root/gen/vm/scripts/00-base.sh
eval "$(sed -n '/^no_on_demand_lxd()/,/^}/p' "$script")"

tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
echo 2 > "$tmp/polls-left"    # an install under way for two polls (a file: the stub runs in a pipeline)
systemctl() { echo "systemctl $*" >> "$tmp/calls"; }
snap() {
    echo "snap $*" >> "$tmp/calls"
    [ "$1" = changes ] || return 0
    local left
    left=$(cat "$tmp/polls-left")
    echo 'ID   Status  Spawn               Ready               Summary'
    echo '3    Done    today at 20:36 UTC  today at 20:37 UTC  Install "astral-uv" snap'
    if [ "$left" -gt 0 ]; then
        echo $((left - 1)) > "$tmp/polls-left"
        echo '5    Doing   today at 20:37 UTC  -                   Install "lxd" snap from "5.21/stable/ubuntu-24.04" channel'
    else
        echo '5    Done    today at 20:37 UTC  today at 20:37 UTC  Install "lxd" snap from "5.21/stable/ubuntu-24.04" channel'
    fi
}
sleep() { echo "sleep $*" >> "$tmp/calls"; }

no_on_demand_lxd

test "$(head -1 "$tmp/calls")" = 'systemctl mask --now lxd-installer.socket'
test "$(grep -c '^sleep 2$' "$tmp/calls")" = 2      # it waited for the install under way
test "$(grep -c '^snap changes$' "$tmp/calls")" = 3

# in the script: called before the first apt-get, and an LXD from another channel is moved
call=$(grep -n -x 'no_on_demand_lxd' "$script" | head -1 | cut -d: -f1)
first_apt=$(grep -n '^apt-get ' "$script" | head -1 | cut -d: -f1)
test -n "$call" && test "$call" -lt "$first_apt"
grep -Fq 'snap refresh lxd --channel="$lxd_channel"' "$script"
echo 'PASS: no on-demand LXD install in the lab VM; one under way finishes first and is moved to the lab channel'
