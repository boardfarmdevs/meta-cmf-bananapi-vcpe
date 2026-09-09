# Room playback: what to watch in both views

This is a viewing and acceptance guide for all 14 Golden Worlds in the source
catalog for the fixed-pool RDK lab. It describes expectations from the checked-in world
plans and the live playback implementation, **not a claim that every room has
passed a complete live playback test**. Loading a room and checking its initial
convergence is not sufficient: inspect network topology while Play is running,
at presence transitions, and again after motion stops.

## Which room is most interesting?

**Choose `home-b-slow-walk-ten` for the richest guided demonstration.** Ten clients
cross the house while ten remain fixed, and the off-centre gateway makes two
backhaul branches preferable to a star with the RDK adaptive-backhaul policy.
It demonstrates the distinction between client roaming and extender parent
selection. First let the backhaul settle at time zero; then alternate Play with
Pause-and-settle checkpoints as explained below.

For a first presentation, choose **`home-a-private-client-room-walk`**, the
default. Its four-minute, single-client path is easier to narrate, using Pause
at the waypoints for steering. **For simply pressing Play and watching native
topology change without pauses, `home-a-flash-crowd` is the best choice:** its
online roster changes 10→20→10. `home-a-disappear-reappear` is the smaller,
easier-to-audit alternative.

For a short guided roaming demonstration, choose **`home-a-one-client-handover`**
(20 seconds of playback, one walker), or **`large-room-perimeter-counter-roam`**
(60 seconds of playback, two opposite-direction walkers). The latter pauses
automatically at 14, 28 and 42 seconds so real steering can catch up: wait for
verified associations in both views, then press Play to continue. These pauses
add wall-clock time; the demo does not promise a complete lap of verified
handovers in one minute. The existing Disappear/Reappear, Extender Loss/Recovery
and Fast Transit rooms are retained, not duplicated under new names.

**0907 candidate qualification caveat (7 September 2026):** Home B reached the
two intended backhaul branches but did not pass complete client best-AP
convergence within the 600-second loaded-state test. It is the most interesting
scenario to investigate, not an unqualified claim of successful acceptance on
that candidate. The published rev140 lab was left unchanged. Full Play coverage
must still be recorded separately from these loaded-state tests.
The published 0906 Home B lab did show 20 converged clients and both branches
in a read-only check; that is an initial-state observation, not a full Play pass.

**Perimeter capture (8 September 2026 UTC):** the isolated rev140 RDK candidate,
with the new quick-scenario source overlay, completed the entire perimeter
playback. At 0/14/28/42/60 seconds, both views agreed on the expected walker APs,
12 clients were healthy, and the saved fleet snapshots were fresh and converged.
All eight moving-client handovers were verified. The side-by-side MP4 is
`/home/rev/Videos/easymesh-perimeter-side-by-side-0907.mp4` on rev150 and rev140
(also available as `.webm`); raw snapshots
and the recording report are under `/home/rev/work/quick-demo-scenarios-0907`.
Its 10:24 runtime includes convergence waits. This is a browser capture, not a
precision wall-clock benchmark or a full-play pass for the other rooms.
An earlier strict preparation timed out with a background client's dwell counter
stuck at zero; the video retains that warning rather than claiming it was fixed.
The published 0906 lab and immutable thin archives were not changed.

### Suggested Home B walkthrough

1. Load Home B and keep it paused at zero. Wait for 20 clients, complete fresh
   measurements, and the two actual backhaul branches illustrated below.
2. Match one walking client's MAC in both views and Ctrl-click it for the
   traffic probe. Note its current AP and signal before moving.
3. Press Play. Watch its floor-plan path and changing link signal alongside
   the native topology; do not mistake a changing dashed candidate line for a
   completed association change.
4. Pause around 30 seconds. Wait for fresh candidate evaluation and any
   verified steering, then confirm the same client's actual AP in both views.
5. Resume to completion and repeat the settled check. The fixed backhaul
   branches should persist while client associations adapt to the final positions.

## Important: what Play currently does and does not do

Both the room scene and native Network Topology offer **Full screen**. The room
keeps Play/Pause and its scenario clock in a floating toolbar; topology retains
its layout/export controls and refits the same node positions to the new bounds.
Use **Exit full screen** or Esc to return. These are presentation-only controls:
they do not acquire a lab lease or write RF. Embedded frames must explicitly
allow fullscreen. Unsupported/denied requests are reported rather than simulated
by hiding browser chrome.

The later [fast-steering overlay](room-fast-steering-0907.md) removes the
blanket Play gate described below. It attempts generation-consistent
measurements while playing, prioritizes both walkers, and has no blocking
highlight or pre-action hold/dwell. Continuous changing RF can still invalidate
a collection, so the explicit corner checkpoints remain useful. The following
limitation describes the earlier recording/baseline, not that new overlay.

**Earlier Live Play moves devices and applies presence/RF changes, but
suspends automatic client steering and adaptive-backhaul optimization.** This
is an implementation boundary, not just slow convergence:

- Playback reports `movement_active` while its status is `playing`, even in
  Stationary or during a scripted wait at one position.
- The conductor defers fresh candidate evaluation while movement is active;
  it also rejects observations that cross RF/revision changes. The backhaul
  manager likewise requires settled RF and no active movement.
- Passive topology, actual-link telemetry and signal reporting continue.
  Explicit appearance/disappearance still changes the real lab, and clients
  can disconnect/reconnect or roam through their own Wi-Fi behavior. Those
  changes must not be mislabeled as optimizer-issued BTM actions.
- **Pause**, then allow fresh measurement, hold/cooldown and any verified
  actions to finish, to demonstrate optimizer-driven reassociation. Script
  completion also clears active playback, allowing optimization to resume.

Therefore, the roaming expectations in this guide apply at the **settled
checkpoints**, not as a promise of continuous BTM steering while Play remains
active. A lower-signal client staying on its current AP during Play can reflect
this guard, rather than a reporting failure. It still needs investigation if
it remains there after Pause with a fresh, actionable better candidate.
An earlier “stable” result or an enabled “Auto BTM” mode is not evidence of a
new steering action: check the event timestamp, current RF epoch and verified
source/target association.

If the desired acceptance requirement is "automatic optimization continues
throughout uninterrupted motion", the current implementation does **not** meet
it. Record that as a feature gap, not a passed test. Continuous steering would
need changes to observation/actuation consistency handling, not simply removal
of a visual indicator or a claim that the animation proves optimization. This
document does not change that behavior.

The perimeter scenario uses explicit signed `pause_at_ms` checkpoints to work
with this guard, not bypass it. At each checkpoint the server first commits and
verifies the new RF, then pauses the clock and clears playback movement activity.
No automatic timer resumes it and no AP is forcibly assigned. The checkpoint
message asks the operator to inspect both views and press Play when ready.
The disconnected preview stops at the same times but cannot verify real roams;
evidence replay follows recorded events instead. Other existing worlds keep
their original uninterrupted playback behavior. Checkpoints are viewer controls,
not timed pauses in a raw exported `.wmd` RF sequence.

## Set up the two views

On the published rev140 lab, open these side by side:

- Room: `http://192.168.2.140:18891/viewer/?mode=interactive`
- EasyMesh WebUI: `http://192.168.2.140:18889/`, then **Network Topology**.

Use the same lab in both windows. A release candidate on temporary ports is a
different lab: do not compare its room with the published lab's topology.
Wait for lab provisioning and initial health checks before starting inspection.
NO CONNECT is a simulation preview, not evidence of real associations.

1. Select the world; selection automatically applies its initial RF and online
   client subset. There is no separate Apply step.
2. Leave it paused at zero until the expected client roster appears, measurements
   are complete/fresh, and any backhaul changes settle.
3. Match devices between windows by MAC address and bound role, not screen
   position. `extender_1` is a world role, not a guarantee of the current
   `Extender-1` display label. The controller's names can differ from world-role
   numbering. Client `sta-xx`/`iot-xx` suffixes are identities, not row numbers.
4. Press **Play** and watch both windows. Keep the controlling room tab open.
   Do not drag or change presence during a scripted acceptance run: those
   actions override that role's remaining script. Reload to clear overrides.
5. At the checkpoints below, note room time, expected/actual clients, actual
   parent/AP, signal age and optimizer reason. Pause briefly when a transition
   needs a clear before/after comparison; resume for the rest of the script.
6. At completion, allow measurement and steering to settle again. Save failures
   before reloading, and restore the original world when testing finishes.

Times in this guide are **room playback time**, not elapsed wall time. Live
playback advances through serialized, verified RF writes and may run slower
under load. Pause freezes scripted motion, not telemetry or optimization.
Goldens are sampled before their nominal end: most 60-second rooms have their
last stored frame at 58 seconds, fast transit at 29 seconds, the default at
235 seconds, and extender recovery at 88 seconds. The final sample is held to
completion; do not require the unrecorded final waypoint to be reached exactly.

## Read the views correctly

| Room view | Network topology | Interpretation |
| --- | --- | --- |
| Client position/trail changes | Its drawn location need not follow the floor plan | Topology describes connectivity, not physical position. |
| Strongest simulated-link indication changes | The current association may initially stay put | A candidate is not a successful roam. Check the actual AP/BSSID and a verified event. |
| Actual client link changes AP | That same MAC moves into the new AP's matching `"private"` or `"iot"` bubble | After normal reporting delay, both views must agree; no duplicate old association should remain. |
| Solid backhaul line changes parent | The corresponding extender's actual parent edge changes | This is a real backhaul association, not client BTM. The thin dashed peer line is only the strongest simulated local link. |
| Client becomes unavailable | Its associated-client node disappears after withdrawal is reported | The container remains running. Reappearance must restore the same identity, not add a new client. |
| Extender shows fronthaul disabled | Extender and its backhaul remain; its served clients leave | This models loss of client-serving RF, not a powered-off mesh device. |
| Signal bars become grey | Corresponding stale/unknown readings must not remain brightly fresh | Grey is unavailable/stale, not zero SNR. A short roam gap can be legitimate; persistent fleet-wide grey is not convergence. |

Both views use the shared red/yellow/green meter with grey unlit bars. The
measured uplink meter is based on RSSI; the separate `RF … dB` indication is
verified applied wmediumd SNR, and strongest-link previews are simulation
predictions. Do not equate these three values or expect all clients to become
fully green. Walls, band, eligibility and the actual uplink still matter.

Backhaul lines lie on the floor, use the upstream AP's colour, and remain
visible through walls with the obscured part lightened. A dashed line beside
an extender's actual link can point elsewhere without proving a fault: the
strongest immediate peer is not necessarily the best loop-free route to the
gateway. Selecting a preview band or band-based link colours does not retune
radios or force cross-band steering.

The permanent pool is **20 client containers and five AP containers**, with
**six mesh nodes** in native topology: Controller, Agent-1 and four extenders.
Smaller worlds make some clients radio-offline; they do not resize or stop the
container pool. All rooms below retain the six-node mesh.

## Room catalog at a glance

Client counts are intended online/associated counts after reporting settles,
not the number of running containers. Intervals are start-inclusive.

| World selector | Room duration | Online clients | Main inspection |
| --- | ---: | --- | --- |
| `home-a-private-client-room-walk` / default | 240 s | 20 throughout | One narrated roaming client; other 19 remain fixed. |
| `home-a-stationary` | 60 s | 10 throughout | Stable baseline; no artificial churn. |
| `home-a-slow-walk-ten` | 60 s | 20 throughout | Ten crossing clients, ten fixed reference clients. |
| `home-b-slow-walk-ten` | 60 s | 20 throughout | Same movement with shifted AP geometry and branched backhaul. |
| `home-a-band-walk-small` | 60 s | 10 throughout | All ten selected clients move; compare eligible same-band APs. |
| `home-a-border-hover` | 60 s | 12 throughout | Two clients repeatedly cross wall/coverage boundaries. |
| `home-a-fast-transit` | 30 s | 12 throughout | Two fast clients; inspect lag and final recovery. |
| `home-a-flash-crowd` | 60 s | 10 → 20 at 20 s → 10 at 50 s | Burst appearance and complete withdrawal. |
| `home-a-disappear-reappear` | 60 s | 12 → 11 at 16 s → 10 at 24 s → 11 at 32 s → 12 at 40 s | Identity-preserving departure and return. |
| `home-a-extender-loss-recovery` | 90 s | 10 throughout | One extender's fronthaul absent from 20 to 60 s. |
| `home-a-asymmetric-link` | 60 s | 11 throughout | One cross-house client; live asymmetry limitation described below. |
| `home-a-one-client-handover` | 20 s | 11 throughout | One wall crossing, then verified steering after completion. |
| `large-room-perimeter-counter-roam` | 60 s + checkpoint waits | 12 throughout | Two opposing perimeter laps, four extender regions, three automatic pauses. |

## What should happen in each room?

### 1. Default: private-client-room-walk

**Room:** Only `sta_mobile_01` walks. It waits at `(3,2)` through 30 s, passes
near `(9,3)` at 90 s, `(13,6)` at 140 s and `(17,10)` at 180 s, then approaches
the lower-right corner. The nine other `sta_mobile_*` roles do not move in this
world; neither do the ten `sta_static_*` roles.

**Topology:** Follow that client's MAC from the upper-left serving region,
through the central region, toward the lower-right region. Its real AP should
change when fresh eligible measurements justify it, preserving the private
SSID cohort and a single association. The other 19 clients provide a stable
reference. Home A's centred gateway normally favours a stable star; this walk
does not move the extenders and should not cause repeated backhaul changes.

**Check:** 0, 30, 90, 140, 180 and 240 s. Ctrl-click the walking client for the
traffic probe. Expect possible brief handover disturbance, not a promised
zero-loss roam or a predetermined handover second.

### 2. Stationary

**Room:** Ten fixed clients; the clock runs but nobody walks.

**Topology:** Ten client identities remain. Initial paused optimization may
redistribute them, then associations and mesh parents should settle. Play still
sets the optimizer's movement guard even though nobody walks. Fresh metrics must
continue even when positions do not change. This is the best room for detecting
stale reporting, duplicates or unnecessary steering unrelated to motion.

**Check:** 0, 30 and 60 s, plus a paused soak. Repeated back-and-forth association
changes without a material RF/eligibility change warrant investigation.

### 3. Home A slow-walk-ten

**Room:** Ten mobile clients cross horizontally, vertically and diagonally;
ten clients remain fixed. Several walkers pass through the central region at
about 30 s. The APs remain at the four corners and centre.

**Topology:** At paused checkpoints, mobile identities should redistribute
between the relevant AP regions as measurements and steering catch up. Fixed clients should be much
quieter. Expect 20 clients throughout, not 10: “ten” counts the walkers.
The centred star should normally remain stable while client edges change.

**Check:** 0, 20, 30, 40 and 60 s. Pause near the middle and after completion
to distinguish transient steering lag from persistent wrong associations.

### 4. Home B slow-walk-ten — recommended

**Room:** The same ten walking paths and ten fixed clients as Home A, but the
gateway is at `(4,7)`. The upper pair of extenders is at `(10,2)` and `(17,3)`;
the lower pair is at `(9,12)` and `(18,11)`.

**Topology:** With the 0907 RDK adaptive-backhaul policy and unchanged geometry,
the expected parent relationships are:

```text
Controller ─ Agent-1 / gateway
               ├─ extender_1 (10,2) ─ extender_2 (17,3)
               └─ extender_3 (9,12) ─ extender_4 (18,11)
```

These are **bound role IDs**, not assumed display numbers. Check the live
role/MAC/name mapping before describing an “Ext-3 to Ext-4” connection.
For the upper-right role, the direct 5 GHz score is 20 dB; the route through
the upper inner extender scores `min(31,25) - 3 = 22`. The 0907 threshold admits
that 2 dB improvement. The extra-hop penalty is a heuristic, not a throughput
prediction. See [adaptive backhaul](room-adaptive-backhaul-0906.md).

Let those two branches settle before Play. At paused checkpoints after walking,
expect client associations to adapt, **not the fixed mesh to oscillate between
star and branches**. A child extender may remain on a relay whose immediate signal is
not its absolute maximum if that is the valid, stable gateway-rooted route.

**Check:** The settled time-zero tree, 20/30/40 s client distributions, and the
final settled tree. Compare actual edges in both views, not just dashed
predictions. This expectation requires `adaptive-rdk`; it is not a claim that
native EasyMesh or the prplMesh lab implements this RDK-specific adapter.

### 5. Band-walk-small

**Room:** All ten `sta_static_01..10` roles move across the house. The role prefix
is an identity convention, not a guarantee of immobility. There are no extra
ten mobile-role clients online in this world.

**Topology:** Ten clients redistribute while keeping their provisioned cohort
and supported/operating band constraints. The current live client optimizer
evaluates eligible same-band APs; neither the room name nor the preview-band
selector promises automatic 2.4↔5↔6 GHz band switching. Inspect actual radio
properties when comparing a simulated strongest link with a real association.

**Check:** 0, 30 and 60 s. Do not fail this room merely because no band change
occurs; fail a persistent poor same-band association after stable, complete
measurements show an actionable better candidate.

### 6. Border-hover

**Room:** Two additional clients move back and forth between x=5.4 and 6.6 at
y=4, and between x=13.4 and 14.6 at y=10. They reverse every 10 s, crossing the
wall boundaries at x=6 and x=14. Ten reference clients remain fixed.

**Topology:** Maintain 12 identities. Signal may change sharply at a wall,
even though the movement is small. During Play, expect the movement guard;
after Pause, the optimizer should explain a hold, settling/cooldown or a
justified steer rather than blindly follow every
instantaneous geometric winner. Some roams can be legitimate: wall loss is a
real model change, so “absolutely no handovers” is not a valid pass condition.

**Check:** Just before/after wall crossings and at 10/20/30/40/50 s reversals.
Pause on one side; associations should settle rather than keep ping-ponging.

### 7. Fast-transit

**Room:** Two clients cross long distances and reverse direction at 10 and
20 s. The other ten remain fixed. The whole script lasts only 30 s.

**Topology:** Twelve identities remain, but actual associations can trail the
moving strongest candidates. The current optimizer does not steer during Play;
Pause or completion is required for it to evaluate and act. A full fleet
measurement/steering cycle also takes longer than a simple animation tick.
Chasing every waypoint is not required, and
the fastest-looking animation is not proof of good steering.

**Check:** 0, 10, 20 and 30 s, then stop motion and inspect recovery. Persistent
missing measurements or wrong eligible APs after the room is stable is a
problem; temporary disagreement during rapid motion is not sufficient proof.

### 8. Flash-crowd

**Room:** Ten fixed clients start online. At 20 s, ten additional clients appear
in two rows near the centre, x=7..11 and y=6/8. At 50 s they all leave again.
This is an appearance burst, not ten clients walking into the room.

**Topology:** Counts should settle to 10, then 20, then 10. The newcomers should
join suitable AP/cohort bubbles, generally in the central serving region, but
not necessarily an equal load split. Their exact same MACs must disappear on
departure without ghost nodes or duplicated associations. Six mesh nodes and
25 running containers remain throughout.

**Check:** 0, just before 20, shortly after 20, 40, shortly after 50 and 60 s.
For an acceptance check, pause after arrival and departure long enough to
confirm both exact rosters; otherwise a slow observer may miss the short burst.

### 9. Disappear-reappear

**Room:** The two changing clients stay at `(4,4)` and `(16,10)`; only presence
changes. Ten reference clients remain online.

| Room time | First changing client | Second changing client | Expected clients |
| --- | --- | --- | ---: |
| 0–16 s | Present | Present | 12 |
| 16–24 s | Absent | Present | 11 |
| 24–32 s | Absent | Absent | 10 |
| 32–40 s | Present | Absent | 11 |
| 40–60 s | Present | Present | 12 |

**Topology:** Remove each absent client's actual association, then restore the
same MAC on return. A returning client is not required to use its old AP if a
better eligible AP exists. Missing clients must not leave fictitious fresh
signal bars or stall the expected-online-client measurement denominator.

**Check:** Pause immediately after 16, 24, 32 and 40 s to confirm each roster.
A traffic probe selected on an absent client should indicate unavailability,
not silently switch to another client or report fabricated successful traffic.

### 10. Extender-loss-recovery

**Room:** `extender_4` at `(18,12)` loses fronthaul service at 20 s and regains it
at 60 s. Ten clients remain logically present for the full 90 s.

**Topology:** Clients served by that extender must leave its fronthaul and
reassociate to available APs, then reconsider it after restoration and a paused
or completed playback checkpoint. Brief
client-count dips during real reassociation are possible; the steady target
is ten. The extender itself and its backhaul should remain visible and alive,
including a valid uplink meter when fresh measurements exist.

This is **not a full extender power failure or backhaul outage**. Live extender
presence deliberately preserves mesh/control RF. Do not expect removal of the
mesh node, a zeroed backhaul meter, or mandatory mesh-tree restructuring.

**Check:** 0, shortly after 20, 40, shortly after 60 and 90 s. Verify no clients
remain associated to disabled fronthaul once withdrawal settles. Restoration
does not mean every client must return; only those with a justified candidate.

### 11. Asymmetric-link

**Room:** One client crosses `(3,7)` → `(10,7)` at 30 s → toward `(17,7)`, with
ten fixed reference clients. The source mobility definition gives this client's
transmitter a −7/−10/−12 dB gain adjustment for 2.4/5/6 GHz respectively. The
compiled Golden World therefore intends weaker client-to-AP than AP-to-client
RF, useful for illustrating why a strong downlink alone is insufficient.

**Important current live limitation:** Interactive RF recomputation constructs
nodes from the layout, while those gain adjustments live in the mobility
definition. World loading and movement recompute directed links from those
layout nodes, rather than carrying the mobility-only transmitter gains into
the live model. Consequently, **do not claim that pressing Play currently
proves the intended uplink asymmetry**. It remains an 11-client moving-room
exercise unless directional applied RF is independently verified. This guide
does not implement an asymmetry fix.

**Topology:** Eleven identities and a moving client's actual associations can
still be checked. Topology is not a two-direction RF chart: one signal meter
cannot establish the intended directional imbalance. Mark asymmetry validation
as unsupported/not demonstrated, rather than passing it from appearance alone.

### 12. One-client-handover — shortest guided roam

**Room:** Ten clients remain fixed. `sta_mobile_01` starts at `(2,2)`, waits for
two seconds, crosses the hall-west wall at x=6 and reaches `(10,3)` at 18 s.
The endpoint is held through completion at 20 s, rather than being truncated
before arrival. Ctrl-click the walker to select its traffic probe.

**Topology:** Start from a settled association to role `extender_1`. At the
final position, `gateway` / Agent-1 is the strongest simulated eligible AP on
all three bands. Once playback completes, allow fresh measurement and verified
steering to move that same client into Agent-1's corresponding SSID bubble.
The total remains eleven and all six mesh nodes remain. Do not claim a BTM
action during motion or a guaranteed zero-loss handover.

**Check:** Loaded and settled at 0 s; moving across the wall; final position at
18–20 s; then settled actual source/target BSSID and traffic after completion.

### 13. Large-room perimeter counter-roam — two opposing laps

**Room:** An open 40×40 m room has Agent-1 at `(20,20)` and extenders at
`(4,4)`, `(36,4)`, `(4,36)` and `(36,36)`. Ten background clients stay fixed.
`sta_mobile_01` follows the outer square, 2 m from the room edges; `sta_mobile_02`
travels in the opposite direction, 3 m from the edges. The separate lanes keep
them from occupying the exact same point when they meet. Neither path cuts
diagonally across the room. Both return to their start at 56 s and hold until
completion at 60 s.

**Topology:** After each settled checkpoint, expect these actual extender
associations, subject to successful eligible steering. Numbers here are bound
role suffixes, not assumed controller display labels:

| Room time | Walker 1 expected AP | Walker 2 expected AP | Playback action |
| --- | --- | --- | --- |
| 0 s | `extender_1` | `extender_1` | Wait for initial convergence, then Play. |
| 14 s | `extender_2` | `extender_3` | Automatic pause; verify both roams, then Play. |
| 28 s | `extender_4` | `extender_4` | Automatic pause; two distinct clients, one serving AP. |
| 42 s | `extender_3` | `extender_2` | Automatic pause; verify that the walkers exchanged sides. |
| 56–60 s | `extender_1` | `extender_1` | Return to start; settle after completion. |

Expect twelve identities throughout, with no duplicate old owners after a
handover. Corner RF gives the expected extender a clear simulated advantage;
mid-edge candidates can tie or change before the real association follows.
The mesh nodes themselves do not move. A stable star is appropriate for this
centred, open geometry; roaming does not require a backhaul parent change.
Keep both windows open and follow the two MAC addresses, not just animated
line colours. A paused checkpoint is an opportunity to verify convergence,
not an assertion that it has already occurred. If a real steer fails, retain
the checkpoint and inspect the reason rather than automatically continuing.

## Acceptance and fault triage

### Recorded playback spot-check

On the rev140 0907 candidate on 7 September 2026, a real browser selected Flash
Crowd, pressed Play, completed the script and restored the default world.
The native topology rendered 10 clients before Play, 20 at room time 28 s, and
10 at 53 s; exact MAC rosters matched the room's present roles, with six mesh
nodes and no duplicate client associations at those checkpoints. Screenshots
were inspected from both views. The optimizer reported `movement_active`
while playing, as described above.

**This was a presence/native-graph spot-check, not complete synchronized-health
acceptance:** at the arrival screenshot the room's health counter still showed
10/20, and at the departure snapshot it showed 13/10 while native topology had
already withdrawn those clients. Those captures establish reporting lag, not
its eventual duration. Pause and confirm the room counter catches up before
marking the telemetry check passed. Full playback of the other ten rooms was
not established by this test. Candidate release blockers remain separate from
this successful roster transition.

### Per-room acceptance checklist

A complete result records three distinct stages for **each room**:

1. **Loaded, paused at zero:** correct roster, six mesh nodes, fresh complete
   measurements and a settled valid backhaul tree.
2. **Play actually pressed:** advancing room time and the documented motion or
   presence transitions; inspect the native topology throughout. Checkpoints
   must include both sides of each presence change, not just the final frame.
3. **Final paused/completed state:** exact expected roster, no duplicate/stale
   owners, valid actual parents in both views, fresh measurements, and eventual
   client convergence or an explicit legitimate eligibility/hold reason.

Use a separate live/replay recording or screenshots for both views. One viewer
opening successfully is not a per-room playback pass. Keep polling modest;
do not launch competing optimizers or many metric-query clients to observe a
small lab. The existing `gen/tests/room-world-switch-smoke.py --all-worlds`
checks loaded-room convergence and presence changes; **it does not press Play
through every room or visually inspect topology throughout playback**. Record
that coverage separately rather than treating it as equivalent.

Check the remaining action budget before a long sequence of demonstrations.
Client steering and adaptive backhaul have separate bounded action counters;
loading another world does not imply a fresh session budget. Budget exhaustion
is a safety stop, not successful convergence. Record it and arrange a controlled
new session before continuing acceptance, rather than repeatedly clicking Play
or silently removing the guard.

Suggested observation sheet:

| World/run ID | Room time/event | Expected/actual clients | Room actual AP/parent | Native AP/parent | Signal freshness | Optimizer reason/action | Result/evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| … | Loaded / Play / transition / completed | … | … | … | … | … | … |

If a client appears stuck, pause motion first and inspect its current band,
SSID eligibility, fresh candidate snapshot and actual source/target BSSID.
Allow a complete measurement cycle plus the reported hold/cooldown; do not
invent a universal fixed convergence time. Repeated HTTP 504s, incomplete
candidate snapshots, fleet-wide stale meters, failed verified moves or a
persistent actual-parent disagreement are failures to investigate—not an
acceptable “stable” result. Save the error and recent events before retrying.

Read-only supporting snapshots are available from `/api/demo/current`,
`/api/demo/interactions` on the room server, and `/api/v1/topology` and
`/api/v1/clients` on the matching native WebUI. Capture the run ID and room time
with each snapshot so an old measurement is not mistaken for the current frame.

## Large-room extender evacuation

`large-room-extender-evacuation` uses twelve stationary clients and five APs in
a 40×40 m room. Before Play, wait for `sta_static_01` through `sta_static_08` to
associate with extender role 1 at (8,8). Four background clients remain around
the other corners. Match actual display names to roles; they need not share
the same numbering.

At 0–4 seconds the extender stays put. At 4–18 seconds it moves to (36,32),
away from the eight-client cluster, and stays there through completion at 20
seconds. Clients, SSIDs, bands, role identities and presence do not change.
The initial extender advantage and final Agent-1 advantage are tested on all
three bands. The stimulus changes RF only; the room script never selects an AP.

Watch the move in room full screen, then switch to topology full screen as the
optimizer resumes after completion. Expect the eight actual client icons to
leave the moved extender for Agent-1, with the same twelve-client roster still
present after settling. In the room, their solid actual links should agree with
those associations. The moved extender's own uplink may prefer nearby extender
role 4, producing a branch; use observed backhaul, not the thin dashed strongest
peer, to judge it. Return to side-by-side views for the final cross-check.

Steering waits are extra wall-clock time. Grey measurements, missing clients,
failed BTM verification or a persistent wrong AP after completion must be
reported, not edited out or called convergence. This scenario does not disable
an extender or force reassociation through a test-only API.

The isolated rev140 capture on 8 September 2026 UTC verified all eight cluster
identities moving from display name Extender-4 to Agent-1, with twelve clients
present and unchanged client positions/SSIDs/presence. The 3:21 MP4/WebM is
`/home/rev/Videos/easymesh-extender-evacuation-fullscreen-0907.{mp4,webm}` on
rev140 and rev150. It includes real full-screen transitions in both views and
ends side by side. This is an association/presence pass, not a complete fresh
fleet snapshot: the final fleet was still being remeasured. The recorded
backhaul remained a star, so this capture does not demonstrate the optional
branch. The default twenty-client world was restored afterward.

## Source of these expectations

- Catalog and sampled states: `gen/wmediumd/configurator/worlds/golden/*.world.json`.
- Paths, presence intervals and intended gain adjustments:
  `gen/wmediumd/configurator/worlds/mobility/*.json`.
- Floor plans: `gen/wmediumd/configurator/worlds/layouts/*.json`.
- Live selection, interpolation, manual overrides and fronthaul-only presence:
  `gen/demo/room_demo/worlds.py` and `gen/demo/room_demo/interactions.py`.
- [Fixed-pool world switching](live-world-switching.md),
  [backhaul policy](room-adaptive-backhaul-0906.md), and
  [reporting diagnostics](reporting-and-optimizer-diagnostics-0906.md).

The movement/presence scripts can also inform prplMesh demonstrations, but
verify that lab's installed catalog, identity binding and steering features.
Do not transfer the RDK-specific branched-backhaul acceptance claim to prplMesh
without equivalent control and real-parent evidence.
