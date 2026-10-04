#!/usr/bin/env bash
set -euo pipefail

# The lab host's part that comes with the commit being built: the lab's checkout, its
# medium and optimizer submodules, and the medium's daemon and console the host built.
# The part that does not depend on the commit, a base VM image's, is 15-prepare-base.sh.

# LXC commands opportunistically parse non-terminal stdin as YAML. Isolate the
# complete host setup from any outer VM-agent input.
exec </dev/null

expected_kernel=${EASYMESH_KERNEL:-7.0.0-30-generic}
assets=${EASYMESH_ASSETS:-/home/easymesh/easymesh-assets}
meta_workspace=/home/easymesh/git
meta_bundle="$assets/meta-cmf-bananapi-vcpe.bundle"
expected_meta_head=${EASYMESH_RUNTIME_COMMIT:-}
runtime_branch=${EASYMESH_RUNTIME_BRANCH:-codex/0916-clean}

if [ "$(uname -r)" != "$expected_kernel" ]; then
    echo "expected $expected_kernel after reboot, found $(uname -r)" >&2
    exit 1
fi
test -f /var/lib/easymesh-lab/base-host.status || {
    echo "the base host is not prepared: 15-prepare-base.sh first" >&2
    exit 1
}

install -d -o easymesh -g easymesh "$meta_workspace"

if [ -z "$expected_meta_head" ]; then
    expected_meta_head=$(git bundle list-heads "$meta_bundle" \
        | awk '$2 == "refs/heads/lxd-appliance-export" {print $1; exit}')
    [ -n "$expected_meta_head" ] || {
        echo "cannot determine the bundled EasyMesh source revision" >&2
        exit 1
    }
fi

if [ ! -d "$meta_workspace/meta-cmf-bananapi-vcpe/.git" ]; then
    test -f "$meta_bundle"
    sudo -u easymesh git clone "$meta_bundle" \
        "$meta_workspace/meta-cmf-bananapi-vcpe"
fi
if [ "$(sudo -u easymesh git -C "$meta_workspace/meta-cmf-bananapi-vcpe" rev-parse HEAD)" != \
    "$expected_meta_head" ] || \
   [ "$(sudo -u easymesh git -C "$meta_workspace/meta-cmf-bananapi-vcpe" symbolic-ref --short -q HEAD || true)" != \
    "$runtime_branch" ]; then
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

# The RF medium (gen/medium, easymesh-medium at the commit the lab pins): the
# submodule from its bundle, then the daemon and console the host built from it.
lab_repo=$meta_workspace/meta-cmf-bananapi-vcpe
medium_bundle=$assets/easymesh-medium.bundle
if [ -f "$medium_bundle" ]; then
    sudo -u easymesh git -C "$lab_repo" config submodule.gen/medium.url "$medium_bundle"
fi
sudo -u easymesh git -c protocol.file.allow=always -C "$lab_repo" submodule update --init gen/medium
test "$(sudo -u easymesh git -C "$lab_repo/gen/medium" rev-parse HEAD)" = \
    "$(sudo -u easymesh git -C "$lab_repo" rev-parse HEAD:gen/medium)"
sudo -u easymesh install -D -m 0755 "$assets/wmediumd" "$lab_repo/gen/medium/wmediumd/build/wmediumd"
sudo -u easymesh install -m 0644 "$assets/wmediumd.provenance.env" \
    "$lab_repo/gen/medium/wmediumd/build/wmediumd.provenance.env"
sudo -u easymesh install -m 0755 "$assets/wmediumd-console" "$lab_repo/gen/medium/observer/wmediumd-console"

# The optimizer (gen/optimizer, easymesh-optimizer at the commit the lab pins): the
# submodule from its bundle.
optimizer_bundle=$assets/easymesh-optimizer.bundle
if [ -f "$optimizer_bundle" ]; then
    sudo -u easymesh git -C "$lab_repo" config submodule.gen/optimizer.url "$optimizer_bundle"
fi
sudo -u easymesh git -c protocol.file.allow=always -C "$lab_repo" submodule update --init gen/optimizer
test "$(sudo -u easymesh git -C "$lab_repo/gen/optimizer" rev-parse HEAD)" = \
    "$(sudo -u easymesh git -C "$lab_repo" rev-parse HEAD:gen/optimizer)"

# The radio module came with the base host (15-prepare-base.sh), built from the medium's
# radio module source; this commit's medium must pin the same, or the base is stale.
test "$(cat /var/lib/easymesh-lab/mac80211_hwsim.source)" = \
    "$(sudo -u easymesh git -C "$lab_repo/gen/medium" rev-parse HEAD:hwsim)" || {
    echo "the radio module was built from another medium: build the base again (EASYMESH_BASE_IMAGE=rebuild)" >&2
    exit 1
}

printf '%s\n' 'lab-host-ready' > /var/lib/easymesh-lab/host.status
