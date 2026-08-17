#!/usr/bin/env bash
set -euo pipefail

exec </dev/null

repo=${EASYMESH_REPO:-/home/vagrant/git/meta-cmf-bananapi-vcpe}
gen="$repo/gen"
assets=${EASYMESH_ASSETS:-/home/vagrant/easymesh-assets}
extender_image=${EXTENDER_IMAGE:-"$assets/X86EMLTRBPIAP_rdk-next_20260817140053.rootfs.lxc.tar.bz2"}

model_counts() {
    lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
        'select concat((select count(*) from DeviceList),"/",(select count(*) from RadioList),"/",(select count(*) from BSSList))' \
        2>/dev/null
}

wait_for_extender() {
    local container=$1 expected=$2 attempt counts
    for attempt in $(seq 1 30); do
        counts=$(model_counts || true)
        echo "$container scale gate $attempt/30: model=${counts:-unavailable}"
        if [ "$counts" = "$expected" ] \
            && [ "$(lxc exec "$container" -- systemctl is-active onewifi 2>/dev/null)" = active ] \
            && [ "$(lxc exec "$container" -- systemctl is-active em_agent 2>/dev/null)" = active ] \
            && lxc exec "$container" -- sh -c \
                "iw dev wifi1.3 link 2>/dev/null | grep -q 'Connected to'"; then
            return 0
        fi
        sleep 10
    done
    return 1
}

cd "$gen"
for index in 2 3; do
    container=$(printf 'bpiap-%03d' "$index")
    devices=$((index + 2))
    expected="$devices/$((devices * 3))/$((devices * 10))"
    counts=$(model_counts || true)
    current_devices=${counts%%/*}
    if ! lxc info "$container" >/dev/null 2>&1 \
        || ! [[ "$current_devices" =~ ^[0-9]+$ ]] \
        || [ "$current_devices" -lt "$devices" ]; then
        ./bpi.sh -F -i "$index" "$extender_image"
        # A running wmediumd has a fixed registration matrix. Include the new
        # extender radios immediately, before waiting for EasyMesh onboarding.
        SNR=40 ./wmediumd/wmediumd-up.sh up
        wait_for_extender "$container" "$expected"
    else
        echo "$container already present in model $counts; validating live backhaul"
        [ "$(lxc exec "$container" -- systemctl is-active onewifi 2>/dev/null)" = active ]
        [ "$(lxc exec "$container" -- systemctl is-active em_agent 2>/dev/null)" = active ]
        lxc exec "$container" -- sh -c \
            "iw dev wifi1.3 link 2>/dev/null | grep -q 'Connected to'"
    fi
done

for index in 5 6 7 8 9; do
    ./wlan-client.sh -i "$index" up private_ssid test-fronthaul
    lxc config set "$(printf 'wlan-client-%03d' "$index")" boot.autostart false
done

for attempt in $(seq 1 30); do
    topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology 2>/dev/null || true)
    live=$(jq -r '[.nodes[].STAList[]?.staMAC] | unique | length' \
        <<<"$topology" 2>/dev/null || true)
    stations=$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
        'select count(*) from STAList where Associated=1' 2>/dev/null || true)
    echo "scaled client gate $attempt/30: live_topology=${live:-?} associated_STA=${stations:-?}"
    if [ "$live" = 10 ] && [ "$stations" = 14 ]; then
        exit 0
    fi
    sleep 10
done

echo 'scaled topology did not converge to 4 extenders and 10 clients' >&2
exit 1
