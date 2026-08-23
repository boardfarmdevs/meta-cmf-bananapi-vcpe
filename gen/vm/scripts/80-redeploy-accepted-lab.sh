#!/usr/bin/env bash
# Recreate an installed VM lab from explicit, verified source and image inputs.
set -euo pipefail

exec </dev/null

repo=${EASYMESH_REPO:-/home/vagrant/git/meta-cmf-bananapi-vcpe}
controller_image=${CONTROLLER_IMAGE:?set CONTROLLER_IMAGE to the controller LXC image}
extender_image=${EXTENDER_IMAGE:?set EXTENDER_IMAGE to the extender LXC image}
expected_repo_head=${EXPECTED_REPO_HEAD:?set EXPECTED_REPO_HEAD to the accepted commit}
controller_sha256=${CONTROLLER_SHA256:?set CONTROLLER_SHA256}
extender_sha256=${EXTENDER_SHA256:?set EXTENDER_SHA256}
expected_wmediumd_sha256=${EXPECTED_WMEDIUMD_SHA256:?set EXPECTED_WMEDIUMD_SHA256}
evidence_root=${EASYMESH_EVIDENCE_ROOT:-/home/vagrant/easymesh-evidence}
hwsim_pool_radios=${EASYMESH_HWSIM_POOL_RADIOS:-32}
run_id=$(date -u +%Y%m%dT%H%M%SZ)
evidence="$evidence_root/$run_id"

case "$hwsim_pool_radios" in
    ''|*[!0-9]*) echo 'EASYMESH_HWSIM_POOL_RADIOS must be an integer' >&2; exit 2 ;;
esac
if [ "$hwsim_pool_radios" -lt 25 ]; then
    echo 'the accepted five-node/20-client profile requires at least 25 hwsim radios' >&2
    exit 2
fi
# bpi.sh intentionally gives HWSIM_RADIOS a different meaning: the number of
# PHYs assigned to one mesh container.  Never leak a caller's pool-size value
# into child deployment commands; each tri-band BPI node uses one hwsim PHY.
unset HWSIM_RADIOS

mkdir -p "$evidence"
exec > >(tee "$evidence/deploy.log") 2>&1

test "$(git -C "$repo" rev-parse HEAD)" = "$expected_repo_head"
test -z "$(git -C "$repo" status --porcelain)"
test "$(sha256sum "$controller_image" | awk '{print $1}')" = \
    "$controller_sha256"
test "$(sha256sum "$extender_image" | awk '{print $1}')" = \
    "$extender_sha256"
test "$(sha256sum "$repo/gen/wmediumd/wmediumd.patched" | awk '{print $1}')" = \
    "$expected_wmediumd_sha256"

sudo systemctl stop easymesh-lab.service 2>/dev/null || true
sudo systemctl reset-failed easymesh-lab.service 2>/dev/null || true
sudo systemctl start docker.service snap.lxd.daemon.service \
    boardfarm-lab.service easymesh-lxd-docker-forward.service
for attempt in $(seq 1 60); do
    ip link show br-wan105 >/dev/null 2>&1 && break
    sleep 2
done
ip link show br-wan105 >/dev/null

cd "$repo/gen"
./wmediumd/wmediumd-up.sh down >/dev/null 2>&1 || true

# Stop every disposable lab instance before detaching legacy NVRAM devices.
# The old bind directories are retained for explicit audit/purge; bpi.sh then
# creates new identities below this checkout instead of silently reusing them.
while read -r container; do
    [ -n "$container" ] || continue
    if [ "$(lxc info "$container" 2>/dev/null | sed -n 's/^Status: //p')" = RUNNING ]; then
        lxc stop "$container" --timeout 20 >/dev/null 2>&1 \
            || lxc stop "$container" --force >/dev/null 2>&1 \
            || true
    fi
done < <(lxc list -c n --format csv \
    | grep -E '^(bpibroadband|bpiap(-[0-9]{3})?|wlan-client(-[0-9]{3})?)$' \
    | sort -Vr)

# Pool size is immutable while mac80211_hwsim is loaded.  The managed service
# and every hwsim container are stopped above, making this the one safe point
# to upgrade an older thin VM from its historical 24-radio pool.  Persist the
# requested size and install the current naming helper before the reload so a
# later VM reboot reconstructs the same pool.
printf 'options mac80211_hwsim radios=%s channels=3 regtest=5\n' "$hwsim_pool_radios" \
    | sudo tee /etc/modprobe.d/easymesh-hwsim.conf >/dev/null
sudo install -m 0755 "$repo/gen/vm/scripts/guest/easymesh-hwsim-pool" \
    /usr/local/sbin/easymesh-hwsim-pool
sudo install -m 0644 "$repo/gen/vm/scripts/guest/easymesh-hwsim-pool.service" \
    /etc/systemd/system/easymesh-hwsim-pool.service
if [ "$(cat /sys/module/mac80211_hwsim/parameters/radios)" != "$hwsim_pool_radios" ] \
    || [ "$(cat /sys/module/mac80211_hwsim/parameters/channels)" != 3 ] \
    || [ "$(cat /sys/module/mac80211_hwsim/parameters/regtest)" != 5 ]; then
    sudo modprobe -r mac80211_hwsim
    sudo modprobe mac80211_hwsim radios="$hwsim_pool_radios" channels=3 regtest=5
fi
sudo systemctl daemon-reload
sudo systemctl enable easymesh-hwsim-pool.service
sudo systemctl restart easymesh-hwsim-pool.service

for profile in bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003; do
    if old_nvram=$(lxc profile device get "$profile" nvram source 2>/dev/null); then
        if [ -n "$old_nvram" ]; then
            printf 'retaining legacy NVRAM for later inventory: %s\n' "$old_nvram"
            lxc profile device remove "$profile" nvram >/dev/null
        fi
    fi
done

rm -f /home/vagrant/.local/state/easymesh-vagrant/deploy.status
EASYMESH_REPO="$repo" \
CONTROLLER_IMAGE="$controller_image" \
EXTENDER_IMAGE="$extender_image" \
EXPECTED_REPO_HEAD="$expected_repo_head" \
EXPECTED_WMEDIUMD_SHA256="$expected_wmediumd_sha256" \
    bash "$repo/gen/vm/scripts/40-deploy-easymesh.sh"

EASYMESH_REPO="$repo" EXTENDER_IMAGE="$extender_image" \
    bash "$repo/gen/vm/scripts/55-scale-topology.sh"

sudo install -m 0755 "$repo/gen/vm/scripts/guest/easymesh-lab-runtime" \
    /usr/local/sbin/easymesh-lab-runtime
sudo install -m 0755 "$repo/gen/vm/scripts/guest/easymesh-labctl" \
    /usr/local/sbin/easymesh-labctl
sudo install -m 0755 "$repo/gen/tests/health-audit.sh" \
    /usr/local/sbin/easymesh-health-audit
sudo install -m 0644 "$repo/gen/vm/scripts/guest/easymesh-lab.service" \
    /etc/systemd/system/easymesh-lab.service
sudo systemctl daemon-reload
sudo systemctl enable easymesh-lab.service
sudo systemctl start easymesh-lab.service

sudo easymesh-labctl check

counts=$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e '
    select concat(
        (select count(*) from DeviceList), "/",
        (select count(*) from RadioList), "/",
        (select count(*) from BSSList), "/",
        (select count(*) from STAList where Associated=1));' 2>/dev/null)
test "$counts" = 5/15/50/24

topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology)
test "$(jq '[.nodes[]?.STAList[]? | select(.ssid == "private_ssid") | .staMAC] | unique | length' <<< "$topology")" = 10
test "$(jq '[.nodes[]?.STAList[]? | select(.ssid == "iot_ssid") | .staMAC] | unique | length' <<< "$topology")" = 10
test "$(jq '[.edges[]? | select(.mediaType == "Wireless LAN" and .rssi != null and .rcpi != null)] | length' <<< "$topology")" = 4

lxc list -c ns4,user.build > "$evidence/lxc-list.txt"
printf '%s\n' "$topology" > "$evidence/topology.json"
curl -fsS http://127.0.0.1:8888/api/v1/clients > "$evidence/clients.json"
printf '%s\n' "$counts" > "$evidence/model-counts.txt"
git -C "$repo" rev-parse HEAD > "$evidence/source-commit.txt"
sha256sum "$controller_image" "$extender_image" > "$evidence/image-sha256.txt"
date -Ins > "$evidence/completed-at.txt"

echo "VM fresh deployment PASS evidence=$evidence"
