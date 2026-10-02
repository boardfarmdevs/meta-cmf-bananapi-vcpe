# Current RDK lab

[Documents](../README.md)

Reviewed 1 October 2026. This is the last-tested deployment, not a live health
monitor. See [operations](../guides/operations.md).

## Identity

| Item | Current value |
| --- | --- |
| Branch | `main` |
| Development and build checkout | `rev140:/home/rev/git/easymesh-labs/meta-cmf-bananapi-vcpe` (the easymesh-labs workspace) |
| Last-tested VM | `rev140:rdk-1001`; with the EMOSA option `rev120:rdk-emosa-1001` |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd from easymesh-medium (the `gen/medium` submodule); the optimizer from easymesh-optimizer (the `gen/optimizer` submodule) |
| Images | the controller and extender images the easymesh-labs `manifest.json` pins, with the commit each was built from |
| Fixed pool | 100 clients; the gateway, four Wi-Fi extenders and the wired extender `bpiap-004` (`extender_5`) |
| prplMesh peer | prplmesh-lab; last-tested VM `rev140:prpl-1001` |

Controller and Agent-1 share the root container. Default selects ten private
and ten IoT clients; other rooms change presence, not permanent pool size.
Do not enable VM autostart as part of rebuilding or optional remote access.

## Qualification

`rdk-1001` was built from scratch on rev140 on 1 October and passed its full suite:
the static section, the room suite's stages, the catalog of 27 rooms and the
geometry stage with the browser on rev150. Its controller image was then replaced
in place (`gen/lab-redeploy.sh`) by one with unified-wifi-mesh 0233, under which an
agent's renewed radios no longer wait for its configured ones; the lab requalified:
readiness, the one-client handover room, `backhaul-wired-parent`, the world switch
and the live RF hover. `rdk-emosa-1001` (rev120, the EMOSA option) took the same
image and passed its suite with the pods.

Open: with the EMOSA option only, before the room first settles after the EMOSA
step's medium restart, the wired extender's 5 GHz radio can stay in `wsc_m2_sent`
and its siblings' configuration cycles until the lab's second bring-up, which has
settled it each time.

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

## Access

The last-tested VM's addresses, not a health promise:

| View | `rdk-1001` |
| --- | --- |
| Live room | <http://192.168.2.140:29882/> |
| Network topology | <http://192.168.2.140:29880/> |
| Console NG | <http://192.168.2.140:29881/> |

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
