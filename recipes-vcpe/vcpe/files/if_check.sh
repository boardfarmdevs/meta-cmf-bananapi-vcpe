#!/bin/sh
# vCPE: rename eth0 -> erouter0 so RdkWanManager finds the WAN interface.

if ip link show erouter0 >/dev/null 2>&1; then
    exit 0
fi

if ip link show eth0 >/dev/null 2>&1; then
    ifconfig eth0 down
    ip link set dev eth0 name erouter0
    ifconfig erouter0 up
fi

exit 0
