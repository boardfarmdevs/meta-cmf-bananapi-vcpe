# 0906 thin appliance refresh

The deliverable is `rdkeasymesh-0906-thin.tar` plus its adjacent
`.tar.sha256`. It refreshes the accepted 0905 appliance with the tested
rev140-only room and signal-meter changes. It does not rebuild Yocto, change
the canonical `codex/0905-clean` branch, or replace either running lab.

## Contents and provenance

- Automatic installed/uploaded world loading with authenticated, serialized
  geometry and presence updates to wmediumd and the existing client pool.
- Per-client convergence and actual current-link measurement fixes.
- Unified device dragging, camera gestures and server-owned Play/Pause.
- Shared red/yellow/green signal meters, with grey unlit/unavailable segments.
- The updated searchable viewer manual and reference documentation.
- The complete current source snapshot, including tested uncommitted changes.

Native controller/agent binaries, OneWifi, IEEE 1905, kernel, hwsim and
wmediumd are inherited from the accepted 0905 release. Only the three native
WebUI static files are replaced/added in the offline controller image. The
extender has no native WebUI and its archive remains byte-identical. Packaging
checks every other archive member's metadata and file digest against the
original image. The image manifest records original and refreshed hashes.

`release.json` records the accepted base tar hash, source base commit,
uncommitted-snapshot identity, refreshed image manifest and inner VM archive.
`source-snapshot.tar.gz` and `source-files.sha256` identify the exact delivered
checkout independently of Git HEAD. This is intentionally not represented as
a clean commit-only build. Do not run a checkout reset/update and expect the
uncommitted snapshot to survive.

Packaging starts from the accepted thin backup in a separate VM, not a clone
of an operator's running room. The exported VM retains zero nested lab
instances, one reusable WLAN-client image and an unselected first-boot
profile. No operator token, selected room or playback state is added.
Monitoring remains opt-in; no generated monitoring credentials are added.

## Import

```sh
sha256sum -c rdkeasymesh-0906-thin.tar.sha256
tar -xf rdkeasymesh-0906-thin.tar
cd rdkeasymesh-0906-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
./import.sh --profile 20
```

The resulting default name is `rdkeasymesh-20-0906`. The 20-client profile
starts all 20 clients and five mesh containers, shown as six mesh nodes
because the controller and colocated Agent-1 are drawn separately. Smaller
rooms change availability, not the provisioned roster. A browser's last room
is not a boot profile. The 50/100 selectors remain available but are not
newly qualified by this refresh.

VM autostart is disabled. Import starts the VM once for provisioning; a later
outer-host reboot leaves it stopped. Start it manually with
`lxc start rdkeasymesh-20-0906`. Services and the nested roster still start
normally inside a manually started VM.

Default host ports remain `18889` (native topology), `18890` (Console), and
`18891` (room while a room run is active). To qualify alongside another lab:

```sh
EASYMESH_LXD_NAME=rdkeasymesh-20-0906-verify \
EASYMESH_WEBUI_PORT=48889 \
WMEDIUMD_CONSOLE_PORT=48890 \
EASYMESH_ROOM_DEMO_PORT=48891 \
  ./import.sh --profile 20
lxc exec rdkeasymesh-20-0906-verify -- easymesh-labctl check
```

The importer returns while offline first-boot provisioning continues. Wait
for the completed first-boot report and health gate; merely creating the VM
is not acceptance. Use the [interactive manual](../live-room-demo/interactive-room-manual.md)
to start the default room and test world loading and playback.

## Verification and distribution

Release evidence is stored outside the immutable tar under the canonical
rev140 workspace's `release-evidence/release-0906/`. It records the source
checks, unchanged native binary identities, zero-instance export, integrity
checks, fresh 20-client import, health audit and interactive-room checks.
Evidence must distinguish tests of this new import from earlier rev140
overlay tests; do not infer acceptance from this document or the filename.

The immutable manifest starts as `candidate`; fresh-import acceptance is
recorded alongside the tar without rewriting the tested archive. Keep the
0905 tar and existing live VMs available for rollback. Copying the 0906
archive to rev150 is distribution only, not permission to cut over its lab.
