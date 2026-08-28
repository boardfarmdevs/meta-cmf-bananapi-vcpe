#!/usr/bin/env bash
# Capture one comparable, read-only ready-state sample for a deployment model.
set -euo pipefail
exec </dev/null

usage() {
    echo "usage: $0 LABEL OUTPUT_DIRECTORY [SAMPLE_SECONDS]" >&2
    exit 2
}

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || usage
label=$1
output=$2
sample_seconds=${3:-30}
[[ "$sample_seconds" =~ ^[1-9][0-9]*$ ]] || usage

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
run="$output/$label/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$run"

capture() {
    local file=$1
    shift
    "$@" >"$run/$file" 2>&1 || true
}

capture_shell() {
    local file=$1 command=$2
    bash -o pipefail -c "$command" >"$run/$file" 2>&1 || true
}

{
    printf 'label=%s\n' "$label"
    printf 'captured_at=%s\n' "$(date -Ins)"
    printf 'hostname=%s\n' "$(hostname)"
    printf 'kernel=%s\n' "$(uname -r)"
    . /etc/os-release
    printf 'os=%s\n' "$PRETTY_NAME"
    printf 'source_commit=%s\n' "$(git -C "$root" rev-parse HEAD)"
    if [ -n "$(git -C "$root" status --porcelain)" ]; then
        printf 'source_clean=false\n'
    else
        printf 'source_clean=true\n'
    fi
    printf 'boot_id=%s\n' "$(cat /proc/sys/kernel/random/boot_id)"
    printf 'uptime_seconds=%s\n' "$(cut -d. -f1 /proc/uptime)"
} >"$run/metadata.env"

capture host.txt sh -c 'uname -a; lscpu; free -b; df -B1 /; cat /proc/loadavg; uptime'
capture module.txt sh -c '
    modinfo mac80211_hwsim | sed -n "/^filename:/p;/^parm:/p"
    sha256sum "$(modinfo -n mac80211_hwsim)"
    for key in radios channels regtest; do
        printf "%s=" "$key"
        cat "/sys/module/mac80211_hwsim/parameters/$key"
    done
    printf "host_hwsim_phys="
    find /sys/devices/virtual/mac80211_hwsim -mindepth 3 -maxdepth 3 \
        -type d -path "*/ieee80211/phy[0-9]*" | wc -l
'
capture lxc-list.txt lxc list -c ns4t
capture lxc-storage.txt lxc storage list
capture docker.txt sh -c 'docker ps --no-trunc; docker stats --no-stream; docker system df'
capture network.txt sh -c 'ip -br link; ip -br address; ip route; ip -6 route'
capture systemd.txt sh -c '
    systemctl is-active boardfarm-lab.service easymesh-lab.service \
        wmediumd-console.service snap.lxd.daemon.service docker.service || true
    systemctl show boardfarm-lab.service easymesh-lab.service \
        -p ActiveEnterTimestampMonotonic -p InactiveExitTimestampMonotonic \
        -p ExecMainStartTimestampMonotonic -p ExecMainExitTimestampMonotonic \
        -p CPUUsageNSec -p MemoryPeak -p NRestarts || true
    systemd-analyze time || true
    journalctl --disk-usage || true
'
capture processes.txt ps -eo user,pid,ppid,nlwp,etimes,pcpu,pmem,vsz,rss,stat,args --sort=-rss
capture slab.txt sh -c 'cat /proc/meminfo; slabtop -o -s c | head -n 40'

capture topology.json curl -fsS --max-time 30 http://127.0.0.1:8888/api/v1/topology
capture clients.json curl -fsS --max-time 30 http://127.0.0.1:8888/api/v1/clients
capture console-health.json curl -fsS --max-time 30 http://127.0.0.1:8890/api/v1/health
capture console-status.json curl -fsS --max-time 30 http://127.0.0.1:8890/api/v1/status
capture model.txt lxc exec -T -n bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
    'select count(*) DeviceList from DeviceList;
     select count(*) RadioList from RadioList;
     select count(*) BSSList from BSSList;
     select count(*) AssociatedSTA from STAList where Associated=1;'
capture restarts.txt sh -c '
    for container in bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003; do
        units="onewifi em_agent"
        [ "$container" != bpibroadband ] || units="$units em_ctrl em_cli"
        lxc exec -T -n "$container" -- sh -c '\''
            container=$1
            shift
            for unit do
                printf "%s %s=" "$container" "$unit"
                systemctl show "$unit" -p NRestarts --value
            done
        '\'' sh "$container" $units
    done
'
capture bpi-pss.txt lxc exec -T -n bpibroadband -- pss.sh
capture bpi-storage.txt lxc exec -T -n bpibroadband -- sh -c \
    'du -x -B1 -s /nvram /var/lib/mysql /rdklogs /var/log 2>/dev/null; df -B1 / /nvram'
capture medium.txt "$root/gen/wmediumd/wmediumd-up.sh" status

capture_shell lxc-state.json '
    first=1
    printf "["
    while read -r name; do
        state=$(lxc query "/1.0/instances/$name/state" 2>/dev/null || true)
        [ -n "$state" ] || continue
        [ "$first" -eq 1 ] || printf ","
        first=0
        jq -c --arg name "$name" ". + {name: \$name}" <<<"$state"
    done < <(lxc list -c n --format csv | sort)
    printf "]\n"
'

capture_shell api-latency.tsv '
    printf "endpoint\tseconds\thttp\n"
    for endpoint in topology clients devices; do
        for attempt in $(seq 1 10); do
            curl -sS -o /dev/null --max-time 30 \
                -w "$endpoint\t%{time_total}\t%{http_code}\\n" \
                "http://127.0.0.1:8888/api/v1/$endpoint" || true
        done
    done
    for attempt in $(seq 1 10); do
        curl -sS -o /dev/null --max-time 30 \
            -w "console-health\t%{time_total}\t%{http_code}\\n" \
            http://127.0.0.1:8890/api/v1/health || true
    done
'

if command -v vmstat >/dev/null 2>&1; then
    capture vmstat.txt vmstat -w 1 "$sample_seconds"
fi

health_start=$(date +%s)
set +e
timeout --signal=TERM --kill-after=5 900 \
    "$root/gen/tests/health-audit.sh" >"$run/health-audit.txt" 2>&1
health_rc=$?
set -e
health_end=$(date +%s)
{
    printf 'health_rc=%d\n' "$health_rc"
    printf 'health_elapsed_seconds=%d\n' "$((health_end - health_start))"
} >"$run/result.env"

capture final-host.txt sh -c 'free -b; cat /proc/loadavg; uptime'
capture final-processes.txt ps -eo user,pid,ppid,nlwp,etimes,pcpu,pmem,vsz,rss,stat,args --sort=-rss

printf '%s\n' "$run"
exit "$health_rc"
