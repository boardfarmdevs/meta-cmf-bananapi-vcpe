#!/bin/bash
# wmediumd-up.sh -- start (or stop) the multichannel wmediumd over the current
# mac80211_hwsim pool, giving the lab a real RF medium instead of the default
# flat-signal everyone-hears-everyone.
#
#   ./wmediumd-up.sh up      # gen config, self-test, start wmediumd (daemon)
#   ./wmediumd-up.sh down     # stop it (kernel reverts to its built-in medium)
#   ./wmediumd-up.sh status
#
# Requires: the pool loaded with a guard-removed module (gen/hwsim/build-hwsim.sh)
# if channels>1 -- stock mac80211_hwsim returns -EOPNOTSUPP to REGISTER at
# channels>1. WMEDIUMD env overrides the binary (default: committed prebuilt).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
WMD=${WMEDIUMD:-$HERE/wmediumd.patched}
[ -x "$WMD" ] || WMD=$HERE/src/wmediumd/wmediumd
CFG=${CFG:-/tmp/wmediumd.cfg}
PIDF=/tmp/wmediumd.pid
CONTROL=${WMEDIUMD_CONTROL:-/run/wmediumd-control.sock}
CONTROL_GROUP=${WMEDIUMD_CONTROL_GROUP:-lxd}

# `up` is also the normal way to refresh the matrix after adding clients.  It
# must replace the existing daemon, not overwrite the pidfile and leave the old
# process registered with mac80211_hwsim.  Match the full executable path so an
# unrelated system wmediumd is not affected, wait for REGISTER ownership to be
# released, and use SIGKILL only as a bounded fallback.
stop_running_wmediumd() {
    local pattern pids n
    pattern="^${WMD//./\\.}([[:space:]]|$)"
    pids=$(sudo pgrep -f "$pattern" 2>/dev/null || true)
    [ -n "$pids" ] || { sudo rm -f "$PIDF" "$CONTROL"; return; }
    sudo kill $pids 2>/dev/null || true
    for n in $(seq 1 20); do
        pids=$(sudo pgrep -f "$pattern" 2>/dev/null || true)
        [ -z "$pids" ] && break
        sleep 0.1
    done
    if [ -n "$pids" ]; then
        sudo kill -KILL $pids 2>/dev/null || true
    fi
    sudo rm -f "$PIDF" "$CONTROL"
}

case "${1:-up}" in
  up)
    [ -x "$WMD" ] || { echo "no wmediumd binary ($WMD); run build-wmediumd.sh" >&2; exit 1; }
    stop_running_wmediumd
    # Pool vifs are created administratively UP even while unused.  They are not
    # part of the active matrix and must not originate frames after REGISTER.
    # bpi.sh/wlan-client.sh bring a vif back up after assigning its phy.
    for netdev in /sys/class/net/virt-wlan*; do
        [ -e "$netdev" ] || continue
        sudo ip link set "${netdev##*/}" down
    done
    echo ">> generating config -> $CFG"
    "$HERE/gen-config.sh" "${SNR:-40}" > "$CFG"
    echo ">> self-test"
    sudo "$WMD" -T || {
        echo "wmediumd self-test failed; the binary may be an unpatched/stale v0.3.1 build" >&2
        exit 1
    }
    echo ">> starting wmediumd"
    sudo rm -f "$PIDF" "$CONTROL" /tmp/wmediumd.log
    sudo sh -c "'$WMD' -c '$CFG' -C '$CONTROL' >/tmp/wmediumd.log 2>&1 & echo \$! > '$PIDF'"
    sleep 1
    pid=$(cat "$PIDF" 2>/dev/null || true)
    if [ -z "$pid" ] || ! sudo kill -0 "$pid" 2>/dev/null; then
        echo "!! wmediumd exited during startup" >&2
        tail -20 /tmp/wmediumd.log 2>/dev/null >&2 || true
        exit 1
    fi
    if grep -Eqi "Operation not supported|Device or resource busy|REGISTER.*failed|Unable to find sender" /tmp/wmediumd.log 2>/dev/null; then
        echo "!! wmediumd registered incompletely or rejected a radio" >&2
        tail -20 /tmp/wmediumd.log 2>/dev/null >&2 || true
        sudo kill "$pid" 2>/dev/null || true
        sudo rm -f "$PIDF"
        exit 1
    fi
    if [ ! -S "$CONTROL" ]; then
        echo "!! wmediumd control socket did not appear: $CONTROL" >&2
        sudo kill "$pid" 2>/dev/null || true
        sudo rm -f "$PIDF" "$CONTROL"
        exit 1
    fi
    sudo chgrp "$CONTROL_GROUP" "$CONTROL"
    sudo chmod 0660 "$CONTROL"
    echo ">> up (pid $pid); log /tmp/wmediumd.log"
    ;;
  down)
    stop_running_wmediumd
    echo ">> down (kernel back to built-in medium)"
    ;;
  status)
    if [ -f "$PIDF" ] && sudo kill -0 "$(cat "$PIDF")" 2>/dev/null; then
        echo "wmediumd running (pid $(cat "$PIDF"))"; tail -3 /tmp/wmediumd.log 2>/dev/null
    else echo "wmediumd not running"; fi
    ;;
  *) echo "usage: $0 {up|down|status}" >&2; exit 2 ;;
esac
