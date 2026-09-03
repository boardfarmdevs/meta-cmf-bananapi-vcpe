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
steering_url=${EASYMESH_STEERING_UI_URL:-${topology_url%/topology}/steering-event}
controller=${EASYMESH_CONTROLLER:-bpibroadband}
repo=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=tests/lib/observer-status.sh
source "$repo/gen/tests/lib/observer-status.sh"
bias_tool=$repo/gen/tests/steering-rf-bias.py
identity_inventory=${EASYMESH_IDENTITY_INVENTORY:-/run/meta-cmf-wmediumd/identity-inventory.json}
curl_connect_timeout=${EASYMESH_CURL_CONNECT_TIMEOUT:-2}
curl_timeout=${EASYMESH_CURL_TIMEOUT:-8}
bias_timeout=${EASYMESH_BIAS_TIMEOUT:-30}
controller_steer_timeout=${EASYMESH_CONTROLLER_STEER_TIMEOUT:-45}
preview_seconds=${EASYMESH_STEERING_PREVIEW_SECONDS:-3}
medium_backend=${EASYMESH_MEDIUM_BACKEND:-}
if [[ -z $medium_backend && -r /etc/default/easymesh-lab ]]; then
    medium_backend=$(sed -n 's/^[[:space:]]*EASYMESH_MEDIUM_BACKEND=//p' \
        /etc/default/easymesh-lab | tail -1 | tr -d "'\"")
fi
medium_backend=${medium_backend:-userspace}
case "$medium_backend" in
    userspace) bias_command=(python3 "$bias_tool" --backend userspace) ;;
    kernel) bias_command=(sudo -n python3 "$bias_tool" --backend kernel) ;;
    *) echo "steer.sh: unsupported medium backend: $medium_backend" >&2; exit 2 ;;
esac

announce_steering() {
    local phase=$1
    local payload
    payload=$(jq -nc --arg sta "$sta" --arg client "$sta_input" \
        --arg target "$target_name" --arg phase "$phase" \
        '{sta_mac:$sta,client_name:$client,target_name:$target,phase:$phase}')
    curl --connect-timeout "$curl_connect_timeout" --max-time 2 -fsS \
        -X POST -H 'Content-Type: application/json' --data "$payload" \
        "$steering_url" >/dev/null 2>&1 || true
}

lxc_exec_bounded() {
    local limit=$1
    shift
    timeout --signal=TERM --kill-after=2 "$limit" \
        lxc exec -T -n "$@"
}

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
    requested_cohort=${BASH_REMATCH[1]}
    requested_suffix=${BASH_REMATCH[2],,}
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
if [[ -n ${requested_cohort:-} ]]; then
    case "$source_ssid" in
        private_ssid) live_label=sta-$requested_suffix ;;
        iot_ssid)     live_label=iot-$requested_suffix ;;
        *)            live_label= ;;
    esac
    if [[ -n $live_label && $sta_input != "$live_label" ]]; then
        echo "steer.sh: '$sta_input' does not exist; $sta is '$live_label' on $source_ssid" >&2
        exit 1
    fi
fi
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

status_section "EasyMesh steering: $sta_input to $target_name"
status_note "Station $sta currently uses $source_name ($source_bssid)."
status_note "Target BSSID $target_bssid carries $target_ssid on band $target_band."
printf 'steer.sh: %s -> %s; STA=%s target_BSSID=%s SSID=%s band=%s\n' \
    "$sta_input" "$target_name" "$sta" "$target_bssid" "$target_ssid" "$target_band"
if ((dry_run)); then
    if ((request_only)); then
        printf 'steer.sh: dry run; request-only mode\n'
    else
        printf 'steer.sh: dry run; deterministic lab mode (temporary RF bias, candidate scan, verified move)\n'
    fi
    printf 'steer.sh: dry run; would execute: lxc exec -T -n %q -- /usr/bin/steer.sh %q %q\n' \
        "$controller" "$sta" "$target_bssid"
    exit 0
fi

timeout --signal=TERM --kill-after=2 5 lxc info "$controller" >/dev/null 2>&1 || {
    echo "steer.sh: controller container '$controller' is not available" >&2
    exit 1
}
if ! lxc_exec_bounded 5 "$controller" -- true >/dev/null 2>&1; then
    echo "steer.sh: nested LXD cannot execute commands in '$controller'; no steering request was sent" >&2
    exit 1
fi

if ((request_only)); then
    status_action "Using standards-only mode; no temporary RF preference will be applied."
    announce_steering planned
    status_wait_seconds "$preview_seconds" "highlighting $sta_input in the topology before the request"
    announce_steering moving
    status_action "Sending the BTM steering request for $sta to $target_bssid."
    lxc_exec_bounded "$controller_steer_timeout" "$controller" -- \
        /usr/bin/steer.sh "$sta" "$target_bssid"
    exit $?
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

[[ -r $identity_inventory ]] || {
    echo "steer.sh: wmediumd identity inventory is unavailable: $identity_inventory" >&2
    exit 1
}
mapfile -t client_identity < <(jq -r --arg input "$sta_input" --arg sta "$sta" '
    [.stations[]?
      | select(.role == "wlan-client" or .role == "iot-client")
      | select(
          ((.label // "" | ascii_downcase) == $input)
          or ((.mac // "" | ascii_downcase | sub("^[^:]+:"; ""))
              == ($sta | sub("^[^:]+:"; ""))))
      | [.owner, (.mac | ascii_downcase)] | @tsv]
    | unique[]' "$identity_inventory")
if ((${#client_identity[@]} != 1)); then
    echo "steer.sh: $sta_input has ${#client_identity[@]} wmediumd identity matches (expected 1)" >&2
    exit 1
fi
IFS=$'\t' read -r client station_radio <<<"${client_identity[0]}"

radio_for_node() {
    local node=$1
    jq -r --arg node "$node" '
        [.stations[]?
          | select(.role == "extender" or .role == "controller-agent")
          | select((.label // "" | ascii_downcase) == ($node | ascii_downcase))
          | (.mac | ascii_downcase)]
        | unique[]' "$identity_inventory"
}
mapfile -t source_radios < <(radio_for_node "$source_name")
mapfile -t target_radios < <(radio_for_node "$target_name")
mapfile -t mesh_radios < <(jq -r '
    [.stations[]?
      | select(.role == "extender" or .role == "controller-agent")
      | (.mac | ascii_downcase)]
    | unique | sort[]' "$identity_inventory")
if ((${#source_radios[@]} != 1)); then
    echo "steer.sh: $source_name has ${#source_radios[@]} wmediumd radio identities (expected 1)" >&2
    exit 1
fi
if ((${#target_radios[@]} != 1)); then
    echo "steer.sh: $target_name has ${#target_radios[@]} wmediumd radio identities (expected 1)" >&2
    exit 1
fi
if ((${#mesh_radios[@]} < 2)); then
    echo "steer.sh: wmediumd identity inventory has fewer than two mesh radios" >&2
    exit 1
fi
source_radio=${source_radios[0]}
target_radio=${target_radios[0]}
timeout --signal=TERM --kill-after=2 5 lxc info "$client" >/dev/null 2>&1 || {
    echo "steer.sh: client container '$client' is not available" >&2
    exit 1
}
if ! lxc_exec_bounded 5 "$client" -- true >/dev/null 2>&1; then
    echo "steer.sh: nested LXD cannot execute commands in '$client'; no RF bias was applied" >&2
    exit 1
fi

bias_state=$(mktemp /tmp/easymesh-steer-bias.XXXXXX.json)
bias_active=0
steering_announced=0
restore_bias() {
    # The helper writes the exact pre-change state before sending its atomic
    # update.  A timeout in that small window must therefore restore too, even
    # though the helper did not live long enough to report success.
    if ((bias_active)) || [[ -s $bias_state ]]; then
        if timeout --signal=TERM --kill-after=2 20 \
                "${bias_command[@]}" restore --state "$bias_state"; then
            bias_active=0
            status_pass "Restored the exact pre-test RF matrix."
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
    if ((rc != 0 && steering_announced)); then announce_steering failed; fi
    restore_bias
    restore_rc=$?
    if ((rc == 0 && restore_rc != 0)); then rc=$restore_rc; fi
    exit "$rc"
}
trap cleanup EXIT INT TERM

status_action "Resolved $sta_input to container $client and ${target_frequency} MHz."
announce_steering planned
steering_announced=1
status_wait_seconds "$preview_seconds" "highlighting $sta_input before it moves"
announce_steering moving
status_action "Making $target_name stronger than $source_name in the simulated medium."
bias_args=(
    apply --client "$client" --source-bssid "$source_bssid"
    --target-bssid "$target_bssid" --state "$bias_state"
    --frequency "$target_frequency" --source-snr 20 --target-snr 60
    --other-snr -20 --station-radio "$station_radio"
    --source-radio "$source_radio" --target-radio "$target_radio"
)
for radio in "${mesh_radios[@]}"; do
    bias_args+=(--mesh-radio "$radio")
done
set +e
timeout --signal=TERM --kill-after=2 "$bias_timeout" \
    "${bias_command[@]}" "${bias_args[@]}"
bias_rc=$?
set -e
if ((bias_rc != 0)); then
    [[ -s $bias_state ]] && bias_active=1
    if ((bias_rc == 124 || bias_rc == 137)); then
        echo "steer.sh: RF-bias setup timed out after ${bias_timeout}s; no steering request was sent" >&2
    else
        echo "steer.sh: RF-bias setup failed (rc=$bias_rc); no steering request was sent" >&2
    fi
    exit "$bias_rc"
fi
bias_active=1

status_action "Scanning ${target_frequency} MHz so the station can see candidate $target_bssid."
if ! lxc_exec_bounded 12 "$client" -- sh -c '
    frequency=$1
    target=$2
    attempt=0
    while [ "$attempt" -lt 3 ]; do
        request=$(wpa_cli -i wlan0 scan "freq=$frequency" 2>/dev/null || true)
        sleep 1
        scan=$(wpa_cli -i wlan0 scan_results 2>/dev/null || true)
        if [ "$request" = OK ] && printf "%s\n" "$scan" | grep -Fqi "$target"; then
            exit 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    exit 1
' sh "$target_frequency" "$target_bssid" >/dev/null 2>&1; then
    echo "steer.sh: target $target_bssid was absent from the ${target_frequency}MHz candidate scan" >&2
    exit 1
fi
link=$(lxc_exec_bounded 6 "$client" -- iw dev wlan0 link 2>/dev/null || true)
physical_bssid=$(awk '/Connected to/{value=$3} END{print value}' <<<"$link")
if [[ ${physical_bssid,,} == "$target_bssid" ]]; then
    status_pass "The station reassociated during RF preparation; no BTM request was needed."
else
    status_pass "The target BSSID is present in the station scan cache."
    status_action "Sending the EasyMesh BTM request for $sta to $target_bssid."
    set +e
    # The native command transport has a 30-second I/O bound and controller
    # commands are serialized.  Keep the outer deadline above that contract so
    # a steer queued behind a live WebUI query is not killed while still valid.
    # Do not retry an ambiguous timeout: the controller may already have sent
    # the BTM request even if delivery of its command result was delayed.
    lxc_exec_bounded "$controller_steer_timeout" "$controller" -- \
        /usr/bin/steer.sh "$sta" "$target_bssid"
    command_rc=$?
    set -e
    ((command_rc == 0)) || {
        echo "steer.sh: controller steering command failed (rc=$command_rc)" >&2
        exit "$command_rc"
    }
fi

status_wait "Waiting up to 10s for the station to associate with $target_bssid."
link=$(lxc_exec_bounded 15 "$client" -- sh -c '
    target=$1
    attempt=0
    link=
    while [ "$attempt" -lt 50 ]; do
        link=$(iw dev wlan0 link 2>/dev/null || true)
        bssid=$(printf "%s\n" "$link" | awk '\''/Connected to/{value=$3} END{print value}'\'')
        if [ "$bssid" = "$target" ]; then
            printf "%s\n" "$link"
            exit 0
        fi
        attempt=$((attempt + 1))
        sleep 0.2
    done
    printf "%s\n" "$link"
    exit 1
' sh "$target_bssid" 2>/dev/null || true)
physical_bssid=$(awk '/Connected to/{value=$3} END{print value}' <<<"$link")
[[ ${physical_bssid,,} == "$target_bssid" ]] || {
    echo "steer.sh: station did not accept/reassociate to $target_bssid" >&2
    exit 1
}
status_pass "$sta_input is physically associated with $target_bssid."

topology_converged=0
status_wait "Waiting up to 6s for controller ownership and the WebUI topology to converge."
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

announce_steering completed
steering_announced=0
restore_bias
status_pass "$sta_input is physically and visibly associated with $target_name ($target_bssid)."
