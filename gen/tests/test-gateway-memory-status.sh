#!/usr/bin/env bash
# lab-bringup.sh status reports the gateway container's memory, its limit, the controller's
# share and the out-of-memory kills.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
eval "$(sed -n '/^gateway_memory() {/,/^}/p' "$root/gen/lab-bringup.sh")"

tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
export EASYMESH_GATEWAY_CGROUP=$tmp
cx() { echo 674204; }    # the controller's VmRSS in kB

echo 1073737728 > "$tmp/memory.current"
echo 1073741824 > "$tmp/memory.max"
printf '%s\n' 'low 0' 'high 0' 'max 6158081' 'oom 1' 'oom_kill 1' 'oom_group_kill 0' > "$tmp/memory.events"
test "$(gateway_memory)" = 'gateway memory: 1023 MiB of 1024 MiB, em_ctrl 658 MiB, oom kills 1'

echo 468590592 > "$tmp/memory.current"
echo max > "$tmp/memory.max"
printf '%s\n' 'low 0' 'oom_kill 0' > "$tmp/memory.events"
cx() { return 1; }       # the controller is not running
test "$(gateway_memory)" = 'gateway memory: 446 MiB of max, em_ctrl 0 MiB, oom kills 0'

export EASYMESH_GATEWAY_CGROUP=$tmp/none    # no gateway container
test "$(gateway_memory)" = 'gateway memory: unavailable'

grep -q '^    gateway_memory$' "$root/gen/lab-bringup.sh"    # status prints it
echo 'PASS: the lab status reports gateway memory, limit, controller share and kills'
