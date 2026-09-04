#!/bin/bash
# build-wnm-supplicant.sh - build a WNM/BTM-capable wpa_supplicant 2.10 inside an
# alpine WLAN-client container, into /tmp, leaving the system binary untouched.
#
#   build-wnm-supplicant.sh [container] [--run [ssid] [psk]]
#
#   container   target alpine client (default: wlan-client). Others come from
#               wlan-client.sh -i NNN, e.g. wlan-client-001.
#   --run       after building, (re)start wpa_supplicant on wlan0 using the WNM
#               binary. Optional ssid/psk; defaults to the current /tmp/wpa.conf
#               if one exists, else PlumeSim/open.
#
# The build is copied back to gen/wpa_supplicant/wpa_supplicant-wnm so it can
# be reviewed, committed, and baked into the reusable client image. See
# README.md for why (802.11v BTM steering) and how to verify.
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CT="${1:-wlan-client}"
shift 2>/dev/null || true
RUN=0; SSID=""; PSK=""
if [ "${1:-}" = "--run" ]; then RUN=1; SSID="${2:-}"; PSK="${3:-}"; fi

VER=2.10
SRC_URL="https://w1.fi/releases/wpa_supplicant-${VER}.tar.gz"
# Official upstream tarball checksum (w1.fi). Verified, not the local re-tar.
SRC_SHA=20df7ae5154b3830355f8ab4269123a87affdea59fe74fe9292a91d0d7e17b2f
HIDDEN_BSS_PATCH=$SCRIPT_DIR/0001-wnm-select-hidden-bss-by-current-ssid.patch

say(){ echo "[wnm-build] $*"; }
ce(){ lxc exec "$CT" -- sh -c "$1"; }

lxc info "$CT" >/dev/null 2>&1 || { echo "container '$CT' not present (create it with wlan-client.sh)"; exit 1; }
[ -r "$HIDDEN_BSS_PATCH" ] || { echo "missing source patch: $HIDDEN_BSS_PATCH"; exit 1; }

# The client holds a DHCP default route from wlan0 that outranks eth0, so apk and
# the source fetch cannot reach the internet. Drop it and DHCP eth0 if needed.
if ! ce 'wget -q -T 5 -O /dev/null https://dl-cdn.alpinelinux.org/ 2>/dev/null'; then
    say "no internet via eth0 -- dropping the wlan0 default route and DHCPing eth0"
    ce 'ip route del default dev wlan0 2>/dev/null; ip link set eth0 up; udhcpc -i eth0 -n -q >/dev/null 2>&1 || true'
fi

# Compiling gcc/wpa_supplicant OOMs at the client's default 128MB. Raise the
# cgroup limit for the build and restore it afterward.
MEM_WAS=$(lxc config get "$CT" limits.memory 2>/dev/null)
say "raising $CT memory to 512MB for the build (was ${MEM_WAS:-unset})"
lxc config set "$CT" limits.memory=512MB 2>/dev/null
restore_mem(){
    if [ -n "$MEM_WAS" ]; then
        lxc config set "$CT" limits.memory="$MEM_WAS" 2>/dev/null && say "restored $CT memory to $MEM_WAS"
    else
        lxc config unset "$CT" limits.memory 2>/dev/null && say "cleared $CT memory override (back to profile)"
    fi
}
trap restore_mem EXIT

say "installing build deps in $CT"
ce 'apk add --no-cache gcc make musl-dev openssl-dev libnl3-dev linux-headers pkgconf wget tar patch >/dev/null 2>&1' \
    || { echo "apk failed -- check the container has internet on eth0 (see README)"; exit 1; }

say "fetching wpa_supplicant $VER source"
ce "cd /tmp && { [ -f wpa_supplicant-${VER}.tar.gz ] || wget -q '${SRC_URL}'; } && \
    echo '${SRC_SHA}  wpa_supplicant-${VER}.tar.gz' | sha256sum -c - 2>/dev/null" \
    || { echo "source download or checksum failed"; exit 1; }

say "configuring (CONFIG_WNM=y) and building"
ce "cd /tmp && rm -rf wpa_supplicant-${VER} && tar xzf wpa_supplicant-${VER}.tar.gz"
lxc file push "$HIDDEN_BSS_PATCH" \
    "$CT/tmp/wpa_supplicant-${VER}/0001-wnm-select-hidden-bss-by-current-ssid.patch" >/dev/null 2>&1
ce "cd /tmp/wpa_supplicant-${VER} && \
    patch -p1 < 0001-wnm-select-hidden-bss-by-current-ssid.patch >/tmp/wnm-patch.log 2>&1" \
    || { echo "source patch failed:"; ce 'cat /tmp/wnm-patch.log'; exit 1; }
# ship the config into the build tree
lxc file push "$SCRIPT_DIR/wpa_supplicant-wnm.config" \
    "$CT/tmp/wpa_supplicant-${VER}/wpa_supplicant/.config" >/dev/null 2>&1 \
    || ce "cat > /tmp/wpa_supplicant-${VER}/wpa_supplicant/.config" < "$(dirname "$0")/wpa_supplicant-wnm.config"
ce "cd /tmp/wpa_supplicant-${VER}/wpa_supplicant && make -j\$(nproc) >/tmp/wnm-build.log 2>&1" \
    || { echo "build failed -- tail of /tmp/wnm-build.log in $CT:"; ce 'tail -20 /tmp/wnm-build.log'; exit 1; }

BIN=/tmp/wpa_supplicant-${VER}/wpa_supplicant/wpa_supplicant
say "built: $(ce "$BIN -v 2>&1 | head -1")"
# WNM is a compile-time feature with no version string; confirm the symbol is in.
if ce "grep -q wnm_process_bss_tm_req '$BIN' 2>/dev/null || strings '$BIN' 2>/dev/null | grep -qi 'BSS Transition Management'"; then
    say "WNM/BTM support: present"
else
    say "WNM/BTM support: NOT detected -- check .config"
fi

lxc file pull "$CT$BIN" "$SCRIPT_DIR/wpa_supplicant-wnm"
chmod 0755 "$SCRIPT_DIR/wpa_supplicant-wnm"
say "updated committed runtime input: $SCRIPT_DIR/wpa_supplicant-wnm"

if [ "$RUN" = "1" ]; then
    say "restarting wpa_supplicant on wlan0 with the WNM binary"
    if [ -n "$SSID" ]; then
        if [ -n "$PSK" ]; then
            NET="ctrl_interface=/run/wpa_supplicant\n\nnetwork={\n ssid=\"$SSID\"\n psk=\"$PSK\"\n key_mgmt=WPA-PSK\n}"
        else
            NET="ctrl_interface=/run/wpa_supplicant\n\nnetwork={\n ssid=\"$SSID\"\n key_mgmt=NONE\n}"
        fi
        ce "printf '$NET\n' > /tmp/wpa.conf"
    fi
    # -B daemonizes; </dev/null and the file redirect let lxc exec return cleanly
    # (an inherited tty pipe is what makes it look like a hang). This matches how
    # the reference wlan-client runs its WNM supplicant.
    ce "pkill -f wpa_supplicant 2>/dev/null; sleep 1
        [ -f /tmp/wpa.conf ] || printf 'network={\n ssid=\"PlumeSim\"\n key_mgmt=NONE\n}\n' > /tmp/wpa.conf
        ip link set wlan0 up
        $BIN -B -P /tmp/wpa.pid -i wlan0 -c /tmp/wpa.conf -D nl80211 </dev/null >/tmp/wpa.log 2>&1
        for i in \$(seq 1 15); do iw dev wlan0 link 2>/dev/null | grep -q Connected && break; sleep 1; done
        ip -4 address flush dev wlan0 scope global 2>/dev/null || true
        udhcpc -i wlan0 -n -q >/dev/null 2>&1 || true"
    say "state: $(ce 'iw dev wlan0 link 2>/dev/null | grep -E "Connected to|SSID" | tr "\n" " "')"
fi

say "done. WNM binary: $SCRIPT_DIR/wpa_supplicant-wnm"
