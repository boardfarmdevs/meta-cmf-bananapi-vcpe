#!/usr/bin/env bash
set -euo pipefail

# Run a repeatable commanded-steering matrix against an already healthy lab.
# A pass requires agreement from the client link, controller DB and WebUI API;
# the command response by itself is not sufficient.
exec </dev/null

rounds=1
ssid=private_ssid
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then rounds=$1; shift; fi
while [ $# -gt 0 ]; do
    case "$1" in
        --ssid) ssid=$2; shift 2 ;;
        *) echo "usage: $0 [rounds] [--ssid private_ssid|iot_ssid]" >&2; exit 2 ;;
    esac
done
case "$ssid" in private_ssid|iot_ssid) ;; *) echo "unsupported SSID: $ssid" >&2; exit 2;; esac
repo=${EASYMESH_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}
results=${RESULTS_FILE:-$repo/tmp/test-results/steering-scale.csv}
steering_frequency=${STEERING_FREQUENCY:-5180}
steering_source_snr=${STEERING_SOURCE_SNR:-20}
steering_target_snr=${STEERING_TARGET_SNR:-60}
steering_other_snr=${STEERING_OTHER_SNR:--20}
[[ "$steering_frequency" =~ ^[1-9][0-9]*$ ]] \
    || { echo "STEERING_FREQUENCY must be a positive integer" >&2; exit 2; }
for value in "$steering_source_snr" "$steering_target_snr" "$steering_other_snr"; do
    [[ "$value" =~ ^-?[0-9]+$ ]] \
        || { echo "steering SNR values must be integers" >&2; exit 2; }
done
mkdir -p "$(dirname "$results")"
run_id=${RUN_ID:-$(date -u +%Y%m%dT%H%M%S.%3NZ)-$$}
events=${EVENTS_FILE:-${results%.csv}.events.log}
commands=${COMMANDS_FILE:-${results%.csv}.commands.log}
: > "$events"
: > "$commands"

medium_backend=${EASYMESH_MEDIUM_BACKEND:-}
if [[ -z $medium_backend && -r /etc/default/easymesh-lab ]]; then
    medium_backend=$(sed -n 's/^[[:space:]]*EASYMESH_MEDIUM_BACKEND=//p' \
        /etc/default/easymesh-lab | tail -1 | tr -d "'\"")
fi
medium_backend=${medium_backend:-userspace}
case "$medium_backend" in
    userspace) bias_command=(python3 "$repo/gen/tests/steering-rf-bias.py" --backend userspace) ;;
    kernel) bias_command=(sudo -n python3 "$repo/gen/tests/steering-rf-bias.py" --backend kernel) ;;
    *) echo "unsupported medium backend: $medium_backend" >&2; exit 2 ;;
esac

# The test starts from the caller's current matrix and restores every temporary
# bias exactly. A full all-strong restart is only the failure-path fallback.
medium_restored=1
restore_medium() {
    if [ "$medium_restored" -eq 1 ]; then
        return 0
    fi
    if [[ -n ${active_bias_state:-} && -s $active_bias_state ]] \
        && "${bias_command[@]}" restore --state "$active_bias_state" >/dev/null; then
        active_bias_state=
        medium_restored=1
        return 0
    fi
    echo "failed to restore the exact $medium_backend medium state" >&2
    return 1
}
cleanup() {
    rc=$?
    trap - EXIT
    set +e
    restore_medium
    cleanup_rc=$?
    if [ "$rc" -eq 0 ] && [ "$cleanup_rc" -ne 0 ]; then
        rc=$cleanup_rc
    fi
    exit "$rc"
}
trap cleanup EXIT

client_mac() {
    local client=$1 value
    for _ in $(seq 1 5); do
        value=$(lxc exec "$client" -- iw dev wlan0 info 2>/dev/null \
            | awk '/addr/{print $2}' || true)
        if [ -n "$value" ]; then
            printf '%s\n' "$value"
            return 0
        fi
        sleep 0.1
    done
    echo "unable to read station MAC from $client" >&2
    return 1
}

client_bssid() {
    local client=$1 attempts=${2:-5} value
    for _ in $(seq 1 "$attempts"); do
        value=$(lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
            | awk '/Connected to/{print $3}' || true)
        if [ -n "$value" ]; then
            printf '%s\n' "$value"
            return 0
        fi
        sleep 0.1
    done
    return 1
}

# The minimal lab supplicant keeps a deliberately small scan cache. A BTM
# candidate that has not been observed recently can therefore be rejected even
# though wmediumd already makes that BSS the strongest choice. Prime the exact
# test frequency after applying the RF bias and require the requested target to
# be visible. This models the candidate discovery a production station normally
# performs and makes private/IoT steering deterministic for the same reason.
prime_candidate_scan() {
    local client=$1 target=$2 frequency=$3 scan
    for _ in $(seq 1 5); do
        scan=$(lxc exec "$client" -- iw dev wlan0 scan freq "$frequency" \
            2>/dev/null || true)
        if grep -Fqi "BSS $target(" <<<"$scan"; then
            echo "candidate scan primed: $client target=$target frequency=${frequency}MHz"
            return 0
        fi
        sleep 1
    done
    echo "$client: target $target was absent from the ${frequency}MHz scan" >&2
    return 1
}

mapfile -t clients < <(
    while read -r client; do
        [ -n "$client" ] || continue
        intent=$(lxc config get "$client" user.easymesh.ssid 2>/dev/null || true)
        [ -n "$intent" ] || intent=$(lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
            | sed -n 's/^[[:space:]]*SSID: //p' | head -1)
        [ "$intent" = "$ssid" ] || continue

        # This matrix intentionally exercises the common 5 GHz steering
        # targets selected below. The small topology also contains one
        # deterministic 2.4 GHz client and one deterministic 6 GHz client;
        # their supplicant freq_list excludes 5 GHz, so a 5 GHz BTM request
        # cannot be a valid test for them. Keep those clients in the full
        # topology, but do not count an intentionally prohibited band change
        # as a steering failure.
        configured_band=$(lxc config get "$client" user.easymesh.band 2>/dev/null || true)
        case "$configured_band" in
            2.4|6)
                echo "skipping $client: configured band $configured_band excludes 5 GHz targets" >&2
                ;;
            *)
                echo "$client"
                ;;
        esac
    done < <(lxc list -c n --format csv \
        | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
)
topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology)
expected_total_clients=$(jq -r \
    '[.nodes[].STAList[]?.staMAC] | unique | length' <<<"$topology")
bsses=$(curl -fsS http://127.0.0.1:8888/api/v1/bsses)
mapfile -t target_rows < <(jq -nr \
    --argjson topology "$topology" --argjson bsses "$bsses" --arg ssid "$ssid" '
      $bsses.bsses[] | select(.ssid == $ssid and .band == 1) as $bss
      | [([$topology.nodes[] | select(.id == $bss.device_id) | .name][0]
          // $bss.device_id), $bss.bssid] | @tsv' | sort -V)

if [ "${#clients[@]}" -eq 0 ] || [ "${#target_rows[@]}" -ne 5 ]; then
    echo "expected a non-empty $ssid cohort and 5 target agents; found ${#clients[@]} and ${#target_rows[@]}" >&2
    exit 1
fi

printf '%s\n' 'round,client,sta,target_name,source_bssid,target_bssid,command_rc,link_ms,db_ms,topology_ms,packet_loss,result,run_id,transaction_id,started_at_utc' > "$results"
failures=0

for ((round=1; round <= rounds; round++)); do
    for ((index=0; index < ${#clients[@]}; index++)); do
        client=${clients[$index]}
        sta=$(client_mac "$client")
        source=$(client_bssid "$client")
        target_index=$(( (index + round) % ${#target_rows[@]} ))
        IFS=$'\t' read -r target_name target <<< "${target_rows[$target_index]}"
        if [ "$target" = "$source" ]; then
            target_index=$(( (target_index + 1) % ${#target_rows[@]} ))
            IFS=$'\t' read -r target_name target <<< "${target_rows[$target_index]}"
        fi
        transaction_id=$(printf '%s-r%03d-c%03d' "$run_id" "$round" "$index")
        started_at=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
        printf '%s transaction=%s event=start client=%s sta=%s source=%s target=%s\n' \
            "$started_at" "$transaction_id" "$client" "$sta" "$source" "$target" \
            | tee -a "$events"

        bias_state=$(mktemp)
        rm -f "$bias_state"
        active_bias_state=$bias_state
        medium_restored=0
        "${bias_command[@]}" apply \
            --client "$client" --source-bssid "$source" \
            --target-bssid "$target" --state "$bias_state" \
            --frequency "$steering_frequency" \
            --source-snr "$steering_source_snr" \
            --target-snr "$steering_target_snr" \
            --other-snr "$steering_other_snr" \
            | tee -a "$commands"
        prime_candidate_scan "$client" "$target" "$steering_frequency" \
            | tee -a "$commands"

        ping_file=$(mktemp)
        lxc exec "$client" -- ping -q -i 0.1 -c 100 -W 2 10.0.0.1 \
            >"$ping_file" 2>&1 &
        ping_pid=$!
        start_ms=$(date +%s%3N)
        set +e
        lxc exec bpibroadband -- /usr/bin/steer.sh "$sta" "$target" 2>&1 \
            | sed "s/^/$transaction_id /" | tee -a "$commands"
        command_rc=${PIPESTATUS[0]}
        set -e

        link_ms=-1
        for _ in $(seq 1 100); do
            actual=$(client_bssid "$client" 1 || true)
            if [ "$actual" = "$target" ]; then
                link_ms=$(( $(date +%s%3N) - start_ms ))
                break
            fi
            sleep 0.1
        done

        db_ms=-1
        topology_ms=-1
        for _ in $(seq 1 100); do
            if [ "$db_ms" -lt 0 ]; then
                db_bssid=$(lxc exec bpibroadband -- mysql -N -ubpi -proot \
                    OneWifiMesh -e "select BSSID from STAList where MACAddress='$sta' and Associated=1 limit 1" \
                    2>/dev/null || true)
                [ "$db_bssid" = "$target" ] \
                    && db_ms=$(( $(date +%s%3N) - start_ms ))
            fi
            if [ "$topology_ms" -lt 0 ] \
                && curl -fsS http://127.0.0.1:8888/api/v1/topology \
                    | jq -e --arg sta "$sta" --arg target "$target" '
                        ([.nodes[]
                          | select(any(.haulTypes[]?.BSSList[]?; .BSSID == $target))
                          | .id][0]) as $target_node
                        | any(.nodes[] | select(.id == $target_node) | .STAList[]?;
                              .staMAC == $sta)' >/dev/null; then
                topology_ms=$(( $(date +%s%3N) - start_ms ))
            fi
            [ "$db_ms" -ge 0 ] && [ "$topology_ms" -ge 0 ] && break
            sleep 0.1
        done

        "${bias_command[@]}" restore \
            --state "$bias_state" | tee -a "$commands"
        active_bias_state=
        medium_restored=1

        wait "$ping_pid" || true
        loss=$(sed -n 's/.* \([0-9]*%\) packet loss.*/\1/p' "$ping_file")
        rm -f "$ping_file"
        result=PASS
        if [ "$command_rc" -ne 0 ] || [ "$link_ms" -lt 0 ] \
            || [ "$db_ms" -lt 0 ] || [ "$topology_ms" -lt 0 ] \
            || [ -z "$loss" ]; then
            result=FAIL
            failures=$((failures + 1))
        fi
        completed_at=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
        printf '%s transaction=%s event=complete command_rc=%s link_ms=%s db_ms=%s topology_ms=%s packet_loss=%s result=%s\n' \
            "$completed_at" "$transaction_id" "$command_rc" "$link_ms" "$db_ms" \
            "$topology_ms" "${loss:-unknown}" "$result" | tee -a "$events"
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "$round" "$client" "$sta" "$target_name" "$source" "$target" \
            "$command_rc" "$link_ms" "$db_ms" "$topology_ms" "${loss:-unknown}" "$result" \
            "$run_id" "$transaction_id" "$started_at" \
            | tee -a "$results"
        sleep 1
    done
done

# Return to the known all-strong baseline before checking final topology. The
# EXIT trap provides the same guarantee when any earlier command fails.
restore_medium

topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology)
[ "$(jq -r '[.nodes[].STAList[]?.staMAC] | unique | length' <<<"$topology")" \
    -eq "$expected_total_clients" ]
echo "steering matrix complete: $((rounds * ${#clients[@]} - failures))/$((rounds * ${#clients[@]})) passed"
echo "results: $results"
echo "events: $events"
echo "commands: $commands"
exit "$failures"
