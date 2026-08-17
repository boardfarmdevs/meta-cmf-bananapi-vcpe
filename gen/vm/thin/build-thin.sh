#!/usr/bin/env bash
set -euo pipefail

online_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cache="$online_dir/.cache"
archive="$cache/linux-7.0.0-28-hwsim.tar.zst"
expected=0cc52c6ae26c0e71e45334461690c46f7d8494b50152d15f739a7a7a4edbb799

mkdir -p "$cache"
if [ -n "${EASYMESH_KERNEL_ARCHIVE:-}" ]; then
    if [ ! "$EASYMESH_KERNEL_ARCHIVE" -ef "$archive" ]; then
        cp --reflink=auto "$EASYMESH_KERNEL_ARCHIVE" "$archive"
    fi
elif [ ! -f "$archive" ]; then
    : "${EASYMESH_KERNEL_URL:?set EASYMESH_KERNEL_URL or EASYMESH_KERNEL_ARCHIVE}"
    curl --fail --location --retry 3 --output "$archive.part" \
        "$EASYMESH_KERNEL_URL"
    mv "$archive.part" "$archive"
fi
echo "$expected  $archive" | sha256sum -c -

cd "$online_dir"
vagrant up --provision
vagrant ssh -c 'test "$(uname -r)" = 7.0.0-28-generic; test "$(findmnt -b -n -o SIZE /)" -ge 60000000000'

mkdir -p artifacts
box=${EASYMESH_THIN_BOX_OUTPUT:-artifacts/easymesh-ubuntu24-linux7-$(date -u +%Y%m%dT%H%M%SZ).box}
vagrant package --output "$box"
sha256sum "$box" | tee "$box.sha256"
