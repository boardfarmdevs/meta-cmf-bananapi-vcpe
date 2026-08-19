#!/usr/bin/env bash
set -euo pipefail

# Vagrant's remote shell leaves control text on stdin. Some LXC subcommands
# opportunistically consume non-terminal stdin as YAML, so isolate the complete
# deployment (individual commands that intentionally pipe YAML still work).
exec </dev/null

repo=${EASYMESH_REPO:-/home/vagrant/git/meta-cmf-bananapi-vcpe}
gen="$repo/gen"
assets=${EASYMESH_ASSETS:-/home/vagrant/easymesh-assets}
state=${EASYMESH_STATE:-/home/vagrant/.local/state/easymesh-vagrant}
boardfarm_status=${BOARDFARM_STATUS:-/var/lib/easymesh-vagrant/boardfarm.status}
controller_image=${CONTROLLER_IMAGE:-"$assets/X86EMLTRBPIBB_rdk-next_20260817135730.rootfs.lxc.tar.bz2"}
extender_image=${EXTENDER_IMAGE:-"$assets/X86EMLTRBPIAP_rdk-next_20260817140053.rootfs.lxc.tar.bz2"}
expected_repo_head=${EXPECTED_REPO_HEAD:-c2e8ce74385d64c788ac750c18342e373d35e878}

mkdir -p "$state"
test -f "$boardfarm_status"
test "$(git -C "$repo" rev-parse HEAD)" = "$expected_repo_head"
test "$(sha256sum "$gen/wmediumd/wmediumd.patched" | awk '{print $1}')" = \
    b7fdaf23c5c490dcfc42f1459cb31b78ab2c801f58c86bbbb7a12eca2a7f2ca9

model_counts() {
    lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
        'select concat((select count(*) from DeviceList),"/",(select count(*) from RadioList),"/",(select count(*) from BSSList))' \
        2>/dev/null
}

services_active() {
    local container=$1
    shift
    local service
    for service in "$@"; do
        test "$(lxc exec "$container" -- systemctl is-active "$service" 2>/dev/null)" = active \
            || return 1
    done
}

wait_for_controller() {
    local attempt counts
    for attempt in $(seq 1 30); do
        counts=$(model_counts || true)
        echo "controller gate $attempt/30: model=${counts:-unavailable}"
        if [ "$counts" = 1/3/10 ] \
            && services_active bpibroadband \
                onewifi ieee1905_em_ctrl em_ctrl \
                ieee1905_em_agent em_agent em_cli \
            && lxc exec bpibroadband -- sh -c \
                "ip -4 -o address show erouter0 | grep -q 'inet '"; then
            return 0
        fi
        sleep 10
    done
    return 1
}

wait_for_extender() {
    local container=$1 expected=$2 attempt counts
    for attempt in $(seq 1 30); do
        counts=$(model_counts || true)
        echo "$container gate $attempt/30: model=${counts:-unavailable}"
        if [ "$counts" = "$expected" ] \
            && services_active "$container" onewifi ieee1905_em_agent em_agent \
            && lxc exec "$container" -- sh -c \
                "iw dev wifi1.3 link 2>/dev/null | grep -q 'Connected to'"; then
            return 0
        fi
        sleep 10
    done
    return 1
}

lab_is_complete() {
    [ -f "$state/deploy.status" ] || return 1
    [ "$(model_counts || true)" = 3/9/30 ] || return 1
    services_active bpibroadband \
        onewifi ieee1905_em_ctrl em_ctrl ieee1905_em_agent em_agent em_cli \
        || return 1
    services_active bpiap onewifi ieee1905_em_agent em_agent || return 1
    services_active bpiap-001 onewifi ieee1905_em_agent em_agent || return 1
    local client
    for client in wlan-client wlan-client-001 wlan-client-002 wlan-client-003 wlan-client-004; do
        lxc exec "$client" -- sh -c \
            "iw dev wlan0 link 2>/dev/null | grep -q 'Connected to'" || return 1
        lxc exec "$client" -- sh -c \
            "ip -4 -o address show wlan0 2>/dev/null | grep -q 'inet '" || return 1
    done
    [[ "$("$gen/wmediumd/wmediumd-up.sh" status)" == *'wmediumd running'* ]]
}

if lab_is_complete; then
    echo 'EasyMesh lab already passes its deployment gate'
    exit 0
fi

rm -f "$state/deploy.status"
cd "$gen"
./wmediumd/wmediumd-up.sh down >/dev/null 2>&1 || true
while read -r client; do
    suffix=${client#wlan-client}
    if [ -n "$suffix" ]; then
        ./wlan-client.sh -i "${suffix#-}" down >/dev/null 2>&1 || true
    else
        ./wlan-client.sh down >/dev/null 2>&1 || true
    fi
done < <(lxc list -c n --format csv \
    | grep -E '^wlan-client(-[0-9]{3})?$' | sort -Vr)

# Quiesce old nodes before generating a fresh, coherent identity set. This
# prevents a partial prior deployment from participating in the new bootstrap.
while read -r container; do
    if lxc info "$container" >/dev/null 2>&1; then
        lxc stop "$container" --timeout 20 >/dev/null 2>&1 \
            || lxc stop "$container" --force >/dev/null 2>&1 \
            || true
    fi
done < <(lxc list -c n --format csv \
    | grep -E '^(bpibroadband|bpiap(-[0-9]{3})?)$' | sort -Vr)

./bpi.sh -F -b br-wan105 "$controller_image"

# The stock em_cli unit is enabled, but on a container reboot it can be absent
# from the boot transaction even though em_agent starts successfully. Make the
# dependency explicit in the direction that matters: starting em_agent pulls
# in em_cli, whose own unit already orders itself after em_agent. This persists
# in the controller rootfs and removes the reboot-only manual start.
lxc exec bpibroadband -- mkdir -p /etc/systemd/system/em_agent.service.d
printf '%s\n' '[Unit]' 'Wants=em_cli.service' \
    | lxc exec bpibroadband -- tee \
        /etc/systemd/system/em_agent.service.d/em-cli.conf >/dev/null
lxc exec bpibroadband -- systemctl daemon-reload
lxc exec bpibroadband -- systemctl enable em_cli.service
lxc exec bpibroadband -- systemctl start em_cli.service
wait_for_controller

./bpi.sh -F "$extender_image"
wait_for_extender bpiap 2/6/20

./bpi.sh -F -i 1 "$extender_image"
wait_for_extender bpiap-001 3/9/30

SNR=40 ./wmediumd/wmediumd-up.sh up
if ! lxc image info wlan-client-base >/dev/null 2>&1; then
    ./wlan-client.sh build-image
fi
./wlan-client.sh up private_ssid test-fronthaul
for index in 1 2 3 4; do
    ./wlan-client.sh -i "$index" up private_ssid test-fronthaul
done

# The host runtime service, not LXD's previous-power-state restoration, owns
# boot order. Clients must remain stopped until every mesh agent has completed
# tri-band onboarding; early associations can overload and restart em_agent.
for client in wlan-client wlan-client-001 wlan-client-002 wlan-client-003 wlan-client-004; do
    lxc config set "$client" boot.autostart false
done

for attempt in $(seq 1 30); do
    topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology 2>/dev/null || true)
    live=$(printf '%s' "$topology" \
        | jq -r '[.nodes[].STAList[]?.staMAC] | unique | length' 2>/dev/null || true)
    echo "live topology gate $attempt/30: clients=${live:-unavailable}"
    if [ "$live" = 5 ]; then
        printf '%s\n' 'easymesh-deploy-ready' > "$state/deploy.status"
        lab_is_complete
        exit 0
    fi
    sleep 10
done

echo 'EasyMesh live topology did not converge to 5 clients' >&2
exit 1
