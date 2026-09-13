#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
eval "$(sed -n '/^check_baseline()/,/^)/p' "$root/gen/vm/lxd/build.sh")"

run_root() {
    printf '%s\n' "$*" >> "$temporary/calls"
    case "$*" in
        'systemctl show easymesh-room-demo.service -p ActiveState --value') echo "$room_state" ;;
        'systemctl stop easymesh-room-demo.service') return "$stop_status" ;;
        'systemctl start easymesh-room-demo.service') return 0 ;;
        *'/usr/local/sbin/easymesh-labctl check') return "$audit_status" ;;
        *) return 99 ;;
    esac
}

stop_status=0
for room_state in active activating inactive; do
    for audit_status in 0 19; do
        : > "$temporary/calls"
        result=0
        check_baseline env HEALTH_EXPECT_CLIENTS=100 || result=$?
        test "$result" = "$audit_status"
        grep -Fxq 'env HEALTH_EXPECT_CLIENTS=100 /usr/local/sbin/easymesh-labctl check' "$temporary/calls"
        if [ "$room_state" != inactive ]; then
            test "$(sed -n '2p' "$temporary/calls")" = 'systemctl stop easymesh-room-demo.service'
            test "$(tail -1 "$temporary/calls")" = 'systemctl start easymesh-room-demo.service'
        else
            test "$(wc -l < "$temporary/calls")" = 3
        fi
    done
done
room_state=active
stop_status=7
: > "$temporary/calls"
result=0
check_baseline || result=$?
test "$result" = 7
test "$(wc -l < "$temporary/calls")" = 3
! grep -Fq '/usr/local/sbin/easymesh-labctl check' "$temporary/calls"
echo 'PASS: baseline audit excludes room RF changes, preserves failures and restores prior service state'
