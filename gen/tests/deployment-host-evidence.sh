#!/usr/bin/env bash
# Capture the physical-host side of a deployment-model measurement.
set -euo pipefail
exec </dev/null

[ "$#" -ge 2 ] && [ "$#" -le 3 ] || {
    echo "usage: $0 LABEL OUTPUT_DIRECTORY [SAMPLE_SECONDS]" >&2
    exit 2
}
label=$1
output=$2
sample_seconds=${3:-30}
[[ "$sample_seconds" =~ ^[1-9][0-9]*$ ]] || exit 2

run="$output/$label/host-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$run"

{
    printf 'label=%s\n' "$label"
    printf 'captured_at=%s\n' "$(date -Ins)"
    printf 'hostname=%s\n' "$(hostname)"
    printf 'kernel=%s\n' "$(uname -r)"
    . /etc/os-release
    printf 'os=%s\n' "$PRETTY_NAME"
    printf 'boot_id=%s\n' "$(cat /proc/sys/kernel/random/boot_id)"
} >"$run/metadata.env"

{
    uname -a
    lscpu
    free -b
    df -B1 /
    cat /proc/loadavg
    uptime
} >"$run/system.txt" 2>&1

ps -eo user,pid,ppid,nlwp,etimes,pcpu,pmem,vsz,rss,stat,args --sort=-rss \
    >"$run/processes.txt" 2>&1

{
    pgrep -a -f 'qemu-system' || true
    for pid in $(pgrep -f 'qemu-system' || true); do
        printf '\nPID %s\n' "$pid"
        grep -E '^(Name|State|Threads|VmPeak|VmSize|VmHWM|VmRSS|RssAnon|RssFile|RssShmem|VmSwap):' \
            "/proc/$pid/status" 2>/dev/null || true
        cat "/proc/$pid/io" 2>/dev/null || true
    done
} >"$run/hypervisor-processes.txt" 2>&1

if command -v sensors >/dev/null 2>&1; then
    sensors >"$run/temperatures.txt" 2>&1 || true
fi
if command -v vmstat >/dev/null 2>&1; then
    vmstat -w 1 "$sample_seconds" >"$run/vmstat.txt" 2>&1 || true
fi
if command -v lxc >/dev/null 2>&1; then
    lxc list -c nst4m >"$run/lxc-list.txt" 2>&1 || true
fi
printf '%s\n' "$run"
