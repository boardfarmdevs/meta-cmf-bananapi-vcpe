#!/usr/bin/env bash
set -euo pipefail

# Host-side, name-aware adapter for the controller image's MAC-level steer.sh.
# The names are the live labels shown by the topology WebUI, not a static table.

usage() {
    cat >&2 <<'EOF'
usage: gen/steer.sh [--band 2.4|5|6] [--ssid SSID] [--dry-run] STA TARGET

Examples:
  gen/steer.sh sta-03 extender-2
  gen/steer.sh sta-03 agent-1
  gen/steer.sh --band 6 sta-03 extender-2

STA may be a WebUI label such as sta-03 or a station MAC. TARGET may be a
live topology node name such as agent-1/extender-2 or a target BSSID. Without
overrides, the target BSSID is selected on the STA's current SSID and band.
EOF
    exit 2
}

band_override=
ssid_override=
dry_run=0
while (($#)); do
    case "$1" in
        --band)
            (($# >= 2)) || usage
            case "${2,,}" in
                2.4|2g|2.4ghz) band_override=0 ;;
                5|5g|5ghz)     band_override=1 ;;
                6|6g|6ghz)     band_override=3 ;;
                *) echo "steer.sh: band must be 2.4, 5 or 6" >&2; exit 2 ;;
            esac
            shift 2
            ;;
        --ssid)
            (($# >= 2)) || usage
            ssid_override=$2
            shift 2
            ;;
        --dry-run) dry_run=1; shift ;;
        -h|--help) usage ;;
        --) shift; break ;;
        -*) echo "steer.sh: unknown option: $1" >&2; usage ;;
        *) break ;;
    esac
done
(($# == 2)) || usage

sta_input=${1,,}
target_input=${2,,}
topology_url=${EASYMESH_TOPOLOGY_URL:-http://127.0.0.1:8888/api/v1/topology}
controller=${EASYMESH_CONTROLLER:-bpibroadband}

for command in curl jq lxc; do
    command -v "$command" >/dev/null || {
        echo "steer.sh: required host command is missing: $command" >&2
        exit 1
    }
done

topology=$(curl -fsS "$topology_url") || {
    echo "steer.sh: cannot read live topology from $topology_url" >&2
    exit 1
}
jq -e '.nodes | type == "array"' >/dev/null <<<"$topology" || {
    echo "steer.sh: topology response has no nodes array" >&2
    exit 1
}

if [[ $sta_input =~ ^sta-([[:xdigit:]]{2})$ ]]; then
    # The WebUI uses the fifth octet for the stable hwsim STA label.
    sta=$(printf '02:00:00:00:%s:00' "${BASH_REMATCH[1],,}")
elif [[ $sta_input =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
    sta=$sta_input
else
    echo "steer.sh: STA must be a WebUI name such as sta-03 or a MAC address" >&2
    exit 2
fi

mapfile -t source_rows < <(jq -r --arg sta "$sta" '
    [.nodes[] as $node | $node.STAList[]?
      | select((.staMAC // "" | ascii_downcase) == $sta)
      | [$node.name, .staMAC, (.band | tostring), .ssid] | @tsv]
    | unique[]' <<<"$topology")
if ((${#source_rows[@]} != 1)); then
    echo "steer.sh: $sta_input resolves to $sta, but it has ${#source_rows[@]} live topology placements (expected 1)" >&2
    exit 1
fi
IFS=$'\t' read -r source_name sta source_band source_ssid <<<"${source_rows[0]}"
target_band=${band_override:-$source_band}
target_ssid=${ssid_override:-$source_ssid}

target_is_name=0
if [[ $target_input =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
    target_bssid=$target_input
    mapfile -t target_rows < <(jq -r --arg bssid "$target_bssid" '
        [.nodes[] as $node | $node.haulTypes[]? as $haul | $haul.BSSList[]?
          | select((.BSSID // "" | ascii_downcase) == $bssid)
          | [$node.name, .BSSID, (.Band | tostring), (.ssid // $haul.ssid // "")] | @tsv]
        | unique[]' <<<"$topology")
    if ((${#target_rows[@]} != 1)); then
        echo "steer.sh: target BSSID $target_bssid has ${#target_rows[@]} live topology matches (expected 1)" >&2
        exit 1
    fi
    IFS=$'\t' read -r target_name target_bssid actual_band actual_ssid <<<"${target_rows[0]}"
    if [[ -n $band_override && $actual_band != "$target_band" ]] \
        || [[ -n $ssid_override && $actual_ssid != "$target_ssid" ]]; then
        echo "steer.sh: explicit BSSID $target_bssid does not match the requested band/SSID" >&2
        exit 1
    fi
    target_band=$actual_band
    target_ssid=$actual_ssid
else
    target_is_name=1
    node_count=$(jq -r --arg target "$target_input" '
        [.nodes[] | select((.name // "" | ascii_downcase) == $target)] | length' \
        <<<"$topology")
    if [[ $node_count != 1 ]]; then
        echo "steer.sh: topology name '$2' has $node_count matches (expected 1)" >&2
        echo "steer.sh: live targets: $(jq -r '[.nodes[].name] | join(", ")' <<<"$topology")" >&2
        exit 1
    fi
    mapfile -t target_rows < <(jq -r \
        --arg target "$target_input" --argjson band "$target_band" --arg ssid "$target_ssid" '
        [.nodes[] | select((.name // "" | ascii_downcase) == $target)
          | . as $node | .haulTypes[]? as $haul
          | select(($haul.name // "" | ascii_downcase) == "fronthaul")
          | $haul.BSSList[]?
          | select(.Band == $band and (.ssid // $haul.ssid // "") == $ssid)
          | [$node.name, .BSSID, (.Band | tostring), (.ssid // $haul.ssid // "")] | @tsv]
        | unique[]' <<<"$topology")
    if ((${#target_rows[@]} != 1)); then
        echo "steer.sh: '$2' has ${#target_rows[@]} fronthaul BSS matches for SSID '$target_ssid', band $target_band (expected 1)" >&2
        echo "steer.sh: the Controller node has no WLAN BSS; use agent-1 for the colocated agent" >&2
        exit 1
    fi
    IFS=$'\t' read -r target_name target_bssid target_band target_ssid <<<"${target_rows[0]}"
fi

if ((target_is_name)) \
    && [[ ${target_name,,} == "${source_name,,}" ]] \
    && [[ $target_band == "$source_band" && $target_ssid == "$source_ssid" ]]; then
    echo "steer.sh: $sta_input is already on $target_name for SSID '$target_ssid', band $target_band" >&2
    exit 1
fi

printf 'steer.sh: %s -> %s; STA=%s target_BSSID=%s SSID=%s band=%s\n' \
    "$sta_input" "$target_name" "$sta" "$target_bssid" "$target_ssid" "$target_band"
if ((dry_run)); then
    printf 'steer.sh: dry run; would execute: lxc exec %q -- /usr/bin/steer.sh %q %q\n' \
        "$controller" "$sta" "$target_bssid"
    exit 0
fi

lxc info "$controller" >/dev/null 2>&1 || {
    echo "steer.sh: controller container '$controller' is not available" >&2
    exit 1
}
exec lxc exec "$controller" -- /usr/bin/steer.sh "$sta" "$target_bssid"
