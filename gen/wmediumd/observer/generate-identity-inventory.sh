#!/bin/bash
# Generate the short-lived, unprivileged Console identity handoff. This runs
# from an operator/cold-start context where LXC discovery is appropriate; the
# long-running Console never receives LXD socket access.
set -euo pipefail

output=${WMEDIUMD_IDENTITY_INVENTORY:-/run/meta-cmf-wmediumd/identity-inventory.json}
lxc_bin=${LXC:-lxc}

usage() {
    echo "usage: $0 [--output PATH]" >&2
    exit 2
}
while [ "$#" -gt 0 ]; do
    case "$1" in
        --output) [ "$#" -ge 2 ] || usage; output=$2; shift 2 ;;
        *) usage ;;
    esac
done

command -v "$lxc_bin" >/dev/null 2>&1 || { echo "identity inventory: LXC command not found: $lxc_bin" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "identity inventory: python3 is required for safe JSON encoding" >&2; exit 1; }

work=$(mktemp -d)
rows=$work/rows.tsv
trap 'rm -rf "$work"' EXIT
: > "$rows"

mapfile -t containers < <("$lxc_bin" list -c n --format csv 2>/dev/null \
    | grep -E '^(bpibroadband|bpiap(-[0-9]{3})?|wlan-client(-[0-9]{3})?)$' \
    | sort -V)

transmitter_mac() {
    local container=$1 permanent first
    permanent=$("$lxc_bin" exec "$container" -- sh -c \
        'cat /sys/class/ieee80211/*/macaddress 2>/dev/null | head -1' \
        </dev/null 2>/dev/null || true)
    permanent=${permanent,,}
    [[ "$permanent" =~ ^[0-9a-f]{2}(:[0-9a-f]{2}){5}$ ]] || return 1
    first=$(printf '%02x' $((16#${permanent:0:2} | 0x40)))
    printf '%s%s\n' "$first" "${permanent:2}"
}

config_value() {
    "$lxc_bin" config get "$1" "$2" 2>/dev/null || true
}

for container in "${containers[@]}"; do
    mac=$(transmitter_mac "$container") || continue
    interface=
    case "$container" in
        bpibroadband)
            label=agent-1; role=controller-agent
            ;;
        bpiap)
            label=extender-1; role=extender
            ;;
        bpiap-[0-9][0-9][0-9])
            suffix=${container#bpiap-}
            label=$(printf 'extender-%d' "$((10#$suffix + 1))")
            role=extender
            ;;
        wlan-client|wlan-client-[0-9][0-9][0-9])
            interface=wlan0
            cohort=$(config_value "$container" user.easymesh.cohort)
            ordinal=$(config_value "$container" user.easymesh.ordinal)
            ssid=$(config_value "$container" user.easymesh.ssid)
            [[ "$ordinal" =~ ^[1-9][0-9]{0,2}$ ]] || {
                if [ "$container" = wlan-client ]; then ordinal=1
                else suffix=${container#wlan-client-}; ordinal=$((10#$suffix + 1)); fi
            }
            if [ "$cohort" != iot ] && [ "$cohort" != private ]; then
                if [ "$ssid" = iot_ssid ]; then cohort=iot; else cohort=private; fi
            fi
            if [ "$cohort" = iot ]; then label=$(printf 'iot-%02d' "$ordinal"); role=iot-client
            else label=$(printf 'sta-%02d' "$ordinal"); role=wlan-client; fi
            ;;
        *) continue ;;
    esac
    printf '%s\t%s\t%s\t%s\t%s\n' "$mac" "$label" "$role" "$container" "$interface" >> "$rows"
done

[ -s "$rows" ] || { echo "identity inventory: no active hwsim radios discovered" >&2; exit 1; }
[ "$(wc -l < "$rows")" -le 512 ] || { echo "identity inventory: more than 512 radios discovered" >&2; exit 1; }

directory=$(dirname -- "$output")
[ -d "$directory" ] || { echo "identity inventory: output directory does not exist: $directory" >&2; exit 1; }
staging=$(mktemp "$directory/.identity-inventory.XXXXXX")
trap 'rm -rf "$work"; rm -f "$staging"' EXIT
python3 - "$rows" "$staging" <<'PY'
import csv
import datetime
import json
import sys

rows_path, output_path = sys.argv[1:]
stations = []
with open(rows_path, encoding="utf-8", newline="") as source:
    for mac, label, role, owner, interface in csv.reader(source, delimiter="\t"):
        stations.append({
            "mac": mac,
            "label": label,
            "role": role,
            "owner": owner,
            "interface": interface,
        })
document = {
    "schema_version": 1,
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "stations": stations,
}
with open(output_path, "w", encoding="utf-8") as target:
    json.dump(document, target, indent=2, sort_keys=True)
    target.write("\n")
PY
chmod 0644 "$staging"
mv -f "$staging" "$output"
trap 'rm -rf "$work"' EXIT
echo "identity inventory: wrote $(wc -l < "$rows") radios to $output"
