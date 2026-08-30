#!/usr/bin/env bash
set -euo pipefail

# LXC commands opportunistically parse non-terminal stdin as YAML. Isolate the
# complete host setup from any outer VM-agent input.
exec </dev/null

expected_kernel=${EASYMESH_KERNEL:-7.0.0-30-generic}
assets=${EASYMESH_ASSETS:-/home/easymesh/easymesh-assets}
meta_workspace=/home/easymesh/git
boardfarm_workspace=/home/easymesh/boardfarm-open-0406
meta_bundle="$assets/meta-cmf-bananapi-vcpe.bundle"
expected_meta_head=${EASYMESH_RUNTIME_COMMIT:-dee4dd4a773d8d4a5fe0e1312c6393b42c986d0c}
runtime_branch=${EASYMESH_RUNTIME_BRANCH:-codex/0829-lxd-primary}
alpine_remote=${EASYMESH_ALPINE_REMOTE:-images:alpine/3.22/amd64}

if [ "$(uname -r)" != "$expected_kernel" ]; then
    echo "expected $expected_kernel after reboot, found $(uname -r)" >&2
    exit 1
fi

install -d -o easymesh -g easymesh "$meta_workspace" "$boardfarm_workspace"

if [ ! -d "$meta_workspace/meta-cmf-bananapi-vcpe/.git" ]; then
    test -f "$meta_bundle"
    sudo -u easymesh git clone "$meta_bundle" \
        "$meta_workspace/meta-cmf-bananapi-vcpe"
fi
if [ "$(sudo -u easymesh git -C "$meta_workspace/meta-cmf-bananapi-vcpe" rev-parse HEAD)" != \
    "$expected_meta_head" ]; then
    test -z "$(sudo -u easymesh git -C "$meta_workspace/meta-cmf-bananapi-vcpe" status --porcelain)"
    if [ -f "$meta_bundle" ]; then
        sudo -u easymesh git -C "$meta_workspace/meta-cmf-bananapi-vcpe" fetch \
            "$meta_bundle" 'refs/heads/*:refs/remotes/bundle/*'
    else
        sudo -u easymesh git -C "$meta_workspace/meta-cmf-bananapi-vcpe" fetch origin
    fi
    sudo -u easymesh git -C "$meta_workspace/meta-cmf-bananapi-vcpe" checkout -B \
        "$runtime_branch" "$expected_meta_head"
fi
test "$(sudo -u easymesh git -C "$meta_workspace/meta-cmf-bananapi-vcpe" rev-parse HEAD)" = \
    "$expected_meta_head"

clone_pinned_repo() {
    local name=$1 branch=$2 expected=$3
    local destination="$boardfarm_workspace/$name"
    if [ ! -d "$destination/.git" ]; then
        sudo -u easymesh git clone "$assets/$name.bundle" "$destination"
    fi
    sudo -u easymesh git -C "$destination" checkout -B "$branch" "$expected"
    test -z "$(sudo -u easymesh git -C "$destination" \
        status --porcelain --untracked-files=no)"
    test "$(sudo -u easymesh git -C "$destination" rev-parse HEAD)" = "$expected"
}

clone_pinned_repo boardfarm-lab-staging main eeb4803c00dc1cae2dda05eb6e1b52c06ad79aa8

if [ ! -x "$boardfarm_workspace/.venv/bin/python" ]; then
    sudo -H -u easymesh /snap/bin/uv venv --python 3.13.15 \
        --prompt bf-venv "$boardfarm_workspace/.venv"
fi
sudo -H -u easymesh env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
    /snap/bin/uv pip install -e "$boardfarm_workspace/boardfarm-lab-staging"
sudo -H -u easymesh env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
    /snap/bin/uv pip check
test "$($boardfarm_workspace/.venv/bin/python -c 'import platform; print(platform.python_version())')" = 3.13.15

printf '%s\n' \
    'BF_LAB_CONFIG=ca-desk6.json' \
    'BF_INVENTORY=ca-desk6.json' \
    "BOARDFARM_WORKSPACE=$boardfarm_workspace" \
    > /etc/default/boardfarm-lab
printf '%s\n' \
    'export BF_LAB_CONFIG=ca-desk6.json' \
    'export BF_INVENTORY=ca-desk6.json' \
    "export PATH=$boardfarm_workspace/.venv/bin:\$PATH" \
    > /etc/profile.d/boardfarm-lab.sh

if ! lxc storage show default >/dev/null 2>&1; then
    # LXD 6.7 may consume outer agent input after --auto and try to decode it
    # as a storage-pool YAML update even though initialization succeeded.
    lxd init --auto --storage-backend dir </dev/null
fi
if ! lxc storage show bpi-lab >/dev/null 2>&1; then
    lxc storage create bpi-lab dir
fi

if ! lxc image info alpine >/dev/null 2>&1 \
    && [ -f "$assets/alpine-3.19-amd64-meta.tar.xz" ] \
    && [ -f "$assets/alpine-3.19-amd64-rootfs.tar.xz" ]; then
    lxc image import \
        "$assets/alpine-3.19-amd64-meta.tar.xz" \
        "$assets/alpine-3.19-amd64-rootfs.tar.xz" \
        --alias alpine
fi
if ! lxc image info alpine >/dev/null 2>&1; then
    # Alpine 3.19 is retained for reproducible offline bundles, but its public
    # image-server alias has expired. Use a maintained, architecture-qualified
    # image when the build has no bundled client image.
    lxc image copy "$alpine_remote" local: --alias alpine
fi
lxc image info alpine >/dev/null

# Stock Linux 7 deliberately rejects HWSIM_CMD_REGISTER when channels > 1.
# Build the repository's narrowly-scoped registration patch against the exact
# installed Ubuntu source package. Keep source repositories supplemental so
# the normal binary repository configuration remains owned by cloud-init.
if [ ! -f /etc/apt/sources.list.d/easymesh-ubuntu-src.sources ]; then
    sed 's/^Types: deb$/Types: deb-src/' \
        /etc/apt/sources.list.d/ubuntu.sources \
        > /etc/apt/sources.list.d/easymesh-ubuntu-src.sources
fi
apt-get update
REFETCH=1 "$meta_workspace/meta-cmf-bananapi-vcpe/gen/hwsim/build-hwsim.sh" \
    --6ghz --install
hwsim_module=$(modinfo -k "$expected_kernel" -F filename mac80211_hwsim)
case "$hwsim_module" in
    "/lib/modules/$expected_kernel/updates/mac80211_hwsim.ko") ;;
    *) echo "patched hwsim module is not selected: $hwsim_module" >&2; exit 1 ;;
esac
grep -aq 'EXPERIMENTAL wmediumd' "$hwsim_module"
sha256sum "$hwsim_module" \
    > /var/lib/easymesh-lab/mac80211_hwsim.sha256
rm -rf "$meta_workspace/meta-cmf-bananapi-vcpe/gen/hwsim/build"

# Start a tri-band pool only after installing the multichannel registration
# patch and confirming that no copied runtime state is present in this guest.
hwsim_radios=${HWSIM_RADIOS:-32}
case "$hwsim_radios" in
    ''|*[!0-9]*|0) echo "HWSIM_RADIOS must be a positive integer" >&2; exit 2 ;;
esac
printf 'options mac80211_hwsim radios=%s channels=3 regtest=5\n' "$hwsim_radios" \
    > /etc/modprobe.d/easymesh-hwsim.conf
printf '%s\n' 'mac80211_hwsim' > /etc/modules-load.d/easymesh-hwsim.conf
if [ ! -d /sys/module/mac80211_hwsim ]; then
    modprobe mac80211_hwsim
fi
# Never reload a live pool: LXD physical NICs move their entire wiphy into
# container namespaces and do not reliably keep modprobe -r from succeeding.
# Reloading here silently removes Wi-Fi from already-running lab nodes.
test "$(cat /sys/module/mac80211_hwsim/parameters/radios)" = "$hwsim_radios"
test "$(cat /sys/module/mac80211_hwsim/parameters/channels)" = 3
test "$(cat /sys/module/mac80211_hwsim/parameters/regtest)" = 5

printf '%s\n' 'lab-host-ready' > /var/lib/easymesh-lab/host.status
