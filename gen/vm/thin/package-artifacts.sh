#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat >&2 <<'EOF'
usage: package-artifacts.sh STAMP THIN_BOX [BINARY_ASSETS_DIR] [OUTPUT_DIR]

Example:
  ./package-artifacts.sh 0817 \
    artifacts/easymesh-ubuntu24-linux7-20260817T210000Z.box \
    ../precooked/assets artifacts
EOF
    exit 2
}

[ "$#" -ge 2 ] && [ "$#" -le 4 ] || usage
stamp=$1
thin_box=$(realpath "$2")
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
vm_dir=$(cd "$script_dir/.." && pwd)
binary_assets=$(realpath "${3:-$vm_dir/precooked/assets}")
output_dir=${4:-$script_dir/artifacts}

[[ "$stamp" =~ ^[0-9]{4,14}$ ]] || {
    echo "STAMP must contain 4-14 digits, for example 0817 or 20260817" >&2
    exit 2
}
test -f "$thin_box"

mapfile -t controller_candidates < <(find "$binary_assets" -maxdepth 1 -type f \
    -name 'X86EMLTRBPIBB_rdk-next_*.rootfs.lxc.tar.bz2' | sort)
mapfile -t extender_candidates < <(find "$binary_assets" -maxdepth 1 -type f \
    -name 'X86EMLTRBPIAP_rdk-next_*.rootfs.lxc.tar.bz2' | sort)
[ "${#controller_candidates[@]}" -eq 1 ] || {
    echo "expected exactly one controller image in $binary_assets; found ${#controller_candidates[@]}" >&2
    exit 1
}
[ "${#extender_candidates[@]}" -eq 1 ] || {
    echo "expected exactly one extender image in $binary_assets; found ${#extender_candidates[@]}" >&2
    exit 1
}
controller_source=${controller_candidates[0]}
extender_source=${extender_candidates[0]}
alpine_meta_source="$binary_assets/alpine-3.19-amd64-meta.tar.xz"
alpine_rootfs_source="$binary_assets/alpine-3.19-amd64-rootfs.tar.xz"
for source_file in \
    "$controller_source" "$extender_source" \
    "$alpine_meta_source" "$alpine_rootfs_source"; do
    test -f "$source_file" || {
        echo "missing required artifact: $source_file" >&2
        exit 1
    }
done

staging=$(mktemp -d)
trap 'rm -rf -- "$staging"' EXIT
install -d "$staging/artifacts" "$output_dir"

box_name="easymesh-thin-$stamp.box"
# Retain the BPIBB/BPIAP tokens: bpi.sh uses them to select the product role.
controller_name=$(basename "$controller_source")
extender_name=$(basename "$extender_source")
alpine_meta_name="easymesh-alpine-meta-$stamp.tar.xz"
alpine_rootfs_name="easymesh-alpine-rootfs-$stamp.tar.xz"
environment_name="easymesh-local-$stamp.env"
manifest_name="SHA256SUMS-$stamp"
archive_name="em-artifacts-$stamp.tar.bz2"

cp --reflink=auto "$thin_box" "$staging/artifacts/$box_name"
cp --reflink=auto "$controller_source" "$staging/artifacts/$controller_name"
cp --reflink=auto "$extender_source" "$staging/artifacts/$extender_name"
cp --reflink=auto "$alpine_meta_source" "$staging/artifacts/$alpine_meta_name"
cp --reflink=auto "$alpine_rootfs_source" "$staging/artifacts/$alpine_rootfs_name"
install -m 0644 "$vm_dir/consumer/Vagrantfile" "$staging/Vagrantfile"

controller_sha=$(sha256sum "$controller_source" | awk '{print $1}')
extender_sha=$(sha256sum "$extender_source" | awk '{print $1}')
alpine_meta_sha=$(sha256sum "$alpine_meta_source" | awk '{print $1}')
alpine_rootfs_sha=$(sha256sum "$alpine_rootfs_source" | awk '{print $1}')
runtime_commit=$(git -C "$vm_dir/../.." rev-parse HEAD)
wmediumd_sha=$(sha256sum "$vm_dir/../wmediumd/wmediumd.patched" | awk '{print $1}')

cat >"$staging/artifacts/$environment_name" <<EOF
EASYMESH_CONTROLLER_IMAGE_URL=file:///vagrant-artifacts/$controller_name
EASYMESH_AP_IMAGE_URL=file:///vagrant-artifacts/$extender_name
EASYMESH_CONTROLLER_IMAGE_NAME=$controller_name
EASYMESH_AP_IMAGE_NAME=$extender_name
EASYMESH_ALPINE_META_URL=file:///vagrant-artifacts/$alpine_meta_name
EASYMESH_ALPINE_ROOTFS_URL=file:///vagrant-artifacts/$alpine_rootfs_name
EASYMESH_CONTROLLER_IMAGE_SHA256=$controller_sha
EASYMESH_AP_IMAGE_SHA256=$extender_sha
EASYMESH_ALPINE_META_SHA256=$alpine_meta_sha
EASYMESH_ALPINE_ROOTFS_SHA256=$alpine_rootfs_sha
EASYMESH_WMEDIUMD_SHA256=$wmediumd_sha
EASYMESH_RUNTIME_COMMIT=$runtime_commit
EOF

cat >"$staging/ARTIFACTS-$stamp.md" <<EOF
# EasyMesh artifact bundle $stamp

Verify from this extracted directory:

    sha256sum -c artifacts/$manifest_name

Register the thin box:

    vagrant box add --name cmf/easymesh-thin artifacts/$box_name

Inside the running VM, install the generated local-artifact configuration:

    sudo install -m 0600 /vagrant-artifacts/$environment_name /etc/easymesh-online.env
EOF

(
    cd "$staging"
    sha256sum \
        "Vagrantfile" "ARTIFACTS-$stamp.md" \
        "artifacts/$box_name" \
        "artifacts/$controller_name" \
        "artifacts/$extender_name" \
        "artifacts/$alpine_meta_name" \
        "artifacts/$alpine_rootfs_name" \
        "artifacts/$environment_name" >"artifacts/$manifest_name"
)

archive="$output_dir/$archive_name"
tar -cjf "$archive" -C "$staging" .
sha256sum "$archive" >"$archive.sha256"

printf 'created: %s\n' "$archive"
printf 'sidecar: %s\n' "$archive.sha256"
printf 'size:    %s\n' "$(du -h "$archive" | awk '{print $1}')"
printf 'upload the tarball to Dropbox; retain the sidecar checksum locally.\n'
