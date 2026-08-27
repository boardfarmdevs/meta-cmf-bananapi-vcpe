#!/usr/bin/env bash
set -euo pipefail

# Host-side, name-aware adapter for the controller image's MAC-level steer.sh.
# The names are the live labels shown by the topology WebUI, not a static table.
#
# The default mode makes a single lab steer deterministic: it temporarily
# makes the target radio preferable in wmediumd and primes the minimal test
# supplicant's scan cache before sending the real EasyMesh BTM request.  The
# exact medium state is restored on every exit path.  --request-only preserves
# the unassisted standards path when client acceptance policy is under test.

usage() {
    cat >&2 <<'EOF'
usage: gen/steer.sh [--band 2.4|5|6] [--ssid SSID] [--request-only] [--dry-run] STA TARGET

Examples:
  gen/steer.sh sta-03 extender-2
  gen/steer.sh iot-14 agent-1
  gen/steer.sh sta-03 agent-1
  gen/steer.sh --band 6 sta-03 extender-2
  gen/steer.sh --request-only iot-14 extender-2

STA may be a WebUI label such as sta-03/iot-14 or a station MAC. TARGET may be a
live topology node name such as agent-1/extender-2 or a target BSSID. Without
overrides, the target BSSID is selected on the STA's current SSID and band.
Default mode applies a temporary, exactly-restored wmediumd RF bias and verifies
the physical and controller-visible move. --request-only sends only the BTM
request; the station may legitimately reject it or remain on its current AP.
EOF
    exit 2
}

band_override=
ssid_override=
dry_run=0
request_only=0
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
        --request-only) request_only=1; shift ;;
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
repo=$(cd "$(dirname "$0")/.." && pwd)
bias_tool=$repo/gen/tests/steering-rf-bias.py
curl_connect_timeout=${EASYMESH_CURL_CONNECT_TIMEOUT:-2}
curl_timeout=${EASYMESH_CURL_TIMEOUT:-8}

for command in curl jq lxc; do
    command -v "$command" >/dev/null || {
        echo "steer.sh: required host command is missing: $command" >&2
        exit 1
    }
done

topology=$(curl --connect-timeout "$curl_connect_timeout" --max-time "$curl_timeout" \
    -fsS "$topology_url") || {
    echo "steer.sh: cannot read live topology from $topology_url" >&2
    exit 1
}
jq -e '.nodes | type == "array"' >/dev/null <<<"$topology" || {
    echo "steer.sh: topology response has no nodes array" >&2
    exit 1
}

if [[ $sta_input =~ ^(sta|iot)-([[:xdigit:]]{2})$ ]]; then
    # The WebUI uses the fifth octet for the stable hwsim STA label.
    sta=$(printf '02:00:00:00:%s:00' "${BASH_REMATCH[2],,}")
elif [[ $sta_input =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
    sta=$sta_input
else
    echo "steer.sh: STA must be a WebUI name such as sta-03/iot-14 or a MAC address" >&2
    exit 2
fi

mapfile -t source_rows < <(jq -r --arg sta "$sta" '
    [.nodes[] as $node | $node.STAList[]?
      | select((.staMAC // "" | ascii_downcase) == $sta)
      | [$node.name, .staMAC, (.band | tostring), .ssid,
         (.bssid // ""), ((.channel // 0) | tostring)] | @tsv]
    | unique[]' <<<"$topology")
if ((${#source_rows[@]} != 1)); then
    echo "steer.sh: $sta_input resolves to $sta, but it has ${#source_rows[@]} live topology placements (expected 1)" >&2
    exit 1
fi
IFS=$'\t' read -r source_name sta source_band source_ssid source_bssid source_channel \
    <<<"${source_rows[0]}"
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
    if ((request_only)); then
        printf 'steer.sh: dry run; request-only mode\n'
    else
        printf 'steer.sh: dry run; deterministic lab mode (temporary RF bias, candidate scan, verified move)\n'
    fi
    printf 'steer.sh: dry run; would execute: lxc exec %q -- /usr/bin/steer.sh %q %q\n' \
        "$controller" "$sta" "$target_bssid"
    exit 0
fi

lxc info "$controller" >/dev/null 2>&1 || {
    echo "steer.sh: controller container '$controller' is not available" >&2
    exit 1
}

if ((request_only)); then
    echo "steer.sh: request-only mode; client acceptance and reassociation are not forced"
    exec lxc exec "$controller" -- /usr/bin/steer.sh "$sta" "$target_bssid"
fi

[[ $source_bssid =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]] || {
    echo "steer.sh: live topology has no serving BSSID for $sta_input; refusing an unsafe RF bias" >&2
    exit 1
}
[[ -x $bias_tool ]] || {
    echo "steer.sh: deterministic steering helper is missing: $bias_tool" >&2
    exit 1
}

case "$target_band" in
    0) target_channel=6; target_frequency=2437 ;;
    1) target_channel=36; target_frequency=5180 ;;
    3) target_channel=5; target_frequency=5975 ;;
    *) echo "steer.sh: unsupported live target band: $target_band" >&2; exit 1 ;;
esac

# Prefer a controller-reported operating channel when it is available.  The
# current hwsim model reports zero, so the fixed lab channels above remain the
# explicit simulator fallback used by the optimizer candidate adapter too.
bsses_url=${topology_url%/topology}/bsses
bsses=$(curl --connect-timeout "$curl_connect_timeout" --max-time "$curl_timeout" \
    -fsS "$bsses_url" 2>/dev/null || true)
reported_channel=$(jq -r --arg bssid "$target_bssid" '
    first(.bsses[]? | select((.bssid // "" | ascii_downcase) == $bssid)
      | (.channel // 0)) // 0' <<<"$bsses" 2>/dev/null || true)
if [[ $reported_channel =~ ^[1-9][0-9]*$ ]]; then
    target_channel=$reported_channel
    case "$target_band" in
        0)
            if ((target_channel == 14)); then target_frequency=2484
            else target_frequency=$((2407 + 5 * target_channel)); fi
            ;;
        1) target_frequency=$((5000 + 5 * target_channel)) ;;
        3) target_frequency=$((5950 + 5 * target_channel)) ;;
    esac
fi

client=
while IFS= read -r candidate; do
    candidate_mac=$(lxc config get "$candidate" \
        volatile.wlan0.last_state.hwaddr </dev/null 2>/dev/null || true)
    if [[ ${candidate_mac,,} == "$sta" ]]; then
        client=$candidate
        break
    fi
done < <(lxc list -c n --format csv | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
[[ -n $client ]] || {
    echo "steer.sh: cannot map $sta to a live WLAN client container" >&2
    exit 1
}

bias_state=$(mktemp /tmp/easymesh-steer-bias.XXXXXX.json)
bias_active=0
restore_bias() {
    if ((bias_active)); then
        if timeout 20 python3 "$bias_tool" restore --state "$bias_state"; then
            bias_active=0
        else
            echo "steer.sh: WARNING: exact wmediumd RF restore failed; state retained at $bias_state" >&2
            return 1
        fi
    else
        rm -f "$bias_state"
    fi
}
cleanup() {
    rc=$?
    trap - EXIT INT TERM
    set +e
    restore_bias
    restore_rc=$?
    if ((rc == 0 && restore_rc != 0)); then rc=$restore_rc; fi
    exit "$rc"
}
trap cleanup EXIT INT TERM

echo "steer.sh: deterministic lab mode; client=$client source=$source_bssid target=$target_bssid frequency=${target_frequency}MHz"
timeout 30 python3 "$bias_tool" apply \
    --client "$client" --source-bssid "$source_bssid" \
    --target-bssid "$target_bssid" --state "$bias_state" \
    --frequency "$target_frequency" --source-snr 20 --target-snr 60 \
    --other-snr -20
bias_active=1

scan_ok=0
for _ in 1 2 3; do
    scan=$(timeout 10 lxc exec "$client" -- iw dev wlan0 scan \
        freq "$target_frequency" 2>/dev/null || true)
    if grep -Fqi "BSS $target_bssid(" <<<"$scan"; then
        scan_ok=1
        break
    fi
    sleep 1
done
((scan_ok)) || {
    echo "steer.sh: target $target_bssid was absent from the ${target_frequency}MHz candidate scan" >&2
    exit 1
}
echo "steer.sh: target candidate is visible; submitting the EasyMesh BTM request"

set +e
timeout 15 lxc exec "$controller" -- /usr/bin/steer.sh "$sta" "$target_bssid"
command_rc=$?
set -e
((command_rc == 0)) || {
    echo "steer.sh: controller steering command failed (rc=$command_rc)" >&2
    exit "$command_rc"
}

physical_bssid=
for _ in $(seq 1 50); do
    link=$(timeout 4 lxc exec "$client" -- iw dev wlan0 link 2>/dev/null || true)
    physical_bssid=$(awk '/Connected to/{value=$3} END{print value}' <<<"$link")
    [[ ${physical_bssid,,} == "$target_bssid" ]] && break
    sleep 0.2
done
[[ ${physical_bssid,,} == "$target_bssid" ]] || {
    echo "steer.sh: station did not accept/reassociate to $target_bssid" >&2
    exit 1
}

topology_converged=0
for _ in $(seq 1 30); do
    current=$(curl --connect-timeout "$curl_connect_timeout" --max-time 3 \
        -fsS "$topology_url" 2>/dev/null || true)
    if jq -e --arg sta "$sta" --arg target "$target_bssid" '
        first(.nodes[]?
          | select(any(.haulTypes[]?.BSSList[]?; (.BSSID // "" | ascii_downcase) == $target))
          | any(.STAList[]?; (.staMAC // "" | ascii_downcase) == $sta)) // false' \
        >/dev/null 2>&1 <<<"$current"; then
        topology_converged=1
        break
    fi
    sleep 0.2
done
((topology_converged)) || {
    echo "steer.sh: physical move succeeded, but controller/WebUI did not converge" >&2
    exit 1
}

restore_bias
echo "steer.sh: PASS $sta_input is physically and visibly associated with $target_name ($target_bssid)"
