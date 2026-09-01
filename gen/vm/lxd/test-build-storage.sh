#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
build=$root/gen/vm/lxd/build.sh
stage=$(mktemp -d /tmp/easymesh-build-storage.XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
log=$stage/lxc.log

# Exercise the exact helper from build.sh without provisioning a VM.
eval "$(sed -n '/^set_root_disk_size()/,/^}/p' "$build")"

lxc() {
    if [ "$1:$2:$3" = config:device:show ]; then
        [ "${EASYMESH_TEST_LOCAL_ROOT:-0}" = 0 ] || printf 'root:\n'
        return 0
    fi
    {
        printf '%q ' "$@"
        printf '\n'
    } >> "$log"
}

name=rdkeasymesh-storage-test
disk=64GiB

: > "$log"
EASYMESH_TEST_LOCAL_ROOT=1
set_root_disk_size
grep -Fx \
    'config device set rdkeasymesh-storage-test root size 64GiB ' \
    "$log" >/dev/null

: > "$log"
EASYMESH_TEST_LOCAL_ROOT=0
set_root_disk_size
grep -Fx \
    'config device override rdkeasymesh-storage-test root size=64GiB ' \
    "$log" >/dev/null

echo 'PASS: LXD build root-device selection'
