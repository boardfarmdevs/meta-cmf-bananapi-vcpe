#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
thin_unit=$root/gen/vm/scripts/guest/easymesh-thin-firstboot.service
lab_unit=$root/gen/vm/scripts/guest/easymesh-lab.service

get_unit_value() {
    local unit=$1 key=$2
    awk -F= -v key="$key" '
        $1 == key {
            count++
            value=$2
        }
        END {
            if (count != 1) {
                exit 1
            }
            print value
        }
    ' "$unit"
}

test "$(get_unit_value "$thin_unit" Type)" = oneshot
test "$(get_unit_value "$thin_unit" ExecStart)" = /usr/local/sbin/easymesh-thin-firstboot
test "$(get_unit_value "$thin_unit" RemainAfterExit)" = yes
test "$(get_unit_value "$thin_unit" TimeoutStartSec)" = infinity

grep -Fx 'ConditionPathExists=/var/lib/easymesh-lab/thin-firstboot.env' \
    "$thin_unit" >/dev/null
grep -Eq '^After=.*(^|[[:space:]])easymesh-thin-firstboot\.service([[:space:]]|$)' \
    "$lab_unit"
grep -Eq '^Requires=.*(^|[[:space:]])easymesh-thin-firstboot\.service([[:space:]]|$)' \
    "$lab_unit"

grep -F 'thin-provisioned-handoff.env' \
    "$root/gen/vm/scripts/guest/easymesh-thin-firstboot" >/dev/null
grep -F 'accept_thin_provisioned_handoff' \
    "$root/gen/vm/scripts/guest/easymesh-lab-runtime" >/dev/null
grep -F 'preserving $((client_count + 5)) running instances' \
    "$root/gen/vm/scripts/guest/easymesh-lab-runtime" >/dev/null

if grep -Eq '^TimeoutStartSec=[0-9]' "$thin_unit"; then
    echo 'thin first-boot service has a fixed numeric start deadline' >&2
    exit 1
fi

echo 'PASS: thin first boot uses bounded provisioning and one-shot runtime handoff'
