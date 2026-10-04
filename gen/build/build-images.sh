#!/usr/bin/env bash
set -euo pipefail

source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
workspace=${TREE:-$(dirname "$source_root")}
evidence=$workspace/build-evidence
manifest=$source_root/gen/build/manifest.xml
threads=${BUILD_THREADS:-$(nproc)}
downloads=${BUILD_DOWNLOADS:-$HOME/oe/downloads}
sstate=${BUILD_SSTATE:-$HOME/oe/sstate-cache}
# BUILD_EMOSA=1: the controller image with EMOSA's adapter in C (EMOSA_ADAPTER, the image's
# opt-in; recorded as controller-emosa-*). Off by default: the default image is unchanged.
emosa=${BUILD_EMOSA:-0}
role_selection=${1:-both}

case "$role_selection" in controller|extender|both) ;; *) echo 'usage: build-images.sh [controller|extender|both]' >&2; exit 2 ;; esac
case "$emosa" in
    0) suffix= ;;
    1) suffix=-emosa; [ "$role_selection" = controller ] || { echo 'BUILD_EMOSA=1 builds the controller image only' >&2; exit 2; } ;;
    *) echo 'BUILD_EMOSA must be 0 or 1' >&2; exit 2 ;;
esac
[[ "$threads" =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_THREADS must be a positive integer' >&2; exit 2; }
test -z "$(git -C "$source_root" status --porcelain)" || { echo 'commit or stash layer changes before building' >&2; exit 1; }
test -f "$workspace/meta-cmf-bananapi/setup-environment-refboard-rdkb" || {
    echo "Missing RDK BPI setup script in $workspace/meta-cmf-bananapi." >&2
    echo "Run gen/build/bootstrap-sources.sh first." >&2
    exit 1
}
mkdir -p "$evidence" "$downloads" "$sstate"

python3 - "$manifest" "$workspace" <<'PY'
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as tree
manifest, workspace = map(pathlib.Path, sys.argv[1:])
for project in tree.parse(manifest).findall('project'):
    directory = workspace / project.get('path', project.get('name'))
    expected = project.get('revision')
    actual = subprocess.check_output(['git', '-C', directory, 'rev-parse', 'HEAD'], text=True).strip()
    if actual != expected:
        raise SystemExit(f'Pinned source mismatch: {directory}: {actual} != {expected}')
PY

cat > "$workspace/clean-build.conf" <<EOF
BB_NUMBER_THREADS:forcevariable = "$threads"
PARALLEL_MAKE:forcevariable = "-j $threads"
DL_DIR:forcevariable = "$downloads"
SSTATE_DIR:forcevariable = "$sstate"
SSTATE_MIRRORS:forcevariable = ""
EOF
# EMOSA's opt-in in a file of its own, given to bitbake only for this build: clean-build.conf
# stays the default image's (a Yocto shell rebuild reads it)
confs=(-R "$workspace/clean-build.conf")
if [ "$emosa" = 1 ]; then
    echo 'EMOSA_ADAPTER = "1"' > "$workspace/emosa-build.conf"
    confs+=(-R "$workspace/emosa-build.conf")
fi

for role in controller extender; do
    [ "$role_selection" = both ] || [ "$role_selection" = "$role" ] || continue
    if [ "$role" = controller ]; then machine=qemux86bpibroadband; target=rdk-generic-broadband-image
    else machine=qemux86bpiap; target=rdk-generic-ap-extender-image; fi
    record=$evidence/$role$suffix-$(date -u +%Y%m%dT%H%M%SZ)
    mkdir -p "$record"
    printf '%s\n' "$record" > "$evidence/latest-$role$suffix"
    printf 'Preparing %s image (%s); evidence: %s\n' "$role" "$target" "$record"
    (
        trap 'status=$?; printf "%s\n" "$status" > "$record/exit-code"; date -u +%FT%TZ > "$record/finished"' EXIT
        cd "$workspace"
        git -C "$source_root" rev-parse HEAD > "$record/layer-commit"
        cp "$manifest" "$record/manifest.xml"
        cp clean-build.conf "$record/"
        [ "$emosa" = 0 ] || cp emosa-build.conf "$record/"
        if [ -f "build-$machine/conf/local.conf" ] && grep -q '##RDK_FLAVOR##' "build-$machine/conf/local.conf"; then
            mv "build-$machine/conf" "$record/incomplete-conf"
        fi
        set +e +u +o pipefail
        MACHINE="$machine" BPI_IMG_TYPE=nand source meta-cmf-bananapi/setup-environment-refboard-rdkb "build-$machine" > "$record/setup.log" 2>&1
        setup_status=$?
        set -euo pipefail
        [ "$setup_status" -eq 0 ] || {
            echo "RDK environment setup failed; see $record/setup.log" >&2
            tail -60 "$record/setup.log" >&2
            exit "$setup_status"
        }
        ! grep -q '##RDK_FLAVOR##' conf/local.conf
        grep -Fq 'meta-cmf-bananapi-vcpe' conf/bblayers.conf
        bitbake "${confs[@]}" -e "$target" > "$record/environment.txt" 2> "$record/environment.err"
        grep -Fx "DL_DIR=\"$downloads\"" "$record/environment.txt"
        grep -Fx "SSTATE_DIR=\"$sstate\"" "$record/environment.txt"
        grep -Fx 'SSTATE_MIRRORS=""' "$record/environment.txt"
        cp conf/local.conf conf/bblayers.conf "$record/"
        printf 'Starting BitBake for %s; log: %s/build.log\n' "$target" "$record"
        bitbake "${confs[@]}" "$target" 2>&1 | tee "$record/build.log"
        find "tmp/deploy/images/$machine" -maxdepth 1 -type f -name '*.rootfs.lxc.tar.bz2' -exec sha256sum {} + > "$record/images.sha256"
        test -s "$record/images.sha256"
    )
done
