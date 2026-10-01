# Current RDK lab

Reviewed 1 October 2026. This is the source/checkpoint and last-tested
deployment summary, not a live health monitor. See [operations](guide/operations.md).

## Identity and release status

| Item | Current value |
| --- | --- |
| Canonical branch | `main` |
| Development and build checkout | `rev140:/home/rev/git/easymesh-labs/meta-cmf-bananapi-vcpe` (the easymesh-labs workspace) |
| Last-tested VM | `rev140:rdk-1001` (from scratch, 1 Oct); with the EMOSA option `rev120:rdk-emosa-1001` |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd from easymesh-medium (the `gen/medium` submodule); the optimizer from easymesh-optimizer (the `gen/optimizer` submodule) |
| Images | the controller and extender images the easymesh-labs `manifest.json` pins, with the commit each was built from |
| Fixed pool | 100 clients; the gateway, four Wi-Fi extenders and the wired extender `bpiap-004` (`extender_5`) |
| Current classification | Fresh VM on easymesh-medium; its full room suite passed (below) |
| prplMesh peer | prplmesh-lab; last-tested VM `rev140:prpl-1001` |

Controller and Agent-1 share the root container. Default selects ten private
and ten IoT clients; other rooms change presence, not permanent pool size.
Do not enable VM autostart as part of rebuilding or optional remote access.

## Qualification

**1 October, `rdk-1001`** (from scratch on rev140 at `badc808`: the medium
`e39e98e`, the optimizer `5e57337`, the controller image `…20260929102959` with
unified-wifi-mesh 0232, the extender image `…20260929014035`): the static section
passed 39 of 39 and the room suite 9 of 9 stages, the catalog 27 of 27 on rev140
and the geometry stage with the browser on rev150 (on rev140 the optimizer had
one client left to steer when the 60 s default recovery ended). The build's
traffic check lost packets while `prpl-1001` ran on the same host and passed with
`rdk-1001` alone: build and test one lab at a time on rev140. `rdk-emosa-1001`
(rev120, emosa-lab `f947bf3`, which fixed the adapter kit's C build) passed its
suite with the pods, `fifty-client-counter-roam` with the browser on rev150.

**30 September, the optimizer split**: `rdk-0930` moved in place to the optimizer
from easymesh-optimizer (`gen/vm/lxd/build.sh update`) and passed a quick
requalification: the offline suites, the default room settled with the
optimizer converged, three live `recommend` cycles through the optimizer's CLI,
default readiness and five optimizer rooms with the browser on rev150 (the
easymesh-labs alignment plan, 6.5).

**30 September, `rdk-0930`** (from scratch on rev140, the RF medium from
easymesh-medium `036cd3f`, the images `…20260929012442` and `…20260929014035`):
the full room suite (`gen/tests/run-easymesh-suite.sh rooms`) passed 8 of 9
stages on rev140: the guest audit, default readiness, the geometry rooms, the RF
hover, access and property rooms, the switch through every world and the
restore. The catalog passed 26 of 27 rooms there; the 27th,
`traffic-low-high-off`, missed its load window with rev140 at load 20 and passed
with the browser on rev150. The same day `rdk-emosa-0930` (the EMOSA option,
rev120) passed its suite with the pods, two rooms and the geometry stage with
the browser on rev150.

**29 September, `rdk-0929`**: the first from-scratch VM with the wired
extender as a backhaul parent; its full suite passed (the easymesh-labs
alignment plan, 1.6).

With a lab VM and its browser on one host, rev140 runs at load 15 to 20 on 16
cores and rooms with short windows can miss them in the browser: run the room
browser from another host (`--host`, `--room-url`, `--topology-url`).

## Rebuild

A new VM from scratch: the [build guide](build/README.md)
(`gen/vm/lxd/build.sh build`), from a clean checkout at the pinned commits; the
medium and the optimizer come from the `gen/medium` and `gen/optimizer`
submodules at the commits this repository pins. A commit the lab runs from its
checkout (the optimizer, the room service) moves an accepted VM in place:
`gen/vm/lxd/build.sh update`.
New images into a running lab: `gen/lab-redeploy.sh`. Retain old VMs stopped
until their replacements pass.

## The record of 22 September

The latest bounded catalog diagnostics then passed **24/24 ordinary rooms** through
load, convergence, Play, native roster/traffic and room/topology checks, followed
by healthy Default-20 restoration, on `rev140:demo-a` with recorded working-tree
fixes (not a clean-source fresh VM). The gates open then:

| Gate | Observation on 22 September |
| --- | --- |
| Geometry branch formation | Failed the initial 60-second convergence gate before Play; all ten clients were present, but fresh candidate coverage was incomplete. Default recovery passed. |
| Geometry parent handover | Passed the scenario and Default recovery. |
| Geometry isolation/recovery | Failed initial convergence before the outage was played; incomplete fresh measurements. Default recovery passed. |
| Guarded load steering | A native BTM and receiver delivery were observed, but repeat qualification hit native 503/504 query failures. |
| Pressure veto / weak-signal rescue | Test stimuli did not sustain the required otherwise-eligible decision context; no complete live proof. |

The geometry gates have passed since (29 and 30 September). The
[maintained RF qualification record](reference/testing/rf-qualification.md#room-catalog-qualification-and-open-failures)
contains exact evidence paths, repaired harness/namespace issues and attribution.
The `rf-actions` tier is included in `all`; known failures remain failures.
Do not relax deadlines, disable native admission checks, or invent unavailable
metrics to make the new build green. Optional live visibility/priority modes
remain unqualified; isolated medium selftests do not qualify those modes.

## Access and distribution

These are the last-tested VM's configured addresses, not a health promise:

| View | RDK |
| --- | --- |
| Live room | <http://192.168.2.140:27292/> |
| Network topology | <http://192.168.2.140:27290/> |
| Console NG | <http://192.168.2.140:27291/> |

New VM names receive their own port blocks. See
[monitoring](reference/observability/monitoring.md) for LXD/Grafana.
The optional [Tailscale gateway](reference/deployment/remote-access.md) is
implemented and locally tested, **not installed or published**. Leave it
disabled for initial VM qualification; it needs no BPI/VM rebuild.

Older 0916 downloads under `/home/rev/releases/0916/` are separately identified
candidates, not builds of this checkpoint. Their manifests, known-issues and
packaging receipts remain authoritative. Original image/model, restoration,
fresh-import and VirtualBox boot limitations are not superseded by these room
diagnostics. See [release information](release-notes.md).

## Supported behavior and boundaries

- Loading applies a world immediately; Play, drag, presence, traffic probes,
  signal colors, fullscreen and room-following topology remain supported.
- The external optimizer supplies client policy through native BTM; this is not
  a claim of native autonomous client optimization.
- Most rooms protect startup backhaul; three geometry rooms exercise native
  parent adaptation. Loss recovery and proactive steering are separate checks.
- Convergence requires native membership, ownership, fresh eligible measurements
  and traffic, not just a green badge or an accepted request.
- Host cooling and observer load remain separate from native steering latency.
- [Neighbor-network rooms](reference/proposals/neighbor-rooms/design.md) remain
  proposed; [room acceptance](reference/testing/room-acceptance.md) defines tests.
