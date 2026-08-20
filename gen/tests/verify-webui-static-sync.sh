#!/bin/sh

set -eu

usage()
{
    echo "Usage: $0 ROOTFS" >&2
    exit 2
}

[ "$#" -eq 1 ] || usage

rootfs=${1%/}
dropin="$rootfs/lib/systemd/system/em_cli.service.d/nvram.conf"

[ -f "$dropin" ] || {
    echo "FAIL: missing $dropin" >&2
    exit 1
}

grep -Fq 'cp -rf /usr/ccsp/EasyMesh/static/. /nvram/static/' "$dropin" || {
    echo "FAIL: packaged WebUI assets are not refreshed in persistent NVRAM" >&2
    exit 1
}

if grep -Eq 'cp +-[^ ]*n[^ ]* +/usr/ccsp/EasyMesh/static' "$dropin"; then
    echo "FAIL: no-clobber still prevents WebUI updates" >&2
    exit 1
fi

echo "PASS: packaged WebUI assets replace stale persistent copies"
