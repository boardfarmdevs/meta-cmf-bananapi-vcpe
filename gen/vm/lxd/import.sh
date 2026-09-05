#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [ -r "$script_dir/release.env" ]; then
    # shellcheck disable=SC1091
    . "$script_dir/release.env"
fi
usage() {
    if [ "${LAB_PROFILE_SELECTABLE:-false}" = true ]; then
        cat >&2 <<EOF
usage: $0 --profile 20|50|100 [EASYMESH-LXD-BACKUP.tar.zst]

The universal thin release requires one profile selection before first boot.
EOF
    else
        echo "usage: $0 [EASYMESH-LXD-BACKUP.tar.zst]" >&2
    fi
}

selected_clients=
backup=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --profile)
            [ "$#" -ge 2 ] || { usage; exit 2; }
            selected_clients=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            [ "$#" -le 1 ] || { usage; exit 2; }
            backup=${1:-}
            shift "$#"
            ;;
        -*)
            echo "unknown option: $1" >&2
            usage
            exit 2
            ;;
        *)
            [ -z "$backup" ] || { usage; exit 2; }
            backup=$1
            shift
            ;;
    esac
done

profile_selectable=${LAB_PROFILE_SELECTABLE:-false}
release_id=${LAB_RELEASE_ID:-0905}
case "$release_id" in
    [0-9][0-9][0-9][0-9]) ;;
    *) echo "invalid LAB_RELEASE_ID: $release_id" >&2; exit 2 ;;
esac
if [ "$profile_selectable" = true ]; then
    case "$selected_clients" in
        20)
            selected_profile=small
            selected_radios=32
            selected_cpus=6
            selected_memory=8GiB
            ;;
        50)
            selected_profile=medium
            selected_radios=64
            selected_cpus=8
            selected_memory=12GiB
            ;;
        100)
            selected_profile=stress
            selected_radios=128
            selected_cpus=12
            selected_memory=20GiB
            ;;
        *)
            echo "the universal thin release requires --profile 20, 50 or 100" >&2
            usage
            exit 2
            ;;
    esac
    default_name="rdkeasymesh-${selected_clients}-${release_id}"
else
    [ -z "$selected_clients" ] || {
        echo "--profile is valid only for a profile-selectable thin release" >&2
        exit 2
    }
    selected_clients=${LAB_CLIENTS:-unknown}
    selected_profile=${LAB_PROFILE:-unknown}
    selected_radios=${LAB_HWSIM_RADIOS:-unknown}
    selected_cpus=${LAB_DEFAULT_CPUS:-6}
    selected_memory=${LAB_DEFAULT_MEMORY:-8GiB}
    default_name=${LAB_DEFAULT_NAME:-rdkeasymesh-20-${release_id}}
fi

if [ -z "$backup" ]; then
    mapfile -t candidates < <(find "$script_dir" -maxdepth 1 -type f \
        -name '*.tar.zst' -printf '%p\n' | sort)
    [ "${#candidates[@]}" -eq 1 ] || {
        usage
        echo "automatic selection requires exactly one .tar.zst beside import.sh" >&2
        exit 2
    }
    backup=${candidates[0]}
fi
name=${EASYMESH_LXD_NAME:-$default_name}
network=${EASYMESH_LXD_NETWORK:-lxdbr0}
storage=${EASYMESH_LXD_STORAGE:-}
cpus=${EASYMESH_LXD_CPUS:-$selected_cpus}
memory=${EASYMESH_LXD_MEMORY:-$selected_memory}
host_address=${EASYMESH_WEBUI_HOST_IP:-$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')}
host_address=${host_address:-127.0.0.1}
webui_port=${EASYMESH_WEBUI_PORT:-18889}
console_address=${WMEDIUMD_CONSOLE_HOST_IP:-$host_address}
console_port=${WMEDIUMD_CONSOLE_PORT:-18890}
room_address=${EASYMESH_ROOM_DEMO_HOST_IP:-$host_address}
room_port=${EASYMESH_ROOM_DEMO_PORT:-18891}
address_timeout=${EASYMESH_LXD_ADDRESS_TIMEOUT:-120}
nested_ready_timeout=${EASYMESH_LXD_NESTED_READY_TIMEOUT:-$address_timeout}

case "$address_timeout" in
    ''|*[!0-9]*|0)
        echo "EASYMESH_LXD_ADDRESS_TIMEOUT must be a positive integer" >&2
        exit 2
        ;;
esac
case "$nested_ready_timeout" in
    ''|*[!0-9]*|0)
        echo "EASYMESH_LXD_NESTED_READY_TIMEOUT must be a positive integer" >&2
        exit 2
        ;;
esac

command -v lxc >/dev/null 2>&1 || { echo "lxc is missing; run install-host.sh" >&2; exit 1; }
[ -c /dev/kvm ] || { echo "/dev/kvm is unavailable; enable hardware virtualization" >&2; exit 1; }
[ -r "$backup" ] || { echo "backup is not readable: $backup" >&2; exit 1; }
lxc network show "$network" >/dev/null 2>&1 || { echo "LXD network does not exist: $network" >&2; exit 1; }
if [ -n "$storage" ]; then
    lxc storage show "$storage" >/dev/null 2>&1 || {
        echo "LXD storage pool does not exist: $storage" >&2
        exit 1
    }
fi
if lxc info "$name" >/dev/null 2>&1; then
    echo "LXD instance already exists: $name" >&2
    echo "stop and delete it explicitly before importing a replacement" >&2
    exit 1
fi

cidr=$(lxc network get "$network" ipv4.address)
gateway=${cidr%/*}
prefix=${cidr#*/}
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

import_args=(lxc import "$backup" "$name")
[ -z "$storage" ] || import_args+=(--storage "$storage")
import_args+=(
    --device "eth0,network=$network"
    --device "eth0,ipv4.address=$guest_address"
    --device "easymesh-webui,listen=tcp:$host_address:$webui_port"
    --device "easymesh-webui,connect=tcp:$guest_address:8888"
    --device "wmediumd-console,listen=tcp:$console_address:$console_port"
    --device "wmediumd-console,connect=tcp:$guest_address:8890"
    --device "room-demo-viewer,listen=tcp:$room_address:$room_port"
    --device "room-demo-viewer,connect=tcp:$guest_address:8891"
)
"${import_args[@]}"
# Device overrides must be applied atomically above: a foreign LXD server
# validates serialized static addresses and proxy listeners while creating the
# instance. An LXD backup also preserves VM firmware, vsock and NIC identities
# for disaster
# recovery.  A portable appliance import is a new instance and may coexist
# with the release-builder instance during acceptance, so reseed all
# host-visible identities before attaching it to the selected network.
instance_uuid=$(cat /proc/sys/kernel/random/uuid)
vsock_id=$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')
lxc config unset "$name" volatile.eth0.hwaddr
lxc config set "$name" volatile.uuid "$instance_uuid"
lxc config set "$name" volatile.uuid.generation "$instance_uuid"
lxc config set "$name" volatile.cloud-init.instance-id "$instance_uuid"
lxc config set "$name" volatile.vsock_id "$vsock_id"
lxc config set "$name" limits.cpu "$cpus"
lxc config set "$name" limits.memory "$memory"
# The portable backup deliberately contains no LXD-version-specific Secure
# Boot key. Select the spelling understood by this host before first boot.
if lxc config set "$name" boot.mode uefi-nosecureboot 2>/dev/null; then
    lxc config unset "$name" security.secureboot 2>/dev/null || true
else
    lxc config set "$name" security.secureboot false
fi
lxc config set "$name" boot.autostart true
for device in easymesh-webui wmediumd-console room-demo-viewer; do
    if lxc config device show "$name" | grep -q "^${device}:"; then
        lxc config device remove "$name" "$device"
    fi
done
lxc config device set "$name" eth0 network "$network"
# The portable import reseeds the NIC MAC after the instance record is
# created. Force LXD to regenerate its static DHCP host entry for that new
# MAC; assigning an unchanged address alone is treated as a no-op.
lxc config device unset "$name" eth0 ipv4.address
lxc config device set "$name" eth0 ipv4.address "$guest_address"
lxc start "$name"

# Imported VM disks can retain a DHCP lease and RFC4361 client identity from
# the build host.  A foreign LXD server may then advertise the requested
# static reservation while the guest continues using its old dynamic address,
# leaving both proxy devices pointed at a non-existent endpoint.  Reconcile
# the selected site address inside the guest over the LXD agent/vsock before
# exposing either service.
agent_ready=false
for attempt in $(seq 1 "$address_timeout"); do
    if lxc exec "$name" -- true >/dev/null 2>&1; then
        agent_ready=true
        break
    fi
    [ "$attempt" -eq "$address_timeout" ] || sleep 1
done
if [ "$agent_ready" != true ]; then
    echo "$name: LXD agent did not become ready within ${address_timeout}s" >&2
    exit 1
fi

eth0_mac=$(lxc config get "$name" volatile.eth0.hwaddr | tr '[:upper:]' '[:lower:]')
[ -n "$eth0_mac" ] || {
    echo "$name: cannot determine the final eth0 MAC" >&2
    exit 1
}
guest_interface=$(lxc exec "$name" -- sh -eu -c '
    wanted=$1
    for address_file in /sys/class/net/*/address; do
        read -r address < "$address_file"
        if [ "$address" = "$wanted" ]; then
            basename "$(dirname "$address_file")"
            exit 0
        fi
    done
    exit 1
' sh "$eth0_mac") || guest_interface=
[ -n "$guest_interface" ] || {
    echo "$name: final eth0 MAC $eth0_mac is not visible in the guest" >&2
    exit 1
}

site_network=$(mktemp /tmp/easymesh-lxd-site.XXXXXX.yaml)
trap 'rm -f -- "$site_network"' EXIT
cat > "$site_network" <<EOF
network:
  version: 2
  ethernets:
    $guest_interface:
      dhcp4: false
      accept-ra: true
      addresses:
        - $guest_address/$prefix
      routes:
        - to: default
          via: $gateway
      nameservers:
        addresses:
          - $gateway
EOF
lxc file push --mode 0600 "$site_network" \
    "$name/run/easymesh-lxd-site.yaml"
lxc exec "$name" -- install -o root -g root -m 0600 \
    /run/easymesh-lxd-site.yaml /etc/netplan/99-easymesh-lxd-site.yaml
lxc exec "$name" -- rm -f /run/easymesh-lxd-site.yaml
lxc exec "$name" -- netplan generate
lxc exec "$name" -- netplan apply

actual_address=
for attempt in $(seq 1 "$address_timeout"); do
    actual_address=$(lxc exec "$name" -- ip -4 -o address show \
        dev "$guest_interface" scope global 2>/dev/null \
        | awk '$3 == "inet" {split($4, field, "/"); print field[1]; exit}')
    [ "$actual_address" = "$guest_address" ] && break
    [ "$attempt" -eq "$address_timeout" ] || sleep 1
done
if [ "$actual_address" != "$guest_address" ]; then
    echo "$name: reserved address $guest_address was not installed" \
        "on $guest_interface within ${address_timeout}s" \
        "(actual: ${actual_address:-none})" >&2
    exit 1
fi

if [ "$profile_selectable" = true ]; then
    # The backup contains no provisioned nodes and cannot start the lab while
    # its selection marker exists.  Select and lock the roster only after the
    # VM identity and site network have been reconciled.  The outer LXD agent
    # can become reachable before the nested snap LXD daemon is ready; wait
    # for its API rather than racing the selector's first `lxc list`.  This
    # also replaces the idle builder hwsim pool with the selected
    # 32/64/128-radio pool.
    nested_ready=false
    for attempt in $(seq 1 "$nested_ready_timeout"); do
        if lxc exec "$name" -- lxc query /1.0 >/dev/null 2>&1; then
            nested_ready=true
            break
        fi
        [ "$attempt" -eq "$nested_ready_timeout" ] || sleep 1
    done
    if [ "$nested_ready" != true ]; then
        echo "$name: nested LXD did not become ready within ${nested_ready_timeout}s" >&2
        exit 1
    fi
    lxc exec "$name" -- /usr/local/sbin/easymesh-select-thin-profile \
        "$selected_clients"
    lxc exec "$name" -- grep -Fx \
        "HEALTH_EXPECT_CLIENTS=$selected_clients" \
        /var/lib/easymesh-lab/thin-profile.lock.env >/dev/null
fi

lxc config device add "$name" easymesh-webui proxy nat=true \
    listen="tcp:${host_address}:${webui_port}" \
    connect="tcp:${guest_address}:8888"
lxc config device add "$name" wmediumd-console proxy nat=true \
    listen="tcp:${console_address}:${console_port}" \
    connect="tcp:${guest_address}:8890"
lxc config device add "$name" room-demo-viewer proxy nat=true \
    listen="tcp:${room_address}:${room_port}" \
    connect="tcp:${guest_address}:8891"

if [ "$profile_selectable" = true ]; then
    # Return after starting the potentially long offline provisioning job.
    # The checksummed first-boot report and labctl gate provide completion.
    # Profile selection removes the file tested by ConditionPathExists in
    # easymesh-lab.service.  systemd can retain the earlier failed condition
    # result from boot, so reload the unit state before asking it to start.
    lxc exec "$name" -- systemctl daemon-reload
    lxc exec "$name" -- systemctl reset-failed easymesh-thin-firstboot.service \
        easymesh-lab.service
    lxc exec "$name" -- systemctl --no-block start easymesh-lab.service
fi

echo "LXD VM started: $name"
echo "site address:      $guest_interface $guest_address/$prefix via $gateway"
echo "profile:           $selected_clients clients ($selected_profile), $selected_radios radios"
echo "EasyMesh WebUI:   http://${host_address}:${webui_port}/"
echo "wmediumd Console: http://${console_address}:${console_port}/"
echo "room demo:        http://${room_address}:${room_port}/viewer/?mode=live"
echo "monitor: lxc exec $name -- journalctl -fu easymesh-lab.service"
echo "accept:  lxc exec $name -- /usr/local/sbin/easymesh-labctl check"
