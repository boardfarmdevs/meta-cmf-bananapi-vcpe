#!/usr/bin/env bash
set -euo pipefail

backup=${1:?usage: import.sh EASYMESH-LXD-BACKUP.tar.zst}
name=${EASYMESH_LXD_NAME:-easymesh-lab-0829}
network=${EASYMESH_LXD_NETWORK:-lxdbr0}
cpus=${EASYMESH_LXD_CPUS:-6}
memory=${EASYMESH_LXD_MEMORY:-6GiB}
host_address=${EASYMESH_WEBUI_HOST_IP:-$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')}
host_address=${host_address:-127.0.0.1}
webui_port=${EASYMESH_WEBUI_PORT:-18889}
console_address=${WMEDIUMD_CONSOLE_HOST_IP:-$host_address}
console_port=${WMEDIUMD_CONSOLE_PORT:-18890}

command -v lxc >/dev/null 2>&1 || { echo "lxc is missing; run install-host.sh" >&2; exit 1; }
[ -c /dev/kvm ] || { echo "/dev/kvm is unavailable; enable hardware virtualization" >&2; exit 1; }
[ -r "$backup" ] || { echo "backup is not readable: $backup" >&2; exit 1; }
lxc network show "$network" >/dev/null 2>&1 || { echo "LXD network does not exist: $network" >&2; exit 1; }
if lxc info "$name" >/dev/null 2>&1; then
    echo "LXD instance already exists: $name" >&2
    echo "stop and delete it explicitly before importing a replacement" >&2
    exit 1
fi

cidr=$(lxc network get "$network" ipv4.address)
used=$(lxc network list-leases "$network" --format csv \
    | awk -F, '$3 ~ /^[0-9]+\./ {print $3}' | paste -sd, -)
guest_address=$(python3 - "$cidr" "$used" <<'PY'
import ipaddress
import sys

network = ipaddress.ip_network(sys.argv[1], strict=False)
if network.num_addresses < 16:
    raise SystemExit(f"managed bridge is too small: {network}")
used = {ipaddress.ip_address(value) for value in sys.argv[2].split(",") if value}
for offset in range(5, min(network.num_addresses - 2, 256)):
    candidate = network.broadcast_address - offset
    if candidate not in used:
        print(candidate)
        break
else:
    raise SystemExit(f"no free appliance address found near the end of {network}")
PY
)

lxc import "$backup" "$name"
lxc config set "$name" limits.cpu "$cpus"
lxc config set "$name" limits.memory "$memory"
lxc config set "$name" boot.autostart true
for device in easymesh-webui wmediumd-console; do
    if lxc config device show "$name" | grep -q "^${device}:"; then
        lxc config device remove "$name" "$device"
    fi
done
lxc config device set "$name" eth0 network "$network"
lxc config device set "$name" eth0 ipv4.address "$guest_address"
lxc config device add "$name" easymesh-webui proxy nat=true \
    listen="tcp:${host_address}:${webui_port}" \
    connect="tcp:${guest_address}:8888"
lxc config device add "$name" wmediumd-console proxy nat=true \
    listen="tcp:${console_address}:${console_port}" \
    connect="tcp:${guest_address}:8890"
lxc start "$name"

echo "LXD VM started: $name"
echo "EasyMesh WebUI:   http://${host_address}:${webui_port}/"
echo "wmediumd Console: http://${console_address}:${console_port}/"
echo "monitor: lxc exec $name -- journalctl -fu easymesh-lab.service"
echo "accept:  lxc exec $name -- /usr/local/sbin/easymesh-labctl check"
