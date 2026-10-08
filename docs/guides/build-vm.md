# Build a named LXD VM

[Documents](../README.md)

Build the BPI images first. This stage consumes their verified paths and creates
one independent EasyMesh appliance; it does not run BitBake.

## Prepare LXD

On the Ubuntu 22.04 build host, from the layer checkout:

```sh
sudo gen/vm/lxd/install-host.sh
newgrp lxd
test -c /dev/kvm
```

The host installer initializes LXD only if it has no pool. The VM builder puts every
lab in the host's one ZFS pool for lab VMs, `labs`, and creates it when it does not
exist (a sparse 500 GiB loop file, `EASYMESH_LXD_STORAGE_SIZE`; compression on):
snapshots and copies are copy-on-write and take seconds, and a lab and its copies share
blocks (easymesh-resources lab-storage). `EASYMESH_LXD_STORAGE=<lab>-pool
EASYMESH_LXD_STORAGE_DRIVER=dir` gives a lab a `dir` pool of its own, as before; a lab
already built stays in the pool it is in ([build speed](../reference/build-speed.md)).

The lab's room evidence (`/home/easymesh/easymesh-evidence`) is on a volume of its own
in that pool, `<lab>-evidence` (20 GiB, `EASYMESH_EVIDENCE_SIZE`; `0` for none), so the
VM's disk holds none; an hourly timer in the VM keeps it under 80 %. The volume outlives
the VM: a rebuild under the same name attaches it again, `copy` gives the copy a copy
of it, an export carries none, and `build.sh evidence` puts a lab built before it on one,
without a restart (between suites).

## Choose a lab name

Source the configuration helper once per shell. It derives a VM name, storage
pool and a six-port block from the name. This makes concurrent labs independent
without editing scripts or hardcoding host addresses.

```sh
cd "$HOME/yocto/easymesh-bpi/meta-cmf-bananapi-vcpe"
source gen/build/lab-config.sh demo-a
```

For `demo-a`, the helper exports:

| Setting | Value |
| --- | --- |
| VM | `demo-a` |
| LXD pool | `labs` (the host's, shared by its labs) |
| topology WebUI | `EASYMESH_WEBUI_PORT` |
| wmediumd Console | `WMEDIUMD_CONSOLE_PORT` |
| room viewer | `EASYMESH_ROOM_DEMO_PORT` |
| LXD UI / Grafana / outer metrics | the next three ports |

The printed port range is deterministic for the lab name. If a site requires a
chosen range, set `EASYMESH_PORT_BASE` before sourcing the helper. Names must be
lowercase letters, digits and hyphens. Give every concurrent VM its own name;
never reuse another VM's pool or ports.

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
The builder prints the three HTTP URLs. Monitoring takes the VM's own ports:

```sh
host_ip=$(ip -4 route get 1.1.1.1 | awk '{for (i=1;i<=NF;i++) if ($i == "src") {print $(i+1); exit}}')
LAB_MONITORING_ALLOW_RESTART=1 \
  gen/vm/lxd/monitoring.sh enable "$EASYMESH_LXD_NAME" "$host_ip"
```

## The wired extender

Next to the gateway and its four Wi-Fi extenders, every new VM has one extender
on a wired backhaul (`EASYMESH_WIRED_EXTENDERS=1`, the default; `0` builds the
Wi-Fi extenders only). It is the extender image as `bpiap-004`, its LAN port
bridged into the controller's LAN through the lab's wired LAN port (`br-wired`,
a port `eth2` of `bpibroadband`'s `brlan0`), made by `gen/wired-extender.sh`
(`lanport`, `up 4`, `status`, `down 4`):

- Its HAL never connects its backhaul station (rdk-wifi-hal 0045, flag
  `/nvram/lab_wired_backhaul`), so it can never make a second path into the
  LAN, and its backhaul BSSs stay open to Wi-Fi extenders that take it as their
  parent. `wired-extender.sh` records that as `user.easymesh.wired_guard=hal`;
  only then does the medium give it RF to the other mesh nodes. An extender
  image without the patch keeps it isolated on the medium. Its unit brings up
  its 5 GHz backhaul BSS, which OneWifi never starts on its own there, and
  gives its `brlan0` an address from the gateway.
- The runtime starts it with the Wi-Fi extenders and checks it once the medium
  runs: its fronthaul up, its ten BSSes in the controller's model, its LAN port
  in its `brlan0`, the gateway's `eth2` in the gateway's `brlan0`, no station up.
  The controller's model then counts six devices (18 radios, 60 BSSes) and one
  association fewer than devices, clients plus the four Wi-Fi extenders.
- The health audit wants it as an Ethernet child of the controller in the
  topology and never a Wi-Fi child.
- The room service runs the lab's own rooms with it
  (`gen/medium/configurator/worlds-wired`: the 27 rooms, the wired extender
  as `extender_5`, plus four rooms about it); the room suite takes that set from
  the room.

## The EMOSA option

`EASYMESH_EMOSA=1` on a build, or `build.sh emosa` on an accepted VM, adds emosa-lab's
OpenSync adapter: two OpenSync pods from the pinned image (`EMOSA_POD_IMAGE`,
`.../out/mvx-pod-STAMP`), their Wi-Fi backhaul and the rooms with the pods
(`gen/medium/configurator/worlds-pods`). With `EASYMESH_EMOSA_IN=gateway`, the target
configuration, EMOSA (its fleet, one agent per pod, the pods' gateway GTP) runs in the
gateway from the controller image's own package (`BUILD_EMOSA=1`, checked before the
build), its state on `/nvram`; without it, in containers of its own on the wired LAN port.
emosa-lab owns the steps (`deploy/rdk-lab/lab.sh`; its `docs/concepts/rdk-lab.md`);
`EMOSA_LAB` names its checkout, clean at the commit `gen/vm/lxd/emosa-lab.env` pins. It
needs the wired extender. After a stop, `build.sh start` brings the pods back too.
`EASYMESH_EMOSA_AGENT=c` installs a container adapter in C instead of the Python reference.

## Build time

A fresh lab takes about an hour on rev140; with the EMOSA option in the gateway about 90
minutes, its acceptance included. A base VM image takes about 20 minutes off a build. The
build log names each phase; the timing records and the ways to a shorter build are in
[build speed](../reference/build-speed.md). The build's acceptance does not replace the
[full room/soak test suite](test-suite.md), and its gates are not shortened to match an
estimate.

## Operate, rebuild and remove

```sh
gen/vm/lxd/build.sh status
gen/vm/lxd/build.sh stop
gen/vm/lxd/build.sh start
gen/vm/lxd/build.sh check
gen/vm/lxd/build.sh update
gen/vm/lxd/build.sh delete
```

`update` moves an accepted VM to the checkout's commit in place; base images,
copies, the artifact store and timing records: [build speed](../reference/build-speed.md).

`delete` removes only the named VM: the pool and the lab's evidence volume stay. To
remove a lab permanently, delete its VM, then its evidence (`lxc storage volume delete
labs <lab>-evidence`) and, for a lab with a pool of its own, review the exact pool name
and delete that pool with LXD. Never delete a pool a VM uses.

New images in a running lab (the Banana Pi images built again, the VM kept): copy
both into the VM's `/home/easymesh/easymesh-assets` and, as root in the VM, run

```sh
gen/lab-redeploy.sh X86EMLTRBPIBB_rdk-next_<stamp>.rootfs.lxc.tar.bz2 X86EMLTRBPIAP_rdk-next_<stamp>.rootfs.lxc.tar.bz2
```

It deploys the gateway and every extender again, each keeping its identity (its
nvram), restores em_cli, a wired LAN port and a wired extender where the lab has
them, then brings the lab up with `gen/lab-bringup.sh up`. Never while a room suite
runs.

For a portable appliance, use `export-thin` only after the appropriate VM test
tier passes. The exported bundle can be imported under another lab name by
sourcing `lab-config.sh` before running its `import.sh`; the importer follows
the same named-pool and port-default rules.
