#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
test -c /dev/kvm || {
    echo 'SKIP: /dev/kvm is unavailable'
    exit 0
}

stage=$(mktemp -d /tmp/easymesh-import-storage.XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
bundle=$stage/rdkeasymesh-20-test-lxd
install -d "$bundle"
install -m 0755 "$root/gen/vm/lxd/import.sh" "$bundle/import.sh"
backup=$bundle/rdkeasymesh-20-test-lxd.tar.zst
log=$stage/lxc.log
: > "$backup"
printf '%s\n' \
    'LAB_PROFILE=small' \
    'LAB_CLIENTS=20' \
    'LAB_DEFAULT_NAME=rdkeasymesh-20-storage-test' \
    'LAB_DEFAULT_CPUS=6' \
    'LAB_DEFAULT_MEMORY=8GiB' > "$bundle/release.env"
: > "$log"
export EASYMESH_TEST_LXC_LOG=$log

lxc() {
    {
        printf '%q ' "$@"
        printf '\n'
    } >> "$EASYMESH_TEST_LXC_LOG"
    case "$1:$2" in
        network:get) printf '10.20.30.1/24\n' ;;
        network:list-leases) : ;;
        storage:show)
            if [ "${3:-}" = missing-pool ]; then
                return 1
            fi
            ;;
        info:*) return 1 ;;
    esac
    return 0
}
export -f lxc

EASYMESH_LXD_STORAGE=large-pool \
EASYMESH_WEBUI_HOST_IP=127.0.0.1 \
EASYMESH_WEBUI_PORT=29889 \
WMEDIUMD_CONSOLE_PORT=29890 \
    bash "$bundle/import.sh" > "$stage/import.out"

grep -Fx \
    "import $backup rdkeasymesh-20-storage-test --storage large-pool --device eth0\\,network=lxdbr0 --device eth0\\,ipv4.address=10.20.30.250 --device easymesh-webui\\,listen=tcp:127.0.0.1:29889 --device easymesh-webui\\,connect=tcp:10.20.30.250:8888 --device wmediumd-console\\,listen=tcp:127.0.0.1:29890 --device wmediumd-console\\,connect=tcp:10.20.30.250:8890 " \
    "$log" >/dev/null
grep -F 'profile:           20 clients (small)' "$stage/import.out" >/dev/null
grep -Fx 'config set rdkeasymesh-20-storage-test limits.memory 8GiB ' \
    "$log" >/dev/null
grep -Fx 'config device unset rdkeasymesh-20-storage-test eth0 ipv4.address ' \
    "$log" >/dev/null

: > "$log"
if EASYMESH_LXD_STORAGE=missing-pool \
    EASYMESH_WEBUI_HOST_IP=127.0.0.1 \
    bash "$bundle/import.sh" \
        >"$stage/missing.out" 2>&1; then
    echo 'missing storage pool was accepted' >&2
    exit 1
fi
grep -F 'LXD storage pool does not exist: missing-pool' \
    "$stage/missing.out" >/dev/null
if grep -q '^import ' "$log"; then
    echo 'import was attempted after storage validation failed' >&2
    exit 1
fi

echo 'PASS: LXD import storage selection'
