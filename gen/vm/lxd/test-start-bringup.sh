#!/usr/bin/env bash
# build.sh start runs the lab's ordered bring-up after starting a stopped VM, and only then.
set -euo pipefail
# hermetic: not the lab a caller configured (lab-config.sh, as the suite and vm.md do)
unset EASYMESH_LAB_NAME EASYMESH_LXD_NAME EASYMESH_LXD_STORAGE EASYMESH_PORT_BASE EASYMESH_ROOM_DEMO_PORT \
    EASYMESH_WEBUI_PORT LAB_GRAFANA_PORT LAB_LXD_UI_PORT LAB_OUTER_METRICS_PORT WMEDIUMD_CONSOLE_PORT

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
eval "$(sed -n '/^start_vm() {/,/^}/p' "$root/gen/vm/lxd/build.sh")"

name=rdk-test
instance_exists() { :; }
instance_state() { cat "$temporary/state"; }
wait_agent() { :; }
lxc() { echo "lxc $*" >> "$temporary/calls"; echo RUNNING > "$temporary/state"; }
run_root() { echo "root $*" >> "$temporary/calls"; }

echo STOPPED > "$temporary/state"; : > "$temporary/calls"
start_vm
grep -q '^lxc start ' "$temporary/calls"
test "$(tail -1 "$temporary/calls")" = 'root /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/lab-bringup.sh up'

echo RUNNING > "$temporary/state"; : > "$temporary/calls"
start_vm    # already running (check on a running lab): no restart of its services
! grep -q 'lab-bringup' "$temporary/calls"
grep -q '^root systemctl start easymesh-lab.service' "$temporary/calls"
echo 'PASS: a started VM gets the ordered bring-up; a running one is left alone'
