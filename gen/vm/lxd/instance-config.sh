#!/usr/bin/env bash

easymesh_instance_name() {
    local candidate=${EASYMESH_LXD_NAME:-${EASYMESH_LAB_NAME:-easymesh}}
    case "$candidate" in
        [a-z0-9][a-z0-9-]*) printf '%s\n' "$candidate" ;;
        *) echo 'EasyMesh lab name must use lowercase letters, numbers and hyphens' >&2; return 2 ;;
    esac
}

easymesh_instance_storage() {
    local instance=$1
    printf '%s\n' "${EASYMESH_LXD_STORAGE:-${instance}-pool}"
}

easymesh_instance_port_base() {
    local instance=$1 hash base
    if [ -n "${EASYMESH_PORT_BASE:-}" ]; then
        base=$EASYMESH_PORT_BASE
    else
        hash=$(printf '%s' "$instance" | cksum | awk '{print $1}')
        base=$((20000 + (hash % 1000) * 10))
    fi
    case "$base" in ''|*[!0-9]*) echo 'EASYMESH_PORT_BASE must be an integer' >&2; return 2 ;; esac
    [ "$base" -ge 1024 ] && [ "$base" -le 65530 ] || {
        echo 'EASYMESH_PORT_BASE must leave six TCP ports available' >&2; return 2;
    }
    printf '%s\n' "$base"
}

easymesh_ensure_storage_pool() {
    local pool=$1 driver=${EASYMESH_LXD_STORAGE_DRIVER:-dir}
    lxc storage show "$pool" >/dev/null 2>&1 && return 0
    case "$driver" in dir|btrfs|zfs|lvm|ceph|cephfs) ;; *) echo "unsupported LXD storage driver: $driver" >&2; return 2 ;; esac
    echo "Creating LXD storage pool $pool with driver $driver"
    lxc storage create "$pool" "$driver"
}
