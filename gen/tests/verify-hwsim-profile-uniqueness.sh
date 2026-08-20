#!/usr/bin/env bash

set -euo pipefail

declare -A owner=()
checked=0

# Profiles, rather than running instances, own physical-radio assignments.
# Inspecting every profile also covers stopped instances—the condition that
# exposed the allocator bug this test protects against.
while read -r profile; do
    [ -n "$profile" ] || continue
    while read -r device; do
        [ -n "$device" ] || continue
        parent=$(lxc profile device get "$profile" "$device" parent 2>/dev/null || true)
        [[ "$parent" == virt-wlan[0-9]* ]] || continue
        checked=$((checked + 1))
        if [ -n "${owner[$parent]:-}" ]; then
            echo "FAIL: $parent is assigned to ${owner[$parent]} and $profile/$device" >&2
            exit 1
        fi
        owner[$parent]="$profile/$device"
    done < <(lxc profile device list "$profile" 2>/dev/null)
done < <(lxc profile list --format csv -c n)

[ "$checked" -gt 0 ] || {
    echo "FAIL: no hwsim profile assignments found" >&2
    exit 1
}

echo "PASS: $checked hwsim profile assignments use unique parents"
