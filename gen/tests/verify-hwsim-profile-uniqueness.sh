#!/usr/bin/env bash

set -euo pipefail

declare -A owner=()
checked=0

# Profiles own the radio assignments, but only profiles attached to instances
# can contend at instance start.  Include stopped instances (the triggering
# case) while ignoring old unattached template profiles.
while IFS=$'\t' read -r instance profile; do
    [ -n "$instance" ] && [ -n "$profile" ] || continue
    while read -r device; do
        [ -n "$device" ] || continue
        parent=$(lxc profile device get "$profile" "$device" parent 2>/dev/null || true)
        [[ "$parent" == virt-wlan[0-9]* ]] || continue
        checked=$((checked + 1))
        if [ -n "${owner[$parent]:-}" ]; then
            echo "FAIL: $parent is assigned to ${owner[$parent]} and $instance/$profile/$device" >&2
            exit 1
        fi
        owner[$parent]="$instance/$profile/$device"
    done < <(lxc profile device list "$profile" 2>/dev/null)
done < <(lxc list --format json | jq -r '.[] | .name as $instance | .profiles[] | [$instance, .] | @tsv')

[ "$checked" -gt 0 ] || {
    echo "FAIL: no hwsim profile assignments found" >&2
    exit 1
}

echo "PASS: $checked hwsim profile assignments use unique parents"
