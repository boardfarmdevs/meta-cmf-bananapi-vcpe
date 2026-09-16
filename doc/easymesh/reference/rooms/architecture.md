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

### Native proactive backhaul steering

The 0916 native patch adds a controller policy and an agent-side IEEE 1905
Backhaul Steering transaction. This is separate from the external client
optimizer and from `--adaptive-backhaul`. It does not read the world, positions,
simulator's strongest-link overlay, or room convergence result. Release acceptance
still requires the bounded branch, parent-handover and isolation room tests;
focused native unit tests alone do not establish live convergence.

The controller copies the native parent graph under the topology mutex and
uses associated-STA RCPI within native AP Metrics reports for each existing
uplink, requesting those reports from its serving backhaul BSS. On-demand
OneWifi queries select only the requested BSSes from actual radio inventory and collect
fresh HAL association snapshots even before any reporting policy is installed,
or when its periodic interval is zero. They neither enable a reporting timer nor
change threshold policy. An unrelated fronthaul BSS cannot block or add work to
a backhaul-only query. Empty samples withdraw cached clients; failed HAL
collections do not publish cached rows as fresh or erase the previous aged
cache as though the AP were empty. Configured per-radio traffic-stat inclusion
is preserved. Query link reports require
the HAL's kernel-backed authorization state; the Banana Pi HAL does not fill
OneWifi's monitor-only `cli_Active` cache flag. Standalone
Associated STA responses reuse a cached data-model delta and are not accepted
as fresh policy evidence. AP reports recompute sample age from the native
provider timestamp and copy the actually reported backhaul rows into an immutable
event snapshot before model translation. Missing or invalid rows never borrow
cached station values. The controller accepts only the matching AP-query
message ID, sender and BSSID, conservatively adding the full query round-trip
time to provider age. Completed query IDs cannot refresh evidence through
duplicate responses. A changed AP owner, channel or operating class invalidates
both retained samples and outstanding query evidence. The public-header provider and its consumers must use the
same enlarged AP-event structure. It queries candidate APs for
the backhaul STA using native Unassociated STA Link Metrics messages.
AP-report polling also includes childless backhaul APs: their genuine native
responses put traffic on otherwise idle uplinks, refreshing the kernel's
packet-derived backhaul RSSI without depending on the external client optimizer.
An empty AP report never supplies a fabricated serving sample. Candidate
queries have independent message IDs and run across eligible APs in parallel;
they do not overwrite the external client's command ownership. The native
agent retains each query's message ID, operating class, channel, STA set and
request time. OneWifi echoes `QueryId` and a monotonic collection timestamp
captured before its synchronous HAL batch; the agent preserves these in the
immutable result command and ages the sample through queueing. Only that exact
transaction can consume the result. Shared or overlapping station queries never
borrow an unrelated latest message ID or satisfy a newer round with an old
callback. This requires matching EasyMesh, OneWifi and libwebconfig builds;
untagged or stale native results fail closed rather than becoming fresh evidence.
Partial and empty HAL batches complete their exact native transaction, including
an empty operating-class TLV where required; they are not suppressed or routed
by the first reported station's operating class. Only actually measured rows
are published as signal evidence.
In this hwsim lab, same-band candidate RCPI remains HAL/matrix-backed idealized
availability, not proof that an unassociated AP physically heard a station.
The HAL first resolves the actual STA interface MAC through the read-only
association ledger to its provisioned radio identity. This handles randomized
backhaul interface addresses without guessing a radio MAC. The returned current
AP owner is evidence only, never the candidate destination. Stations connected
elsewhere can be measured; globally unassociated, unknown, ambiguous or departed
endpoints remain unavailable rather than returning zero or a guessed signal.

The initial policy is deliberately conservative:

- Same operating class/channel and enabled backhaul APs only; no channel change
  or credential replacement during reparenting.
- Query weak uplinks below RCPI 100 (-60 dBm) on a four-second cadence. Existing
  associated-link reports remain the source of current-parent measurements.
- Require measurements no older than six seconds, at least 12 RCPI (6 dB)
  local-link improvement, and target RCPI at least 50 (-85 dBm).
- Reject self, descendants, cycles, unknown/disconnected ancestry and a weaker
  root-path bottleneck. An extra hop must improve the path bottleneck, rather
  than merely give a stronger local signal. This is a signal-based guard, not
  a measured end-to-end capacity calculation.
- Require two distinct candidate rounds and ten seconds on the observed parent;
  failed handovers have a twenty-second cooldown. Conflicting tree mutations
  have one in-flight reservation; measurement collection is not serialized.

The agent validates the controller, destination, exact local backhaul STA,
target and channel, then acknowledges the request. OneWifi interface-name
readback uses the bus's bounded string count: RBUS
excludes the trailing NUL from that count. A local terminated copy supports
both bus encodings without accepting empty, oversized or embedded-NUL names.
The interface must still resolve to the exact requested STA MAC. The agent uses
the existing native OneWifi BSSID setter with the current credentials. OneWifi
validates connected-scan results against the current radio and requested target
before disconnecting. Other-radio results do not cancel its pending timer;
missing targets, invalid results or allocation/submission failure keep the
current link. The candidate count covers only initialized matching entries.
A synchronous connect rejection enters the existing bounded retry state machine
without waiting for an asynchronous indication timeout. These checks do not
extend the native protocol deadlines or establish the cause of an earlier
intermittent handover delay. Setter acceptance is not a
completed roam. The agent reports success only after connected native readback
shows the requested BSSID; the native mesh-STA callback triggers an immediate
check, with one-second fallback polling and a ten-second transaction deadline.
Duplicate requests replay the original result without reapplying the change.
The controller retries an unacknowledged request at most twice, two seconds
apart, with the same message ID and without extending its deadline.
The controller separately requires the actual new topology parent and a fresh
serving measurement before logging `Native backhaul verified`; a response alone
does not rewrite the topology. Its verification deadline is fifteen seconds.
After a correlated success, the next native tick requests topology directly
from the moved agent, at most three times two seconds apart. Once that native
observation confirms the new parent, it requests fresh serving AP metrics
without waiting for the periodic cadence. A successful response cannot invent
a parent or measurement; the bounded refresh avoids false timeouts caused by
waiting for unrelated periodic topology discovery.
Failure does not prove OneWifi stopped its asynchronous connection attempt.
An unresolved handover therefore remains recorded: its node cannot become a
new target's ancestor, and that node can retry only the same requested parent,
at most three attempts in total. Other safe branches can continue. Fresh native
observation of the requested parent clears the uncertainty; late outcomes are
logged separately rather than counted as an on-time successful transaction.

Observe native controller/agent journals for `Native backhaul request`,
`response`, `verified` and `timeout`, including message ID, STA, old/new BSSID,
RCPI and elapsed time where applicable. Fixed-RF rooms remain fixed-RF: this
native policy does not make their extender positions affect RF. Geometry rooms
can now exercise a stronger-parent handover without first breaking the old
link, subject to the native safety and stability guards.

## Read-only topology positioning

Station persistence shares the topology-notification mutex while traversing and
committing association, departure and metrics records (native patch0199). This
closes a lookup-to-update race that produced a null station write during0916
startup; it complements the earlier topology-encoding lifetime fix0193. Missing
direct updates are ignored rather than resurrecting a departed station. The
lock is released before unrelated tables and topology publication.

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
