#!/usr/bin/env bash
set -euo pipefail

# LXC commands opportunistically parse non-terminal stdin as YAML. Vagrant's
# remote shell leaves control text there, so isolate the whole host setup.
exec </dev/null

expected_kernel=${EASYMESH_KERNEL:-7.0.0-30-generic}
assets=${EASYMESH_ASSETS:-/home/vagrant/easymesh-assets}
meta_workspace=/home/vagrant/git
boardfarm_workspace=/home/vagrant/boardfarm-open-0406
meta_bundle="$assets/meta-cmf-bananapi-vcpe.bundle"
expected_meta_head=${EASYMESH_RUNTIME_COMMIT:-dee4dd4a773d8d4a5fe0e1312c6393b42c986d0c}
runtime_branch=${EASYMESH_RUNTIME_BRANCH:-codex/0828-clean}
alpine_remote=${EASYMESH_ALPINE_REMOTE:-images:alpine/3.22/amd64}

if [ "$(uname -r)" != "$expected_kernel" ]; then
    echo "expected $expected_kernel after reboot, found $(uname -r)" >&2
    exit 1
fi

install -d -o vagrant -g vagrant "$meta_workspace" "$boardfarm_workspace"

if [ ! -d "$meta_workspace/meta-cmf-bananapi-vcpe/.git" ]; then
    test -f "$meta_bundle"
    sudo -u vagrant git clone "$meta_bundle" \
        "$meta_workspace/meta-cmf-bananapi-vcpe"
fi
if [ "$(sudo -u vagrant git -C "$meta_workspace/meta-cmf-bananapi-vcpe" rev-parse HEAD)" != \
    "$expected_meta_head" ]; then
    test -z "$(sudo -u vagrant git -C "$meta_workspace/meta-cmf-bananapi-vcpe" status --porcelain)"
    if [ -f "$meta_bundle" ]; then
        sudo -u vagrant git -C "$meta_workspace/meta-cmf-bananapi-vcpe" fetch \
            "$meta_bundle" 'refs/heads/*:refs/remotes/bundle/*'
    else
        sudo -u vagrant git -C "$meta_workspace/meta-cmf-bananapi-vcpe" fetch origin
    fi
    sudo -u vagrant git -C "$meta_workspace/meta-cmf-bananapi-vcpe" checkout -B \
        "$runtime_branch" "$expected_meta_head"
fi
test "$(sudo -u vagrant git -C "$meta_workspace/meta-cmf-bananapi-vcpe" rev-parse HEAD)" = \
    "$expected_meta_head"

clone_pinned_repo() {
    local name=$1 branch=$2 expected=$3
    local destination="$boardfarm_workspace/$name"
    if [ ! -d "$destination/.git" ]; then
        sudo -u vagrant git clone "$assets/$name.bundle" "$destination"
    fi
    sudo -u vagrant git -C "$destination" checkout -B "$branch" "$expected"
    test -z "$(sudo -u vagrant git -C "$destination" \
        status --porcelain --untracked-files=no)"
    test "$(sudo -u vagrant git -C "$destination" rev-parse HEAD)" = "$expected"
}

clone_pinned_repo boardfarm-lab-staging main eeb4803c00dc1cae2dda05eb6e1b52c06ad79aa8

if [ ! -x "$boardfarm_workspace/.venv/bin/python" ]; then
    sudo -H -u vagrant /snap/bin/uv venv --python 3.13.15 \
        --prompt bf-venv "$boardfarm_workspace/.venv"
fi
sudo -H -u vagrant env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
    /snap/bin/uv pip install -e "$boardfarm_workspace/boardfarm-lab-staging"
sudo -H -u vagrant env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
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
    # Vagrant's remote shell leaves control text on stdin. LXD 6.7 otherwise
    # consumes that text after --auto and tries to decode it as a storage-pool
    # YAML update even though initialization itself succeeded.
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

# The module archive contains the same patched binary accepted on rev130.
# Start a tri-band pool only after confirming that no copied runtime state is
# present in this clean guest.
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

printf '%s\n' 'lab-host-ready' > /var/lib/easymesh-vagrant/host.status
