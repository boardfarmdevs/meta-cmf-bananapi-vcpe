#!/usr/bin/env bash
set -euo pipefail

exec </dev/null

ap=${1:?usage: ap-recovery.sh AP_CONTAINER AP_BSSID}
target=${2:?usage: ap-recovery.sh AP_CONTAINER AP_BSSID}
mapfile -t clients < <(lxc list -c n --format csv \
    | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
repo=${EASYMESH_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}
medium_backend=${EASYMESH_MEDIUM_BACKEND:-}
if [[ -z $medium_backend && -r /etc/default/easymesh-lab ]]; then
    medium_backend=$(sed -n 's/^[[:space:]]*EASYMESH_MEDIUM_BACKEND=//p' \
        /etc/default/easymesh-lab | tail -1 | tr -d "'\"")
fi
medium_backend=${medium_backend:-userspace}
medium_identity() {
    case "$medium_backend" in
        userspace) cat /run/meta-cmf-wmediumd/wmediumd.pid ;;
        kernel)
            sudo -n env PYTHONPATH="$repo/gen/wmediumd/configurator" \
                python3 -m wmdcfg.cli status --backend kernel \
                | jq -r .instance_id
            ;;
        *) echo "unsupported medium backend: $medium_backend" >&2; return 2 ;;
    esac
}
medium_id=$(medium_identity)
topology_url=${TOPOLOGY_URL:-http://127.0.0.1:8888/api/v1/topology}
ap_stopped=0
impacted=()

topology=$(curl -fsS "$topology_url")
mapfile -t target_bssids < <(jq -r --arg target "${target,,}" '
    [.nodes[]?
      | select(any(.haulTypes[]?.BSSList[]?;
          ((.BSSID // "") | ascii_downcase) == $target))
      | .haulTypes[]?.BSSList[]?.BSSID
      | ascii_downcase]
    | unique[]' <<<"$topology")
[ "${#target_bssids[@]}" -gt 0 ] || {
    echo "target BSSID $target is absent from the live topology" >&2
    exit 1
}

bssid_belongs_to_ap() {
    local actual=${1,,} candidate
    for candidate in "${target_bssids[@]}"; do
        [ "$actual" = "$candidate" ] && return 0
    done
    return 1
}

restore_ap() {
    if [ "$ap_stopped" -eq 1 ]; then
        echo "cleanup_restarting_ap=$ap" >&2
        lxc start "$ap" >/dev/null 2>&1 || true
        for _ in $(seq 1 90); do
            private=$(lxc exec "$ap" -- iw dev 2>/dev/null \
                | grep -c 'ssid private_ssid' || true)
            iot=$(lxc exec "$ap" -- iw dev 2>/dev/null \
                | grep -c 'ssid iot_ssid' || true)
            [ "$private" -eq 3 ] && [ "$iot" -eq 3 ] && break
            sleep 1
        done
        for client in "${impacted[@]}"; do
            lxc exec "$client" -- ip link set wlan0 down >/dev/null 2>&1 || true
            lxc exec "$client" -- ip link set wlan0 up >/dev/null 2>&1 || true
            lxc exec "$client" -- wpa_cli -i wlan0 enable_network all \
                >/dev/null 2>&1 || true
            lxc exec "$client" -- wpa_cli -i wlan0 reassociate \
                >/dev/null 2>&1 || true
        done
    fi
}
trap restore_ap EXIT

echo "BASELINE ap=$ap target_bssid=$target bss_count=${#target_bssids[@]} clients=${#clients[@]} medium_backend=$medium_backend medium_identity=$medium_id"
for client in "${clients[@]}"; do
    bssid=$(lxc exec "$client" -- iw dev wlan0 link \
        | awk '/Connected to/{print $3}')
    if bssid_belongs_to_ap "$bssid"; then
        echo "target_client=$client bssid=$bssid"
        impacted+=("$client")
    fi
done
[ "${#impacted[@]}" -gt 0 ]

# A destructive recovery measurement is meaningful only from a coherent
# baseline.  Refuse to attribute a pre-existing controller ownership mismatch
# to the AP outage being tested.
for client in "${impacted[@]}"; do
    sta=$(lxc exec "$client" -- cat /sys/class/net/wlan0/address)
    link_bssid=$(lxc exec "$client" -- iw dev wlan0 link \
        | awk '/Connected to/{print $3}')
    db_bssid=$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh \
        -e "select BSSID from STAList where MACAddress='$sta' and Associated=1 limit 1" \
        2>/dev/null || true)
    [ "$db_bssid" = "$link_bssid" ] || {
        echo "baseline_model_mismatch client=$client sta=$sta link=$link_bssid db=$db_bssid" >&2
        exit 1
    }
done

start=$(date +%s%3N)
# This is an abrupt AP-loss test, so use LXD's forced stop. A graceful init
# shutdown can spend more than a minute in the RDK service chain and report a
# context deadline after the caller has already lost control of cleanup.
ap_stopped=1
lxc stop "$ap" --force >/dev/null
echo "ap_stopped_ms=$(( $(date +%s%3N) - start ))"

# mac80211_hwsim does not synthesize beacon-loss/link-loss when LXD returns a
# stopped AP's wiphy to the host. Record that fidelity boundary, then inject
# the missing station-side link-loss indication before testing reassociation.
stale=0
failed=0
for client in "${impacted[@]}"; do
    bssid=$(lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
        | awk '/Connected to/{print $3}')
    if bssid_belongs_to_ap "$bssid"; then
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
    # Repeated authentication attempts while the AP is absent may leave the
    # only configured network TEMP-DISABLED.  Re-enable it after injecting the
    # hwsim link-loss transition so the station can select another live BSS
    # immediately instead of waiting for supplicant backoff to expire.
    lxc exec "$client" -- wpa_cli -i wlan0 enable_network all >/dev/null
    lxc exec "$client" -- wpa_cli -i wlan0 reassociate >/dev/null
done
start=$(date +%s%3N)
connected=0
old=99
for _ in $(seq 1 120); do
    connected=0
    old=0
    for client in "${clients[@]}"; do
        bssid=$(lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
            | awk '/Connected to/{print $3}')
        if [ -n "$bssid" ]; then
            connected=$((connected + 1))
        fi
        if bssid_belongs_to_ap "$bssid"; then
            old=$((old + 1))
        fi
    done
    elapsed=$(( $(date +%s%3N) - start ))
    echo "link_loss_recovery_ms=$elapsed connected=$connected old_bssid=$old"
    if [ "$connected" -eq "${#clients[@]}" ] && [ "$old" -eq 0 ]; then
        break
    fi
    sleep 0.5
done
[ "$connected" -eq "${#clients[@]}" ] && [ "$old" -eq 0 ]

traffic_failures=0
for client in "${clients[@]}"; do
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

medium_id_after=$(medium_identity)
echo "medium_identity_after=$medium_id_after"
[ "$medium_id_after" = "$medium_id" ]
lxc exec bpibroadband -- systemctl show em_ctrl em_cli \
    -p Id -p MainPID -p NRestarts --no-pager
trap - EXIT
