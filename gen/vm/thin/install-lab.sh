#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo --preserve-env=SSH_AUTH_SOCK $0" >&2
    exit 1
fi
if [ -f /etc/easymesh-online.env ]; then
    # The file is root-owned configuration, not untrusted command-line input.
    # shellcheck disable=SC1091
    source /etc/easymesh-online.env
fi

thin_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
vm_dir=$(cd "$thin_dir/.." && pwd)
source_root=$(cd "$vm_dir/../.." && pwd)
assets=/home/vagrant/easymesh-assets
runtime_repo=/home/vagrant/git/meta-cmf-bananapi-vcpe
bf_workspace=/home/vagrant/boardfarm-open-0406
lab_user=vagrant

controller=X86EMLTRBPIBB_rdk-next_20260817135730.rootfs.lxc.tar.bz2
ap=X86EMLTRBPIAP_rdk-next_20260817140053.rootfs.lxc.tar.bz2
alpine_meta=alpine-3.19-amd64-meta.tar.xz
alpine_rootfs=alpine-3.19-amd64-rootfs.tar.xz
: "${EASYMESH_CONTROLLER_IMAGE_URL:?set it in /etc/easymesh-online.env}"
: "${EASYMESH_AP_IMAGE_URL:?set it in /etc/easymesh-online.env}"
: "${EASYMESH_ALPINE_META_URL:?set it in /etc/easymesh-online.env}"
: "${EASYMESH_ALPINE_ROOTFS_URL:?set it in /etc/easymesh-online.env}"
: "${EASYMESH_CONTROLLER_IMAGE_SHA256:=b0a299b58b921733a573de501f8405e8da1579dde9eadf8c7a62c00cf86fb4e7}"
: "${EASYMESH_AP_IMAGE_SHA256:=a4491eec0116d2bc0b2f6f0b438c43e77ec0ca95214d36ac7f80d039e818e6cd}"
: "${EASYMESH_ALPINE_META_SHA256:=c04158f82707f34cfca17bf01367b8330b0d53aaf6a801c4852c3a2bf3bcabac}"
: "${EASYMESH_ALPINE_ROOTFS_SHA256:=16d0b946436bd42ba43ace0b9b075a2f15b9fbc31393ecccfe45694db8653ac4}"

test "$(uname -r)" = 7.0.0-28-generic
test -d "$source_root/.git"
install -d -o "$lab_user" -g "$lab_user" "$assets" /home/vagrant/git "$bf_workspace"

download() {
    local url=$1 destination=$2 checksum=$3
    if [ ! -f "$destination" ] \
        || ! echo "$checksum  $destination" | sha256sum -c - >/dev/null 2>&1; then
        curl --fail --location --retry 3 --output "$destination.part" "$url"
        mv "$destination.part" "$destination"
    fi
    echo "$checksum  $destination" | sha256sum -c -
}

download "$EASYMESH_CONTROLLER_IMAGE_URL" "$assets/$controller" \
    "$EASYMESH_CONTROLLER_IMAGE_SHA256"
download "$EASYMESH_AP_IMAGE_URL" "$assets/$ap" \
    "$EASYMESH_AP_IMAGE_SHA256"
download "$EASYMESH_ALPINE_META_URL" "$assets/$alpine_meta" \
    "$EASYMESH_ALPINE_META_SHA256"
download "$EASYMESH_ALPINE_ROOTFS_URL" "$assets/$alpine_rootfs" \
    "$EASYMESH_ALPINE_ROOTFS_SHA256"

if [ ! -f "$assets/astral-uv_1662.snap" ]; then
    (cd "$assets" && \
        snap download astral-uv --revision=1662 --basename=astral-uv_1662)
fi
if [ ! -f "$assets/lxd_38768.snap" ]; then
    (cd "$assets" && snap download lxd --revision=38768 --basename=lxd_38768)
fi

install -m 0644 "$vm_dir/config/boardfarm-requirements.lock" "$assets/"
install -m 0644 "$vm_dir/config/boardfarm-easymesh.json" "$assets/"
install -m 0644 "$vm_dir/config/boardfarm-easymesh-inventory.json" "$assets/"
for file in \
    boardfarm-lab-rebuild boardfarm-lab.service \
    easymesh-hwsim-pool easymesh-hwsim-pool.service \
    easymesh-lab-runtime easymesh-lab.service \
    easymesh-labctl \
    easymesh-lxd-docker-forward easymesh-lxd-docker-forward.service \
    lxd-easymesh-ordering.conf; do
    install -m 0644 "$vm_dir/scripts/guest/$file" "$assets/$file"
done
install -m 0644 "$vm_dir/scripts/70-health-audit.sh" \
    "$assets/easymesh-health-audit"
install -o "$lab_user" -g "$lab_user" -m 0755 \
    "$vm_dir/scripts/60-scale-steering-test.sh" \
    /home/vagrant/scale-steering-test.sh
install -o "$lab_user" -g "$lab_user" -m 0755 \
    "$vm_dir/scripts/61-return-steering-regression.sh" \
    /home/vagrant/return-steering-test.sh

(cd "$assets" && sha256sum \
    "$controller" "$ap" "$alpine_meta" "$alpine_rootfs" \
    astral-uv_1662.assert astral-uv_1662.snap \
    lxd_38768.assert lxd_38768.snap > SHA256SUMS)

# Install Docker, pinned uv and pinned LXD from the network-fetched artifacts.
bash "$vm_dir/scripts/00-base.sh"

ssh_env=()
if [ -n "${SSH_AUTH_SOCK:-}" ]; then
    ssh_env=(env "SSH_AUTH_SOCK=$SSH_AUTH_SOCK")
fi
as_lab_user() {
    sudo -H -u "$lab_user" "${ssh_env[@]}" "$@"
}
clone_exact() {
    local url=$1 destination=$2 commit=$3
    if [ ! -d "$destination/.git" ]; then
        as_lab_user git clone "$url" "$destination"
    fi
    as_lab_user git -C "$destination" fetch origin
    as_lab_user git -C "$destination" checkout --detach "$commit"
    test "$(git -C "$destination" rev-parse HEAD)" = "$commit"
}

# The bootstrap checkout contains the exact runtime commit as an ancestor, so
# no second set of credentials or unpublished meta-layer URL is necessary.
if [ ! -d "$runtime_repo/.git" ]; then
    as_lab_user git clone "$source_root" "$runtime_repo"
fi
as_lab_user git -C "$runtime_repo" checkout --detach \
    beef6311cec68bf4276b9f54905cdea84ba70ea1

clone_exact "${BOARDFARM_URL:-git@github.com:robvogelaar/boardfarm.git}" \
    "$bf_workspace/boardfarm" 58501f4b86baf045a2a43d9aba7b69a717377f94
clone_exact "${PYTEST_BOARDFARM_URL:-git@github.com:robvogelaar/pytest-boardfarm.git}" \
    "$bf_workspace/pytest-boardfarm" 2eb81e271f1846b2255f31dfb724540fdfdb8316
clone_exact "${BOARDFARM_DOCSIS_URL:-git@github.com:robvogelaar/boardfarm-docsis.git}" \
    "$bf_workspace/boardfarm-docsis" 7235bc320bce2ac2f8da5f9f477a5f4749960229
clone_exact "${BOARDFARM_CHARTER_URL:-git@github.com:robvogelaar/boardfarm-charter.git}" \
    "$bf_workspace/boardfarm-charter" 92de47717f787701f14fefa9280525218ea69c84
clone_exact "${BOARDFARM_LAB_URL:-git@github.com:robvogelaar/boardfarm-lab-staging.git}" \
    "$bf_workspace/boardfarm-lab-staging" 510c65fc4a880471e344a88d824fd0bc07a342d8

bash "$vm_dir/scripts/20-prepare-lab-host.sh"
bash "$vm_dir/scripts/30-boardfarm-wan.sh"
as_lab_user env EASYMESH_REPO="$runtime_repo" bash "$vm_dir/scripts/40-deploy-easymesh.sh"
as_lab_user env EASYMESH_REPO="$runtime_repo" bash "$vm_dir/scripts/55-scale-topology.sh"
bash "$vm_dir/scripts/50-runtime-service.sh"
systemctl start easymesh-lab.service
bash "$vm_dir/scripts/70-health-audit.sh"
echo 'One-time installation and first cold-start PASS. The lab is ready.'
