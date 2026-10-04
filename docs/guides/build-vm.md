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

The host installer initializes LXD only if it has no pool. The VM builder creates
a separate `dir` storage pool for each lab name when it does not already exist.
That pool persists if the VM is deleted, so a rebuild of the same lab reuses its
named pool. `EASYMESH_LXD_STORAGE_DRIVER=btrfs` (or `zfs`) makes the new pool
copy-on-write, a sparse 400 GiB loop file by default (`EASYMESH_LXD_STORAGE_SIZE`):
its labs copy and snapshot in seconds (`build.sh copy`, below). LXD's snap carries
the Btrfs tools; ZFS needs the host's module.

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
| LXD pool | `demo-a-pool` |
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

`EASYMESH_EMOSA=1` on a build, or `build.sh emosa` on an accepted VM, adds
emosa-lab's OpenSync adapter to the lab: EMOSA, its fleet, the pods' gateway
(GTP) on the wired LAN port, two OpenSync pods from the pinned image
(`EMOSA_POD_IMAGE`, `.../out/mvx-pod-STAMP`), their telemetry and their Wi-Fi
backhaul, and the room service on the rooms with the pods
(`gen/medium/configurator/worlds-pods`: the standard rooms plus `pod_1`,
`pod_2`). emosa-lab owns the steps (`deploy/rdk-lab/lab.sh stage`, then `up`;
`EMOSA_LAB` names its checkout, clean at the commit `gen/vm/lxd/emosa-lab.env`
pins). It needs the wired extender. After a reboot,
`build.sh emosa` brings the pods back. `EASYMESH_EMOSA_AGENT=c` installs
emosa-lab's adapter in C (fleet, GTP and agents; no Python) instead of the Python
reference (the default); both take the same files, and `lab.sh agent POD python|c`
in the VM swaps one pod's agent later.

## A development lab

`EASYMESH_DEV_CLIENTS=20 gen/vm/lxd/build.sh build` builds a lab with 20 clients
(half private, half IoT; any even number from 10 to 98) instead of 100: quicker to
build and lighter to run, for work on the mesh, the medium and steering. It has no
room service (its unit needs the full roster), its acceptance checks the 20 and the
medium's telemetry, and `snapshot`, `export` and `export-thin` refuse it.
Qualification and every room run need the full lab.

## Faster builds: the base image, the artifact store, the records

A build starts from a **base VM image** when this host or the artifact store has
one: the stages that do not depend on the commit (`00-base.sh`,
`10-install-linux-7.sh`, `15-prepare-base.sh`, `30-boardfarm-wan.sh`: the OS and its
packages, the radio kernel, nested LXD and its client image, the patched radio
module, Boardfarm and its WAN) as an LXD image named by their inputs,
`easymesh-rdk-base-KEY`. Without one, the build makes it on the way and publishes
it (`EASYMESH_BASE_IMAGE=auto`, the default; `off` builds every stage and publishes
nothing; `rebuild` makes it anew). The commit's own part of the host,
`20-prepare-lab-host.sh`, refuses a base whose radio module was built from another
medium.

The **artifact store** (the umbrella's `docs/reference/artifact-store.md`) keeps
what is slow to build, by the inputs it was built from. With
`EASYMESH_ARTIFACT_STORE=http://HOST:8180`, `build-images.sh` fetches the Banana Pi
images whose inputs match this checkout instead of running BitBake, and a VM build
fetches the base image; `BUILD_SSTATE_MIRROR=http://HOST:8180/sstate-cache` gives a
BitBake that does run another host's sstate cache. With
`EASYMESH_ARTIFACT_PUBLISH=DIR` or `HOST:/DIR`, what is built is published.

Every build, update and copy writes a **record** to
`../build-evidence/KIND-NAME-STAMP/` (`EASYMESH_BUILD_RECORDS` moves it):
`environment.txt` (host, commit, image, kernel, sizes, storage driver, whether it
started from the base image), `phases.tsv` (each phase's start and seconds),
`summary.txt`, `exit-code` and, on failure, `failed-phase`; `latest-KIND-NAME`
links the newest. The suite's `summary.json` carries the run's and each section's
seconds.

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
[full room/soak test suite](test-suite.md). Build-time acceptance does not
replace that suite. Client expansion includes association/convergence checks,
not just container creation; cold-boot acceptance verifies reconstruction after
the final reboot. Do not shorten these gates merely to match the estimate.

## Operate, rebuild and remove

```sh
gen/vm/lxd/build.sh status
gen/vm/lxd/build.sh stop
gen/vm/lxd/build.sh start
gen/vm/lxd/build.sh check
gen/vm/lxd/build.sh update
gen/vm/lxd/build.sh delete
```

`update` moves an accepted VM to the checkout's commit in place: its checkout and
submodules (the medium, the optimizer) follow, and the room service restarts and
settles. When the commit changes what a build installs from the checkout, the update
makes and installs that too and restarts the VM, as a build's cold boot does: the
medium's daemon and console (built on the host, as a build builds them), its radio
module (built in the VM from the medium's bundle, loaded by the restart), and the
guest's services and tools (stages 30 and 50 again, with the lab's own settings).
Its record (below) says what it did. `gen/tests/affected-suites.py BASE` says which
step and which suite sections a change needs ([test suite](test-suite.md)).

`copy NEW` copies the VM in its storage pool as NEW, with its own LXD identities,
address and port block (from NEW's name, or `EASYMESH_COPY_PORT_BASE`), and leaves
it stopped; `EASYMESH_LXD_NAME=NEW gen/vm/lxd/build.sh start` starts it. A running
VM is copied through a snapshot. On a Btrfs or ZFS pool
(`EASYMESH_LXD_STORAGE_DRIVER=btrfs` for a new lab's pool, sized by
`EASYMESH_LXD_STORAGE_SIZE`, 400 GiB sparse by default) the copy takes seconds and
shares the original's blocks; on `dir` it is a full copy. A copy shares the
original's machine-id, so its first start writes its address into its netplan: two
labs on one bridge never take each other's lease. Experiment on copies; never run a
suite on two copies of one lab at the same time.

`delete` removes only the named VM. It deliberately leaves the matching storage
pool intact. To remove a lab permanently, stop/delete its VM, review the exact
pool name, then delete that pool with LXD. Never delete a pool shared by a VM.

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
