# Current RDK lab

[Documents](../README.md)

Reviewed 2 October 2026. This is the last-tested deployment, not a live health
monitor. See [operations](../guides/operations.md).

## Identity

| Item | Current value |
| --- | --- |
| Branch | `main` |
| Development and build checkout | `rev140:/home/rev/git/easymesh-labs/meta-cmf-bananapi-vcpe` (the easymesh-labs workspace) |
| Last-tested VM | `rev140:rdk-1002b`; with the EMOSA option `rev120:rdk-emosa-1002` |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd from easymesh-medium (the `gen/medium` submodule); the optimizer from easymesh-optimizer (the `gen/optimizer` submodule) |
| Images | the controller and extender images the easymesh-labs `manifest.json` pins, with the commit each was built from |
| Fixed pool | 100 clients; the gateway, four Wi-Fi extenders and the wired extender `bpiap-004` (`extender_5`) |
| prplMesh peer | prplmesh-lab; last-tested VM `rev140:prpl-1002` |

Controller and Agent-1 share the root container. Default selects ten private
and ten IoT clients; other rooms change presence, not permanent pool size.
Do not enable VM autostart as part of rebuilding or optional remote access.

## Qualification

`rdk-1002b` was built from scratch on rev140 on 2 October, from this repository as
it is after its cleanup (the build scripts under `gen/build`, the documents under
`docs/`), with a controller image `gen/build/build-images.sh` built that day. It
passed the build's acceptance and, with the browser on rev150, readiness, five
rooms (`home-a-one-client-handover`, `band-upgrade-24-5`, `received-same-band-roam`,
`large-room-perimeter-counter-roam`, `traffic-quieter-ap`), `backhaul-wired-parent`
and `fifty-client-counter-roam`. `rdk-emosa-1002` (rev120, the EMOSA option) was
built the same day and passed readiness, the five rooms with the pods and
`backhaul-wired-parent`. On 3 October it took emosa-lab's adapter in C
(`EASYMESH_EMOSA_AGENT=c`: the fleet, the GTP and the agents, with no Python) and passed
readiness, the five rooms with the pods, `backhaul-wired-parent` and
`fifty-client-counter-roam` again. With emosa-lab after its plan 8.4 (the adapter's
features at its production bar) the full rooms section ran on it the same day with
the adapter in C: 26 of the catalog's 27 rooms on rev120 and the 27th
(`home-a-wired-extender-loss-recovery`, a client move between two native extenders
1 s past its check) in 4 of 4 runs after, the four geometry rooms, the RF stages and
the switch through every world. The suite needs `EASYMESH_HOST_ADDRESS=192.168.2.120`
and `EASYMESH_SSH_HOST=rev120` on rev120, where the VM's proxies listen on the host's
address.

The controller image carries unified-wifi-mesh 0233 and 0234: a radio the
controller renews on its own waits neither at the Topology Query nor at the AP
Capability Query for its agent's radios that stayed configured. Without 0234 such
a radio was renewed again every 88 seconds and reported on no client of its band;
with the EMOSA option the room then never settled.

Open, each with what shows it in the easymesh-labs
[open work](https://mesh.vcpe.dev/):

- The controller's memory grows while the mesh keeps re-forming; it is killed at
  the gateway's 1 GiB limit, which stays as it is. Idle and through the rooms it
  is flat.
- Under heavy contention for the host's CPU the extenders keep leaving and
  rejoining their backhaul.
- A controller that restarts on its own comes back with part of the model;
  `gen/lab-bringup.sh up` restores it.

Build and test one lab at a time on rev140: with a second lab running, the
build's traffic check loses packets. With a lab VM and its browser on one host,
rev140 runs at load 15 to 20 and rooms with short windows can miss them: run the
room browser from another host (`--host`, `--room-url`, `--topology-url`). Do not
relax deadlines, disable native admission checks or invent unavailable metrics to
make a run green; the [RF qualification record](../records/rf-qualification.md)
holds the evidence and the attribution of past failures.

## Rebuild

A new VM from scratch: the [build guide](../guides/build.md)
(`gen/vm/lxd/build.sh build`), from a clean checkout; the medium and the optimizer
come from the `gen/medium` and `gen/optimizer` submodules at the commits this
repository pins, EMOSA from emosa-lab at the commit `gen/vm/lxd/emosa-lab.env`
pins. A change the lab runs from its checkout (the optimizer, the room service)
moves an accepted VM in place: `gen/vm/lxd/build.sh update`. New images into a
running lab: `gen/lab-redeploy.sh`. Keep old VMs stopped until their
replacements pass.

EMOSA in the controller image itself is opt-in and off by default (the recipe
`recipes-emosa/emosa`, `EMOSA_ADAPTER = "1"`; `BUILD_EMOSA=1 gen/build/build-images.sh
controller`): emosa-lab's C programs at the same pinned commit, logging through RDK's
logger into `/rdklogs/logs`, the fleet enabled and inert until `/etc/emosa-fleet.json`
exists. Built on 3 October on rev140 (`X86EMLTRBPIBB_rdk-next_20261004013832`): it
differs from the default image only by the package `emosa` (520 KiB); without the
setting the image's packages are the default's. No lab runs it yet: the lab's EMOSA
option keeps the adapter in its own container (the easymesh-labs plan's 8.6 measures it in the
gateway).

## Access

The last-tested VM's addresses, not a health promise:

| View | `rdk-1002b` |
| --- | --- |
| Live room | <http://192.168.2.140:29302/> |
| Network topology | <http://192.168.2.140:29300/> |
| Console NG | <http://192.168.2.140:29301/> |

Each new VM name receives its own port block. See
lab monitoring (in [easymesh-medium](https://vcpe.dev/easymesh-medium/)) for LXD and Grafana. The optional
[Tailscale gateway](../reference/remote-access.md) is implemented and locally
tested, **not installed or published**; leave it disabled for a VM's first
qualification.

## Supported behavior and boundaries

- Loading applies a world immediately; Play, drag, presence, traffic probes,
  signal colors, fullscreen and room-following topology are supported.
- The external optimizer supplies client policy through native BTM; this is not
  a claim of native autonomous client optimization.
- Most rooms protect startup backhaul; three geometry rooms exercise native
  parent adaptation. Loss recovery and proactive steering are separate checks.
- Convergence requires native membership, ownership, fresh eligible measurements
  and traffic, not just a green badge or an accepted request.
- Host cooling and observer load remain separate from native steering latency.
- Neighbor-network rooms (in [easymesh-medium](https://vcpe.dev/easymesh-medium/)) remain proposed;
  [room acceptance](../reference/room-acceptance.md) defines the tests.
