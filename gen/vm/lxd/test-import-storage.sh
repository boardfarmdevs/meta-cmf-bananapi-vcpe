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
netplan_capture=$stage/site-netplan.yaml
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
        config:get) printf '00:16:3e:aa:bb:cc\n' ;;
        exec:*)
            case " $* " in
                *' lxc query /1.0 '*)
                    if [ -n "${EASYMESH_TEST_NESTED_READY_COUNT:-}" ]; then
                        count=0
                        [ ! -r "$EASYMESH_TEST_NESTED_READY_COUNT" ] || \
                            read -r count < "$EASYMESH_TEST_NESTED_READY_COUNT"
                        count=$((count + 1))
                        printf '%s\n' "$count" \
                            > "$EASYMESH_TEST_NESTED_READY_COUNT"
                        [ "$count" -ge \
                            "${EASYMESH_TEST_NESTED_READY_AFTER:-1}" ] || return 1
                    fi
                    ;;
                *' /sys/class/net/'*) printf 'enp5s0\n' ;;
                *' ip -4 -o address show '*)
                    printf '2: enp5s0    inet %s/24 scope global enp5s0\n' \
                        "${EASYMESH_TEST_GUEST_ADDRESS:-10.20.30.250}"
                    ;;
            esac
            ;;
        file:push)
            cp "$5" "$EASYMESH_TEST_NETPLAN_CAPTURE"
            ;;
    esac
    return 0
}
export -f lxc
export EASYMESH_TEST_NETPLAN_CAPTURE=$netplan_capture

EASYMESH_LXD_STORAGE=large-pool \
EASYMESH_WEBUI_HOST_IP=127.0.0.1 \
EASYMESH_WEBUI_PORT=29889 \
WMEDIUMD_CONSOLE_PORT=29890 \
EASYMESH_ROOM_DEMO_PORT=29891 \
    bash "$bundle/import.sh" > "$stage/import.out"

grep -Fx \
    "import $backup rdkeasymesh-20-storage-test --storage large-pool --device eth0\\,network=lxdbr0 --device eth0\\,ipv4.address=10.20.30.250 --device easymesh-webui\\,listen=tcp:127.0.0.1:29889 --device easymesh-webui\\,connect=tcp:10.20.30.250:8888 --device wmediumd-console\\,listen=tcp:127.0.0.1:29890 --device wmediumd-console\\,connect=tcp:10.20.30.250:8890 --device room-demo-viewer\\,listen=tcp:127.0.0.1:29891 --device room-demo-viewer\\,connect=tcp:10.20.30.250:8891 " \
    "$log" >/dev/null
grep -F 'profile:           20 clients (small)' "$stage/import.out" >/dev/null
grep -Fx 'config set rdkeasymesh-20-storage-test limits.memory 8GiB ' \
    "$log" >/dev/null
grep -Fx 'config device unset rdkeasymesh-20-storage-test eth0 ipv4.address ' \
    "$log" >/dev/null
grep -Fx 'site address:      enp5s0 10.20.30.250/24 via 10.20.30.1' \
    "$stage/import.out" >/dev/null
grep -Fx 'room demo:        http://127.0.0.1:29891/viewer/?mode=live' \
    "$stage/import.out" >/dev/null
grep -Fx '      dhcp4: false' "$netplan_capture" >/dev/null
grep -Fx '      accept-ra: true' "$netplan_capture" >/dev/null
grep -Fx '        - 10.20.30.250/24' "$netplan_capture" >/dev/null
grep -Fx '          via: 10.20.30.1' "$netplan_capture" >/dev/null
grep -Fx '          - 10.20.30.1' "$netplan_capture" >/dev/null

start_line=$(grep -nFx 'start rdkeasymesh-20-storage-test ' "$log" | cut -d: -f1)
apply_line=$(grep -nFx \
    'exec rdkeasymesh-20-storage-test -- netplan apply ' "$log" | cut -d: -f1)
proxy_line=$(grep -nF \
    'config device add rdkeasymesh-20-storage-test easymesh-webui proxy ' \
    "$log" | tail -1 | cut -d: -f1)
test "$start_line" -lt "$apply_line"
test "$apply_line" -lt "$proxy_line"

: > "$log"
if EASYMESH_TEST_GUEST_ADDRESS=10.20.30.99 \
    EASYMESH_LXD_ADDRESS_TIMEOUT=1 \
    EASYMESH_LXD_STORAGE=large-pool \
    EASYMESH_WEBUI_HOST_IP=127.0.0.1 \
    bash "$bundle/import.sh" >"$stage/address-mismatch.out" 2>&1; then
    echo 'mismatched guest address was accepted' >&2
    exit 1
fi
grep -F \
    'reserved address 10.20.30.250 was not installed on enp5s0 within 1s' \
    "$stage/address-mismatch.out" >/dev/null
if grep -q '^config device add .* easymesh-webui proxy ' "$log"; then
    echo 'WebUI proxy was added before the reserved-address gate passed' >&2
    exit 1
fi

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

# A universal thin import must not race the nested snap LXD daemon.  Prove a
# delayed API becomes ready before profile selection and that timeout leaves
# the profile lock and host proxies unpublished.
cat > "$bundle/release.env" <<'EOF'
LAB_PROFILE_SELECTABLE=true
LAB_SUPPORTED_PROFILES=20,50,100
EOF
ready_count=$stage/nested-ready.count
export EASYMESH_TEST_NESTED_READY_COUNT=$ready_count

: > "$log"
printf '0\n' > "$ready_count"
EASYMESH_TEST_NESTED_READY_AFTER=2 \
EASYMESH_LXD_NESTED_READY_TIMEOUT=3 \
EASYMESH_LXD_STORAGE=large-pool \
EASYMESH_WEBUI_HOST_IP=127.0.0.1 \
EASYMESH_WEBUI_PORT=29889 \
WMEDIUMD_CONSOLE_PORT=29890 \
EASYMESH_ROOM_DEMO_PORT=29891 \
    bash "$bundle/import.sh" --profile 20 "$backup" \
        > "$stage/nested-delayed.out"
test "$(cat "$ready_count")" = 2
ready_line=$(grep -nF \
    'exec rdkeasymesh-20-0905 -- lxc query /1.0 ' "$log" \
    | tail -1 | cut -d: -f1)
select_line=$(grep -nF \
    'exec rdkeasymesh-20-0905 -- /usr/local/sbin/easymesh-select-thin-profile 20 ' \
    "$log" | cut -d: -f1)
proxy_line=$(grep -nF \
    'config device add rdkeasymesh-20-0905 easymesh-webui proxy ' \
    "$log" | tail -1 | cut -d: -f1)
reload_line=$(grep -nF \
    'exec rdkeasymesh-20-0905 -- systemctl daemon-reload ' \
    "$log" | tail -1 | cut -d: -f1)
start_line=$(grep -nF \
    'exec rdkeasymesh-20-0905 -- systemctl --no-block start easymesh-lab.service ' \
    "$log" | tail -1 | cut -d: -f1)
test "$ready_line" -lt "$select_line"
test "$select_line" -lt "$proxy_line"
test "$proxy_line" -lt "$reload_line"
test "$reload_line" -lt "$start_line"

: > "$log"
printf '0\n' > "$ready_count"
if EASYMESH_TEST_NESTED_READY_AFTER=999 \
    EASYMESH_LXD_NESTED_READY_TIMEOUT=2 \
    EASYMESH_LXD_STORAGE=large-pool \
    EASYMESH_WEBUI_HOST_IP=127.0.0.1 \
    bash "$bundle/import.sh" --profile 20 "$backup" \
        > "$stage/nested-timeout.out" 2>&1; then
    echo 'unready nested LXD was accepted' >&2
    exit 1
fi
grep -F 'nested LXD did not become ready within 2s' \
    "$stage/nested-timeout.out" >/dev/null
if grep -q '/usr/local/sbin/easymesh-select-thin-profile' "$log"; then
    echo 'thin profile was locked before nested LXD became ready' >&2
    exit 1
fi
if grep -q '^config device add .* easymesh-webui proxy ' "$log"; then
    echo 'WebUI proxy was published before nested LXD became ready' >&2
    exit 1
fi

echo 'PASS: LXD import storage selection'
