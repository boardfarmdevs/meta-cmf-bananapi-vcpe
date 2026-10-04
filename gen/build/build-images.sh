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
# Another host's sstate cache over HTTP (http://HOST:PORT/sstate-cache): its objects are
# fetched instead of rebuilt; the local cache stays where it is.
sstate_mirror=${BUILD_SSTATE_MIRROR:-}
# shellcheck source=gen/build/artifact-store.sh
source "$source_root/gen/build/artifact-store.sh"
# Kirkstone's pseudo cannot follow a GNU tar that extracts through openat2 (Ubuntu's tar
# does): every do_package BitBake runs itself then fails, "unknown base path for fd"
# (~/yocto/fast-labs-test, 4 Oct). docs/guides/build.md builds a tar 1.34 without it in
# $HOME/hosttools/bin: the build takes that first, and checks the tar BitBake will use.
[ ! -x "$HOME/hosttools/bin/tar" ] || PATH=$HOME/hosttools/bin:$PATH
tar_uses_openat2() {    # tar_uses_openat2 TAR: 0 when it extracts through openat2
    local tar=$1 probe status
    command -v strace >/dev/null 2>&1 || return 1    # cannot tell without strace
    probe=$(mktemp -d)
    mkdir -p "$probe/in/a/b" "$probe/out"
    : > "$probe/in/a/b/c"
    "$tar" -cf "$probe/probe.tar" -C "$probe/in" .
    strace -f -e trace=openat2 -o "$probe/trace" \
        "$tar" -xf "$probe/probe.tar" -C "$probe/out" >/dev/null 2>&1 || true
    grep -q openat2 "$probe/trace" && status=0 || status=1
    rm -rf -- "$probe"
    return "$status"
}

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

mirrors=
[ -z "$sstate_mirror" ] || mirrors="file://.* ${sstate_mirror%/}/PATH;downloadfilename=PATH"
cat > "$workspace/clean-build.conf" <<EOF
BB_NUMBER_THREADS:forcevariable = "$threads"
PARALLEL_MAKE:forcevariable = "-j $threads"
DL_DIR:forcevariable = "$downloads"
SSTATE_DIR:forcevariable = "$sstate"
SSTATE_MIRRORS:forcevariable = "$mirrors"
EOF

# An image's key: every input bitbake reads from this checkout (the layer's recipes,
# classes, configuration and build files, the medium's topology page and the viewer
# modules it shares), the manifest that pins every other layer, and the variant.
image_key() {
    local role=$1 path medium module
    local -a inputs=("image=$role$suffix" "manifest=$(sha256sum < "$manifest" | cut -c1-64)")
    for path in classes conf gen/build $(cd "$source_root" && ls -d recipes-*); do
        inputs+=("$path=$(git -C "$source_root" rev-parse "HEAD:$path")")
    done
    medium=$(git -C "$source_root" rev-parse HEAD:gen/medium)
    inputs+=("topology-ui=$(git -C "$source_root/gen/medium" rev-parse "$medium:topology-ui")")
    while read -r module; do
        [ -n "$module" ] || continue
        inputs+=("viewer/$module=$(git -C "$source_root/gen/medium" rev-parse \
            "$medium:configurator/worlds/viewer/$module")")
    done < "$source_root/gen/medium/topology-ui/shared-modules"
    [ "$emosa" = 0 ] || inputs+=("emosa=$(git -C "$source_root" rev-parse HEAD:gen/vm/lxd/emosa-lab.env)")
    artifact_key "${inputs[@]}"
}
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
        key=$(image_key "$role")
        printf '%s\n' "$key" > "$record/image-key"
        # The same inputs built anywhere before: fetch the image instead of building it
        # (BUILD_FORCE=1 builds regardless).
        if [ "${BUILD_FORCE:-0}" != 1 ] \
            && artifact_fetch "rdk-image-$role$suffix" "$key" "$record/fetched"; then
            find "$record/fetched" -maxdepth 1 -type f -name '*.rootfs.lxc.tar.bz2' \
                -exec sha256sum {} + > "$record/images.sha256"
            test -s "$record/images.sha256"
            printf 'fetched\n' > "$record/source"
            printf 'Fetched the %s image for key %s: %s\n' "$role" "$key" \
                "$(awk '{print $2}' "$record/images.sha256")"
            exit 0
        fi
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
        if grep -q '##RDK_FLAVOR##' conf/local.conf; then
            echo "the RDK environment setup left conf/local.conf incomplete; see $record/setup.log" >&2
            exit 1
        fi
        grep -Fq 'meta-cmf-bananapi-vcpe' conf/bblayers.conf
        # the tar BitBake links into its hosttools once, from PATH, and keeps
        if [ -e tmp/hosttools/tar ]; then tar_for_bitbake=$(readlink -f tmp/hosttools/tar)
        else tar_for_bitbake=$(command -v tar); fi
        if tar_uses_openat2 "$tar_for_bitbake"; then
            echo "$tar_for_bitbake extracts through openat2, which BitBake's pseudo cannot follow:" \
                "build GNU tar 1.34 into \$HOME/hosttools/bin (docs/guides/build.md)" >&2
            [ ! -e tmp/hosttools/tar ] ||
                echo "then remove $PWD/tmp/hosttools/tar: BitBake links it again from PATH" >&2
            exit 1
        fi
        bitbake "${confs[@]}" -e "$target" > "$record/environment.txt" 2> "$record/environment.err"
        grep -Fx "DL_DIR=\"$downloads\"" "$record/environment.txt"
        grep -Fx "SSTATE_DIR=\"$sstate\"" "$record/environment.txt"
        grep -Fx "SSTATE_MIRRORS=\"$mirrors\"" "$record/environment.txt"
        cp conf/local.conf conf/bblayers.conf "$record/"
        printf 'Starting BitBake for %s; log: %s/build.log\n' "$target" "$record"
        bitbake "${confs[@]}" "$target" 2>&1 | tee "$record/build.log"
        find "tmp/deploy/images/$machine" -maxdepth 1 -type f -name '*.rootfs.lxc.tar.bz2' -exec sha256sum {} + > "$record/images.sha256"
        test -s "$record/images.sha256"
        printf 'built\n' > "$record/source"
        # Publish the image this build made, under its inputs' key
        # (EASYMESH_ARTIFACT_PUBLISH; unset, nothing is published).
        if [ -n "${EASYMESH_ARTIFACT_PUBLISH:-}" ]; then
            entry=$(mktemp -d "$workspace/.image-entry.XXXXXX")
            newest=$(find "tmp/deploy/images/$machine" -maxdepth 1 -type f \
                -name '*.rootfs.lxc.tar.bz2' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)
            cp --reflink=auto "$newest" "$entry/"
            {
                printf 'KEY=%s\nIMAGE=%s\nLAYER_COMMIT=%s\n' "$key" "$role$suffix" \
                    "$(cat "$record/layer-commit")"
                printf 'BUILT=%s\nHOST=%s\nEVIDENCE=%s\n' "$(date -u +%FT%TZ)" "$(hostname)" "$record"
            } > "$entry/provenance.env"
            artifact_publish "rdk-image-$role$suffix" "$key" "$entry"
            rm -rf -- "$entry"
        fi
    )
done
