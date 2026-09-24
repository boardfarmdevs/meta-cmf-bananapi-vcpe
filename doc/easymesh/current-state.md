# Current RDK lab

Reviewed 22 September 2026. This is the source/checkpoint and last-tested
deployment summary, not a live health monitor. See [operations](guide/operations.md).

## Identity and release status

| Item | Current value |
| --- | --- |
| Canonical branch | `main` |
| Development checkout | `rev150:/home/rev/git/meta-cmf-bananapi-vcpe-builddocs` |
| Existing build checkout | `rev140:/home/rev/yocto/easymesh-bpi/meta-cmf-bananapi-vcpe` |
| Last-tested VM | `rev140:demo-a` |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd |
| Fixed pool | 100 clients; five mesh containers / six displayed roles |
| Current classification | Development checkpoint; fresh-VM/full-suite acceptance pending |
| prplMesh peer | Separate repository; last-tested VM `rev120:demo-prpl` |

Controller and Agent-1 share the root container. Default selects ten private
and ten IoT clients; other rooms change presence, not permanent pool size.
Do not enable VM autostart as part of rebuilding or optional remote access.

## Qualification and remaining failures

The latest bounded catalog diagnostics passed **24/24 ordinary rooms** through
load, convergence, Play, native roster/traffic and room/topology checks, followed
by healthy Default-20 restoration. Native identities stayed unchanged. These
runs included recorded working-tree fixes; they are not clean-source fresh-VM
acceptance and do not replace the next full 100-client baseline.

| Remaining gate | Last observation |
| --- | --- |
| Geometry branch formation | Failed the initial 60-second convergence gate before Play; all ten clients were present, but fresh candidate coverage was incomplete. Default recovery passed. |
| Geometry parent handover | Passed the scenario and Default recovery. |
| Geometry isolation/recovery | Failed initial convergence before the outage was played; incomplete fresh measurements. Default recovery passed. |
| Guarded load steering | A native BTM and receiver delivery were observed, but repeat qualification hit native 503/504 query failures. |
| Pressure veto / weak-signal rescue | Test stimuli did not sustain the required otherwise-eligible decision context; no complete live proof. |

The [maintained RF qualification record](reference/radio/rf-property-coverage.md#room-catalog-qualification-and-open-failures)
contains exact evidence paths, repaired harness/namespace issues and attribution.
The `rf-actions` tier is included in `all`; known failures remain failures.
Do not relax deadlines, disable native admission checks, or invent unavailable
metrics to make the new build green. Optional live visibility/priority modes
remain unqualified; isolated medium selftests do not qualify those modes.

## Rebuild checkpoint

Use clean, matching host/guest source commits. The existing rev140 build
checkout contains older uncommitted diagnostic copies; it was inspected but
not reset or overwritten. Preserve/reconcile that work, or use a fresh source
workspace before following the [build guide](build/README.md).

The latest recorded controller and extender image builds there used layer
`3b81ede45d765062f64daa6da9aeeed385448dfb`. Native recipe inputs have changed
since then. **Build both BPI roles again before the new VM**, retaining
`$HOME/oe/downloads` and `$HOME/oe/sstate-cache`; do not clean those caches.
The VM builder consumes images and does not invoke BitBake itself.
The UAF repair, native AP threshold/query handling, proactive backhaul steering
and current candidate-admission patch remain selected by the layer.

Start with static/webui/browser checks, then a fresh VM baseline, rooms and
the remaining [test suite](test/README.md). Retain old VMs stopped until their
replacements pass. No new thin archive or VirtualBox package is produced by
this source checkpoint.

## Access and distribution

These are the last-tested VM's configured addresses, not a health promise:

| View | RDK |
| --- | --- |
| Live room | <http://192.168.2.140:26342/> |
| Network topology | <http://192.168.2.140:26340/> |
| Console NG | <http://192.168.2.140:26341/> |

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
