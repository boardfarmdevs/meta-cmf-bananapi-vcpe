#!/usr/bin/env bash
set -euo pipefail

systemctl is-active --quiet wmediumd-console.service
curl -fsS http://127.0.0.1:8890/api/v2/health \
    | jq -e '.ready == true and .telemetry_extension == true and .identity_inventory.matched > 0' \
        >/dev/null

exec </dev/null

echo BOARDFARM
systemctl is-active boardfarm-lab.service
BF_LAB_CONFIG=ca-desk6.json \
    BF_INVENTORY=ca-desk6.json \
    timeout 180 /home/easymesh/boardfarm-open-0406/.venv/bin/bf-lab status
test "$(docker network inspect wan-cpe1 \
    -f '{{index .Options "com.docker.network.bridge.name"}}')" = br-wan101
test "$(docker ps --filter 'name=^/dhcp-cpe1$' --filter 'name=^/wan-cpe1$' --format '{{.Names}}' | sort | paste -sd, -)" = \
    dhcp-cpe1,wan-cpe1

echo TOPOLOGY
curl -fsS http://127.0.0.1:8888/api/v1/topology | jq -r '
    .nodes[] | [.name, .id, ([.haulTypes[]?.BSSList[]?] | length),
    (.STAList | length)] | @tsv'
echo LIVE_CLIENTS
curl -fsS http://127.0.0.1:8888/api/v1/topology \
    | jq -r '[.nodes[].STAList[]?.staMAC] | unique | length'

echo RESTARTS
restart_fail=0
# every mesh node, the lab's extenders on a wired backhaul (gen/wired-extender.sh) too
wired=$(for c in $(lxc list -c n --format csv | grep -E '^bpiap-[0-9]{3}$' | sort -V); do
    [ "$(lxc config get "$c" user.easymesh.backhaul)" = wired ] && echo "$c"; done || true)
for container in bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003 $wired; do
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
matrix=/home/easymesh/.local/state/easymesh-lab/steering-scale.csv
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

echo STORAGE
# What grows past its bound (easymesh-resources lab-storage W9): the VM's disk, each EMOSA
# pod's journal against its 128 MiB cap (W3; warned from 160 MiB), the room evidence (from
# 16 GiB, 80 % of the volume W4 gives it). Warnings, not failures.
df -h / | awk 'NR == 2 {print "disk " $3 " of " $2 " used (" $5 ")"}'
for pod in $(lxc list -f json | jq -r '.[] | select(.config["user.emosa.role"] == "pod" and .status == "Running") | .name'); do
    mib=$(lxc exec "$pod" -- du -sm /var/log/journal 2>/dev/null | cut -f1 || true)
    echo "pod $pod journal ${mib:-?} MiB"
    [ "${mib:-0}" -le 160 ] || echo "WARNING: pod $pod's journal is over its 128 MiB cap"
done
evidence=/home/easymesh/easymesh-evidence
if [ -d "$evidence" ]; then
    gib=$(du -s --block-size=1G "$evidence" 2>/dev/null | cut -f1 || true)
    echo "room evidence ${gib:-?} GiB"
    [ "${gib:-0}" -lt 16 ] || echo "WARNING: room evidence at $gib GiB, over 80 % of the 20 GiB it should hold"
fi

echo MEMORY
free -h | sed -n '1,2p'

[ "$restart_fail" = 0 ] || {
    echo "FAIL: one or more monitored services restarted" >&2
    exit 1
}
