#!/usr/bin/env bash
set -eo pipefail
source_root=$(cd "$(dirname "$0")/../.." && pwd)
workspace=$(dirname "$source_root")
evidence=$workspace/release-evidence
threads=${BUILD_THREADS:-8}
downloads=${BUILD_DOWNLOADS:-$workspace/downloads}
role_selection=${1:-both}
case "$role_selection" in controller|extender|both) ;; *) echo 'usage: bash doc/build/build-images.sh [controller|extender|both]' >&2; exit 2 ;; esac
[[ "$threads" =~ ^[1-9][0-9]*$ ]] || { echo 'Invalid BUILD_THREADS' >&2; exit 2; }
test -z "$(git -C "$source_root" status --porcelain)" || { echo 'Commit source changes before building' >&2; exit 1; }
test -f "$workspace/meta-cmf-bananapi/setup-environment-refboard-rdkb"
mkdir -p "$evidence" "$downloads" "$workspace/sstate-cache"
python3 - "$source_root/doc/build/rdkb-bpi-nosrc-0908.xml" "$workspace" <<'PY'
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as tree

manifest, workspace = sys.argv[1:]
for project in tree.parse(manifest).findall('project'):
    directory = pathlib.Path(workspace) / project.get('path', project.get('name'))
    expected = project.get('revision')
    actual = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != expected:
        raise SystemExit(f'Source lock mismatch: {directory}: {actual} != {expected}')
print('All upstream revisions match the 0908 source lock')
PY
cat > "$workspace/clean-build.conf" <<EOF
BB_NUMBER_THREADS:forcevariable = "$threads"
PARALLEL_MAKE:forcevariable = "-j $threads"
DL_DIR:forcevariable = "$downloads"
SSTATE_DIR:forcevariable = "$workspace/sstate-cache"
SSTATE_MIRRORS:forcevariable = ""
EOF
for role in controller extender; do
    if [ "$role_selection" != both ] && [ "$role_selection" != "$role" ]; then continue; fi
    (
        cd "$workspace"
        if [ "$role" = controller ]; then
            machine=qemux86bpibroadband
            target=rdk-generic-broadband-image
        else
            machine=qemux86bpiap
            target=rdk-generic-ap-extender-image
        fi
        attempt=$(date -u +%Y%m%dT%H%M%SZ)
        record=$evidence/$role-$attempt
        mkdir -p "$record"
        git -C "$source_root" rev-parse HEAD > "$record/source-commit"
        cp "$workspace/clean-build.conf" "$record/clean-build.conf"
        date -u +%FT%TZ > "$record/started"
        MACHINE="$machine" BPI_IMG_TYPE=nand source meta-cmf-bananapi/setup-environment-refboard-rdkb "build-$machine" > "$record/setup.log" 2>&1
        bitbake -R "$workspace/clean-build.conf" -e "$target" > "$record/environment.txt" 2> "$record/environment.err"
        grep -Fx "SSTATE_DIR=\"$workspace/sstate-cache\"" "$record/environment.txt"
        grep -Fx "DL_DIR=\"$downloads\"" "$record/environment.txt"
        grep -Fx 'SSTATE_MIRRORS=""' "$record/environment.txt"
        cp conf/local.conf conf/bblayers.conf "$record/"
        printf '%s\n' "$record" > "$evidence/latest-$role"
        printf 'Building %s; log: %s/build.log\n' "$target" "$record"
        set +e
        bitbake -R "$workspace/clean-build.conf" "$target" > "$record/build.log" 2>&1
        result=$?
        set -e
        printf '%s\n' "$result" > "$record/exit-code"
        date -u +%FT%TZ > "$record/finished"
        if [ "$result" -ne 0 ]; then tail -80 "$record/build.log"; exit "$result"; fi
        find "tmp/deploy/images/$machine" -maxdepth 1 -type f -name '*.rootfs.lxc.tar.bz2' -exec sha256sum {} + > "$record/images.sha256"
        test -s "$record/images.sha256"
        cat "$record/images.sha256"
    )
done
