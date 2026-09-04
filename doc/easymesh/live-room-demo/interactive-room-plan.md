# Interactive room architecture and improvement plan

## Purpose

The room demonstration is a closed-loop EasyMesh experiment, not a topology
animation. It supports precooked Golden Worlds, live operator movement, a
combination of scripted and manual movement, and evidence-only replay.

The browser may preview geometry, but it must not manufacture controller
telemetry or visually assert that an association changed. Room geometry is
compiled into RF conditions, wmediumd applies those conditions to real hwsim
frames, the mesh reports measurements through its normal telemetry path, and
the optimizer reasons only from those measurements. A steering result is
successful only after physical association, controller ownership and traffic
have been independently verified.

The target causal chain is:

```text
operator or scenario intent
          |
          v
authoritative room position/presence
          |
          v
one applied and read-back wmediumd generation
          |
          v
fresh controller measurement from the new RF epoch
          |
          v
optimizer reason and recommendation
          |
          v
optional, explicitly armed EasyMesh/BTM request
          |
          v
verified association + controller convergence + traffic
```

This document is the governing improvement plan. Where the current
implementation differs, the difference is identified as transitional work and
must be removed before broader interactive controls are accepted.

## Non-negotiable design rules

1. One `RoomEngine` owns all mutable room state and is the only RF writer.
2. HTTP handlers validate and enqueue commands; they never mutate wmediumd.
3. State is committed only after an atomic medium apply and exact readback.
4. An unexplained medium generation or instance change contaminates the run.
5. Predicted SNR, applied SNR and controller RCPI remain separate truths.
6. Optimizer observations are usable only within one stable environment epoch.
7. Association changes only through normal Wi-Fi and EasyMesh behavior.
8. `private_ssid` and hidden `iot_ssid` stay distinct end-to-end.
9. Recommendation is the default. Actuation is immutable per run and bounded.
10. The complete pre-run RF state is restored exactly, including after faults.
11. Every requested, rejected, committed and verified transition is auditable.
12. Live, reconnect and replay state are produced by the same state reducer.

## Presentation modes

| Mode | Movement source | RF changes | Steering authority |
|---|---|---|---|
| Scripted | Precooked scenario clock | `RoomEngine` composes and applies scenario state | off, recommend or bounded act |
| Interactive | Operator commands | `RoomEngine` applies accepted live state | recommend by default; bounded act only when process permits it |
| Hybrid | Scenario plus leased manual overlays | `RoomEngine` composes both once per tick | recommend by default; bounded act only when process permits it |
| Replay | Recorded event journal/evidence | none | none |

An interactive clip can be exported as a valid world scenario and replayed as
a regression test. Recording does not disable the permanent audit journal.

## Authoritative RoomEngine

The current interactive session serializes work with a lock, but HTTP request
threads can still enter its mutation path. That is transitional. The accepted
architecture is an actor-like engine with one ordered command queue:

```text
browser commands ---------\
                            \
scripted clock ticks --------> RoomEngine command queue
                             |        |
presence and movement -------/        v
                              compose authoritative state
                                       |
                                       v
                             canonical geometry module
                                       |
                                       v
                                 MediumSession
                              one socket / one writer
                                       |
                              atomic apply + readback
                                       |
                                       v
                             commit state and emit event
```

The `RoomEngine` owns:

- authoritative role positions and presence;
- immutable base scenario plus manual overlays;
- scenario clock and movement jobs;
- per-role control state and leases;
- world revision and environment epoch;
- recording and state reduction; and
- optimizer gating state.

Its internal `MediumSession` owns:

- the control connection and medium instance identifier;
- the expected medium generation;
- the complete captured baseline and touched-key set;
- serialized atomic writes and readback verification;
- medium ownership/lock renewal; and
- exact restoration.

Hybrid control is state composition, not a second writer. A leased role uses
its manual overlay while scripted positions continue for unleased roles.
Releasing an override explicitly chooses one of:

- resume the base scenario at current scenario time;
- rejoin it over a selected transition; or
- remain manual for the rest of the run.

An unexpected generation advance emits `medium.external_write_detected` and
freezes or aborts the experiment. It is not silently retried. All RF-writing
tools must honor the same host-wide lock. A future daemon protocol should add
an owner token with acquire, renew, apply and release/restore operations.

## Independent state machines and clocks

The room cannot represent all control with one overall `state` value. The
normalized state has independent dimensions:

```text
run_state:             preparing | ready | running | restoring | passed | failed
scenario_clock_state:  playing | paused | stopped
interaction_state:     unowned | leased
role.control_state:    scripted | manual | moving | rejoining | absent
optimizer_authority:   observe | recommend | act-capable
act_arm_state:         disarmed | armed-until-T
```

Pausing scripted time must not set `run_state=paused`; the server, telemetry
and leases continue to run.

Every event carries both:

- `run_elapsed_ms`: monotonic elapsed time since process start, never paused;
- `scenario_time_ms`: position on the scenario clock, which may pause or vary.

UTC `recorded_at` remains the evidence timestamp. Measurements additionally
carry their own observed timestamp and age.

## Ordering, causality and commit semantics

Three counters have different meanings and must never be overloaded:

| Identifier | Meaning |
|---|---|
| `sequence` | total order in the evidence journal |
| `world_revision` | optimistic-concurrency version of authoritative room state |
| `medium_generation` | generation accepted by the current wmediumd instance |

Commands and events also carry, where applicable:

- `command_id` or `intent_id` for idempotency;
- `client_request_sequence` for browser ordering;
- `causation_id` and `correlation_id` for end-to-end transactions;
- `lease_id`; and
- `medium_instance_id`.

The engine calculates a proposed state and RF delta, applies it, reads it back,
then commits the role state and increments `world_revision`. A failed or
mismatched apply leaves authoritative state and revision unchanged.

An accepted position event is conceptually:

```json
{
  "kind": "room.position.committed",
  "sequence": 417,
  "run_elapsed_ms": 72842,
  "scenario_time_ms": 65000,
  "world_revision": 19,
  "medium_instance_id": "wmediumd-instance-X",
  "medium_generation": 883,
  "causation_id": "command-934",
  "payload": {
    "role": "sta_mobile_01",
    "position_m": [15.2, 8.4],
    "changed_link_keys": 24,
    "telemetry_state": "awaiting_fresh_measurement"
  }
}
```

Persisted interaction events use intent/commit/reject terminology:

- `interaction.position.intent`
- `room.position.committed`
- `room.position.rejected`

A browser-local ghost is not a persisted `previewed` event because it was not
accepted by the server.

## Drag and movement semantics

### Direct placement

The accepted default is commit-on-drop:

```text
pointer motion: local ghost + predicted geometry, no RF write
pointer-up:     one final idempotent position command
server:         one atomic RF transaction and readback
viewer:         reconcile solid authoritative role to committed position
```

This avoids write storms, stale telemetry streams and dropped final positions.
An expert live-drag option may later apply at one or two Hz using latest-wins
coalescing. A final pointer-up command is marked `final=true` and is never
coalesced away.

Accepted coordinates are quantized to a defined grid, initially 5 or 10 cm.
If geometry changes but integer applied SNR values do not, record a committed
RF no-op without creating a new medium generation.

For five APs and three bands, moving one client affects no more than:

```text
5 APs * 3 bands * 2 directions = 30 frequency-qualified link keys
```

That limit, and the fact that no unrelated keys change, is a tested invariant.

### Destination movement

Right-click **Move**, then choose a destination and speed. The server owns the
movement clock and emits fixed-time keyframes. Useful presets are 0.5 m/s,
1.2 m/s and 1.8 m/s. Pause, resume and cancel act on that server movement;
cancel freezes the last committed position.

RF rays are straight lines and may cross attenuation walls. A person's route
must eventually use a walkable visibility graph or room/door waypoints and not
pass through walls. The viewer draws movement paths and RF rays differently.
Until navigation geometry exists, free drag is explicitly labelled **RF
placement mode**.

### Presence

Disappear drives all links for the role below the usable threshold while
preserving its container and identity. Reappear recomputes links at its current
position and lets normal discovery/association occur. Container power cycling
is a separate expert lifecycle test.

## Canonical geometry

Geometry must not be duplicated from private helpers. Extract a public module,
for example `wmdcfg/geometry.py`, with pure functions for:

- position validation and quantization;
- distance and deterministic wall intersections;
- path loss and directed per-band SNR;
- affected links for a moved role; and
- position interpolation at a scenario time.

The Golden World compiler, RoomEngine and tests use this module. The browser
may use a JavaScript implementation for display-rate preview, but Python is
authoritative. Generated parity fixtures cover random positions, every band,
wall crossings and asymmetric source gains. State and evidence expose a
`geometry_model_hash` so version drift is detectable.

Wall endpoints, collinear motion and positions on a wall need deterministic
rules. Coordinates are quantized and placement is either rejected within a
small wall-clearance distance or snapped consistently to one side. Wall-loss
transitions must not flicker.

Link direction is explicit. The display keeps both:

- AP to STA predicted SNR, useful for downlink visualization; and
- STA to AP predicted SNR, relevant to an EasyMesh candidate AP hearing a STA.

## Measurement causality and optimizer gating

Every successful RF mutation starts a new `environment_epoch`. Telemetry from
an earlier epoch remains visible with age/stale status but is not actionable.

After a commit, the conductor:

1. marks previous measurements stale for optimizer use;
2. suspends action while drag or destination movement is active;
3. resets the hero client's policy hold state;
4. waits for an associated-link metric received after the RF apply;
5. waits for the position to remain stable for the settle interval;
6. starts candidate collection with the current revision and generation;
7. discards the complete result if either changes before completion; and
8. permits recommendation/action only from the fresh stable epoch.

A candidate observation records generation and revision at both start and end.
Mixed observations emit `observation.inconsistent_rf_epoch` and are never fed
to policy evaluation.

The UI makes latency part of the story:

```text
POSITION COMMITTED
RF GENERATION APPLIED AND VERIFIED
WAITING FOR FRESH CURRENT-LINK TELEMETRY
COLLECTING CANDIDATE MEASUREMENTS
POLICY HOLDING: 3.4 / 5.0 s
RECOMMENDATION READY
```

While a client is continuously moving, show current-link telemetry and perform
active candidate collection only at deliberate stable waypoints or after it
stops.

Controller access also needs one scheduler:

1. steering and verification;
2. active candidate measurement;
3. passive topology/client refresh;
4. full periodic health sample.

Passive polling pauses while an active candidate transaction owns the
serialized controller adapter. The viewer retains the last valid snapshot and
shows its age.

## Permanent visual truth layers

Never replace one measurement class with another. The inspector retains:

| Lane | Unit | Source |
|---|---|---|
| Predicted geometry | SNR dB | canonical room model |
| Applied medium | SNR dB and generation | wmediumd readback |
| Associated signal | RCPI and derived dBm | controller telemetry |
| Candidate signal | RCPI and derived dBm | EasyMesh candidate query |

Each has direction, timestamp and age. Predicted values are never relabelled as
measured values.

The room uses:

- a translucent ghost for local drag preview;
- a solid marker for the last authoritative position;
- a dashed modeled-best link;
- a solid controller-observed association;
- a distinct animated optimizer-target link; and
- a short RF-apply pulse between commit and fresh telemetry.

Association changes are attributed as `optimizer_steer`, `client_autonomous`,
`link_loss_recovery` or `unknown`. A BSSID change without an active steering
transaction emits `association.changed_uncommanded` and is never presented as
optimizer success.

## Private and IoT cohorts

Both networks are a permanent part of the presentation:

```text
private_ssid: 10 clients
iot_ssid:     10 clients, hidden
```

They use distinct shapes/outlines and fixed cohort colors. Signal quality uses
links, halos or gauges rather than changing identity color. The viewer offers
All, Private and IoT filters, persistent 10/10 counters, same-SSID candidate
counts and an explanation when a BSS is excluded for belonging to the other
network.

The initial capability matrix is:

| Operation | Private hero | Hidden IoT client |
|---|---|---|
| Drag/place | yes | yes |
| Destination movement | yes | yes |
| Predicted/applied RF | yes | yes |
| Current-link telemetry | yes | yes |
| Disappear/reappear | yes | yes |
| Optimizer recommendation | yes | optional observe-only |
| BTM actuation | yes | disabled until hidden-candidate steering is accepted |

The actuation restriction is enforced server-side. Once hidden-SSID directed
probe/BTM behavior passes its regression suite, enabling IoT action becomes a
manifest capability change rather than a new path.

## Presenter and engineering views

The same state stream supports two layouts.

Presenter mode emphasizes the hero client, actual/modelled/target links, a
small current-versus-target chart, traffic continuity, whole-lab health and
plain-language policy narration. Non-hero clients are dimmed, not removed.

Engineering mode adds top-down editing, exact coordinates, directional link
budgets, role/medium revisions, lease and movement state, candidate transaction
details, raw reason codes and measurement ages.

Both modes include accessible, redundant encodings: shape plus color, visible
focus, keyboard nudging, reduced motion and textual state. A rolling 60-120
second hero chart shows current RCPI, best measured target, threshold, actions
and association changes.

## Actuation boundary and transaction evidence

Actuation capability is immutable per process:

- a process started in recommend mode can never be elevated by a browser;
- an act-capable process requires the command-line safety confirmation; and
- the browser can arm one action for a short period, initially 30 seconds.

Movement leases never authorize steering. The action gate requires:

- act-capable run and live one-shot operator arm;
- no active movement;
- stable world revision and environment epoch;
- successful RF readback;
- fresh current and candidate measurements from that epoch;
- an eligible optimizer recommendation; and
- remaining action budget.

Before submitting, revalidate source BSSID, target SSID/band, target freshness,
revision/generation and absence of an uncommanded move.

The steering path should produce structured events with one transaction ID:

1. optimizer recommendation;
2. operator arm/confirmation;
3. Client Steering Request submitted;
4. 1905 ACK observed or unavailable;
5. BTM request observed or unavailable;
6. BTM response status observed or unavailable;
7. physical BSSID change;
8. controller ownership convergence;
9. traffic verification; and
10. cooldown.

Unknown stages remain explicitly unknown. Terminal strings are not parsed as
proof; `steer.sh` or its adapter should expose structured JSON events.

## State reducer and reconnect contract

`GET /api/demo/current` evolves to a normalized state rather than only “latest
event by kind”:

```json
{
  "schema": "easymesh.room-demo.state.v2",
  "run_id": "...",
  "run_state": "running",
  "clocks": {},
  "world_revision": 19,
  "environment_epoch": 7,
  "medium": {},
  "roles": {},
  "leases": {},
  "movements": {},
  "recording": {},
  "optimizer": {},
  "network": {},
  "capabilities": []
}
```

Events are reduced into this state. The same reducer drives live state, SSE
reconnect, replay, undo, override clearing and named snapshots. Replaying the
complete journal must reproduce the final state hash exactly.

The viewer keeps three positions per role:

- immutable `basePosition` from the scenario;
- authoritative `acceptedPosition` from reduced server state; and
- local `previewPosition` used only while interacting.

The loaded Golden World is never edited in place.

## Write API and security

Read-only observer access and operator mutation access are separate. Write
access uses:

- loopback binding by default and explicit LAN operator exposure;
- a random run-scoped bearer token printed or written by the CLI;
- same-origin mutation checks and no permissive CORS;
- strict `application/json`, a small body limit and unknown-field rejection;
- finite numeric and room-boundary validation;
- role allowlists and capability checks;
- idempotent `command_id` values;
- per-role movement leases with monotonic expiry; and
- `ETag`/`If-Match` world-revision concurrency.

Useful responses are:

| Status | Meaning |
|---|---|
| 200 | committed or duplicate result returned |
| 202 | command or movement queued |
| 409/412 | revision conflict |
| 410 | run no longer active |
| 422 | invalid state/position/path |
| 423 | role lease conflict |
| 503 | medium unavailable, restoring or contaminated |

Lease acquisition returns a `lease_id`. The client renews it explicitly every
few seconds using `POST /api/demo/interactions/lease/{lease_id}/renew`.
Expiration stops a destination movement, freezes the last committed position
and discards only local preview; it does not reset the room.

HTTP threads only enqueue commands. The serialized queue supports commands
such as `SetPosition`, `MoveRole`, `SetPresence`, `PauseMovement`,
`ReleaseOverride` and `ClearOverrides`.

## Audit, recording and replay

The audit journal is always on for the complete run. Start/stop recording only
selects the clip exported as scenario keyframes.

The journal records requested, duplicate, stale and rejected commands; lease
changes; commits and RF no-ops; medium generations; presence; movement;
telemetry; recommendations; actions; verification; reset and undo operations.

Events are hash-chained with `previous_event_hash` and `event_hash`. Completion
writes and prints a root evidence digest.

The unsimplified accepted-position stream is retained. Export simplification
must pin:

- presence transitions;
- wall-crossing changes;
- integer RF changes;
- predicted-best AP changes;
- optimizer eligibility/hold/action times;
- association changes; and
- operator annotations.

The exported scenario declares maximum position and RF error. It is recompiled
and compared with recorded applied generations before being accepted.

Three reset operations remain distinct:

- **Undo**: revert the last committed interaction;
- **Clear overrides**: return to base scenario state at current scenario time;
- **Stop and restore**: end the run and restore the pre-run RF baseline.

## Crash-resistant restoration

Before the first RF write, persist a checksummed recovery record, for example:

```text
/run/easymesh-room-demo/recovery.json
```

It contains run ID, medium instance ID, inventory/geometry hashes, captured
generation, baseline, touched keys, last committed generation and recovery
state. A recovery command and preferably a small supervisor or systemd
`ExecStopPost` path can restore after worker failure. Never restore a baseline
into a restarted or differently inventoried medium instance.

Normal SIGTERM, exceptions and completed sessions still restore through the
live `MediumSession`. SIGKILL/power-loss recovery is an explicit acceptance
case, not an assumption.

## Guided demonstration

Freeform control is useful for engineering; a presentation needs a repeatable
guided story. The first guide is **Office to living room**:

1. select the private laptop;
2. move it to the highlighted destination at normal walking speed;
3. wait for fresh current-link and candidate telemetry;
4. inspect the optimizer reason and optionally arm one action;
5. verify association, ownership and traffic; and
6. clear overrides or stop/restore.

A pause near the RF boundary deliberately exposes hold/hysteresis behavior.
One short second act can disappear/reappear an IoT sensor while preserving the
hidden IoT cohort. IoT remains observe-only until its steering acceptance gate
passes.

## Scale and atomic capacity

Client movement has a small bounded delta. Moving an AP at 100 clients can
require about 600 directed three-band fronthaul keys plus backhaul changes.
Before enabling gateway/extender movement, preflight verifies:

```text
required update count <= daemon atomic max_updates
```

If not, the UI disables that action and explains why. Splitting one conceptual
AP move across visible generations is not accepted as atomic behavior.

## Delivery phases

### Current implementation

The RDK interactive branch provides real RF application, exact baseline
restoration, server-owned destination movement, leases/revisions, presence,
recording/export, ordered SSE and a working room viewer. All 20 real clients
remain active.

The first Phase 0 foundation is now implemented:

- one actor-style `RoomEngine` serializes HTTP commands, autonomous movement
  ticks, medium mutations, readback, state snapshots and shutdown;
- command admission closes atomically, so work cannot be queued behind the
  terminal restore;
- all successful writes are idempotent by `command_id` and a repeated ID with
  different content is rejected;
- HTTP world mutations require an `ETag`/`If-Match` revision contract;
- same-origin checks and a random, run-scoped operator capability protect the
  mutation API independently of the movement lease;
- state schema v2 separates run/scenario clocks and reduces all role,
  movement, lease, medium, optimizer, network and health state;
- events are hash chained and the reduced state has its own digest;
- public canonical geometry is shared by compilation and live interaction;
- client coordinates are quantized to 5 cm, unchanged integer RF values are
  recorded as no-ops, and one client remains bounded to 30 directed keys;
- environment epochs prevent movement from being mixed with candidate
  measurement and reset the optimizer hold;
- unexpected medium instances/generations contaminate the run instead of
  being silently retried; and
- a checksummed recovery record is persisted before every RF write. The
  guarded `room-demo recover` command restores only the exact recorded medium
  instance and an allowed committed/pending generation.

Default dragging is preview-only with one RF commit on pointer-up. Remaining
foundation work includes complete intent/causation identifiers on every
derived event, explicit per-role rather than one-session leases, supervised
kill-recovery acceptance, and browser/Python geometry parity fixtures.

### Phase 0: ownership and state foundation

- Introduce `RoomEngine`, serialized commands and `MediumSession`.
- Extract the public canonical geometry module and parity fixtures.
- Add separate run/scenario clocks and state dimensions.
- Add world revision, environment epoch and complete causal identifiers.
- Implement normalized state v2 and one reducer for live/replay.
- Add idempotency, per-role leases/renewal and secure mutation authorization.
- Persist crash-recovery metadata before the first write.
- Reject unexpected external generations.

Exit criterion: all mutations are single-writer, replay reproduces the state
hash, stale/duplicate/faulted commands cannot advance the medium or world, and
kill recovery is demonstrable.

### Phase 1: preview-only interaction

- Top-down operator view and presentation view.
- Ghost dragging and server-side preview validation.
- Canonical directional geometry, walls and three-band link budget.
- Cohort identity, filters and 10/10 counters.
- No RF writes.

Exit criterion: preview is smooth, deterministic, accessible and incapable of
changing the lab.

### Phase 2: commit-on-drop live RF

- Private hero first, then all movable clients.
- Quantized pointer-up commit and RF no-op detection.
- Exact <=30-key client delta, atomic apply/readback and commit-after-readback.
- Presence/reappearance and telemetry settle state.
- Exact stop/restore and fault recovery.

Exit criterion: only intended keys change, controller measurement follows,
traffic stays within limits and restoration is byte-for-byte exact.

### Phase 3: guided movement and recommendation

- Server-owned walkable destination paths and speed presets.
- Pause/resume/cancel and stable measurement waypoints.
- Controller scheduler and environment-epoch observation guard.
- Current/candidate history chart and human-readable reasons.
- Recommendation only.

Exit criterion: the guided story consistently reaches a fresh, stable,
auditable recommendation without mixed-epoch measurements.

### Phase 4: one confirmed action and complete replay

- Immutable act-capable run and 30-second one-shot browser arm.
- Structured EasyMesh/BTM transaction events.
- Reassociation attribution and pre-action revalidation.
- Physical, controller and traffic verification.
- Hash-chained audit, final digest and replay equivalence.

Exit criterion: at most one request-only BTM action produces a fully explained
verified outcome, and replay reconstructs it without RF writes.

### Phase 5: recording and hybrid takeover

- Base-plus-overlay composition through the same engine.
- Resume/rejoin/remain-manual transitions.
- Separate scenario/run clocks under pause and takeover.
- Significant-event-preserving simplification and export validation.
- One-command replay regression.

Exit criterion: an improvised path can be exported and replayed with declared
position/RF tolerances and identical final reduced state.

### Phase 6: full-room controls and scale

- Gateway/extender motion after atomic-capacity preflight.
- Backhaul effects, doors, walls and interference regions.
- Traffic controls, named snapshots and undo/redo.
- 20-, 50- and 100-client capacity and UI tests.

Exit criterion: all controls remain bounded, atomic and understandable at each
supported scale.

## Acceptance tests

The release gate includes unit, fake-medium, integration, browser and live
tests. It proves at least:

- one client changes exactly its expected directed frequency keys and no
  unrelated key;
- stale revision and duplicate idempotency keys produce no extra generation;
- lease acquire/renew/expire/conflict and final pointer-up semantics;
- readback mismatch does not commit state;
- unexpected generation or medium restart contaminates the run;
- movement invalidates an in-flight candidate cycle and resets hold;
- no BTM can be sent while movement is active;
- IoT cannot be actuated while observe-only;
- private and IoT candidate inventories never cross SSID boundaries;
- SSE reconnect reconstructs every role, lease, movement and presence state;
- replay reaches the same final reduced-state hash as live operation;
- SIGTERM and supervised worker death restore the exact eligible baseline;
- browser ghost and authoritative position remain visually distinct;
- presenter and engineering layouts pass visual regression and accessibility
  checks;
- all 20 clients remain present as 10 private plus 10 IoT;
- act mode produces no more than one action; and
- a complete run ends with 5 devices, 15 radios, 50 BSS entries, at least 24
  associations, passing traffic and zero monitored service restarts.

## Completion definition

The room demo is complete when an observer can follow, without hidden repair
steps:

```text
intent -> geometry -> applied RF -> fresh telemetry -> optimizer reason
       -> optional bounded BTM -> verified network result -> exact restore
```

Every arrow must be backed by separately labelled live state and replayable
evidence. That causal clarity is more important than adding additional knobs.
