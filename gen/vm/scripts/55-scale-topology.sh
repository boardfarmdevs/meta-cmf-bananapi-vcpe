#!/usr/bin/env bash
set -euo pipefail

exec </dev/null

repo=${EASYMESH_REPO:-/home/easymesh/git/meta-cmf-bananapi-vcpe}
gen="$repo/gen"
assets=${EASYMESH_ASSETS:-/home/easymesh/easymesh-assets}
nvram_root=${EASYMESH_NVRAM_ROOT:-/var/lib/easymesh-lab/nvram}
extender_image=${EXTENDER_IMAGE:-"$assets/X86EMLTRBPIAP_rdk-next_20260830064504.rootfs.lxc.tar.bz2"}
profile=${EASYMESH_SCALE_PROFILE:-small}
case "$profile" in
    20|small) profile=small; expected_clients=20; expected_private=10; expected_iot=10 ;;
    50|medium) profile=medium; expected_clients=50; expected_private=25; expected_iot=25 ;;
    100|stress) profile=stress; expected_clients=100; expected_private=50; expected_iot=50 ;;
    *) echo "invalid EASYMESH_SCALE_PROFILE: $profile" >&2; exit 2 ;;
esac

mkdir -p "$nvram_root"
export BPI_NVRAM_ROOT="$nvram_root"

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
# Scaling is intentionally incremental.  Permit the medium refresh after the
# first new extender while later managed nodes are still stopped.  This export
# is confined to this child script; the final runtime gate remains strict.
export WMEDIUMD_ALLOW_INCOMPLETE_RADIOS=1
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

# Complete the private cohort and add the hidden-SSID IoT cohort as one
# resumable operation. The pool helper retains the five healthy private clients
# from the base deployment and registers wmediumd once after all new radios
# exist, rather than restarting it for every station.
./wlan-client-pool.sh up --profile "$profile"

for attempt in $(seq 1 30); do
    topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology 2>/dev/null || true)
    live=$(jq -r '[.nodes[].STAList[]?.staMAC] | unique | length' \
        <<<"$topology" 2>/dev/null || true)
    private_live=$(jq -r \
        '[.nodes[].STAList[]? | select(.ssid == "private_ssid") | .staMAC] | unique | length' \
        <<<"$topology" 2>/dev/null || true)
    iot_live=$(jq -r \
        '[.nodes[].STAList[]? | select(.ssid == "iot_ssid") | .staMAC] | unique | length' \
        <<<"$topology" 2>/dev/null || true)
    stations=$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
        'select count(*) from STAList where Associated=1' 2>/dev/null || true)
    echo "scaled client gate $attempt/30: live=${live:-?} private=${private_live:-?} iot=${iot_live:-?} associated=${stations:-?}"
    # The topology counts are SSID-qualified and therefore exact.  STAList also
    # contains the four associated extender backhaul STAs in this profile, so
    # use it only to prove that at least all 20 fronthaul clients are present.
    if [ "$live" = "$expected_clients" ] \
        && [ "$private_live" = "$expected_private" ] \
        && [ "$iot_live" = "$expected_iot" ] \
        && [[ "$stations" =~ ^[0-9]+$ ]] \
        && [ "$stations" -ge "$expected_clients" ]; then
        exit 0
    fi
    sleep 10
done

echo "scaled topology did not converge to 4 extenders, $expected_private private and $expected_iot IoT clients" >&2
exit 1
