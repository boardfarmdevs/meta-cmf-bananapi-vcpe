#!/usr/bin/env bash
set -euo pipefail

exec </dev/null
repo=${EASYMESH_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}
results=${RESULTS_FILE:-$repo/tmp/test-results/steering-scale.csv}
ping_count=${HEALTH_PING_COUNT:-10}
ping_interval=${HEALTH_PING_INTERVAL:-1}
ping_max_loss=${HEALTH_PING_MAX_LOSS:-0}

[[ "$ping_count" =~ ^[1-9][0-9]*$ ]] \
    || { echo "HEALTH_PING_COUNT must be a positive integer" >&2; exit 2; }
[[ "$ping_interval" =~ ^[0-9]+([.][0-9]+)?$ ]] \
    || { echo "HEALTH_PING_INTERVAL must be a non-negative number" >&2; exit 2; }
[[ "$ping_max_loss" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
    || { echo "HEALTH_PING_MAX_LOSS must be an integer from 0 through 100" >&2; exit 2; }

echo TOPOLOGY
curl -fsS http://127.0.0.1:8888/api/v1/topology | jq -r '
    .nodes[] | [.name, .id, ([.haulTypes[]?.BSSList[]?] | length),
    (.STAList | length)] | @tsv'
echo MODEL
lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
    'select (select count(*) from DeviceList),
    (select count(*) from RadioList),
    (select count(*) from BSSList),
    (select count(*) from STAList where Associated=1)' 2>/dev/null
echo LIVE_CLIENTS
curl -fsS http://127.0.0.1:8888/api/v1/topology \
    | jq -r '[.nodes[].STAList[]?.staMAC] | unique | length'

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
        loss=$(lxc exec "$client" -- ping -q -c "$ping_count" \
            -i "$ping_interval" -W 2 10.0.0.1 \
            | sed -n 's/.* \([0-9]*%\) packet loss.*/\1/p')
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
[ "$traffic_fail" = 0 ] || {
    echo "FAIL: one or more WLAN clients exceeded ${ping_max_loss}% packet loss" >&2
    exit 1
}
