#!/bin/sh
# Rebuild the checked-in 32-bit onewifi_em_cli helper from a patched Yocto workdir.
#
# Usage:
#   gen/rebuild-em-cli-artifact.sh \
#     build-qemux86bpibroadband/tmp/work/core2-32-rdk-linux/unified-wifi-mesh/1.0-r0
#
# Run unified-wifi-mesh through do_compile first. The script uses its target
# sysroot and freshly linked libemcli, refreshes the helper and its static
# WebUI bundle in em-cli.tar.gz, and emits deterministic archive metadata.

set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 UNIFIED_WIFI_MESH_WORKDIR" >&2
    exit 2
fi

work=${1%/}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$script_dir/.." && pwd)
source_dir="$work/git/src/rdkb-cli"
sysroot="$work/recipe-sysroot"
native="$work/recipe-sysroot-native"
libemcli="$work/build/src/rdkb-cli/.libs/libemcli.so"
artifact="$repo/recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh/em-cli.tar.gz"
go_bin=${GO_BIN:-$(command -v go || true)}

for required in "$source_dir" \
    "$source_dir/static/index.html" "$source_dir/static/script.js" \
    "$sysroot/usr/include/ccsp/wifi_webconfig.h" \
    "$native/usr/bin/i686-rdk-linux/i686-rdk-linux-gcc" "$libemcli" "$artifact"; do
    if [ ! -e "$required" ]; then
        echo "missing required build input: $required" >&2
        exit 1
    fi
done
if [ -z "$go_bin" ] || [ ! -x "$go_bin" ]; then
    echo "Go compiler not found; set GO_BIN to a usable host Go binary" >&2
    exit 1
fi

# The helper is one Go package split over several production files.  Keep the
# input list derived from that package so adding another non-test source file
# cannot silently leave the checked-in binary behind the patched source tree.
go_sources=$(find "$source_dir" -maxdepth 1 -type f -name '*.go' \
    ! -name '*_test.go' -exec basename {} \; | LC_ALL=C sort)
if [ -z "$go_sources" ]; then
    echo "no production Go sources found in: $source_dir" >&2
    exit 1
fi

mkdir -p "$work/git/install/lib"
ln -sfn "$libemcli" "$work/git/install/lib/libemcli.so"

binary="$work/onewifi_em_cli.rebuilt"
(
    cd "$source_dir"
    PATH="$native/usr/bin/i686-rdk-linux:$native/usr/bin:$PATH" \
    CGO_ENABLED=1 GOOS=linux GOARCH=386 GO386=sse2 \
    CC="i686-rdk-linux-gcc --sysroot=$sysroot -m32 -march=core2 -mtune=core2 -msse3 -mfpmath=sse" \
    CGO_CFLAGS="--sysroot=$sysroot -m32 -I$sysroot/usr/include -I$sysroot/usr/include/ccsp -I$sysroot/usr/include/rbus" \
    CGO_LDFLAGS="--sysroot=$sysroot -m32 -L$(dirname "$libemcli") -L$sysroot/usr/lib" \
    "$go_bin" build -trimpath -ldflags='-s -w' -o "$binary" \
        $go_sources
)

if ! file "$binary" | grep -q 'ELF 32-bit.*Intel 80386'; then
    echo "rebuilt helper is not a 32-bit x86 ELF: $binary" >&2
    exit 1
fi
if ! grep -a -q 'UnassociatedSTAErrors' "$binary"; then
    echo "rebuilt helper omits the candidate-rejection API schema" >&2
    exit 1
fi

archive_dir=$(mktemp -d /tmp/em-cli-archive.XXXXXX)
tar -xzf "$artifact" -C "$archive_dir"
install -m 0755 "$binary" "$archive_dir/onewifi_em_cli"
rm -rf "$archive_dir/static"
install -d -m 0755 "$archive_dir/static"
cp -a "$source_dir/static/." "$archive_dir/static/"
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
    -czf "$artifact.new" -C "$archive_dir" .
mv "$artifact.new" "$artifact"

echo "helper:"
sha256sum "$binary"
echo "archive:"
sha256sum "$artifact"
echo "temporary archive tree retained at: $archive_dir"
