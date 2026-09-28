#!/bin/bash
# wired-extender.sh -- an EasyMesh extender (bpiap image) on a WIRED backhaul: its LAN
# port bridged into the controller's LAN instead of a Wi-Fi backhaul station.
#
#   ./wired-extender.sh up [INDEX]       create bpiap-00INDEX (default 4) or complete an
#                                         existing one, in the only safe order (below)
#   ./wired-extender.sh down [INDEX]     delete it, regenerate the medium, forget its rows
#                                         in the controller's model
#   ./wired-extender.sh status
#
# Run as root in the lab VM. The controller's LAN is reached through LAN_BRIDGE (default
# br-emosa: a VM bridge that is a port of bpibroadband's brlan0, see emosa-lab
# deploy/rdk-lab lab.sh lanport).
#
# Order matters. A pool radio handed to a new container is on the medium at once (the
# medium lists idle pool radios at its default SNR), so a new extender's backhaul station
# can associate before anything else happens; with its LAN port also bridged that is a
# second path into the controller's LAN, an L2 loop. So: create it without a LAN port,
# mark it wired (user.easymesh.backhaul=wired: gen-config gives it no RF to the other
# mesh nodes), regenerate the medium, and only then attach and bridge the LAN port.
set -euo pipefail
exec </dev/null
gen=$(cd "$(dirname "$0")" && pwd)
LAN_BRIDGE=${LAN_BRIDGE:-br-emosa}
REFERENCE=${REFERENCE_EXTENDER:-bpiap}   # an existing extender: its image and binaries
# The reference extender's binaries (OneWifi 0040/0041, unified-wifi-mesh 0213, ieee1905
# 0009): installed in place in the lab's extenders until the images carried them (layer
# ba10c66 on); with such an image nothing differs and nothing is copied.
# OneWifi and its own libraries go together: a newer OneWifi with the image's libwifi_bus
# or libwifi_webconfig never finishes starting (start timeout, restart loop).
MATCHED=(/usr/bin/OneWifi /usr/lib/libwifi.so.0.0.0 /usr/lib/libwifi_quality_manager.so.0.0.0
    /usr/lib/libwifi_math_utils.so.0.0.0 /usr/lib/libwifi_bus.so.0.0.0 /usr/lib/libwifi_webconfig.so.0.0.0
    /usr/bin/onewifi_em_agent /usr/bin/ieee1905)
# em_agent's start waits for a bridged backhaul; the bbappend (e8682fa) accepts an
# Ethernet port of brlan0 with carrier. Applied in place to an image without it.
WAIT_LINE='ExecStartPre=/bin/sh -c '"'"'i=0; while [ $i -lt 150 ]; do for d in /sys/class/net/*/phy80211; do n=$(basename $(dirname $d)); if iw dev "$n" link 2>/dev/null | grep -q "Connected to" && [ -e "/sys/class/net/$n/master" ]; then exit 0; fi; done; for p in /sys/class/net/brlan0/brif/eth*; do n=$(basename $p); case $n in *virt*) continue;; esac; [ "$(cat /sys/class/net/$n/carrier 2>/dev/null)" = 1 ] && exit 0; done; i=$((i+1)); sleep 2; done; exit 0'"'"

log() { printf '\033[1;36m[wired-extender %s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf '\033[1;31m[wired-extender] FATAL\033[0m %s\n' "$*" >&2; exit 1; }
exists() { lxc info "$1" >/dev/null 2>&1; }
cx() { local c=$1; shift; lxc exec "$c" -- "$@"; }
name_of() { printf 'bpiap-%03d' "${1:-4}"; }
active() {    # wait (up to 10 min) for a unit: a first OneWifi start on a loaded VM takes minutes
    local c=$1 unit=$2
    for _ in $(seq 120); do [ "$(cx "$c" systemctl is-active "$unit" 2>/dev/null)" = active ] && return; sleep 5; done
    die "$c: $unit is not active"
}

medium() {    # regenerate wmediumd; the room demo drives it live, so it stops around the restart
    # A restart drops every Wi-Fi backhaul, and the Wi-Fi extenders lost their APs with it
    # until OneWifi and em_agent were restarted: only when the medium would change.
    local room= cfg=${CFG:-/run/meta-cmf-wmediumd/wmediumd.cfg} pid=/run/meta-cmf-wmediumd/wmediumd.pid
    if [ -f "$cfg" ] && kill -0 "$(cat "$pid" 2>/dev/null)" 2>/dev/null &&
            cmp -s "$cfg" <(bash "$gen/wmediumd/gen-config.sh" "${SNR:-40}" 2>/dev/null); then
        log "medium: already current"
        return
    fi
    systemctl is-active --quiet easymesh-room-demo && room=1 && systemctl stop easymesh-room-demo
    (cd "$gen" && bash wmediumd/wmediumd-up.sh up) | tail -1
    [ -z "$room" ] || systemctl start easymesh-room-demo
}

match_binaries() {    # the reference extender's in-place binaries, where they differ
    local c=$1 f t
    t=$(mktemp -d)
    for f in "${MATCHED[@]}"; do
        lxc file pull -q "$REFERENCE$f" "$t/x" 2>/dev/null || continue
        [ "$(sha256sum < "$t/x")" = "$(cx "$c" sh -c "sha256sum < $f" 2>/dev/null)" ] && continue
        lxc file push -q "$t/x" "$c/tmp/matched"
        cx "$c" sh -ec "[ -e $f.pre-match ] || cp -p $f $f.pre-match; install -m 0755 /tmp/matched $f; rm -f /tmp/matched"
        log "$c: $f as on $REFERENCE"
    done
    rm -rf "$t"
}

agent_wait() {    # em_agent's backhaul wait also ends on a wired uplink
    local c=$1 u=/lib/systemd/system/em_agent.service t
    cx "$c" grep -q 'brlan0/brif' "$u" && return
    t=$(mktemp)
    printf '%s\n' "$WAIT_LINE" > "$t"
    lxc file push -q "$t" "$c/tmp/wired-wait.line"
    rm -f "$t"
    cx "$c" sh -ec "[ -e $u.pre-wired ] || cp -p $u $u.pre-wired
        grep -v phy80211 $u.pre-wired | awk -v pre=\"\$(cat /tmp/wired-wait.line)\" '/^ExecStart=/{print pre} {print}' > $u
        systemctl daemon-reload"
    cx "$c" grep -q 'brlan0/brif' "$u" || die "$c: could not update $u"
}

no_sta_selfheal() {    # OneWifi's station selfheal must not fire on a station that never connects
    # A disconnected extender station makes OneWifi disable and enable every radio after half
    # the selfheal publish time (default 10 minutes; sta_selfheal_handing, wifi_ctrl.c), which
    # takes every AP down; a Wi-Fi extender gets them back when its station reconnects, a wired
    # one never. OneWifi's own Ethernet backhaul signal (Device.X_RDK_MeshAgent.
    # EthernetBhaulUplink.Status) needs RDKB_EXTENDER_ENABLED, which the image does not build;
    # the publish time (minutes, read on every check) is the knob it has.
    cx "$1" sh -c 'echo 1000000 > /nvram/selfheal_event_publish_time'
}

bridge_unit() {    # keep eth1 a port of brlan0 (RDK does not bridge it in extender mode) and repair the fronthaul
    local c=$1
    cx "$c" sh -c 'cat > /usr/bin/lab-wired-backhaul.sh' <<'SCRIPT'
#!/bin/sh
# lab: the wired backhaul port eth1 stays a port of brlan0. And the fronthaul comes back
# if a radio reconfiguration ever takes it down (OneWifi's station selfheal did, before
# /nvram/selfheal_event_publish_time): a Wi-Fi extender restores its APs on its backhaul
# station's reconnect, which a wired extender never has. OneWifi then em_agent (which
# pushes the controller's settings again) bring them back. At most once per 3 minutes, logged.
# And no Wi-Fi station stays up: with eth1 in brlan0 an associated backhaul station is a
# second path into the LAN (an L2 loop), whatever the medium says.
down=0 last=-180
while :; do
    for n in $(iw dev 2>/dev/null | awk '$1 == "Interface" {n = $2} $1 == "type" && $2 == "managed" {print n}'); do
        if [ -e "/sys/class/net/$n/master" ] || [ "$(cat "/sys/class/net/$n/operstate" 2>/dev/null)" != down ]; then
            echo "$n: a station on a wired extender: out of the bridge and down"
            ip link set "$n" nomaster 2>/dev/null; ip link set "$n" down
        fi
    done
    if [ -e /sys/class/net/brlan0 ] && [ -e /sys/class/net/eth1 ] &&
            [ "$(basename "$(readlink /sys/class/net/eth1/master)")" != brlan0 ]; then
        ip link set eth1 up; ip link set eth1 master brlan0
    fi
    if [ "$(systemctl is-active em_agent)" = active ] && [ "$(systemctl is-active onewifi)" = active ] &&
            ! iw dev wifi0 info 2>/dev/null | grep -q ssid; then
        down=$((down + 1))
    else
        down=0
    fi
    now=$(cut -d. -f1 /proc/uptime)
    if [ "$down" -ge 6 ] && [ $((now - last)) -ge 180 ]; then
        echo "fronthaul down for 30 s: restarting onewifi, then em_agent"
        systemctl restart onewifi
        sleep 20
        systemctl restart em_agent --no-block
        last=$now
        down=0
    fi
    sleep 5
done
SCRIPT
    cx "$c" chmod 0755 /usr/bin/lab-wired-backhaul.sh
    cx "$c" sh -c 'cat > /etc/systemd/system/lab-wired-backhaul.service' <<'UNIT'
[Unit]
Description=lab: a wired backhaul extender (eth1 in brlan0, fronthaul repaired)
After=network.target
Before=em_agent.service

[Service]
ExecStart=/usr/bin/lab-wired-backhaul.sh
Restart=always

[Install]
WantedBy=multi-user.target
UNIT
    cx "$c" sh -c 'systemctl daemon-reload; systemctl enable -q lab-wired-backhaul.service; systemctl restart lab-wired-backhaul.service'
}

up() {
    local c image
    c=$(name_of "${1:-4}")
    exists "$REFERENCE" || die "no reference extender $REFERENCE"
    exists bpibroadband || die "no controller"
    ip link show "$LAN_BRIDGE" >/dev/null 2>&1 || die "no LAN bridge $LAN_BRIDGE (emosa-lab lab.sh lanport)"
    if ! exists "$c"; then
        # a profile left from an earlier instance must not bring the LAN port with it
        if lxc profile show "$c" >/dev/null 2>&1; then
            for d in $(lxc profile device list "$c"); do
                [ "$(lxc profile device get "$c" "$d" parent 2>/dev/null)" = "$LAN_BRIDGE" ] &&
                    lxc profile device remove "$c" "$d" >/dev/null
            done
        fi
        image=$(lxc config get "$REFERENCE" user.image)
        [ -f "$image" ] || die "$REFERENCE's image $image is gone"
        (cd "$gen" && ./bpi.sh -F -i "${1:-4}" "$image") | tail -2    # no LAN port yet
    fi
    lxc config set "$c" user.easymesh.backhaul wired
    medium                                                           # isolated before any wire
    active "$c" onewifi
    cx "$c" systemctl stop onewifi 2>/dev/null    # replaced as a set, not under a running OneWifi
    match_binaries "$c"
    agent_wait "$c"
    no_sta_selfheal "$c"
    bridge_unit "$c"
    if ! lxc config device show "$c" | grep -q "parent: $LAN_BRIDGE" &&
        ! lxc config show "$c" --expanded | grep -q "parent: $LAN_BRIDGE"; then
        lxc config device add "$c" eth1 nic nictype=bridged parent="$LAN_BRIDGE" name=eth1 >/dev/null
    fi
    cx "$c" systemctl restart onewifi --no-block    # the matched binaries
    active "$c" onewifi
    sleep 20
    cx "$c" systemctl restart em_agent --no-block
    log "$c: wired to $LAN_BRIDGE; em_agent onboards over it (a few minutes). lab: $0 status"
}

down() {
    local c al
    c=$(name_of "${1:-4}")
    exists "$c" || { log "$c: not present"; return; }
    al=$(cx "$c" cat /sys/class/net/eth1_virt_peer/address 2>/dev/null || true)
    lxc delete -f "$c"
    lxc profile delete "$c" >/dev/null 2>&1 || true
    medium
    if [ -n "$al" ]; then    # its rows in the controller's model, em_ctrl stopped
        cx bpibroadband sh -ec "systemctl stop em_ctrl
            for t in PolicyList OperatingClassList BSSList RadioList DeviceList; do
                mysql -N -ubpi -proot OneWifiMesh -e \"delete from \$t where ID like '%@$al@%'\" 2>/dev/null; done
            systemctl start em_ctrl"
        log "controller model: $al removed"
    fi
    log "$c: deleted"
}

status() {
    local c
    for c in $(lxc list -c n -f csv | grep -E '^bpiap(-[0-9]{3})?$'); do
        [ "$(lxc config get "$c" user.easymesh.backhaul)" = wired ] || continue
        printf '%s: onewifi %s, em_agent %s, eth1 in %s, fronthaul BSSes %s, backhaul station %s\n' "$c" \
            "$(cx "$c" systemctl is-active onewifi 2>/dev/null)" "$(cx "$c" systemctl is-active em_agent 2>/dev/null)" \
            "$(cx "$c" sh -c 'basename "$(readlink /sys/class/net/eth1/master)"' 2>/dev/null)" \
            "$(cx "$c" sh -c 'iw dev | grep -c ssid' 2>/dev/null)" \
            "$(cx "$c" sh -c 'iw dev wifi1.3 link | head -1' 2>/dev/null)"
    done
}

case ${1:-} in
    up) up "${2:-4}" ;;
    down) down "${2:-4}" ;;
    status) status ;;
    *) sed -n '2,12p' "$0"; exit 2 ;;
esac
