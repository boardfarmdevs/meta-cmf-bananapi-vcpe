#!/usr/bin/env bash

easymesh_instance_name() {
    local candidate=${EASYMESH_LXD_NAME:-${EASYMESH_LAB_NAME:-easymesh}}
    case "$candidate" in
        [a-z0-9][a-z0-9-]*) printf '%s\n' "$candidate" ;;
        *) echo 'EasyMesh lab name must use lowercase letters, numbers and hyphens' >&2; return 2 ;;
    esac
}

# The host's one ZFS pool for its lab VMs, labs (easymesh-resources lab-storage W1, W2):
# snapshots and copies copy-on-write, blocks compressed, a lab and its copies sharing
# blocks. EASYMESH_LXD_STORAGE=<lab>-pool EASYMESH_LXD_STORAGE_DRIVER=dir is the old pool
# of a lab's own; an existing lab's commands use the pool it is in (build.sh storage_pool).
easymesh_instance_storage() {
    printf '%s\n' "${EASYMESH_LXD_STORAGE:-labs}"
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

# The room evidence on a volume of its own (easymesh-resources lab-storage W4): LAB-evidence in
# the lab's pool, mounted in the guest (virtiofs) at its evidence directory. Its quota bounds it
# and the guest's hourly retention keeps it under 80 %. It outlives its lab: a rebuild or a new
# import under the same name gets the evidence back. EASYMESH_EVIDENCE_SIZE=0: no volume, the
# evidence on the VM's disk as before. A copy of a lab gets a copy of the volume; an export
# carries none (LXD refuses to import a backup with a custom volume attached).
easymesh_evidence_path=/home/easymesh/easymesh-evidence

easymesh_attach_evidence() {    # easymesh_attach_evidence INSTANCE POOL: the volume, made if new
    local instance=$1 pool=$2 volume=$1-evidence size=${EASYMESH_EVIDENCE_SIZE:-20GiB}
    local -a create=(lxc storage volume create "$pool" "$volume")
    [ "$size" != 0 ] || return 0
    ! lxc config device get "$instance" evidence source >/dev/null 2>&1 || return 0
    if ! lxc storage volume show "$pool" "$volume" >/dev/null 2>&1; then
        # a dir pool has no quotas on most hosts: there the retention's own cap bounds it
        lxc storage show "$pool" | awk '$1 == "driver:" {print $2}' | grep -qx dir \
            || create+=(size="$size")
        "${create[@]}" </dev/null
    fi
    lxc config device add "$instance" evidence disk pool="$pool" source="$volume" \
        path="$easymesh_evidence_path" </dev/null
}

easymesh_ensure_storage_pool() {
    local pool=$1 driver=${EASYMESH_LXD_STORAGE_DRIVER:-zfs}
    local size=${EASYMESH_LXD_STORAGE_SIZE:-500GiB}
    lxc storage show "$pool" >/dev/null 2>&1 && return 0
    case "$driver" in dir|btrfs|zfs|lvm|ceph|cephfs) ;; *) echo "unsupported LXD storage driver: $driver" >&2; return 2 ;; esac
    echo "Creating LXD storage pool $pool with driver $driver"
    case "$driver" in
        # A copy-on-write pool on a loop file: LXD's automatic size (at most 30 GiB) is
        # smaller than one lab's disk. The file is sparse; copies of a lab share its blocks.
        btrfs|zfs) lxc storage create "$pool" "$driver" size="$size" ;;
        *) lxc storage create "$pool" "$driver" ;;
    esac
}
