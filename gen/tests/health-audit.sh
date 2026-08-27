#!/usr/bin/env bash
set -euo pipefail

exec </dev/null
repo=${EASYMESH_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}
results=${RESULTS_FILE:-$repo/tmp/test-results/steering-scale.csv}
ping_count=${HEALTH_PING_COUNT:-10}
ping_interval=${HEALTH_PING_INTERVAL:-1}
ping_max_loss=${HEALTH_PING_MAX_LOSS:-0}
ping_exec_attempts=${HEALTH_PING_EXEC_ATTEMPTS:-2}
ping_exec_timeout=${HEALTH_PING_EXEC_TIMEOUT:-20}
expected_devices=${HEALTH_EXPECT_DEVICES:-5}
expected_radios=${HEALTH_EXPECT_RADIOS:-15}
expected_bsses=${HEALTH_EXPECT_BSSES:-50}
expected_clients=${HEALTH_EXPECT_CLIENTS:-20}
expected_associated=$((expected_clients + expected_devices - 1))

[[ "$ping_count" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_PING_COUNT must be a positive integer" >&2; exit 2; }
[[ "$ping_interval" =~ ^[0-9]+([.][0-9]+)?$ ]] \
    || { echo "HEALTH_PING_INTERVAL must be a non-negative number" >&2; exit 2; }
[[ "$ping_max_loss" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
    || { echo "HEALTH_PING_MAX_LOSS must be an integer from 0 through 100" >&2; exit 2; }
[[ "$ping_exec_attempts" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_PING_EXEC_ATTEMPTS must be a positive integer" >&2; exit 2; }
[[ "$ping_exec_timeout" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_PING_EXEC_TIMEOUT must be a positive integer" >&2; exit 2; }

echo TOPOLOGY
curl -fsS http://127.0.0.1:8888/api/v1/topology | jq -r '
    .nodes[] | [.name, .id, ([.haulTypes[]?.BSSList[]?] | length),
    (.STAList | length)] | @tsv'
echo MODEL
model=$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
    'select (select count(*) from DeviceList),
    (select count(*) from RadioList),
    (select count(*) from BSSList),
    (select count(*) from STAList where Associated=1)' 2>/dev/null)
echo "$model"
read -r devices radios bsses associated <<<"$model"
model_fail=0
if [ "$devices/$radios/$bsses/$associated" != \
    "$expected_devices/$expected_radios/$expected_bsses/$expected_associated" ]; then
    model_fail=1
fi
echo LIVE_CLIENTS
topology_json=$(mktemp)
curl -fsS http://127.0.0.1:8888/api/v1/topology >"$topology_json"
live_clients=$(jq -r '[.nodes[].STAList[]?.staMAC] | unique | length' "$topology_json")
echo "$live_clients"
[ "$live_clients" = "$expected_clients" ] || model_fail=1

echo BACKHAUL_SIGNALS
read -r wireless_edges fresh_edges < <(jq -r '
    [.edges[]? | select(.mediaType == "Wireless LAN")] as $edges |
    [$edges | length,
     [$edges[] | select(.signal.status == "fresh")] | length] | @tsv
' "$topology_json")
echo "fresh=$fresh_edges/$wireless_edges"
[ "$wireless_edges" = "$((expected_devices - 1))" ] || model_fail=1
[ "$fresh_edges" = "$wireless_edges" ] || model_fail=1

echo ASSOCIATION_OWNERSHIP
clients_json=$(mktemp)
trap 'rm -f "$clients_json" "$topology_json"' EXIT
curl -fsS http://127.0.0.1:8888/api/v1/clients >"$clients_json"
ownership_fail=0
while read -r client; do
    mac=$(lxc exec "$client" -- cat /sys/class/net/wlan0/address </dev/null 2>/dev/null |
        tr '[:upper:]' '[:lower:]')
    physical=$(lxc exec "$client" -- iw dev wlan0 link </dev/null 2>/dev/null |
        awk '/^Connected to / && !found {bssid=tolower($3); found=1}
             END {if (found) print bssid}')
    api=$(jq -r --arg mac "$mac" '(.clients // .)[]? |
        select((.mac | ascii_downcase) == $mac) | .connected_bssid' \
        "$clients_json" | head -1 | tr '[:upper:]' '[:lower:]')
    if [ -n "$physical" ] && [ "$physical" = "$api" ]; then
        echo "$client $mac $physical OK"
    else
        echo "$client $mac physical=${physical:-missing} api=${api:-missing} MISMATCH"
        ownership_fail=1
    fi
done < <(lxc list -c n --format csv |
    grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)

echo RESTARTS
restart_fail=0
for container in bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003; do
    for unit in onewifi em_agent; do
        restarts=$(lxc exec "$container" -- systemctl show "$unit" \
            -p NRestarts --value)
        echo "$container $unit=$restarts"
        [ "$restarts" = 0 ] || restart_fail=1
    done
done
for unit in em_ctrl em_cli; do
    restarts=$(lxc exec bpibroadband -- systemctl show "$unit" \
        -p NRestarts --value)
    echo "bpibroadband $unit=$restarts"
    [ "$restarts" = 0 ] || restart_fail=1
done

echo CONNECTIVITY
traffic_fail=0
declare -a traffic_pids=()
while read -r client; do
    (
        ping_output=
        for ((attempt = 1; attempt <= ping_exec_attempts; attempt++)); do
            if ping_output=$(timeout "$ping_exec_timeout" \
                lxc exec "$client" -- ping -q -c "$ping_count" \
                -i "$ping_interval" -W 2 10.0.0.1 2>/dev/null); then
                break
            fi
            ping_output=
        done
        loss=$(sed -n 's/.* \([0-9]*%\) packet loss.*/\1/p' <<<"$ping_output")
        echo "$client ${loss:-FAIL}"
        loss_value=${loss%%%}
        [[ "$loss_value" =~ ^[0-9]+$ ]] \
            && [ "$loss_value" -le "$ping_max_loss" ]
    ) &
    traffic_pids+=("$!")
done < <(lxc list -c n --format csv \
    | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
for pid in "${traffic_pids[@]}"; do
    wait "$pid" || traffic_fail=1
done

if [ -s "$results" ]; then
    echo MATRIX
    awk -F, 'NR > 1 {
        gsub(/%/, "", $11)
        n++; pass += ($12 == "PASS")
        sl += $8; sd += $9; sa += $10; loss += $11
        if (($8 + 0) > ml) ml = $8 + 0
        if (($9 + 0) > md) md = $9 + 0
        if (($10 + 0) > ma) ma = $10 + 0
        if (($11 + 0) > mx) mx = $11 + 0
    } END {
        if (!n) { print "no steering samples"; exit }
        printf "pass=%d/%d link_avg=%.0fms link_max=%dms db_avg=%.0fms db_max=%dms api_avg=%.0fms api_max=%dms loss_avg=%.1f%% loss_max=%d%%\n", pass, n, sl/n, ml, sd/n, md, sa/n, ma, loss/n, mx
    }' "$results"
fi

echo MEMORY
free -h | sed -n '1,2p'

[ "$restart_fail" = 0 ] || {
    echo "FAIL: one or more monitored services restarted" >&2
    exit 1
}
[ "$model_fail" = 0 ] || {
    echo "FAIL: topology model is not the expected $expected_devices/$expected_radios/$expected_bsses/$expected_associated with $expected_clients clients" >&2
    exit 1
}
[ "$ownership_fail" = 0 ] || {
    echo "FAIL: physical and controller serving-BSSID ownership differ" >&2
    exit 1
}
[ "$traffic_fail" = 0 ] || {
    echo "FAIL: one or more WLAN clients exceeded ${ping_max_loss}% packet loss" >&2
    exit 1
}
