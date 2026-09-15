# Room coordination and authority

[Room reference](README.md)

The browser submits control intent; the room conductor owns the live session.
The configurator runner is the single RF writer. It compiles world positions,
walls, directional gains and presence into atomic wmediumd changes, reads them
back, and publishes the committed revision/environment epoch. The native stack
and station software—not the scene graph—own association.

## State and observation

- Playback publishes all role positions/presence and the clock in one commit.
  Loading resets playback/overrides and applies the initial world immediately.
- The fixed pool is not resized. Presence transitions disconnect/reconnect
  the affected roles even when the calculated RF matrix needs no change.
- Candidate collection, decisions, submission and verification retain correlated
  action IDs, timestamps, RF epoch and native operation timings.
- Superseded observations are discarded. A missing roster member or incomplete
  fresh candidate coverage remains visible; it cannot be hidden to claim that
  the whole fleet converged.
- Passive serving-state/traffic observation continues without using geometry
  as a secret native-metrics oracle. Simulated measurements stay labeled.

RDK uses controller HTTP APIs; prplMesh uses native NBAPI via its local adapter.
Whole-second prpl candidate timestamps can require a recorded wait until the
baseline second ends. RDK native command admission and response timeouts remain
a real constraint. Neither backend has a zero-outside-stack-latency guarantee.

## Select one authority

| Room CLI mode | Client steering | Backhaul |
| --- | --- | --- |
| `interactive --mode act --yes-act --profiling` | External policy, unassisted native BTM | Startup RF protected |
| `interactive --mode stimulus --profiling` | No external client policy/candidate requests | Startup RF protected |
| `interactive --mode stimulus --profiling --model-backhaul` | No external client policy | AP-to-AP RF follows world |
| `interactive --mode act --yes-act --profiling`, geometry room | External client policy, unassisted native BTM | Geometry RF; native parent selection |

The CLI entry point is `gen/demo/room-demo`; inspect `--help` for all
options before replacing a service's command. These CLI modes are distinct from
the browser's default URL. Serving-state and traffic observations remain active.

Rooms may declare signed `backhaul_rf: "geometry"` metadata in their mobility
source and compiled golden. Missing metadata defaults to `fixed`, preserving
the original client/band room behavior. A geometry room bypasses the startup
AP-to-AP RF freeze during loading, playback and dragging, but does not create
an external parent manager. The same client-profiling server can load both
kinds without restarting containers or changing optimizer authority.

Before applying geometry RF, RDK checks all five 5 GHz backhaul APs for an
operating `mesh_backhaul` SSID and channel 36. An enabled but unstarted AP is
applied through OneWifi's `AccessPoint.14.ForceApply`; administratively down
backhaul STA interfaces are brought up and read back. This is an idempotent
room-load prerequisite, not a background parent controller: it never writes a
parent BSSID, triggers reassociation, or repairs links during playback. A
failed prerequisite rejects the world before changing its RF. Fixed rooms
do not perform these setup writes. Native AP readiness is distinct from cached
configuration; the short backhaul test also checks all six client-facing APs
per node. A stale controller database cannot override missing live mesh nodes
in the room health indicator.

The saved fixed RF baseline survives geometry rooms. Returning to a fixed room
restores it with atomic apply/readback; actual association, topology freshness
and traffic recovery must then be checked independently. RF restoration is
not a promise that native parents immediately return to their old BSSIDs.
Failed world writes restore both the previous RF and room policy. Recorded
worlds retain their effective RF policy; malformed uploaded policies are
rejected before any write.

`--model-backhaul` remains an explicit global geometry override, now independent
of client policy. It does not add a parent-selection algorithm and cannot be
combined with `--adaptive-backhaul`. The latter is separately labeled external
RDK assistance and remains excluded from profiling. Weak geometry links can
disconnect nodes; do not silently restore a star to make a test pass.

The viewer's Backhaul policy card distinguishes fixed RF, geometry with native
parent selection, external assistance, and disconnected previews. Extender
presence still means fronthaul availability, not power loss. The dedicated
isolation room instead weakens real AP-to-AP RF while preserving nearby client
RF. Geometry .world.json playback needs the interactive room engine: legacy
`.wmd` exports remain explicitly labeled fronthaul-only projections.

## Read-only topology positioning

The room exposes `GET /api/demo/mesh-layout`: five or fewer mapped mesh device
IDs, stable room roles and committed positions, plus run/world/sequence and
observation timestamps. It projects cached event state under its existing lock;
it neither copies the full client/optimizer snapshot nor queries native metrics
or wmediumd. Playback and drag commits update the same coordinate source.

RDK EM CLI proxies this through `GET /api/v1/room-layout` on its own origin.
`EASYMESH_ROOM_URL` in the controller's `em_cli.service` environment defaults to
`http://10.101.0.1:8891`, the outer lab VM endpoint, not the browser's host/port.
Use a systemd drop-in to override it for another network; an empty value disables
the upstream. No public new port, browser CORS exception or extra service is
required. Requests are read-only, have a 750 ms upstream deadline and 64 KiB
response limit, reject redirects, and coalesce concurrent browsers behind a
200 ms cache. This route bypasses native API ownership, so an unavailable room
does not serialize topology or metrics behind the layout request.

While the topology tab is visible and following is enabled, a separate 250 ms
poll consumes this small projection. One browser request can be in flight;
unavailability backs off to about two seconds. Manual layout polls about every
two seconds solely to keep the current room heading up to date, without moving
nodes. Both views retain their room heading in fullscreen; unavailable topology
data marks its previous heading as **last observed**. Unchanged poses do not repaint.
Only existing controller-reported nodes are positioned, using device IDs rather
than display ordinals. Projection scale/origin are held for the current world,
so moving one node does not continuously rescale all its peers or pin Agent-1
to its original location. Both frontends share the default camera angles in
`room-projection.js`. Topology projects the floor into that rotated, tilted
orientation rather than displaying raw X/Y (which previously mirrored/rotated
the apparent arrangement). Initial spacing uses projected distances; bounded
collision separation keeps nearby AP/client groups readable. Controller stays
near Agent-1 and unmapped reported devices remain separate. This is an affine
floor projection, not a perspective copy; manual room-camera orbit remains
browser-local. No camera reporting service or extra network request is added.
The display then uniformly compresses mesh spacing using the occupied AP/SSID
circles, label clearance and manually moved clients, rather than fitting the
large safety circles used for initial separation. This keeps mesh bearings and
ordering while reducing empty space. Controller is placed separately nearby.
The final SVG fit retains a six-pixel border and reacts to the pane's size.
Coordinates do not specify
backhaul parents or client association instructions. Missing/future/stale room
mapping, replay and disconnect stop following and retain the last drawing.
Manual mesh dragging unchecks Follow room layout; the preference is browser-local.
Client dragging only adjusts its diagram position. Optimize Layout preserves
follow anchors when active; fitting and fullscreen still use the thin margin.
Both frontends share a pointer/keyboard divider with browser-local persisted
widths, right-pane minimums and a double-click reset. Resize notifications use
the existing canvas/SVG observers and are coalesced into animation frames;
resizing neither rebuilds the graph nor sends lab commands. Mobile layouts
retain their stacked panels and fullscreen excludes the divider.

Native accepted BTM submissions retain up to 100 recent station/source/target
BSSID records for 30 seconds. The topology correlates a newly observed handover
with this evidence; it never infers non-BTM from a missing record. An existing
operator `POST /api/v1/steering-event` annotation may additionally contain
`method: "non-btm"`, `phase: "completed"`, `source_bssid` and `target_bssid` alongside
its usual `sta_mac`, `client_name` and `target_name`. Both BSSIDs and the station
must be six-byte MACs and source must differ from target. This is explicitly
operator-reported evidence, not a native protocol assertion or a steering command.
Ghosts, arrows and method captions expire at the original six-second deadline
even across redraws, without holding association rendering or native processing.
Late method evidence recolors an existing cue in place; it neither rebuilds the
SVG nor restarts its expiry timer.

## Steering protection

Interactive automatic steering has no default lifetime request cap. The installed
service uses `--steering-rate-limit 300`: at most 300 submissions in any rolling
60 seconds, with at least five seconds between submissions to the same client.
Admission is atomic across concurrent batches. In-flight requests, native
verification, policy cooldowns and failure backoff remain in force; this is
external lab protection, not a change to the native EasyMesh implementation.

Only the affected client pauses after three consecutive terminal failures within
180 seconds, or before a fourth alternating A→B/B→A request within 60 seconds
under unchanged RF. Successful verification resets its failure streak.
Relevant client/AP RF changes clear that client's stale failure/oscillation
history; unrelated client movement does not. Measurements and other eligible
clients continue. A full request window recovers automatically.

**Resume steering**, beside External optimizer, clears client protection pauses.
It does not restart the room or reset positions, presence, playback, RF,
lifetime counters, cooldowns or the rolling window. Loading a world clears old
world-specific pauses but retains rate accounting. Preview, replay and
observation-only sessions cannot resume steering. Explicit `--max-actions N`
remains available for deliberately finite runs; Resume does not bypass it.

`GET /api/demo/optimizer/safety` reports the current guard without actuation.
`POST /api/demo/optimizer/resume` requires the browser control lease, same-origin
request, world `If-Match` revision, unique `command_id` and the GET response's
`expected_pause_revision`. Duplicate command IDs return the original response
without rearming a later pause. A changed pause revision returns 409 for review.
Safety revisions protect HTTP/SSE state from older evaluations.

## Recovery and bounded evidence

A checksummed journal records touched RF state, daemon/generation ownership
and stable radio/container identities. Restore only if those still match.
Recovery does not delete an incompatible journal or blindly restart native
services. After rejoining, require health and real client traffic before ready.

Interactive evidence uses a bounded asynchronous writer and bounded history.
Overflow, disk errors or expired history are explicit qualification failures;
a partial tail is not a complete replay. SSE cursor expiry triggers resync.
HTTP/SSE capacity is bounded so a slow observer cannot own the control loop.

Per-run bounds do not clean old run directories or unlimited user recordings.
Archive/delete completed evidence under an explicit retention policy. Never
ship installed secrets, private monitoring backups or raw credentials.

See [room acceptance](../testing/room-acceptance.md) for independent physical,
native and browser checks; see [performance](../testing/performance.md) before
attributing collection or display delay to native steering.
