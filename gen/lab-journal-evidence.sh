#!/usr/bin/env bash
set -euo pipefail

# Inside the lab VM: journal evidence mode for the gateway and the extenders.
#
# The images bound the EasyMesh daemons' journal output: em_ctrl and em_agent
# may write 1000 lines per 30 s each into a 16 MB volatile journal. Under room
# load em_ctrl writes about 700 lines per second, so journald drops most of
# them ("Suppressed N messages") and a failed room cannot be read afterwards.
#
# `on` lifts the two units' rate limits and allows a 256 MB volatile journal
# per extender and 96 MB on the gateway (about 9 minutes of em_ctrl under
# load): the journal lives in /run, which counts against the container's
# 1 GiB memory limit, and the gateway's daemons take 450 to 700 MB of it. With
# 256 MB there it reached the limit and thrashed (VM load 100, every lxc exec
# and wpa_cli timing out). `off` removes both
# and returns to the image's bounds. The settings are drop-ins in each
# container's /etc, so they survive a container restart. A unit's rate limit
# takes effect when it starts: both commands stop the room service, restart
# em_ctrl and then every em_agent (the controller first, or it forgets agents
# that registered before it restarted), wait until the controller's topology
# is complete again and start the room service. Run them with no room test
# active; the room then settles on its own.

usage() {
    echo "usage: gen/lab-journal-evidence.sh on|off|status" >&2
    exit 2
}

(($# == 1)) || usage
action=$1
case $action in on|off|status) ;; *) usage ;; esac

name=zz-lab-journal-evidence.conf
units=(em_ctrl em_agent)

containers() {
    lxc list -c n -f csv | grep -E '^(bpibroadband|bpiap(-[0-9]{3})?)$'
}

in_container() {
    local container=$1
    shift
    timeout --signal=TERM --kill-after=2 60 lxc exec -T -n "$container" -- sh -c "$*"
}

apply() {
    local container=$1 unit journal=256M
    [[ $container == bpibroadband ]] && journal=96M
    in_container "$container" "mkdir -p /etc/systemd/journald.conf.d && printf '%s\n' '[Journal]' \
        'RuntimeMaxUse=$journal' 'RuntimeMaxFileSize=16M' > /etc/systemd/journald.conf.d/$name"
    for unit in "${units[@]}"; do
        in_container "$container" "[ -f /lib/systemd/system/$unit.service ] || exit 0
            mkdir -p /etc/systemd/system/$unit.service.d
            printf '%s\n' '[Service]' 'LogRateLimitIntervalSec=0' 'LogRateLimitBurst=0' \
                > /etc/systemd/system/$unit.service.d/$name"
    done
}

remove() {
    local container=$1 unit
    in_container "$container" "rm -f /etc/systemd/journald.conf.d/$name"
    for unit in "${units[@]}"; do
        in_container "$container" "rm -f /etc/systemd/system/$unit.service.d/$name"
    done
}

restart() {
    local container=$1 unit
    in_container "$container" "systemctl daemon-reload && systemctl restart systemd-journald"
    for unit in "${units[@]}"; do
        # --no-block: em_agent's start waits for a backhaul (up to 5 min), longer than
        # in_container allows; wait_topology waits for the result
        in_container "$container" "! systemctl cat $unit.service >/dev/null 2>&1 || systemctl restart --no-block $unit.service"
    done
}

# One complete agent per gateway and extender container (ten BSSes each), and
# every OpenSync pod with its five.
topology_complete() {
    curl -fsS --max-time 5 http://127.0.0.1:8888/api/v1/topology 2>/dev/null | EXPECTED=${#targets[@]} python3 -c '
import json, os, sys
nodes = json.load(sys.stdin).get("nodes", [])
bss = lambda n: sum(len(h.get("BSSList") or []) for h in (n.get("haulTypes") or []))
pods = [n for n in nodes if str(n.get("name", "")).startswith("Pod-")]
agents = [n for n in nodes if n.get("name") != "Controller" and n not in pods]
sys.exit(0 if len(agents) == int(os.environ["EXPECTED"]) and all(bss(n) == 10 for n in agents)
         and all(bss(n) == 5 for n in pods) else 1)'
}

wait_topology() {
    local i
    for i in $(seq 36); do
        topology_complete && return 0
        sleep 5
    done
    return 1
}

# After a controller restart some agents come back registered without their
# BSSes (named Agent-N). Restarting every agent once, controller up, fixes it.
settle_topology() {
    local container
    wait_topology && return 0
    for container in "${targets[@]}"; do
        in_container "$container" "systemctl restart --no-block em_agent.service"
        sleep 3
    done
    wait_topology && return 0
    echo "lab-journal-evidence.sh: controller topology incomplete after agent restarts" >&2
    return 1
}

status() {
    local container=$1
    in_container "$container" "printf '%-13s ' $container
        for unit in ${units[*]}; do
            systemctl cat \$unit.service >/dev/null 2>&1 || continue
            printf '%s=%s/%s ' \$unit \$(systemctl show \$unit -p LogRateLimitIntervalUSec --value) \
                \$(systemctl show \$unit -p LogRateLimitBurst --value)
        done
        printf 'journal=%s suppressed_5min=%s\n' \
            \"\$(journalctl --disk-usage | grep -oE '[0-9.]+[KMG]')\" \
            \"\$(journalctl -u systemd-journald --since -5min -o cat | grep -c Suppressed || true)\""
}

# The gateway (controller) first, then the extenders.
mapfile -t targets < <(containers | sort -r)
((${#targets[@]})) || { echo "lab-journal-evidence.sh: no gateway or extender containers" >&2; exit 1; }
[[ ${targets[0]} == bpibroadband ]] || { echo "lab-journal-evidence.sh: no gateway container" >&2; exit 1; }
if [[ $action != status ]]; then
    systemctl stop easymesh-room-service.service 2>/dev/null || true
    for container in "${targets[@]}"; do
        if [[ $action == on ]]; then apply "$container"; else remove "$container"; fi
        restart "$container"
        [[ $container == bpibroadband ]] && sleep 20
    done
    settle_topology
    systemctl reset-failed easymesh-room-service.service 2>/dev/null || true
    systemctl start easymesh-room-service.service
fi
for container in "${targets[@]}"; do status "$container"; done
