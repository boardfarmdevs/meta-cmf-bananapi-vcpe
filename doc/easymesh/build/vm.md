# Build a named LXD VM

Build the BPI images first. This stage consumes their verified paths and creates
one independent EasyMesh appliance; it does not run BitBake.

## Prepare LXD

On the Ubuntu 22.04 build host, from the layer checkout:

```sh
sudo gen/vm/lxd/install-host.sh
newgrp lxd
test -c /dev/kvm
```

The host installer initializes LXD only if it has no pool. The VM builder creates
a separate `dir` storage pool for each lab name when it does not already exist.
That pool persists if the VM is deleted, so a rebuild of the same lab reuses its
named pool. Set `EASYMESH_LXD_STORAGE_DRIVER` only when a non-`dir` LXD backend
is intentionally required.

## Choose a lab name

Source the configuration helper once per shell. It derives a VM name, storage
pool and a six-port block from the name. This makes concurrent labs independent
without editing scripts or hardcoding host addresses.

```sh
cd "$HOME/yocto/easymesh-bpi/meta-cmf-bananapi-vcpe"
source doc/easymesh/build/scripts/lab-config.sh demo-a
```

For `demo-a`, the helper exports:

| Setting | Value |
| --- | --- |
| VM | `demo-a` |
| LXD pool | `demo-a-pool` |
| topology WebUI | `EASYMESH_WEBUI_PORT` |
| wmediumd Console | `WMEDIUMD_CONSOLE_PORT` |
| room viewer | `EASYMESH_ROOM_DEMO_PORT` |
| LXD UI / Grafana / outer metrics | the next three ports |

The printed port range is deterministic for the lab name. If a site requires a
chosen range, set `EASYMESH_PORT_BASE` before sourcing the helper. Names must be
lowercase letters, digits and hyphens. Use a different name for every concurrent
VM; do not manually reuse one VM's pool or port values for another VM.

## Build and start

Give the builder the two images recorded by the BPI build. It creates the named
pool if needed, creates the VM, assigns a free bridge address, installs only
commit-bounded source/assets, provisions the fixed client capacity and starts
the lab.

Every new VM includes **wmediumd Console NG**, its updated daemon telemetry,
the room observer endpoint and survey bridge. No separate Go/Node install is
needed in the VM. The final build gate checks NG telemetry and matching room
and survey sources, not just whether a web page answers. The console uses the
same named port; its header includes the manual and RF property field guide.

Fresh appliances use a Btrfs-backed nested LXD pool, so the 100 client roots
are copy-on-write clones of the prepared client image. Use eight bounded client
workers for a faster first build; final association and convergence gates remain
unchanged. Set `EASYMESH_NESTED_LXD_STORAGE_DRIVER=dir` or
`CLIENT_CREATE_PARALLELISM=1` only for compatibility diagnosis.

Workers share one short-lived hwsim allocation session. It inventories existing
profile radio assignments once, reserves new radios under the allocator lock,
then lets container creation and readiness continue in parallel. The build log
reports the client-provisioning duration for direct build-to-build comparison.

```sh
controller=$(find "$HOME/yocto/easymesh-bpi/build-qemux86bpibroadband/tmp/deploy/images" \
  -name '*.rootfs.lxc.tar.bz2' -type f | head -n 1)
extender=$(find "$HOME/yocto/easymesh-bpi/build-qemux86bpiap/tmp/deploy/images" \
  -name '*.rootfs.lxc.tar.bz2' -type f | head -n 1)
test -n "$controller" && test -n "$extender"
CLIENT_CREATE_PARALLELISM=8 \
EASYMESH_CONTROLLER_IMAGE="$controller" EASYMESH_EXTENDER_IMAGE="$extender" \
  gen/vm/lxd/build.sh build
```

The default outer address is the source address of the host's default route.
Set `EASYMESH_WEBUI_HOST_IP` only if the host has multiple usable interfaces.
The builder prints the three HTTP URLs. Monitoring can use the ports exported by
`lab-config.sh`:

```sh
host_ip=$(ip -4 route get 1.1.1.1 | awk '{for (i=1;i<=NF;i++) if ($i == "src") {print $(i+1); exit}}')
LAB_MONITORING_ALLOW_RESTART=1 \
  gen/vm/lxd/observability/enable.sh "$EASYMESH_LXD_NAME" "$host_ip"
```

## Estimated build phases and time

Use **about 55 minutes** as a planning reference for a fresh 100-client VM
with Btrfs-backed nested storage and eight client-creation workers. The example
below was reconstructed from provisioning markers and service logs, from VM
creation through final readiness. These are observed phase durations, not
timeouts or guaranteed performance; CPU, storage, download speeds, caches and
competing workloads affect the result.

| Phase | Example duration |
| --- | ---: |
| VM creation, input upload and base OS | 2m 23s |
| Kernel installation and first reboot | 1m 05s |
| Nested LXD/hwsim preparation and second reboot | 2m 38s |
| Boardfarm/WAN setup | 9m 08s |
| Initial mesh deployment and first five clients | 10m 10s |
| Additional extenders and expansion to 100 clients | 13m 55s |
| Runtime/Console installation, final reboot and WAN readiness | 2m 11s |
| Cold-boot reconstruction and acceptance | 11m 45s |
| Final audit, room startup and readiness | 1m 35s |
| **Measured total** | **54m 50s** |

The total excludes the separate BPI image builds, host-side asset preparation
before VM creation, optional monitoring setup, and the subsequent
[full room/soak test suite](../test/README.md). Build-time acceptance does not
replace that suite. Client expansion includes association/convergence checks,
not just container creation; cold-boot acceptance verifies reconstruction after
the final reboot. Do not shorten these gates merely to match the estimate.

## Operate, rebuild and remove

```sh
gen/vm/lxd/build.sh status
gen/vm/lxd/build.sh stop
gen/vm/lxd/build.sh start
gen/vm/lxd/build.sh check
gen/vm/lxd/build.sh delete
```

`delete` removes only the named VM. It deliberately leaves the matching storage
pool intact. To remove a lab permanently, stop/delete its VM, review the exact
pool name, then delete that pool with LXD. Never delete a pool shared by a VM.

For a portable appliance, use `export-thin` only after the appropriate VM test
tier passes. The exported bundle can be imported under another lab name by
sourcing `lab-config.sh` before running its `import.sh`; the importer follows
the same named-pool and port-default rules.
