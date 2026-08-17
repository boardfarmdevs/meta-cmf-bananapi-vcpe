#!/usr/bin/env bash
set -euo pipefail

exec </dev/null

ap=${1:?usage: ap-recovery.sh AP_CONTAINER PRIVATE_BSSID}
target=${2:?usage: ap-recovery.sh AP_CONTAINER PRIVATE_BSSID}
clients='wlan-client wlan-client-001 wlan-client-002 wlan-client-003 wlan-client-004 wlan-client-005 wlan-client-006 wlan-client-007 wlan-client-008 wlan-client-009'
wpid=$(cat /run/meta-cmf-wmediumd/wmediumd.pid)
topology_url=${TOPOLOGY_URL:-http://10.105.0.101:8888/api/v1/topology}
ap_stopped=0

restore_ap() {
    if [ "$ap_stopped" -eq 1 ]; then
        echo "cleanup_restarting_ap=$ap" >&2
        lxc start "$ap" >/dev/null 2>&1 || true
    fi
}
trap restore_ap EXIT

echo "BASELINE ap=$ap target_bssid=$target wmediumd_pid=$wpid"
impacted=()
for client in $clients; do
    bssid=$(lxc exec "$client" -- iw dev wlan0 link \
        | awk '/Connected to/{print $3}')
    if [ "$bssid" = "$target" ]; then
        echo "target_client=$client"
        impacted+=("$client")
    fi
done
[ "${#impacted[@]}" -gt 0 ]

start=$(date +%s%3N)
lxc stop "$ap" --timeout 30 >/dev/null
ap_stopped=1
echo "ap_stopped_ms=$(( $(date +%s%3N) - start ))"

# mac80211_hwsim does not synthesize beacon-loss/link-loss when LXD returns a
# stopped AP's wiphy to the host. Record that fidelity boundary, then inject
# the missing station-side link-loss indication before testing reassociation.
stale=0
failed=0
for client in "${impacted[@]}"; do
    bssid=$(lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
        | awk '/Connected to/{print $3}')
    if [ "$bssid" = "$target" ]; then
        stale=$((stale + 1))
    fi
    if ! lxc exec "$client" -- ping -q -c 2 -W 1 10.0.0.1 >/dev/null; then
        failed=$((failed + 1))
    fi
done
echo "raw_ap_drop stale_links=$stale traffic_failures=$failed impacted=${#impacted[@]}"

for client in "${impacted[@]}"; do
    lxc exec "$client" -- ip link set wlan0 down
    lxc exec "$client" -- ip link set wlan0 up
done
start=$(date +%s%3N)
connected=0
old=99
for _ in $(seq 1 80); do
    connected=0
    old=0
    for client in $clients; do
        bssid=$(lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
            | awk '/Connected to/{print $3}')
        if [ -n "$bssid" ]; then
            connected=$((connected + 1))
        fi
        if [ "$bssid" = "$target" ]; then
            old=$((old + 1))
        fi
    done
    elapsed=$(( $(date +%s%3N) - start ))
    echo "link_loss_recovery_ms=$elapsed connected=$connected old_bssid=$old"
    if [ "$connected" -eq 10 ] && [ "$old" -eq 0 ]; then
        break
    fi
    sleep 0.5
done
[ "$connected" -eq 10 ] && [ "$old" -eq 0 ]

traffic_failures=0
for client in $clients; do
    if ! lxc exec "$client" -- ping -q -c 3 -W 1 10.0.0.1 >/dev/null; then
        traffic_failures=$((traffic_failures + 1))
    fi
done
echo "post_drop_traffic_failures=$traffic_failures"
[ "$traffic_failures" -eq 0 ]
model_start=$(date +%s%3N)
model_mismatches=99
for _ in $(seq 1 120); do
    model_mismatches=0
    mismatch_rows=()
    for client in "${impacted[@]}"; do
        sta=$(lxc exec "$client" -- iw dev wlan0 info | awk '/addr/{print $2}')
        link_bssid=$(lxc exec "$client" -- iw dev wlan0 link \
            | awk '/Connected to/{print $3}')
        db_bssid=$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh \
            -e "select BSSID from STAList where MACAddress='$sta' and Associated=1 limit 1" \
            2>/dev/null || true)
        if [ "$db_bssid" != "$link_bssid" ]; then
            mismatch_rows+=("model_mismatch client=$client sta=$sta link=$link_bssid db=$db_bssid")
            model_mismatches=$((model_mismatches + 1))
        fi
    done
    if [ "$model_mismatches" -eq 0 ]; then
        break
    fi
    sleep 0.5
done
printf '%s\n' "${mismatch_rows[@]:-}"
echo "post_drop_model_ms=$(( $(date +%s%3N) - model_start )) mismatches=$model_mismatches"
[ "$model_mismatches" -eq 0 ]
echo "offline_topology_nodes=$(curl -fsS "$topology_url" | jq '.nodes | length')"

start=$(date +%s%3N)
lxc start "$ap"
ap_stopped=0
services_ms=-1
backhaul_ms=-1
ready_ms=-1
for _ in $(seq 1 180); do
    now=$(( $(date +%s%3N) - start ))
    if [ "$services_ms" -lt 0 ] \
        && lxc exec "$ap" -- systemctl is-active --quiet onewifi em_agent; then
        services_ms=$now
        echo "rejoin_services_ms=$services_ms"
    fi
    if [ "$backhaul_ms" -lt 0 ] \
        && lxc exec "$ap" -- sh -c \
            "iw dev wifi1.3 link | grep -q 'Connected to'" 2>/dev/null; then
        backhaul_ms=$now
        echo "rejoin_backhaul_ms=$backhaul_ms"
    fi
    private=$(lxc exec "$ap" -- iw dev 2>/dev/null \
        | grep -c 'ssid private_ssid' || true)
    iot=$(lxc exec "$ap" -- iw dev 2>/dev/null \
        | grep -c 'ssid iot_ssid' || true)
    if [ "$private" -eq 3 ] && [ "$iot" -eq 3 ] \
        && [ "$backhaul_ms" -ge 0 ]; then
        ready_ms=$now
        echo "rejoin_ready_ms=$ready_ms private=$private iot=$iot"
        break
    fi
    sleep 1
done
[ "$ready_ms" -ge 0 ]

controller_ms=-1
for _ in $(seq 1 180); do
    if curl -fsS "$topology_url" \
        | jq -e --arg bssid "$target" \
            'any(.nodes[].haulTypes[]?.BSSList[]?; .BSSID == $bssid)' >/dev/null; then
        controller_ms=$(( $(date +%s%3N) - start ))
        echo "rejoin_controller_visible_ms=$controller_ms"
        break
    fi
    sleep 0.5
done
[ "$controller_ms" -ge 0 ]

echo "wmediumd_pid_after=$(cat /run/meta-cmf-wmediumd/wmediumd.pid)"
[ "$(cat /run/meta-cmf-wmediumd/wmediumd.pid)" = "$wpid" ]
lxc exec bpibroadband -- systemctl show em_ctrl em_cli \
    -p Id -p MainPID -p NRestarts --no-pager
trap - EXIT
