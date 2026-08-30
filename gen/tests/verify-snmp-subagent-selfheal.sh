#!/bin/sh

set -eu

usage()
{
    echo "Usage: $0 ROOTFS" >&2
    exit 2
}

[ "$#" -eq 1 ] || usage

rootfs=${1%/}
health_monitor="$rootfs/usr/ccsp/tad/task_health_monitor.sh"
launcher="$rootfs/usr/ccsp/snmp/run_subagent.sh"

for script in "$health_monitor" "$launcher"; do
    [ -f "$script" ] || {
        echo "FAIL: missing $script" >&2
        exit 1
    }
    sh -n "$script"
    grep -Fq 'SNMP_PID=$(pidof snmp_subagent)' "$script" || {
        echo "FAIL: cross-user SNMP lookup missing from $script" >&2
        exit 1
    }
    if grep -E 'SNMP_PID=.*ps .*snmp_subagent' "$script" >/dev/null; then
        echo "FAIL: UID-scoped SNMP lookup remains in $script" >&2
        exit 1
    fi
done

grep -Fq 'if [ -n "$SNMP_PID" ]; then' "$launcher" || {
    echo "FAIL: launcher does not guard an empty pidof result" >&2
    exit 1
}

echo "PASS: SNMP self-heal process detection is cross-user and shell-valid"
