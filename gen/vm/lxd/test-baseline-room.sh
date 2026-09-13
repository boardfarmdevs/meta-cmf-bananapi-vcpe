#!/bin/bash
set -euo pipefail

source_dir=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
eval "$(sed -n '/^check_baseline() (/,/^)/p' "$source_dir/build.sh")"
run_root() {
    printf '%s\n' "$*" >> "$work/calls"
    case "$*" in
        'systemctl show easymesh-room-demo.service -p ActiveState --value') echo "$room_state" ;;
        'systemctl stop easymesh-room-demo.service') return "$stop_status" ;;
        'systemctl start easymesh-room-demo.service') return 0 ;;
        'env HEALTH_EXPECT_CLIENTS=100 /usr/local/sbin/easymesh-labctl check') return "$audit_status" ;;
        *) return 99 ;;
    esac
}
stop_status=0
for room_state in active activating inactive; do
    for audit_status in 0 19; do
        : > "$work/calls"
        result=0
        check_baseline env HEALTH_EXPECT_CLIENTS=100 || result=$?
        test "$result" = "$audit_status"
        grep -Fq 'systemctl stop easymesh-room-demo.service' "$work/calls"
        if [ "$room_state" != inactive ]; then
            test "$(tail -1 "$work/calls")" = 'systemctl start easymesh-room-demo.service'
        else
            ! grep -Fq 'systemctl start easymesh-room-demo.service' "$work/calls"
        fi
    done
done
room_state=active
stop_status=7
audit_status=0
: > "$work/calls"
result=0
check_baseline env HEALTH_EXPECT_CLIENTS=100 || result=$?
test "$result" = 7
! grep -Fq '/usr/local/sbin/easymesh-labctl check' "$work/calls"
echo 'PASS: baseline audits suspend room RF ownership and restore it on success/failure'
