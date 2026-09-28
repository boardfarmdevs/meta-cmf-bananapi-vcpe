#!/usr/bin/env bash
set -euo pipefail

# Inside the lab VM (root): bring the EasyMesh lab to a state a room suite can start from.
#
#   gen/lab-bringup.sh status   one line per gateway/extender (services, fronthaul SSIDs,
#                               backhaul), the controller's topology and model, the room
#   gen/lab-bringup.sh up       the ordered restart below, then the room settled
#   gen/lab-bringup.sh room     restart the room service (the client pool online first) and
#                               wait until the default room is settled (the suite's starting point)
#
# `up`, in the only order that works: the room service stops (it drives the medium);
# em_ctrl restarts, then the gateway's co-located agent (a controller restart forgets
# agents that registered before it). A Wi-Fi extender whose fronthaul or backhaul
# station is down (every one of them after a wmediumd restart) does not recover on its
# own: its OneWifi restarts first. Then every extender's agent restarts, and the
# controller's topology must become complete (ten BSSes per agent, five per OpenSync
# pod); some agents come back registered without their BSSes, so every agent restarts
# once more if it does not. The room service then starts and must settle.
#
# Never while a room suite runs: it restarts services the suite measures.

usage() {
    sed -n '4,10p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit 2
}

TOPOLOGY=${EASYMESH_TOPOLOGY_URL:-http://127.0.0.1:8888/api/v1/topology}
ROOM=${EASYMESH_ROOM_URL:-http://127.0.0.1:8891}
ROOM_UNIT=easymesh-room-demo.service

log() { printf '[lab-bringup %s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf '[lab-bringup] %s\n' "$*" >&2; exit 1; }
cx() {
    local container=$1
    shift
    timeout --signal=TERM --kill-after=2 60 lxc exec -T -n "$container" -- sh -c "$*"
}

extenders() { lxc list -c n -f csv | grep -E '^bpiap(-[0-9]{3})?$' || true; }
wired() { [ "$(lxc config get "$1" user.easymesh.backhaul)" = wired ]; }
ssids() { cx "$1" "iw dev | grep -c ssid || true" 2>/dev/null || echo 0; }
station() { cx "$1" "iw dev wifi1.3 link 2>/dev/null | head -1" 2>/dev/null || true; }

active() {    # wait (up to 10 min) for a unit in a container
    local container=$1 unit=$2 i
    for i in $(seq 120); do
        [ "$(cx "$container" "systemctl is-active $unit" 2>/dev/null)" = active ] && return 0
        sleep 5
    done
    die "$container: $unit is not active"
}

# One complete agent per gateway and extender container (ten BSSes each), and every
# OpenSync pod with its five.
topology_complete() {
    curl -fsS --max-time 5 "$TOPOLOGY" 2>/dev/null | EXPECTED=$1 python3 -c '
import json, os, sys
nodes = json.load(sys.stdin).get("nodes", [])
bss = lambda n: sum(len(h.get("BSSList") or []) for h in (n.get("haulTypes") or []))
pods = [n for n in nodes if n.get("kind") == "opensync-pod"]
agents = [n for n in nodes if n.get("kind") != "controller" and n not in pods]
sys.exit(0 if len(agents) == int(os.environ["EXPECTED"]) and all(bss(n) == 10 for n in agents)
         and all(bss(n) == 5 for n in pods) else 1)' 2>/dev/null
}

wait_topology() {
    local expected=$1 i
    for i in $(seq 36); do
        topology_complete "$expected" && return 0
        sleep 5
    done
    return 1
}

restart_agents() {
    local container
    cx bpibroadband "systemctl restart em_agent"
    sleep 20
    for container in $(extenders); do cx "$container" "systemctl restart em_agent --no-block"; done
}

up() {
    local container expected recovered=
    lxc info bpibroadband >/dev/null 2>&1 || die "no gateway container bpibroadband"
    expected=$(( $(extenders | grep -c .) + 1 ))
    systemctl stop "$ROOM_UNIT" 2>/dev/null || true
    for container in $(extenders); do
        wired "$container" && continue
        if [ "$(ssids "$container")" -eq 0 ] || ! station "$container" | grep -q '^Connected'; then
            log "$container: fronthaul or backhaul station down, restarting OneWifi"
            cx "$container" "systemctl restart onewifi --no-block"
            recovered="$recovered $container"
        fi
    done
    for container in $recovered; do active "$container" onewifi; done
    [ -z "$recovered" ] || sleep 20
    log "restarting em_ctrl, the gateway's agent, then the extenders' agents"
    cx bpibroadband "systemctl restart em_ctrl"
    sleep 20
    restart_agents
    if ! wait_topology "$expected"; then
        log "topology incomplete: restarting every agent once more"
        restart_agents
        wait_topology "$expected" || die "controller topology incomplete after two agent restarts (lab-bringup.sh status)"
    fi
    log "topology complete: $expected agents"
    room
}

# The suite's starting point: the default room healthy, paused at time zero, all twenty
# clients online, measured and converged.
room_settled() {
    curl -fsS --max-time 5 "$ROOM/api/demo/current" 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin); h = d.get("health", {}); f = (d.get("optimizer") or {}).get("fleet") or {}
ok = (h.get("healthy") and h.get("api_total") == 20 and h.get("expected_online_clients") == 20
      and f.get("converged") and f.get("measurement_complete") and f.get("clients_checked") == 20)
print("settled" if ok else "waiting", d.get("scenario"), h.get("api_total"), f.get("clients_checked"), f.get("converged"))
sys.exit(0 if ok else 1)' 2>/dev/null
}

# The interactive room's baseline is the whole client pool online: it pauses the clients a world
# leaves dormant itself, and resumes them when its session ends. Its preflight counts all of them,
# so a client left disconnected (by hand, or by an interrupted session) keeps it from starting.
pool_online() {
    local c n=0
    for c in $(lxc list -c n -f csv | grep -E '^wlan-client(-[0-9]{3})?$'); do
        [ "$(cx "$c" "wpa_cli -i wlan0 status | sed -n 's/^wpa_state=//p'" 2>/dev/null)" = COMPLETED ] && continue
        cx "$c" "wpa_cli -i wlan0 reconnect" >/dev/null 2>&1 || true
        n=$((n + 1))
    done
    [ "$n" -eq 0 ] || { log "reconnected $n pool clients (the room's baseline is every client online)"; sleep 30; }
}

room() {
    local i state=
    systemctl stop "$ROOM_UNIT" 2>/dev/null || true
    pool_online
    systemctl reset-failed "$ROOM_UNIT" 2>/dev/null || true
    systemctl start "$ROOM_UNIT"
    for i in $(seq 120); do
        state=$(room_settled) && { log "room $state"; return 0; }
        if [ "$(systemctl is-active "$ROOM_UNIT")" = failed ]; then
            die "room service failed: $(journalctl -u "$ROOM_UNIT" -n 40 --no-pager -q | grep -o 'session failed: .*' | tail -1)"
        fi
        sleep 5
    done
    die "room not settled after 10 min: ${state:-no answer} (journalctl -u $ROOM_UNIT)"
}

status() {
    local container kind
    for container in bpibroadband $(extenders); do
        kind=wifi
        [ "$container" = bpibroadband ] && kind=gateway
        wired "$container" && kind=wired
        printf '%-13s %-7s onewifi=%-8s em_agent=%-8s ssids=%-2s backhaul=%s\n' "$container" "$kind" \
            "$(cx "$container" "systemctl is-active onewifi" 2>/dev/null || true)" \
            "$(cx "$container" "systemctl is-active em_agent" 2>/dev/null || true)" \
            "$(ssids "$container")" \
            "$( [ "$kind" = wifi ] && station "$container" || echo -)"
    done
    printf 'em_ctrl=%s topology: ' "$(cx bpibroadband "systemctl is-active em_ctrl" 2>/dev/null || true)"
    curl -fsS --max-time 5 "$TOPOLOGY" 2>/dev/null | python3 -c '
import json, sys
nodes = json.load(sys.stdin).get("nodes", [])
bss = lambda n: sum(len(h.get("BSSList") or []) for h in (n.get("haulTypes") or []))
print(" ".join("%s:%d" % (n.get("name"), bss(n)) for n in nodes if n.get("kind") != "controller"))' 2>/dev/null || echo unavailable
    printf 'model (devices radios bsses associated): %s\n' "$(cx bpibroadband "mysql -N -ubpi -proot OneWifiMesh -e \
        'select (select count(*) from DeviceList),(select count(*) from RadioList),(select count(*) from BSSList),(select count(*) from STAList where Associated=1)' 2>/dev/null" | tr '\t' ' ')"
    printf 'room: %s %s\n' "$(systemctl is-active "$ROOM_UNIT" || true)" "$(room_settled || true)"
}

[ $# -eq 1 ] || usage
case $1 in
    status) status ;;
    up) up ;;
    room) room ;;
    *) usage ;;
esac
