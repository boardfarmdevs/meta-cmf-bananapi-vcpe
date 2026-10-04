# Build speed: updates, copies, the base image, the artifact store, the records

[Documents](../README.md) · [Build a named LXD VM](../guides/build-vm.md)

What makes a lab VM cheaper to build, to try things on and to requalify, from the labs'
faster, cheaper labs proposal (in [easymesh-labs](https://mesh.vcpe.dev/)). The prplMesh
lab has the same mechanisms under the same names.

## Update in place

`gen/vm/lxd/build.sh update` moves an accepted VM to the checkout's commit in place: its
checkout and submodules (the medium, the optimizer) follow, and the room service restarts
and settles. When the commit changes what a build installs from the checkout, the update
makes and installs that too and restarts the VM, as a build's cold boot does:

| Changed | The update |
| --- | --- |
| the medium's daemon or console (`gen/medium/wmediumd`, `gen/medium/observer`) | builds them on the host, as a build does, and installs them in the VM's checkout and as the Console's service |
| the medium's radio module (`gen/medium/hwsim`) | builds it in the VM from the medium's bundle, as `15-prepare-base.sh` does; the restart loads it |
| the guest's services and tools (`gen/vm/scripts/guest`, stages 30, 50, 55, 60, 61) | runs stages 30 and 50 again with the lab's own settings (`/etc/default/easymesh-lab`) |

Its record (below) says what it rebuilt. The VM's other stages need a build. The topology
page comes with the controller image: the update notes a change to it, and a controller
image built from the checkout brings it.

## What a change needs

`gen/tests/affected-suites.py BASE [HEAD]` reads a change and prints the least an accepted
lab needs (nothing, `update`, `build`, or new BPI images first) and the suite sections that
can see it, with the paths that chose each one ([test suite](../guides/test-suite.md)).

## Copies

`gen/vm/lxd/build.sh copy NEW` copies the VM in its storage pool as NEW, with its own LXD
identities, address and port block (from NEW's name, or `EASYMESH_COPY_PORT_BASE`), and
leaves it stopped; `EASYMESH_LXD_NAME=NEW gen/vm/lxd/build.sh start` starts it. A running
VM is copied through a snapshot. On a Btrfs or ZFS pool (`EASYMESH_LXD_STORAGE_DRIVER=btrfs`
for a new lab's pool, sized by `EASYMESH_LXD_STORAGE_SIZE`, 400 GiB sparse by default; LXD's
snap carries the Btrfs tools, ZFS needs the host's module) the copy takes seconds and
shares the original's blocks; on `dir` it is a full copy. A copy shares the original's
machine-id, and with it the DHCP client identity: its first start writes its address into
its netplan, so two labs on one bridge never take each other's lease. Experiment on
copies; never run a suite on two copies of one lab at the same time.

## The base VM image

A build starts from a base VM image when this host or the artifact store has one: the
stages that do not depend on the commit (`00-base.sh`, `10-install-linux-7.sh`,
`15-prepare-base.sh`, `30-boardfarm-wan.sh`: the OS and its packages, the radio kernel,
nested LXD and its client image, the patched radio module, Boardfarm and its WAN) as an LXD
image named by their inputs, `easymesh-rdk-base-KEY`. The key covers those scripts and the
guest files they install, the kernel, the radio count, Boardfarm's commit, the LXD channel,
the nested storage driver, the Alpine client image and the medium's radio module source.
Without one, the build makes it on the way and publishes it:

| `EASYMESH_BASE_IMAGE` | |
| --- | --- |
| `auto` (default) | start from the base image if there is one, else make and publish it |
| `off` | build every stage, publish nothing |
| `rebuild` | make the base image anew |

The commit's own part of the host, `20-prepare-lab-host.sh`, refuses a base whose radio
module was built from another medium than the checkout pins.

## The artifact store

The umbrella's artifact store (easymesh-labs, `docs/reference/artifact-store.md`) keeps
what is slow to build by the inputs it was built from:

| Component | What |
| --- | --- |
| `rdk-image-controller`, `rdk-image-extender` (`-emosa`) | the Banana Pi images, by the manifest and every input BitBake reads from this layer |
| `rdk-base-vm` | the base VM image |

With `EASYMESH_ARTIFACT_STORE=http://HOST:8180`, `gen/build/build-images.sh` fetches the
images whose inputs match this checkout instead of running BitBake, and a VM build fetches
the base image. `BUILD_SSTATE_MIRROR=http://HOST:8180/sstate-cache` gives a BitBake that
does run another host's sstate cache. With `EASYMESH_ARTIFACT_PUBLISH=DIR` or `HOST:/DIR`,
what is built here is published; `BUILD_FORCE=1` builds anyway.

## The records

Every build, update and copy writes a record to `../build-evidence/KIND-NAME-STAMP/`
(`EASYMESH_BUILD_RECORDS` moves it): `environment.txt` (host, commit, image, kernel,
sizes, storage driver, whether it started from the base image; an update adds what it
rebuilt), `phases.tsv` (each phase's start and seconds), `summary.txt`, `exit-code` and, on
failure, `failed-phase`. `latest-KIND-NAME` links the newest. The suite's `summary.json`
carries the run's start, end and seconds and each section's seconds.

## Measured

rev140 (16 CPUs, 62 GiB), 3 and 4 October 2026, with another lab VM running beside the
builds, from the builds' records. `rdk-fast-a` was built cold and made the base image (its
build stopped after it on an ordering fault, fixed since); `rdk-fast-b` started from that
image, fetched from the store over HTTP and imported, and passed its acceptance.

| Phase | Cold | From the base image |
| --- | ---: | ---: |
| assets, create, push inputs | 72 s | 117 s (the 3.2 GB image fetched and imported) |
| base OS, kernel, base host (radio module) | 454 s | — |
| Boardfarm and its WAN | 767 s | 2 s |
| publishing the base image (once per key; 3.1 GiB) | 612 s | — |
| lab host (the commit's checkout) | | 5 s |
| mesh and the first five clients | | 852 s |
| 95 more clients | | 1213 s |
| the wired extender | | 636 s |
| runtime services | | 73 s |
| cold boot (the 100-client lab reconstructed) | | 1218 s |
| acceptance | | 290 s |

Everything before the lab host took 1293 s cold and 119 s from the base image: the base
image saves about 20 minutes a build. The lab part, 71.5 minutes here (4287 s), is longer
than the build guide's 55-minute reference: that was
measured on an idle host and before the wired extender. A copy of the accepted lab on its
Btrfs pool took 8 s (2 s to copy, 6 s for its identities and ports), and the two labs share
9 GiB of pool.

## A development lab

`EASYMESH_DEV_CLIENTS=20 gen/vm/lxd/build.sh build` builds a lab with 20 clients (half
private, half IoT; any even number from 10 to 98) instead of 100: quicker to build and
lighter to run, for work on the mesh, the medium and steering. It has no room service (its
unit needs the full roster), its acceptance checks its roster and the medium's telemetry,
and `snapshot`, `export` and `export-thin` refuse it. Qualification and every room run need
the full lab.
