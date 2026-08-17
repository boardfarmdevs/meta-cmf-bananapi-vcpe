#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
precooked_dir="$root/gen/vm/precooked"
assets="$precooked_dir/assets"
boardfarm_workspace=${BOARDFARM_WORKSPACE:-/home/rev/git/boardfarm-open-0406}
binary_assets=${EASYMESH_VM_BINARY_ASSETS:-/home/rev/easymesh-vagrant-lab/assets}

install -d "$assets"

locked_revision() {
    awk -v name="$1" '$1 == name {print $3}' "$precooked_dir/assets.lock"
}

bundle_repo() {
    local name=$1
    local repo="$boardfarm_workspace/$name"
    local commit export_ref
    commit=$(locked_revision "$name")
    export_ref=refs/heads/vm-export
    test -d "$repo/.git"
    if ! git -C "$repo" cat-file -e "$commit^{commit}" 2>/dev/null; then
        if [ -f "$assets/$name.bundle" ] \
            && git bundle list-heads "$assets/$name.bundle" \
                | awk -v commit="$commit" '$1 == commit {found=1} END {exit !found}'; then
            echo "retaining $name.bundle: source clone lacks locked $commit"
            return
        fi
        echo "$repo does not contain locked commit $commit" >&2
        exit 1
    fi
    git -C "$repo" update-ref "$export_ref" "$commit"
    git -C "$repo" bundle create "$assets/$name.bundle" "$export_ref"
    git -C "$repo" update-ref -d "$export_ref"
}

bundle_repo boardfarm
bundle_repo pytest-boardfarm
bundle_repo boardfarm-docsis
bundle_repo boardfarm-charter
bundle_repo boardfarm-lab-staging

meta_commit=$(locked_revision meta-cmf-bananapi-vcpe)
meta_ref=refs/heads/vm-export
git -C "$root" update-ref "$meta_ref" "$meta_commit"
git -C "$root" bundle create "$assets/meta-cmf-bananapi-vcpe.bundle" "$meta_ref"
git -C "$root" update-ref -d "$meta_ref"

for name in \
    linux-7.0.0-28-hwsim.tar.zst \
    lxd_38768.assert lxd_38768.snap \
    X86EMLTRBPIBB_rdk-next_20260817135730.rootfs.lxc.tar.bz2 \
    X86EMLTRBPIAP_rdk-next_20260817140053.rootfs.lxc.tar.bz2 \
    alpine-3.19-amd64-meta.tar.xz alpine-3.19-amd64-rootfs.tar.xz; do
    test -f "$binary_assets/$name"
    if [ ! "$binary_assets/$name" -ef "$assets/$name" ]; then
        cp --reflink=auto "$binary_assets/$name" "$assets/$name"
    fi
done

if [ ! -f "$assets/astral-uv_1662.snap" ] \
    || [ ! -f "$assets/astral-uv_1662.assert" ]; then
    snap download astral-uv --revision=1662 --basename=astral-uv_1662 \
        --target-directory="$assets"
fi

(cd "$assets" && sha256sum \
    X86EMLTRBPIAP_rdk-next_20260817140053.rootfs.lxc.tar.bz2 \
    X86EMLTRBPIBB_rdk-next_20260817135730.rootfs.lxc.tar.bz2 \
    alpine-3.19-amd64-meta.tar.xz alpine-3.19-amd64-rootfs.tar.xz \
    boardfarm-charter.bundle boardfarm-docsis.bundle \
    boardfarm-lab-staging.bundle boardfarm.bundle \
    linux-7.0.0-28-hwsim.tar.zst \
    astral-uv_1662.assert astral-uv_1662.snap \
    lxd_38768.assert lxd_38768.snap \
    meta-cmf-bananapi-vcpe.bundle pytest-boardfarm.bundle > SHA256SUMS)
(cd "$assets" && sha256sum -c SHA256SUMS)
echo "VM inputs are complete; assets/SHA256SUMS records this exact assembly"
