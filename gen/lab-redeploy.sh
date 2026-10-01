#!/usr/bin/env bash
# Inside the lab VM (root): new images in a running lab. Every gateway and extender
# container is deployed again from the new image and keeps its identity (its nvram: AL
# MAC, radios, the controller's database), and what the build set up around them is
# restored.
#
#   gen/lab-redeploy.sh CONTROLLER_IMAGE EXTENDER_IMAGE
#
# Each image is a *.rootfs.lxc.tar.bz2, named in the assets directory
# (/home/easymesh/easymesh-assets) or given as a path. Never while a room suite runs.
#
# The order, as the lab needs it: the room service stops (it drives the medium); the
# gateway, and em_cli started with its agent (40-deploy-easymesh.sh); the wired LAN
# port into the gateway's brlan0 again, when the lab has one (a new gateway container
# has no eth2); the Wi-Fi extenders; the medium; a wired extender again, in the order
# gen/wired-extender.sh keeps (no LAN port until it is isolated on the medium); the
# journal evidence mode again when it was on; then gen/lab-bringup.sh up. Last it
# lists each node's image and any file installed in place (*.pre-*) left in it.
set -euo pipefail
exec </dev/null

GEN=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
ASSETS=${EASYMESH_ASSETS:-/home/easymesh/easymesh-assets}
ROOM_UNIT=easymesh-room-service.service
EVIDENCE=/etc/systemd/journald.conf.d/zz-lab-journal-evidence.conf

log() { printf '\n== %s %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { echo "lab-redeploy: $*" >&2; exit 1; }
image() { case $1 in */*) echo "$1" ;; *) echo "$ASSETS/$1" ;; esac; }
exists() { lxc info "$1" >/dev/null 2>&1; }

[ $# -eq 2 ] || { sed -n '2,10p' "$0"; exit 2; }
[ "$(id -u)" = 0 ] || die "run as root in the lab VM"
controller=$(image "$1"); extender=$(image "$2")
for f in "$controller" "$extender"; do [ -f "$f" ] || die "no image $f"; done
exists bpibroadband || die "no gateway container bpibroadband: build the lab first"

# what the lab has now, before anything is replaced
wifi_extenders=() wired_extenders=()
for c in $(lxc list -c n -f csv | grep -E '^bpiap(-[0-9]{3})?$' | sort -V); do
    if [ "$(lxc config get "$c" user.easymesh.backhaul)" = wired ]; then
        wired_extenders+=("$c")
    else
        wifi_extenders+=("$c")
    fi
done
evidence=no
lxc exec bpibroadband -- test -e "$EVIDENCE" 2>/dev/null && evidence=yes
lanport=no
lxc config device show bpibroadband 2>/dev/null | grep -q 'name: eth2' && lanport=yes
echo "gateway, Wi-Fi extenders ${wifi_extenders[*]:-none}, wired extenders ${wired_extenders[*]:-none};" \
    "wired LAN port $lanport, journal evidence $evidence"

index() { case $1 in bpiap) ;; *) echo "-i $((10#${1#bpiap-}))" ;; esac; }

cd "$GEN"
log "room stopped"; systemctl stop "$ROOM_UNIT"

log "gateway"
./bpi.sh -b br-wan101 "$controller" 2>&1 | tail -3
lxc exec bpibroadband -- mkdir -p /etc/systemd/system/em_agent.service.d
printf '%s\n' '[Unit]' 'Wants=em_cli.service' |
    lxc exec bpibroadband -- tee /etc/systemd/system/em_agent.service.d/em-cli.conf >/dev/null
lxc exec bpibroadband -- systemctl daemon-reload
lxc exec bpibroadband -- systemctl enable em_cli.service
lxc exec bpibroadband -- systemctl start em_cli.service
if [ "$lanport" = yes ]; then
    log "wired LAN port"; ./wired-extender.sh lanport 2>&1 | tail -2
fi

for c in "${wifi_extenders[@]}"; do
    log "extender $c"
    # shellcheck disable=SC2046  # index is "" or "-i N"
    ./bpi.sh $(index "$c") "$extender" 2>&1 | tail -2
done
for c in bpibroadband "${wifi_extenders[@]}"; do lxc config set "$c" boot.autostart false; done

log "medium"; SNR=40 bash medium/wmediumd/wmediumd-up.sh up | tail -1

for c in "${wired_extenders[@]}"; do
    log "wired extender $c"
    # shellcheck disable=SC2046
    ./bpi.sh $(index "$c") "$extender" 2>&1 | tail -2    # no LAN port: wired-extender.sh adds it
    ./wired-extender.sh up "$((10#${c#bpiap-}))" 2>&1 | sed 's/\x1b\[[0-9;]*m//g'
done

if [ "$evidence" = yes ]; then
    log "journal evidence"; ./lab-journal-evidence.sh on 2>&1 | tail -8
fi

log "bring-up"; ./lab-bringup.sh up
./lab-bringup.sh status

log "images and files installed in place"
for c in bpibroadband "${wifi_extenders[@]}" "${wired_extenders[@]}"; do
    echo "$c: $(lxc config get "$c" user.build) $(lxc exec "$c" -- sh -c \
        'find /usr /lib -name "*.pre-*" 2>/dev/null | wc -l') *.pre-* files"
done
log done
