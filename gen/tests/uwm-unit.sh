#!/usr/bin/env bash
# The unified-wifi-mesh unit suites on the patched tree, as checks.yml's unit job runs them:
# the patched tree (patched-tree.sh); OneWifi at the image's ccsp-one-wifi SRCREV
# (gen/tests/onewifi-upstream.srcrev, from meta-cmf-broadband's ccsp-one-wifi.bbappend), fetched
# by its hash, with its setup and its he_bus and webconfig libraries, which is all of OneWifi the
# unit builds link (webconfig includes the patched tree's headers, from ../unified-wifi-mesh as
# OneWifi's makefile names it, so the tree is made first); the controller's and the agent's test
# binaries through upstream's native makefiles read with uwm-unit.mk; each binary run through
# uwm-unit-run.py, its whole output kept in WORKDIR/logs.
# OneWifi is upstream's at that commit: this repository's OneWifi patches are made on top of
# meta-cmf-broadband's, which CI does not have, and the headers they change (wifi_base.h,
# wifi_events.h) are none the unit builds include.
#   uwm-unit.sh WORKDIR   (the build packages and gtest installed; network)
# Exit status: 0 when both suites passed, else the first failing step's.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
work=${1:?a work directory}
step() { echo "== $(date -u +%H:%M:%SZ) $*"; }
mkdir -p "$work/logs" || exit 1
work=$(cd "$work" && pwd)
srcrev=$(tr -d '[:space:]' < "$here/onewifi-upstream.srcrev")

step "the patched tree"
bash "$here/patched-tree.sh" "$work/unified-wifi-mesh" || exit 1

step "OneWifi $srcrev"
mkdir -p "$work/OneWifi" || exit 1
git -C "$work/OneWifi" init -q || exit 1
git -C "$work/OneWifi" fetch -q --depth 1 https://github.com/rdkcentral/OneWifi.git "$srcrev" || exit 1
git -C "$work/OneWifi" checkout -q FETCH_HEAD || exit 1
head=$(git -C "$work/OneWifi" rev-parse HEAD)
if [ "$head" != "$srcrev" ]; then
    echo "FAIL: fetched OneWifi $head, not $srcrev"
    exit 1
fi
# the setup fetches OneWifi's own dependencies at the commits its makefile names
make -C "$work/OneWifi" -f build/linux/bpi/makefile setup > "$work/logs/onewifi-setup.log" 2>&1 ||
    { echo "FAIL: OneWifi setup (logs/onewifi-setup.log)"; exit 1; }
for lib in libhebus libwebconfig; do
    make -j"$(nproc)" -C "$work/OneWifi" -f build/linux/bpi/makefile "$work/OneWifi/install/lib/$lib.a" \
        > "$work/logs/onewifi-$lib.log" 2>&1 || { echo "FAIL: OneWifi's $lib (logs/onewifi-$lib.log)"; exit 1; }
done

rc=0
for part in ctrl agent; do
    step "$part: the test binary"
    if ! make -j"$(nproc)" -C "$work/unified-wifi-mesh/build/$part" -f makefile -f "$here/uwm-unit.mk" \
            unit-test-binary > "$work/logs/$part-build.log" 2>&1; then
        grep -E " error: |undefined reference|cannot find" "$work/logs/$part-build.log" | head -20
        echo "FAIL: the $part test binary did not build (logs/$part-build.log)"
        rc=1
        continue
    fi
    # the command transport it was built with is the unix socket (0281, em_cmd_exec.h), as the
    # image's build checks for the daemons and libemcli
    if ! grep -q -a -F "em_cmd transport: unix socket" "$work/unified-wifi-mesh/install/bin/onewifi_em_${part}_test"; then
        echo "FAIL: the $part test binary does not carry the unix command transport (0281)"
        rc=1
        continue
    fi
    step "$part: the run"
    ASAN_OPTIONS=detect_leaks=0 python3 -I "$here/uwm-unit-run.py" --log "$work/logs/$part-run.log" \
        "$work/unified-wifi-mesh/install/bin/onewifi_em_${part}_test" || rc=1
done
exit $rc
