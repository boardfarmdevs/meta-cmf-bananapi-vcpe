#!/usr/bin/env bash
set -euo pipefail

# LXC commands opportunistically parse non-terminal stdin as YAML. Vagrant's
# remote shell leaves control text there, so isolate the whole host setup.
exec </dev/null

expected_kernel=7.0.0-28-generic
assets=/home/vagrant/easymesh-assets
meta_workspace=/home/vagrant/git
boardfarm_workspace=/home/vagrant/boardfarm-open-0406
meta_bundle="$assets/meta-cmf-bananapi-vcpe.bundle"
expected_meta_head=${EASYMESH_RUNTIME_COMMIT:-5f8cd4b60398d96812b03466d10223307ec3a58f}

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
        codex/0815-clean "$expected_meta_head"
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
    # Generated lab configuration is installed below these checkouts. Preserve
    # tracked-source integrity without rejecting those intentional untracked
    # runtime files when the thin installer is resumed.
    test -z "$(sudo -u vagrant git -C "$destination" \
        status --porcelain --untracked-files=no)"
    test "$(sudo -u vagrant git -C "$destination" rev-parse HEAD)" = "$expected"
}

clone_pinned_repo boardfarm master 58501f4b86baf045a2a43d9aba7b69a717377f94
clone_pinned_repo pytest-boardfarm master 2eb81e271f1846b2255f31dfb724540fdfdb8316
clone_pinned_repo boardfarm-docsis master 7235bc320bce2ac2f8da5f9f477a5f4749960229
clone_pinned_repo boardfarm-charter master 92de47717f787701f14fefa9280525218ea69c84
clone_pinned_repo boardfarm-lab-staging main 510c65fc4a880471e344a88d824fd0bc07a342d8

if [ ! -x "$boardfarm_workspace/.venv/bin/python" ]; then
    sudo -H -u vagrant /snap/bin/uv venv --python 3.13.15 \
        --prompt bf-venv "$boardfarm_workspace/.venv"
fi
sudo -H -u vagrant env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
    /snap/bin/uv pip install \
        --requirement "$assets/boardfarm-requirements.lock"
sudo -H -u vagrant env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
    /snap/bin/uv pip install --no-deps --no-build-isolation \
        -e "$boardfarm_workspace/boardfarm[doc,dev,test]" \
        -e "$boardfarm_workspace/pytest-boardfarm[doc,dev,test]" \
        -e "$boardfarm_workspace/boardfarm-docsis[doc,dev,test]" \
        -e "$boardfarm_workspace/boardfarm-charter[doc,dev,test]" \
        -e "$boardfarm_workspace/boardfarm-lab-staging"
sudo -H -u vagrant env VIRTUAL_ENV="$boardfarm_workspace/.venv" \
    /snap/bin/uv pip check
test "$($boardfarm_workspace/.venv/bin/python -c 'import platform; print(platform.python_version())')" = 3.13.15

install -m 0644 "$assets/boardfarm-easymesh.json" \
    "$boardfarm_workspace/boardfarm-lab-staging/lab/boardfarm-easymesh.json"
install -m 0644 "$assets/boardfarm-easymesh-inventory.json" \
    "$boardfarm_workspace/boardfarm-lab-staging/inventories/boardfarm-easymesh.json"
cat > /etc/default/boardfarm-lab <<'EOF'
BF_LAB_CONFIG=boardfarm-easymesh.json
BF_INVENTORY=boardfarm-easymesh.json
BOARDFARM_WORKSPACE=/home/vagrant/boardfarm-open-0406
EOF
cat > /etc/profile.d/boardfarm-lab.sh <<'EOF'
export BF_LAB_CONFIG=boardfarm-easymesh.json
export BF_INVENTORY=boardfarm-easymesh.json
export PATH=/home/vagrant/boardfarm-open-0406/.venv/bin:$PATH
EOF

if ! lxc storage show default >/dev/null 2>&1; then
    # Vagrant's remote shell leaves control text on stdin. LXD 6.7 otherwise
    # consumes that text after --auto and tries to decode it as a storage-pool
    # YAML update even though initialization itself succeeded.
    lxd init --auto --storage-backend dir </dev/null
fi
if ! lxc storage show bpi-lab >/dev/null 2>&1; then
    lxc storage create bpi-lab dir
fi

if ! lxc image info alpine >/dev/null 2>&1; then
    lxc image import \
        "$assets/alpine-3.19-amd64-meta.tar.xz" \
        "$assets/alpine-3.19-amd64-rootfs.tar.xz" \
        --alias alpine
fi
test "$(lxc image info alpine | sed -n 's/^Fingerprint: *//p')" = \
    9a86f5422adbe70bfae1ed90007256fd121e5a04aae46c3d3e411279ba04955b

# The module archive contains the same patched binary accepted on rev130.
# Start a tri-band pool only after confirming that no copied runtime state is
# present in this clean guest.
printf '%s\n' 'options mac80211_hwsim radios=24 channels=3 regtest=5' \
    > /etc/modprobe.d/easymesh-hwsim.conf
printf '%s\n' 'mac80211_hwsim' > /etc/modules-load.d/easymesh-hwsim.conf
if [ ! -d /sys/module/mac80211_hwsim ]; then
    modprobe mac80211_hwsim
fi
# Never reload a live pool: LXD physical NICs move their entire wiphy into
# container namespaces and do not reliably keep modprobe -r from succeeding.
# Reloading here silently removes Wi-Fi from already-running lab nodes.
test "$(cat /sys/module/mac80211_hwsim/parameters/radios)" = 24
test "$(cat /sys/module/mac80211_hwsim/parameters/channels)" = 3
test "$(cat /sys/module/mac80211_hwsim/parameters/regtest)" = 5

printf '%s\n' 'lab-host-ready' > /var/lib/easymesh-vagrant/host.status
