# The gateway's EasyMesh and OneWifi services, whatever starts them. Sourced.
#
# RDK's Banana Pi images run them as systemd units, which the lab's gates and repairs
# name: onewifi, ieee1905_em_ctrl, em_ctrl, ieee1905_em_agent, em_agent, em_cli. A
# busybox-init CPE in the gateway's place (bpi.sh -t busybox) runs the same programs
# from its init scripts. bpi.sh records that on the container: user.easymesh.cpe-init
# (busybox) and user.easymesh.cpe-service (the init script that starts the controller).
# A container without the record is a systemd one, and the callers keep their systemd
# commands for it as they were; these functions are the busybox side.

cpe_init() {    # cpe_init CT: busybox or systemd
    local init
    init=$(lxc config get "$1" user.easymesh.cpe-init 2>/dev/null || true)
    [ "$init" = busybox ] && echo busybox || echo systemd
}

cpe_busybox() { [ "$(cpe_init "$1")" = busybox ]; }

# The unit's program in the container, one line per unit: "unit pid", pid 0 when it
# is not running. ieee1905 runs twice; the controller's instance is the one on the
# controller's SAP sockets (/tmp/al_em_ctrl_*), as the units start them.
cpe_pids() {    # cpe_pids CT UNIT...
    local ct=$1
    shift
    lxc exec "$ct" -- sh -c '
        ieee() {    # ieee ctrl|agent: the ieee1905 instance PID
            for p in /proc/[0-9]*; do
                [ "$(cat "$p/comm" 2>/dev/null)" = ieee1905 ] || continue
                if tr "\0" " " < "$p/cmdline" 2>/dev/null | grep -q al_em_ctrl; then
                    [ "$1" = ctrl ] && { echo "${p#/proc/}"; return; }
                else
                    [ "$1" = agent ] && { echo "${p#/proc/}"; return; }
                fi
            done
        }
        for unit do
            case "$unit" in
                onewifi) pid=$(pidof OneWifi) ;;
                em_ctrl) pid=$(pidof onewifi_em_ctrl) ;;
                em_agent) pid=$(pidof onewifi_em_agent) ;;
                em_cli) pid=$(pidof onewifi_em_cli) ;;
                ieee1905_em_ctrl) pid=$(ieee ctrl) ;;
                ieee1905_em_agent) pid=$(ieee agent) ;;
                *) pid= ;;
            esac
            set -- $pid
            echo "$unit ${1:-0}"
        done
    ' sh "$@" < /dev/null
}

cpe_active() {    # cpe_active CT UNIT...: every unit's program running
    local ct=$1
    shift
    ! cpe_pids "$ct" "$@" | grep -q ' 0$'
}

# The container's reboot. Busybox init may not take LXD's halt signal: stopped within
# 30 s or forced, then started.
cpe_reboot() {    # cpe_reboot CT
    lxc stop "$1" --timeout 30 > /dev/null 2>&1 || lxc stop "$1" --force > /dev/null 2>&1 || true
    lxc start "$1"
}

# A restart of an EasyMesh unit is the init script's restart: it stops and starts the
# controller and the co-located agent together, in the units' order. OneWifi is not
# its: the container reboots, as its own boot starts OneWifi.
cpe_restart() {    # cpe_restart CT UNIT
    local ct=$1 service
    case "$2" in
        onewifi)
            cpe_reboot "$ct"
            ;;
        *)
            service=$(lxc config get "$ct" user.easymesh.cpe-service 2>/dev/null)
            [ -n "$service" ] || { echo "$ct: no init script recorded (user.easymesh.cpe-service)" >&2; return 1; }
            lxc exec "$ct" -- "$service" restart < /dev/null
            ;;
    esac
}

# The lab's LAN on a busybox CPE: the gateway's, as RDK's Banana Pi defaults have it
# (10.0.0.1/24, DHCP 10.0.0.2-10.0.0.253). Set as an operator sets a CPE's LAN, in its
# syscfg, then a reboot. Its first boot runs as it is (no syscfg.db is its factory
# reset), so the keys are set after it; a redeploy that kept /nvram has them already.
cpe_lan() {    # cpe_lan CT
    local ct=$1 current="" _
    for _ in $(seq 1 60); do
        current=$(lxc exec "$ct" -- syscfg get lan_ipaddr 2> /dev/null < /dev/null || true)
        [ -n "$current" ] && break
        sleep 5
    done
    [ -n "$current" ] || { echo "$ct: no syscfg after 300 s" >&2; return 1; }
    [ "$current" = 10.0.0.1 ] && return 0
    lxc exec "$ct" -- sh -ec '
        syscfg set lan_ipaddr 10.0.0.1
        syscfg set lan_netmask 255.255.255.0
        syscfg set dhcp_start 10.0.0.2
        syscfg set dhcp_end 10.0.0.253
        syscfg set dhcp_num 252
        syscfg commit' < /dev/null || return 1
    echo "$ct: LAN $current -> 10.0.0.1/24 in its syscfg; rebooting"
    cpe_reboot "$ct"
}

# A unit's log: the busybox CPE's programs write RDK's logs, /rdklogs/logs/<unit>.txt,
# capped by the image (no journal, so no time window: the whole capped file).
cpe_log() {    # cpe_log CT UNIT
    lxc exec "$1" -- sh -c 'cat "/rdklogs/logs/$1.txt" 2>/dev/null' sh "$2" < /dev/null
}

# Restarts without a restart counter: the PIDs at a known point, then whether each
# changed. cpe_pid_changes prints "unit=0" for the same PID, "unit=1" for a new one (at
# least one restart) and "unit=down" for a program not running.
cpe_pid_snapshot() {    # cpe_pid_snapshot CT FILE UNIT...
    local ct=$1 file=$2
    shift 2
    cpe_pids "$ct" "$@" > "$file"
}

cpe_pid_changes() {    # cpe_pid_changes CT FILE
    local ct=$1 file=$2 unit before now
    while read -r unit before; do
        now=$(cpe_pids "$ct" "$unit" | awk '{print $2}')
        if [ "$now" = 0 ]; then
            echo "$unit=down"
        elif [ "$now" = "$before" ]; then
            echo "$unit=0"
        else
            echo "$unit=1"
        fi
    done < "$file"
}
