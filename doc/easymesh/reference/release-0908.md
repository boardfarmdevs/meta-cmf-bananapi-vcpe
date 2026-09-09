# 0908 clean rebuild and rev140 deployment

## Scope and status

This release moves RDK development to `codex/0908-clean` and canonical source
`rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0908-clean/meta-cmf-bananapi-vcpe`.
It rebuilds both full role images and a new appliance, exports a universal
`rdkeasymesh-0908-thin.tar`, then deploys **from that tar**, not from the builder.
RDK is deployed only on rev140. The separate prplMesh 0908 release is built
and deployed from its own repository on rev150; no active prplMesh checkout,
build container, packaging VM or UI service remains on rev140. rev120 is unchanged.
Qualification is limited to profile 20 and short smoke tests, not a full soak.

Both full images build and the corrected fresh appliance passes native cold
reconstruction. Subsequent live-room testing exposed the helper/health-check
gaps described below. The actual thin-tar import, browser smoke results, archive hash and
cleanup are recorded beside the release archive in acceptance evidence. A
builder pass is not an import pass; retain 0907 until that qualification passes.

## Rebuilt inputs and appliance check

The native cold-reconstruction evidence below uses source commit `9175e74`
on `codex/0908-clean`. These are diagnostic inputs: the release controller is
rebuilt afterward to include the refreshed EM CLI helper. Use the exact final
image names and hashes in the thin bundle's release metadata/acceptance evidence,
not the diagnostic controller image below.

| Role | Image | SHA-256 |
| --- | --- | --- |
| Controller | `X86EMLTRBPIBB_rdk-next_20260909022038.rootfs.lxc.tar.bz2` | `62c55c0e0404a14457b14747eec93a9288442dcbc93579131c1bf727acb68a16` |
| Extender | `X86EMLTRBPIAP_rdk-next_20260909022625.rootfs.lxc.tar.bz2` | `035d3a77fea1ea51ee07537cc30e4f43072b3618c70417707cec6263d78b149d` |

At 2026-09-09 03:07 UTC, fresh-appliance reboot reconstruction passed with
five physical mesh devices, fifteen radios, fifty BSS records, twenty clients
and twenty reporting client metrics, twenty-four associations including the
four backhaul STAs, and zero EasyMesh/OneWifi service restarts. All twenty
clients reached the controller. Reconstruction took 466.49 seconds including
the bounded stability and traffic checks. The displayed topology has six
roles because Controller and Agent-1 share the physical root container.

## Fresh-build findings

The download-from-empty run exposed retired hostap/virglrenderer source URLs
and a blocked crates.io API download route. Repository overrides retain the
exact pinned revisions while using current upstream HTTPS/CDN endpoints.

The first fresh appliance also exposed native onboarding recovery that an
existing controller database can hide: the initial M1 may race the controller's
queued agent-model creation. Without any M2, the agent's retry destination was
not remembered from the autoconfig response. Patch 0172 records that validated
controller AL address before the first WSC exchange, retaining the native
retry schedule instead of adding deployment-side sleeps or service restarts.
The failing appliance and diagnostic capture are evidence, not release inputs.

The next appliance passed virgin onboarding but its reboot exposed a controller
segfault in CAC capability handling. The sender emits compact variable-length
radio/method/channel lists; the receiver copied a much larger in-memory radio
structure from that wire payload. Patch 0173 decodes those lists with bounds
checks and network-order duration conversion. Its compiled regression covers
multiple radios, every byte truncation and a guard-page boundary. Neither a
service restart nor a relaxed acceptance gate substitutes for this fix.

## Recreate on another machine

Follow [the source-build instructions](../../build/README.md) to clone this
branch and synchronize `rdkb-bpi-nosrc-0908.xml`. The new tree must not be a copy
of a working build directory. Start with empty `build-qemux86bpibroadband`,
`build-qemux86bpiap`, downloads and sstate locations; the script creates them.

```sh
cd "$HOME/yocto/rdkb-bpi-nosrc-vcpe-0908-clean/meta-cmf-bananapi-vcpe"
bash doc/build/build-images.sh
```

This is a source-level rebuild using external, pinned upstream repositories,
not a claim that Git alone includes Ubuntu packages, upstream source archives
or credentials. Internet access and required source-host permissions are
prerequisites. The repository contains the native patches, machine configs,
runtime tools, image/appliance builders and checked-in WebUI/Console helpers;
it does not require the old rev140 build scripts or an old VM disk.
Rebuilding the checked-in Go helper is documented in the build guide; record
any resulting artifact update before creating the appliance Git bundle.
The image recipe checks the helper's archived Go-source hashes against the
patched workdir and rejects an outdated binary. This caught an important
release gap: the prior archive lacked the coordination and native-steering
APIs even though the current Go patches and static assets were present.
Refresh it with `gen/rebuild-em-cli-artifact.sh WORKDIR` after native compilation,
commit the archive, then rebuild the controller image. Never hot-copy a helper
into a VM and call that a qualified thin release.

Appliance build/export checks temporarily stop an already-running room, which
restores its RF baseline, before testing zero-loss traffic. They restart the
room afterward, including on audit failure; an initially stopped room stays
stopped. These baseline checks must not race the room's RF changes or steering.
Use a separate live-room smoke test for interactive behavior. Transient
controller transport failures now pause steering and report unavailability
instead of terminating and resetting the interactive room.

## Build a fresh appliance and thin tar

Install the normal outer-host prerequisites using
`sudo bash gen/vm/lxd/install-host.sh`. Use fresh image paths from the two
successful builds, not the retained 0905/0907 archives. Commit any source
changes first: the builder requires a clean checkout and bundles that commit.

```sh
SOURCE="$HOME/yocto/rdkb-bpi-nosrc-vcpe-0908-clean/meta-cmf-bananapi-vcpe"
export EASYMESH_RELEASE_ID=0908 EASYMESH_RUNTIME_BRANCH=codex/0908-clean
export EASYMESH_LAB_PROFILE=20 EASYMESH_LXD_NAME=rdkeasymesh-0908-builder
export EASYMESH_WEBUI_HOST_IP=192.168.2.140
export EASYMESH_WEBUI_PORT=58889 WMEDIUMD_CONSOLE_PORT=58890 EASYMESH_ROOM_DEMO_PORT=58891
export EASYMESH_LXD_EXPORT_DIR="$HOME/releases/0908"
export EASYMESH_CONTROLLER_IMAGE=/absolute/path/to/new/controller.rootfs.lxc.tar.bz2
export EASYMESH_EXTENDER_IMAGE=/absolute/path/to/new/extender.rootfs.lxc.tar.bz2
bash "$SOURCE/gen/vm/lxd/build.sh" build
bash "$SOURCE/gen/vm/lxd/build.sh" export-thin
bash "$SOURCE/gen/vm/lxd/package-release.sh" "$HOME/releases/0908/rdkeasymesh-0908-thin"
```

Replace the two image placeholders and site IP/ports. On another host use its
own management IPv4. The fresh builder installs Ubuntu packages, the Linux 7
kernel, patched hwsim, pinned Boardfarm code and runtime services from source.
The room service is now tracked and enabled for the 20-client profile; it
waits for native lab startup and does not run before thin profile selection.
Its defaults match the live profiling room, without a manual systemd drop-in.

The hwsim build uses the installed kernel's headers. Its source helper first
requests the installed Ubuntu version, then falls back to the available HWE
source package when that source version is no longer indexed. Preserve the
appliance build log and module checksum: for this rebuild, kernel headers
are `7.0.0-30-generic` and the fetched HWE source is `7.0.0-31.31~24.04.1`.
This is not a claim of a byte-identical Ubuntu source lock.

Thin export removes all provisioned nested instances, retaining the exact role
archives and reusable client image. It stops the room before the lab, does not
include optional monitoring credentials, and records checksums in `SHA256SUMS`.
Do not enable monitoring on a builder that will be exported.

## Import the actual tar and perform a short acceptance check

Extract into a new directory, validate both checksum layers, and import using
the supplied script. A source-mounted host path must not be required at runtime.
Use spare ports while the old 0907 VM is still running, then switch to the
existing rev140 browser ports after the replacement passes smoke checks.

```sh
cd "$HOME/releases/0908"
sha256sum -c rdkeasymesh-0908-thin.tar.sha256
mkdir fresh-import
tar -xf rdkeasymesh-0908-thin.tar -C fresh-import
cd fresh-import/rdkeasymesh-0908-thin
sha256sum -c SHA256SUMS
EASYMESH_WEBUI_HOST_IP=192.168.2.140 EASYMESH_WEBUI_PORT=38889 \
  WMEDIUMD_CONSOLE_PORT=38890 EASYMESH_ROOM_DEMO_PORT=38891 \
  bash import.sh --profile 20
```

The expected new VM is `rdkeasymesh-20-0908`. Its own source branch must be
`codex/0908-clean` at the packaged commit; nested LXD should contain 25 running
containers: controller/Agent-1, four extenders and 20 clients. Check
`/var/lib/easymesh-lab/thin-firstboot-report.json` for zero initial instances
and successful offline provisioning. New outer VMs retain autostart disabled.

Limited acceptance consists of:

- The normal `easymesh-labctl check`, native topology/client roster and basic
  traffic checks, without a repeated long-running soak.
- Topology, Console and room HTTP endpoints; room `/healthz` is healthy.
- Browser visibility of the default 20 clients and six displayed mesh nodes,
  one short Play/Pause/drag interaction and restoration to the default world.
- Optional monitoring, when enabled after import: correct TLS/credentials,
  target health and representative CPU/memory/network dashboard data.

Enable LXD UI/Grafana after import using the included observability bundle;
see [the monitoring guide](lxd-ui-and-monitoring.md). Generate per-VM credentials
on the new installation rather than copying credentials from 0907. The outer
VM dashboard is an explicit opt-in and shares the same monitoring services.

## Cutover and obsolete VM cleanup

After smoke acceptance, stop 0907, move the new VM's proxy listeners to the
existing rev140 ports `48889`/`48890`/`48891`, and use `48892`/`48893` for LXD
UI/Grafana. Recheck those URLs. Save the old VM inventory/configuration and
wanted evidence first; delete only confirmed obsolete RDK instances and the
disposable 0908 builder once the thin-tar import is accepted. Do not delete
unrelated kernel-development or prplMesh instances by a broad name pattern.
No RDK deployment is required on rev120 or rev150. prplMesh's independent
rev150 topology/room/console ports are `8091`/`18891`/`8090`.

The archive and adjacent checksum are the portable delivery; the new canonical
build workspace and `release-evidence/` retain build/import provenance. Old
canonical directories and previous immutable release archives are historical
records, not active build or runtime dependencies.
