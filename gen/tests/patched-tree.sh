#!/usr/bin/env bash
# The fully patched unified-wifi-mesh source tree without Yocto, as the image builds it: upstream
# at the base recipe's SRCREV (gen/tests/uwm-upstream.srcrev, from meta-cmf-broadband's
# unified-wifi-mesh.bb), fetched by its hash and checked to be that commit; every file://*.patch
# of unified-wifi-mesh.bbappend in SRC_URI order, with patch -p1 --fuzz=0, so a patch Yocto would
# apply only with fuzz fails here too; then the Go files the bbappend's do_patch_append copies
# into src/rdkb-cli.
#   patched-tree.sh DIR   (DIR new or empty)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
bbappend=$repo/recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh.bbappend
files=$repo/recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh
dir=${1:?the directory for the tree}
srcrev=$(tr -d '[:space:]' < "$here/uwm-upstream.srcrev")

mkdir -p "$dir"
git -C "$dir" init -q
git -C "$dir" fetch -q --depth 1 https://github.com/rdkcentral/unified-wifi-mesh.git "$srcrev"
git -C "$dir" checkout -q FETCH_HEAD
head=$(git -C "$dir" rev-parse HEAD)
if [ "$head" != "$srcrev" ]; then
    echo "FAIL: fetched $head, not $srcrev"
    exit 1
fi

# EASYMESH_CORE_PATCHES, the patches' one list, in its order
n=0
while read -r patch; do
    if ! (cd "$dir" && patch -p1 --fuzz=0 --no-backup-if-mismatch -s < "$files/$patch"); then
        echo "FAIL: $patch does not apply to the tree the patches before it make, without fuzz"
        exit 1
    fi
    n=$((n + 1))
done < <(sed -n 's#^[[:space:]]*file://\([^ ;]*\.patch\).*#\1#p' "$bbappend")

# the Go files of do_patch_append's list
gofiles=$(sed -n '/^python do_patch_append/,/^}/s/.*for name in (\(.*\)):.*/\1/p' "$bbappend" | tr -d '",')
g=0
for name in $gofiles; do
    cp "$files/$name" "$dir/src/rdkb-cli/$name"
    g=$((g + 1))
done
if [ "$n" -eq 0 ] || [ "$g" -eq 0 ]; then
    echo "FAIL: $n patches and $g Go files read from $bbappend"
    exit 1
fi
echo "patched tree: upstream $srcrev, $n patches, $g Go files"
