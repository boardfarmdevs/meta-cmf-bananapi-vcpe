#!/usr/bin/env bash
set -euo pipefail

exec </dev/null

echo BOARDFARM
systemctl is-active boardfarm-lab.service
BF_LAB_CONFIG=boardfarm-easymesh.json \
    BF_INVENTORY=boardfarm-easymesh.json \
    timeout 180 /home/vagrant/boardfarm-open-0406/.venv/bin/bf-lab status
test "$(docker network inspect wan-cpe5 \
    -f '{{index .Options "com.docker.network.bridge.name"}}')" = br-wan105

echo TOPOLOGY
curl -fsS http://127.0.0.1:8888/api/v1/topology | jq -r '
    .nodes[] | [.name, .id, ([.haulTypes[]?.BSSList[]?] | length),
    (.STAList | length)] | @tsv'
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
while read -r client; do
    (
        loss=$(lxc exec "$client" -- ping -q -c 40 -i 0.05 -W 1 10.0.0.1 \
            | sed -n 's/.* \([0-9]*%\) packet loss.*/\1/p')
        echo "$client ${loss:-FAIL}"
    ) &
done < <(lxc list -c n --format csv \
    | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
wait

echo MATRIX
matrix=/home/vagrant/.local/state/easymesh-vagrant/steering-scale.csv
if [ -f "$matrix" ]; then
awk -F, 'NR > 1 {
    gsub(/%/, "", $11)
    n++; pass += ($12 == "PASS")
    sl += $8; sd += $9; sa += $10; loss += $11
    if (($8 + 0) > ml) ml = $8 + 0
    if (($9 + 0) > md) md = $9 + 0
    if (($10 + 0) > ma) ma = $10 + 0
    if (($11 + 0) > mx) mx = $11 + 0
} END {
    printf "pass=%d/%d link_avg=%.0fms link_max=%dms db_avg=%.0fms db_max=%dms api_avg=%.0fms api_max=%dms loss_avg=%.1f%% loss_max=%d%%\n", pass, n, sl/n, ml, sd/n, md, sa/n, ma, loss/n, mx
}' "$matrix"
else
    echo 'not-run (bring-up acceptance does not require a steering matrix)'
fi

echo MEMORY
free -h | sed -n '1,2p'

[ "$restart_fail" = 0 ] || {
    echo "FAIL: one or more monitored services restarted" >&2
    exit 1
}
