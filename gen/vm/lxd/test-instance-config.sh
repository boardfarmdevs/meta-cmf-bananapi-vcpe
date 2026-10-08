#!/usr/bin/env bash
set -euo pipefail
# hermetic: not the lab a caller configured (lab-config.sh, as the suite and vm.md do)
unset EASYMESH_LAB_NAME EASYMESH_LXD_NAME EASYMESH_LXD_STORAGE EASYMESH_PORT_BASE EASYMESH_ROOM_DEMO_PORT \
    EASYMESH_WEBUI_PORT LAB_GRAFANA_PORT LAB_LXD_UI_PORT LAB_OUTER_METRICS_PORT WMEDIUMD_CONSOLE_PORT

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
source "$root/gen/vm/lxd/instance-config.sh"

test "$(EASYMESH_LXD_NAME=alpha easymesh_instance_name)" = alpha
test "$(EASYMESH_LXD_NAME=alpha easymesh_instance_storage alpha)" = labs
test "$(EASYMESH_LXD_STORAGE=alpha-pool easymesh_instance_storage alpha)" = alpha-pool
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
easymesh_ensure_storage_pool labs
grep -Fx 'storage create labs zfs size=500GiB' "$log" >/dev/null
EASYMESH_LXD_STORAGE_DRIVER=dir easymesh_ensure_storage_pool alpha-pool
grep -Fx 'storage create alpha-pool dir' "$log" >/dev/null

# the evidence volume: made when new (sized on a pool with quotas), attached, never twice
pool_driver=zfs
lxc() {
    printf '%s\n' "$*" >> "$log"
    case "$1 $2 $3" in
        'config device get') return 1 ;;
        'storage volume show') return 1 ;;
        'storage show '*) printf 'name: %s\ndriver: %s\n' "$3" "$pool_driver" ;;
    esac
    return 0
}
: > "$log"
easymesh_attach_evidence alpha labs
grep -Fx 'storage volume create labs alpha-evidence size=20GiB' "$log" >/dev/null
grep -Fx 'config device add alpha evidence disk pool=labs source=alpha-evidence path=/home/easymesh/easymesh-evidence' "$log" >/dev/null
: > "$log"
pool_driver=dir easymesh_attach_evidence alpha alpha-pool
grep -Fx 'storage volume create alpha-pool alpha-evidence' "$log" >/dev/null
: > "$log"
EASYMESH_EVIDENCE_SIZE=0 easymesh_attach_evidence alpha labs
test ! -s "$log"
lxc() {
    printf '%s\n' "$*" >> "$log"
    [ "$1 $2 $3" = 'config device get' ] && echo alpha-evidence
    return 0
}
easymesh_attach_evidence alpha labs
if grep -q 'device add\|volume create' "$log"; then exit 1; fi

# free page reporting: the balloon section added once, after what raw.qemu.conf already holds
raw=
lxc() {
    case "$1 $2 $4" in
        'config get raw.qemu.conf') printf '%s' "$raw" ;;
        'config set raw.qemu.conf') printf '%s' "$5" > "$log" ;;
    esac
    return 0
}
: > "$log"
easymesh_free_page_reporting alpha
test "$(cat "$log")" = "$(printf '[device "qemu_balloon"]\nfree-page-reporting = "on"')"
raw=$(printf '[global]\nfoo = "1"')
easymesh_free_page_reporting alpha
test "$(cat "$log")" = "$(printf '[global]\nfoo = "1"\n[device "qemu_balloon"]\nfree-page-reporting = "on"')"
raw=$(cat "$log")
: > "$log"
easymesh_free_page_reporting alpha
test ! -s "$log"

echo 'PASS: named EasyMesh LXD defaults'
