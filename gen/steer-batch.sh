#!/usr/bin/env bash
set -euo pipefail

# Submit a deterministic group of EasyMesh steers under one RF transaction.
exec </dev/null

usage()
{
    cat >&2 <<'EOF'
usage:
  gen/steer-batch.sh STA TARGET [STA TARGET ...]
  gen/steer-batch.sh --count N

Examples:
  gen/steer-batch.sh sta-03 extender-1 sta-04 extender-2 iot-15 agent-1
  gen/steer-batch.sh --count 5

Explicit moves use the same client and target names as gen/steer.sh. --count
selects N distinct connected clients and compatible live destinations. The
batch applies one atomic wmediumd RF update, prepares all candidates, submits
BTM requests in a short serialized burst, verifies moves concurrently, and
restores the exact pre-test medium once.

Environment:
  EASYMESH_TOPOLOGY_URL          normalized topology API
  EASYMESH_STEER_BATCH_TIMEOUT   convergence timeout in seconds (default 45)
  EASYMESH_STEER_BATCH_RESULTS   result CSV path
  EASYMESH_COLOR                 auto, always or never
EOF
    exit "${1:-2}"
}

case ${1:-} in
    -h|--help) usage 0 ;;
esac
if (($# == 0)); then
    usage
fi

count=
if [[ ${1:-} == --count ]]; then
    (($# == 2)) || usage
    count=$2
    [[ $count =~ ^[1-9][0-9]*$ ]] || {
        echo "steer-batch.sh: --count requires a positive integer" >&2
        exit 2
    }
elif (($# % 2 != 0)); then
    usage
fi

repo=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=tests/lib/observer-status.sh
source "$repo/gen/tests/lib/observer-status.sh"
topology_url=${EASYMESH_TOPOLOGY_URL:-http://127.0.0.1:8888/api/v1/topology}
steering_url=${EASYMESH_STEERING_UI_URL:-${topology_url%/topology}/steering-event}
identity_inventory=${EASYMESH_IDENTITY_INVENTORY:-/run/meta-cmf-wmediumd/identity-inventory.json}
controller=${EASYMESH_CONTROLLER:-bpibroadband}
timeout_seconds=${EASYMESH_STEER_BATCH_TIMEOUT:-45}
results=${EASYMESH_STEER_BATCH_RESULTS:-$repo/tmp/test-results/steer-batch-$(date -u +%Y%m%dT%H%M%SZ).csv}
bias_tool=$repo/gen/tests/steering-rf-bias.py

[[ $timeout_seconds =~ ^[1-9][0-9]*$ ]] || {
    echo "steer-batch.sh: EASYMESH_STEER_BATCH_TIMEOUT must be a positive integer" >&2
    exit 2
}
for command in curl jq lxc flock python3; do
    command -v "$command" >/dev/null || {
        echo "steer-batch.sh: required command is missing: $command" >&2
        exit 1
    }
done
[[ -x $bias_tool ]] || {
    echo "steer-batch.sh: RF actuator is unavailable: $bias_tool" >&2
    exit 1
}
[[ -r $identity_inventory ]] || {
    echo "steer-batch.sh: identity inventory is unavailable: $identity_inventory" >&2
    exit 1
}

lock_root=${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}
lock_file=${EASYMESH_STEERING_LOCK:-$lock_root/easymesh-steering-$UID.lock}
exec 9>"$lock_file" || exit 1
if ! flock -n 9; then
    echo "steer-batch.sh: another batch steering transaction is active" >&2
    exit 1
fi

work=$(mktemp -d /tmp/easymesh-steer-batch.XXXXXX)
raw_moves=$work/raw.tsv
moves=$work/moves.tsv
plan=$work/plan.json
bias_state=$work/bias-state.json
: >"$raw_moves"
: >"$moves"
bias_active=0

medium_backend=${EASYMESH_MEDIUM_BACKEND:-}
if [[ -z $medium_backend && -r /etc/default/easymesh-lab ]]; then
    medium_backend=$(sed -n 's/^[[:space:]]*EASYMESH_MEDIUM_BACKEND=//p' \
        /etc/default/easymesh-lab | tail -1 | tr -d "'\"")
fi
medium_backend=${medium_backend:-userspace}
case "$medium_backend" in
    userspace) bias_command=(python3 "$bias_tool" --backend userspace) ;;
    kernel) bias_command=(sudo -n python3 "$bias_tool" --backend kernel) ;;
    *) echo "steer-batch.sh: unsupported medium backend: $medium_backend" >&2; exit 2 ;;
esac

restore_medium()
{
    if ((bias_active)) || [[ -s $bias_state ]]; then
        if "${bias_command[@]}" restore --state "$bias_state"; then
            bias_active=0
            status_pass "Restored the exact pre-batch RF matrix."
        else
            echo "steer-batch.sh: exact RF restore failed; state remains at $bias_state" >&2
            return 1
        fi
    fi
}

cleanup()
{
    rc=$?
    trap - EXIT INT TERM
    set +e
    restore_medium
    restore_rc=$?
    if ((rc == 0 && restore_rc != 0)); then rc=$restore_rc; fi
    if ((restore_rc == 0)); then rm -rf "$work"; fi
    exit "$rc"
}
trap cleanup EXIT INT TERM

topology=$(curl --connect-timeout 2 --max-time 10 -fsS "$topology_url") || {
    echo "steer-batch.sh: cannot read $topology_url" >&2
    exit 1
}
jq -e '.nodes | type == "array"' >/dev/null <<<"$topology" || {
    echo "steer-batch.sh: topology response has no nodes array" >&2
    exit 1
}

client_label()
{
    local sta=$1 ssid=$2 suffix
    suffix=$(cut -d: -f5 <<<"$sta" | tr '[:upper:]' '[:lower:]')
    case "$ssid" in
        private_ssid) printf 'sta-%s\n' "$suffix" ;;
        iot_ssid) printf 'iot-%s\n' "$suffix" ;;
        *) printf '%s\n' "$sta" ;;
    esac
}

sta_for_input()
{
    local input=${1,,}
    if [[ $input =~ ^(sta|iot)-([[:xdigit:]]{2})$ ]]; then
        printf '02:00:00:00:%s:00\n' "${BASH_REMATCH[2],,}"
    elif [[ $input =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
        printf '%s\n' "$input"
    else
        return 1
    fi
}

current_row()
{
    local sta=$1
    jq -r --arg sta "$sta" '
        [.nodes[] as $node | $node.STAList[]?
          | select((.staMAC // "" | ascii_downcase) == $sta)
          | [$node.name, (.bssid // ""), (.ssid // ""),
             ((.band // -1) | tostring)] | @tsv]
        | unique[]' <<<"$topology"
}

target_rows()
{
    local target=${1,,} source=$2 ssid=$3 band=$4
    if [[ $target =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
        jq -r --arg target "$target" --arg source "$source" \
            --arg ssid "$ssid" --argjson band "$band" '
            [.nodes[] | select(.name != $source) | . as $node
              | .haulTypes[]? as $haul | $haul.BSSList[]?
              | select((.BSSID // "" | ascii_downcase) == $target
                       and .Band == $band
                       and (.ssid // $haul.ssid // "") == $ssid)
              | [$node.name, .BSSID] | @tsv] | unique[]' <<<"$topology"
    else
        jq -r --arg target "$target" --arg source "$source" \
            --arg ssid "$ssid" --argjson band "$band" '
            [.nodes[]
              | select(.name != $source and (.name // "" | ascii_downcase) == $target)
              | . as $node | .haulTypes[]? as $haul | $haul.BSSList[]?
              | select(.Band == $band and (.ssid // $haul.ssid // "") == $ssid)
              | [$node.name, .BSSID] | @tsv] | unique[]' <<<"$topology"
    fi
}

append_explicit_move()
{
    local input=$1 target_input=$2 sta current_count target_count
    local source source_bssid ssid band label target target_bssid expected
    sta=$(sta_for_input "$input") || {
        echo "steer-batch.sh: invalid client '$input'" >&2
        return 1
    }
    mapfile -t current < <(current_row "$sta")
    current_count=${#current[@]}
    ((current_count == 1)) || {
        echo "steer-batch.sh: $input has $current_count live placements (expected one)" >&2
        return 1
    }
    IFS=$'\t' read -r source source_bssid ssid band <<<"${current[0]}"
    label=$(client_label "$sta" "$ssid")
    if [[ ${input,,} =~ ^(sta|iot)- && ${input,,} != "$label" ]]; then
        echo "steer-batch.sh: '$input' does not exist; $sta is '$label'" >&2
        return 1
    fi
    mapfile -t targets < <(target_rows "$target_input" "$source" "$ssid" "$band")
    target_count=${#targets[@]}
    ((target_count == 1)) || {
        echo "steer-batch.sh: target '$target_input' has $target_count compatible live BSSes for $label" >&2
        return 1
    }
    IFS=$'\t' read -r target target_bssid <<<"${targets[0]}"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$label" "$sta" "$source" "$source_bssid" "$ssid" "$band" \
        "$target" "$target_bssid" >>"$raw_moves"
}

if [[ -n $count ]]; then
    mapfile -t client_macs < <(jq -r '
        [.nodes[].STAList[]?.staMAC
          | select(. != null) | ascii_downcase] | unique | sort[]' <<<"$topology")
    if ((count > ${#client_macs[@]})); then
        echo "steer-batch.sh: requested $count moves but only ${#client_macs[@]} clients are connected" >&2
        exit 2
    fi
    for ((index=0; index<count; index++)); do
        sta=${client_macs[$index]}
        mapfile -t current < <(current_row "$sta")
        ((${#current[@]} == 1)) || exit 1
        IFS=$'\t' read -r source source_bssid ssid band <<<"${current[0]}"
        label=$(client_label "$sta" "$ssid")
        mapfile -t candidates < <(jq -r --arg source "$source" --arg ssid "$ssid" \
            --argjson band "$band" '
            [.nodes[] | select(.name != $source) | . as $node
              | [.haulTypes[]? as $haul | $haul.BSSList[]?
                  | select(.Band == $band and (.ssid // $haul.ssid // "") == $ssid)
                  | [$node.name, .BSSID] | @tsv]
              | unique[]] | flatten[]' <<<"$topology")
        ((${#candidates[@]} > 0)) || {
            echo "steer-batch.sh: no compatible destination for $label" >&2
            exit 1
        }
        IFS=$'\t' read -r target target_bssid \
            <<<"${candidates[$((index % ${#candidates[@]}))]}"
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$label" "$sta" "$source" "$source_bssid" "$ssid" "$band" \
            "$target" "$target_bssid" >>"$raw_moves"
    done
else
    while (($#)); do
        append_explicit_move "$1" "$2" || exit 1
        shift 2
    done
fi

duplicate=$(cut -f2 "$raw_moves" | sort | uniq -d | head -1)
[[ -z $duplicate ]] || {
    echo "steer-batch.sh: station $duplicate occurs more than once" >&2
    exit 2
}

mesh_radios=$(jq -c '
    [.stations[]?
      | select(.role == "extender" or .role == "controller-agent")
      | (.mac | ascii_downcase)] | unique | sort' "$identity_inventory")
(( $(jq 'length' <<<"$mesh_radios") >= 2 )) || {
    echo "steer-batch.sh: mesh radio roster is incomplete" >&2
    exit 1
}

radio_identity()
{
    local node=$1
    jq -r --arg node "$node" '
        [.stations[]?
          | select(.role == "extender" or .role == "controller-agent")
          | select((.label // "" | ascii_downcase) == ($node | ascii_downcase))
          | [.owner, (.mac | ascii_downcase)] | @tsv] | unique[]' \
        "$identity_inventory"
}

operating_tuple()
{
    local band=$1 frequency=$2 channel opclass
    case "$band" in
        0)
            if ((frequency == 2484)); then channel=14; opclass=82
            elif ((frequency >= 2412 && frequency <= 2472 && (frequency-2407)%5 == 0)); then
                channel=$(((frequency-2407)/5)); opclass=81
            else return 1; fi ;;
        1)
            ((frequency >= 5000 && frequency < 5955 && (frequency-5000)%5 == 0)) || return 1
            channel=$(((frequency-5000)/5))
            case "$channel" in
                36|40|44|48) opclass=115 ;;
                52|56|60|64) opclass=118 ;;
                100|104|108|112|116|120|124|128|132|136|140|144) opclass=121 ;;
                149|153|157|161) opclass=124 ;;
                165|169|173|177) opclass=125 ;;
                *) return 1 ;;
            esac ;;
        3)
            ((frequency >= 5955 && frequency <= 7115 && (frequency-5950)%5 == 0)) || return 1
            channel=$(((frequency-5950)/5)); opclass=131 ;;
        *) return 1 ;;
    esac
    printf '%s\t%s\n' "$opclass" "$channel"
}

while IFS=$'\t' read -r label sta source source_bssid ssid band target target_bssid; do
    mapfile -t client_ids < <(jq -r --arg sta "$sta" '
        [.stations[]?
          | select(.role == "wlan-client" or .role == "iot-client")
          | select((.mac // "" | ascii_downcase | sub("^[^:]+:"; ""))
                   == ($sta | sub("^[^:]+:"; "")))
          | [.owner, (.mac | ascii_downcase)] | @tsv] | unique[]' "$identity_inventory")
    mapfile -t source_ids < <(radio_identity "$source")
    mapfile -t target_ids < <(radio_identity "$target")
    ((${#client_ids[@]} == 1 && ${#source_ids[@]} == 1 && ${#target_ids[@]} == 1)) || {
        echo "steer-batch.sh: identity resolution failed for $label: client=${#client_ids[@]} source=${#source_ids[@]} target=${#target_ids[@]}" >&2
        exit 1
    }
    IFS=$'\t' read -r client station_radio <<<"${client_ids[0]}"
    IFS=$'\t' read -r _source_owner source_radio <<<"${source_ids[0]}"
    IFS=$'\t' read -r target_owner target_radio <<<"${target_ids[0]}"
    radio_state=$(timeout 6 lxc exec -T -n "$target_owner" -- iw dev 2>/dev/null || true)
    mapfile -t live_rows < <(awk -v target="${target_bssid,,}" '
        /^[[:space:]]*Interface / { interface=$2; address="" }
        /^[[:space:]]*addr / { address=tolower($2) }
        /^[[:space:]]*channel / && address == target {
            frequency=$3; gsub(/[()]/, "", frequency)
            print interface "\t" frequency
        }' <<<"$radio_state")
    ((${#live_rows[@]} == 1)) || {
        echo "steer-batch.sh: cannot resolve live frequency for $target/$target_bssid" >&2
        exit 1
    }
    IFS=$'\t' read -r target_interface frequency <<<"${live_rows[0]}"
    tuple=$(operating_tuple "$band" "$frequency") || {
        echo "steer-batch.sh: invalid live frequency ${frequency}MHz for $target/band $band" >&2
        exit 1
    }
    IFS=$'\t' read -r opclass channel <<<"$tuple"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$label" "$sta" "$source" "$source_bssid" "$ssid" "$band" "$target" \
        "$target_bssid" "$client" "$station_radio" "$source_radio" "$target_radio" \
        "$target_owner" "$frequency" "$opclass" "$channel" "$target_interface" >>"$moves"
done <"$raw_moves"

while IFS=$'\t' read -r label sta source source_bssid ssid band target target_bssid \
        client station_radio source_radio target_radio target_owner frequency opclass channel target_interface; do
    jq -nc --arg client "$client" --arg station "$station_radio" \
        --arg source "$source_radio" --arg target "$target_radio" \
        --argjson frequency "$frequency" --argjson radios "$mesh_radios" \
        '{client:$client,station_radio:$station,source_radio:$source,
          target_radio:$target,frequency_mhz:$frequency,mesh_radios:$radios,
          source_snr:20,target_snr:60,other_snr:-20}'
done <"$moves" | jq -s '{schema:"easymesh.steering-batch-plan.v1",moves:.}' >"$plan"

move_count=$(wc -l <"$moves")
mkdir -p "$(dirname "$results")"
printf '%s\n' 'client,sta,source,target,ssid,band,frequency_mhz,opclass,channel,command_rc,physical,modeled,result,duration_ms' >"$results"
status_section "EasyMesh batch steering"
status_note "Prepared $move_count distinct simultaneous moves."
status_note "One RF transaction: target=60dB, source=20dB, other=-20dB SNR per client."

announce()
{
    local sta=$1 label=$2 target=$3 phase=$4
    payload=$(jq -nc --arg sta "$sta" --arg client "$label" \
        --arg target "$target" --arg phase "$phase" \
        '{sta_mac:$sta,client_name:$client,target_name:$target,phase:$phase}')
    curl --connect-timeout 2 --max-time 2 -fsS -X POST \
        -H 'Content-Type: application/json' --data "$payload" "$steering_url" \
        >/dev/null 2>&1 || true
}

while IFS=$'\t' read -r label sta source source_bssid ssid band target _; do
    status_note "$label: $source -> $target on $ssid/band $band."
    announce "$sta" "$label" "$target" planned
done <"$moves"

status_action "Applying all client RF preferences atomically."
"${bias_command[@]}" apply-batch --plan "$plan" --state "$bias_state"
bias_active=1
while IFS=$'\t' read -r label sta source source_bssid ssid band target _; do
    announce "$sta" "$label" "$target" moving
done <"$moves"

prime_scan()
{
    local client=$1 target=$2 ssid=$3 frequency=$4 request scan ssid_hex
    ssid_hex=$(printf '%s' "$ssid" | od -An -tx1 | tr -d ' \n')
    for _ in 1 2 3; do
        request=$(timeout 8 lxc exec -T -n "$client" -- wpa_cli -i wlan0 scan \
            "freq=$frequency" "bssid=$target" "ssid $ssid_hex" 2>/dev/null || true)
        for _ in $(seq 1 20); do
            scan=$(timeout 5 lxc exec -T -n "$client" -- wpa_cli -i wlan0 scan_results \
                2>/dev/null || true)
            if [[ $request == OK ]] && awk -F $'\t' -v b="$target" -v s="$ssid" '
                tolower($1) == tolower(b) && $5 == s { found=1 }
                END { exit found ? 0 : 1 }' <<<"$scan"; then
                return 0
            fi
            sleep 0.1
        done
    done
    return 1
}

status_action "Preparing every candidate scan concurrently."
scan_index=0
scan_pids=()
while IFS=$'\t' read -r label sta source source_bssid ssid band target target_bssid \
        client station_radio source_radio target_radio target_owner frequency rest; do
    scan_log=$work/scan-$scan_index.log
    (prime_scan "$client" "$target_bssid" "$ssid" "$frequency") >"$scan_log" 2>&1 &
    scan_pids+=("$!")
    scan_index=$((scan_index + 1))
done <"$moves"
scan_failures=0
for ((index=0; index<${#scan_pids[@]}; index++)); do
    if ! wait "${scan_pids[$index]}"; then
        sed -n "$((index+1))p" "$moves" | cut -f1,8 | \
            awk -F '\t' '{print "steer-batch.sh: candidate scan failed for " $1 " -> " $2}' >&2
        scan_failures=$((scan_failures + 1))
    fi
done
((scan_failures == 0)) || exit 1
status_pass "All candidate BSS/ESS identities are present in their station caches."

status_action "Submitting BTM requests through the serialized controller command path."
start_ms=$(date +%s%3N)
command_index=0
while IFS=$'\t' read -r label sta source source_bssid ssid band target target_bssid \
        client station_radio source_radio target_radio target_owner frequency opclass channel target_interface; do
    command_file=$work/command-$command_index.rc
    current=$(timeout 5 lxc exec -T -n "$client" -- iw dev wlan0 link 2>/dev/null \
        | awk '/Connected to/{print tolower($3); exit}' || true)
    if [[ $current == "${target_bssid,,}" ]]; then
        status_pass "$label reassociated during RF preparation; no BTM was needed."
        printf '0\n' >"$command_file"
    else
        status_action "$label: sending BTM request to $target ($target_bssid), opclass $opclass/channel $channel."
        set +e
        timeout --signal=TERM --kill-after=2 45 lxc exec -T -n "$controller" -- \
            /usr/bin/steer.sh "$sta" "$target_bssid" "$opclass" "$channel"
        command_rc=$?
        set -e
        printf '%s\n' "$command_rc" >"$command_file"
    fi
    command_index=$((command_index + 1))
done <"$moves"

verify_move()
{
    local index=$1 label=$2 sta=$3 source=$4 target=$5 target_bssid=$6 client=$7
    local ssid=$8 band=$9 frequency=${10} opclass=${11} channel=${12}
    local physical= modeled= topology_now deadline command_rc result
    command_rc=$(cat "$work/command-$index.rc")
    deadline=$((SECONDS + timeout_seconds))
    while ((SECONDS < deadline)); do
        physical=$(timeout 5 lxc exec -T -n "$client" -- iw dev wlan0 link 2>/dev/null \
            | awk '/Connected to/{print tolower($3); exit}' || true)
        topology_now=$(curl --connect-timeout 2 --max-time 4 -fsS "$topology_url" 2>/dev/null || true)
        modeled=$(jq -r --arg sta "$sta" '
            first(.nodes[].STAList[]?
              | select((.staMAC // "" | ascii_downcase) == $sta)
              | (.bssid // "" | ascii_downcase)) // ""' <<<"$topology_now" 2>/dev/null || true)
        if [[ $physical == "${target_bssid,,}" && $modeled == "${target_bssid,,}" ]]; then
            result=PASS
            announce "$sta" "$label" "$target" completed
            break
        fi
        sleep 0.25
    done
    if [[ ${result:-} != PASS ]]; then
        result=FAIL
        announce "$sta" "$label" "$target" failed
    fi
    duration=$(( $(date +%s%3N) - start_ms ))
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$label" "$sta" "$source" "$target" "$ssid" "$band" "$frequency" \
        "$opclass" "$channel" "$command_rc" "${physical:-none}" "${modeled:-none}" \
        "$result" "$duration" >"$work/result-$index.csv"
    [[ $result == PASS ]]
}

status_wait "Waiting up to ${timeout_seconds}s for every physical and controller-visible move."
verify_pids=()
verify_index=0
while IFS=$'\t' read -r label sta source source_bssid ssid band target target_bssid \
        client station_radio source_radio target_radio target_owner frequency opclass channel target_interface; do
    verify_move "$verify_index" "$label" "$sta" "$source" "$target" "$target_bssid" \
        "$client" "$ssid" "$band" "$frequency" "$opclass" "$channel" &
    verify_pids+=("$!")
    verify_index=$((verify_index + 1))
done <"$moves"
failures=0
for pid in "${verify_pids[@]}"; do
    wait "$pid" || failures=$((failures + 1))
done
for ((index=0; index<move_count; index++)); do
    cat "$work/result-$index.csv" >>"$results"
done

restore_medium
status_section "Batch steering summary"
status_note "moves=$move_count passed=$((move_count-failures)) failed=$failures"
status_note "results=$results"
if ((failures > 0)); then
    exit 1
fi
status_pass "All $move_count batch moves converged physically and in the WebUI model."
