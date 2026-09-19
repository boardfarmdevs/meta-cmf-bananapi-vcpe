#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
source "$root/gen/vm/lxd/instance-config.sh"

test "$(EASYMESH_LXD_NAME=alpha easymesh_instance_name)" = alpha
test "$(EASYMESH_LXD_NAME=alpha easymesh_instance_storage alpha)" = alpha-pool
first=$(EASYMESH_LXD_NAME=alpha easymesh_instance_port_base alpha)
second=$(EASYMESH_LXD_NAME=alpha easymesh_instance_port_base alpha)
test "$first" = "$second"
test "$first" -ge 20000
test "$first" -le 29990
test "$(EASYMESH_PORT_BASE=32000 easymesh_instance_port_base alpha)" = 32000

log=$(mktemp)
trap 'rm -f -- "$log"' EXIT
lxc() {
    printf '%s\n' "$*" >> "$log"
    if [ "$1 $2" = 'storage show' ]; then return 1; fi
    return 0
}
easymesh_ensure_storage_pool alpha-pool
grep -Fx 'storage create alpha-pool dir' "$log" >/dev/null

echo 'PASS: named EasyMesh LXD defaults'
