#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
eval "$(sed -n '/^check_baseline()/,/^)/p' "$root/gen/vm/lxd/build.sh")"

run_root() {
    printf '%s\n' "$*" >> "$temporary/calls"
    case "$*" in
        'systemctl is-active --quiet easymesh-room-demo.service') return "$room_status" ;;
        'systemctl stop easymesh-room-demo.service') return "$stop_status" ;;
        'systemctl start easymesh-room-demo.service') return 0 ;;
        *'/usr/local/sbin/easymesh-labctl check') return "$audit_status" ;;
        *) return 99 ;;
    esac
}

stop_status=0
for room_status in 0 3; do
    for audit_status in 0 19; do
        : > "$temporary/calls"
        result=0
        check_baseline env HEALTH_EXPECT_CLIENTS=20 || result=$?
        test "$result" = "$audit_status"
        grep -Fxq 'env HEALTH_EXPECT_CLIENTS=20 /usr/local/sbin/easymesh-labctl check' "$temporary/calls"
        if [ "$room_status" = 0 ]; then
            test "$(sed -n '2p' "$temporary/calls")" = 'systemctl stop easymesh-room-demo.service'
            test "$(tail -1 "$temporary/calls")" = 'systemctl start easymesh-room-demo.service'
        else
            test "$(wc -l < "$temporary/calls")" = 2
        fi
    done
done
room_status=0
stop_status=7
: > "$temporary/calls"
result=0
check_baseline || result=$?
test "$result" = 7
test "$(wc -l < "$temporary/calls")" = 2
echo 'PASS: baseline audit excludes room RF changes, preserves failures and restores prior service state'
