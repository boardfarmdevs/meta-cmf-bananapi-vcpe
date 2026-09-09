# Room observation and rendering latency: rev140

The earlier [fast steering work](room-fast-steering-0907.md) does **not** mean
that everything outside the BPI EasyMesh implementation is instantaneous. This
audit finds and removes additional head-of-line blocking in the room's passive
observer, client probes, native topology browser and Three.js viewer. It does
not change the native controller/agent binaries or relax measurement identity.

## Deployment boundary

Only rev140's isolated RDK candidate `rdkeasymesh-20-0907` is updated:

- Room: `http://192.168.2.140:48891/viewer/?mode=interactive`
- Native topology: `http://192.168.2.140:48889/`
- Guest source: `/home/easymesh/git/meta-cmf-bananapi-vcpe`
- Native browser script, inside `bpibroadband`: `/nvram/static/script.js`
  and its persistent image seed `/usr/ccsp/EasyMesh/static/script.js`.

Python changes require restarting `easymesh-room-demo`; browser changes require
a page reload. No native BPI service is restarted. Published 18889/18891,
prpl labs, other hosts' running labs and the immutable 0907 thin archives are
not updated or promoted by this work. The shared source and recipe patches are
retained for future builds; this is a working overlay, not a new thin release.

## Weaknesses and corrections

### Associations waited for unrelated measurements

The old room network observer fetched topology, clients, devices and BSSes in
sequence, then refreshed stale client measurements, and only then published
the association graph. It slept another two seconds after finishing. A slow
metric response or client probe delayed even an already visible native
association. An incomplete metrics inventory could also temporarily omit a
client that was still present in native `STAList`.

The interactive association worker now reads only `/api/v1/topology` and
publishes its actual `STAList`. It targets a one-second start-to-start cadence,
accounting for collection time rather than adding a full sleep after work.
`network.snapshot.collection_seconds` makes that collection cost visible in
the evidence. Empty controller topology and duplicate ownership are errors;
world geometry is never used to invent an association.

A separate background worker obtains serving measurements. Missing or late
measurements cannot delete clients from the authoritative native roster. A
metric can join an association only when MAC, BSSID, band and SSID agree and
its original timestamp passes the relevant RF-change boundary. Unknown signal
on a newly observed AP is preferable to displaying the previous AP's signal.

### Display reads queued behind medium transactions

The room's normal `RoomEngine.snapshot()` is an actor command: it can expire a
lease and must obey mutation ordering. Using it on the association display
path queued a harmless graph update behind an RF/steering transaction.

`RoomEngine.projection_snapshot()` delegates to a nonblocking session read. It
does not enter the command queue, expire a lease or mutate the medium. If the
RF lock is busy, the graph uses the last committed role/traffic selection from
the event store and omits unavailable applied-RF detail for that sample. It
does not wait or guess temporary RF state. Control commands retain the actor.

### One client probe blocked all other clients

The previous cache lock covered the external `lxc` traffic probe and `iw link`
read. One unreachable client could hold up all other clients and both observer
paths. Probes were also collected serially.

Independent clients now share a bounded four-thread probe executor. A
per-client lock coalesces duplicate work for that same station; the shared lock
only protects bookkeeping and never surrounds external I/O. Successful samples
are cached for five seconds, failed probes for one second, with AP/band/RF
generation included in the cache key. Signal still comes from actual client
kernel reporting after WLAN traffic, with its real timestamp.

The background display collector targets a three-second round and refreshes
serving data older than five seconds. Completed clients publish to its cache
individually, from their worker, rather than waiting for the last slow client
in the round. The one-second association stream can immediately consume those
completed measurements. Optimizer candidate evaluation still requires its
complete, internally consistent snapshot; partial display telemetry cannot
authorize a steering decision.

### Native topology rendering waited for client telemetry

The browser launched topology and client requests concurrently but awaited
`Promise.all` before applying either. A slow `/clients` response therefore
held back topology, and a slow topology response held back signal updates.

Recipe patch `0165-cli-decouple-topology-from-client-metrics.patch` separates
the two completion paths. Each stream permits only one request in flight; a
slow endpoint cannot create a growing request backlog. Topology applies as
soon as its response arrives; metrics refresh meters without forcing a graph
rebuild. WebSocket topology-change notifications still trigger refresh, with
the existing two-second polling fallback.

Patch `0166-cli-bind-signal-to-serving-bssid.patch` makes asynchronous metrics
safe: the native browser does not paint a newly associated AP with cached
source-AP metrics. Both patches apply in order and reproduce the deployed
script byte-for-byte. The Go/native API implementation is unchanged.

### Repeated scene updates and GPU-buffer churn

Every SSE event previously triggered a full scene update, even when several
events arrived before the next browser frame. Link segments also recreated
their position/color attributes on updates that did not change geometry.

Events are still reduced immediately and in order. Only rendering is coalesced
through `requestAnimationFrame`, producing at most one queued update per frame.
Stable-size buffers are reused, unchanged values are not marked for GPU upload,
and bounds/dash distances are recalculated only when positions change. Changed
geometry still renders normally. `window.__viewer.renderStats` exposes update
counts and CPU time for diagnosis without sending performance data elsewhere.

### SSE replay scanned the entire run repeatedly

`EventStore.after()` and `wait_after()` used a linear scan of the complete
journal on every delivery. Longer interactive runs and multiple browsers
amplified that unnecessary work. A sequence index and binary search now select
only the suffix after the subscriber's cursor. Ordering, replay, event hashes
and durable evidence remain unchanged. This removes an algorithmic weakness;
it is not claimed as the main cause of the measured seconds-long delay.

## Measurement method and initial results

Evidence and reproducible scripts are under
`/home/rev/work/room-observation-latency-0907` on rev150 and rev140. The live
benchmark drives real playback through all four perimeter checkpoints. It
requires two verified association-and-traffic handovers per checkpoint,
twelve unique native clients, six nodes and the correct target BSSIDs, then
restores the default twenty-client room paused at zero without a lease.

`measure-reporting.py` compares each successful native association/traffic
verification with the first server `network.snapshot` containing that target
BSSID. It measures **server projection**, not the exact browser paint or
physical radio-association instant. Negative lag means the passive native
observer saw the new association before the verifier finished its traffic
check; negative values are retained, not clamped to zero.

The immediate pre-audit baseline is a fresh lap with the preceding fast-steering
overlay, not the much slower original implementation:

| Measurement | Immediate baseline | First corrected observation overlay |
| --- | ---: | ---: |
| Mean projection lag after verification, eight handovers | 4.824 s | -0.022 s |
| Maximum projection lag after verification | 6.948 s | 0.344 s |
| Mean interval between room network snapshots | 5.006 s | 1.079 s |
| Maximum interval between room network snapshots | 8.100 s | 5.283 s |
| Mean snapshot publication age | 5.39 ms | 4.88 ms |
| Both walkers verified after each corner, four-corner mean | 17.178 s | 13.323 s |

The first corrected overlay completes all eight perimeter handovers without a
failed verification or a logged worker/candidate outage during those timed
segments. A separate evacuation regression verifies all eight clients in
34.390 seconds after extender movement stops. That evacuation journal still
contains six passive worker timeouts and two candidate-unavailable events;
these are retained and are not described as fixed native reliability problems.

The final progressive-metric iteration also removes the per-round publication
barrier and shortens serving-cache age. Its separate reports are named
`progressive-perimeter` and `progressive-evacuation`; do not conflate them with
the first corrected overlay's numbers above.

### Final progressive-metric perimeter results

The final `observation-v3` lap completes all eight handovers without failed
verification or worker/candidate outages in the timed segments. Client
identities, SSIDs, bands and all non-moving positions are unchanged.

| Measurement | Immediate baseline | Final progressive overlay |
| --- | ---: | ---: |
| Mean association projection lag after verification | 4.824 s | 0.767 s |
| Maximum association projection lag after verification | 6.948 s | 3.157 s |
| Mean room network snapshot interval | 5.006 s | 1.131 s |
| Maximum room network snapshot interval | 8.100 s | 5.597 s |
| Both walkers verified after each corner, mean | 17.178 s | 13.326 s |
| Clients with measurements at most 10 s old, four checkpoints | 43 / 48 | 48 / 48 |
| Fresh post-request target metrics seen within checkpoint captures | 8 / 8 | 8 / 8 |
| Mean fresh target-metric projection lag after verification | 4.824 s | 3.730 s |
| Maximum fresh target-metric projection lag after verification | 6.948 s | 7.306 s |

Average association reporting lag falls about 84.1%, and the mean snapshot
interval falls about 77.4%. The final lap is **not** uniformly faster than the
first corrected lap: its worst association lag is 3.157 seconds rather than
0.344 seconds. Fresh target metrics still arrive later than association, and
their worst observed delay is slightly higher than the baseline. These small
samples do not justify a zero-delay claim or a guaranteed latency bound.

The intermediate metric audit found only 24 / 48 checkpoint measurements at
most ten seconds old and one mover without a fresh target measurement before
that capture ended. The progressive publication/cache changes improve that to
48 / 48 and 8 / 8 respectively; the viewer's twenty-second stale cutoff is not
relaxed to achieve this result. `audit-metrics.py` requires the correct target
BSSID and a genuine sample timestamp after the steering request. It reports
missing measurements explicitly rather than averaging them as zero latency.

The final evacuation regression also verifies all eight requested handovers:
the first in 7.532 seconds and all eight in 35.531 seconds after movement stops.
There are no failed verifications, but eight worker/candidate error events
remain in its checkpoint journal. This is not a new evacuation baseline or a
claim of improved native timeout reliability. Both final scenarios restore
twenty clients and six native nodes, paused at zero without a control lease.

## Browser checks

A controlled browser-only comparison serves the saved pre-audit viewer HTML
to one test browser and the deployed viewer to another, sequentially, against
the same twelve-client evacuation room. It does not roll back the server or
write RF. Both use Chromium, a 1600×1000 viewport and software WebGL. Three
100-call update bursts produce:

| Render-burst measurement | Before | After |
| --- | ---: | ---: |
| Scene updates per 100 requests | 100 | 1 |
| Mean scene-update CPU per burst | 54.567 ms | 1.367 ms |
| Existing position attributes retained | 266 / 276 | 276 / 276 |

This is approximately 97.5% less scene-update CPU for that burst, not a claim
that end-to-end handover or frame time improved by 97.5%. State, SSE traffic,
layout and actual rendering still consume time. Both successful browser runs
report no page errors. Initial headless-browser attempts failed to initialize
WebGL because the local ANGLE build needed a valid X display; `DISPLAY=:0`
resolved the test environment failure without changing viewer code.

A native-browser test deliberately withholds its client-metric response.
Two real topology responses still apply in 2.227 seconds total, while exactly
one metrics request remains pending. No page errors occur. The withheld
response is browser-local: the test does not delay the lab API or optimizer.

## Safety, remaining weaknesses and limits

- Atomic RF mutations, temporary steering assistance and exact restoration
  remain serialized because they share one simulated medium. Removing those
  guards would allow conflicting matrices or steering against obsolete RF.
  Independent read/render work no longer waits behind that control queue.
- The native/libemcli command path can still queue or time out. A completed
  topology response cannot reveal an association that native topology has not
  reported. This audit does not introduce unsafe parallel native workers or
  infer success from geometry. Candidate HTTP 504s still require separate
  native/API investigation.
- A slow metric API request still delays the start of its own background probe
  round; it no longer gates the association graph. Failed traffic/`iw` probes
  remain genuinely unavailable. One missing measurement must not be replaced
  with a fabricated timestamp or a green modeled signal.
- There remains sampling latency: one-second room topology cadence,
  three-second metric rounds, five-second successful-probe reuse and the
  native browser's two-second fallback poll. These are bounded load/freshness
  choices, not evidence that all external latency is gone. Slow native calls
  can exceed a target cadence, as the maximum snapshot gaps demonstrate.
  Playback RF also follows the configured scenario tick, one second in these
  benchmark worlds; smooth camera frames do not imply continuous RF updates.
- Required optimizer generation checks, native request deadlines, scan work,
  anti-flap cooldowns and failure recovery are unchanged by this audit.
  The earlier five-second post-success cooldown remains intentional.
- Event hashing, state copying and journal persistence remain ordered under
  the event-store lock. Long-lived journal memory and synchronous persistence
  deserve profiling under larger subscriber/run loads; removing durability or
  ordering without measurement would trade correctness for an unproven gain.

The correct conclusion is therefore: several externally imposed observation
and rendering delays were real and are now removed, but not every delay after
moving a client can be attributed exclusively to the EasyMesh optimizer.

## Validation and retained failures

Python validation passes 312 tests and 39 subtests, with one existing skip.
Coverage includes independent client progress, a blocked peer, cache isolation,
exact association/measurement joins, missing metrics, real `RoomEngine`
projection wiring, busy RF transactions and replay index behavior. All 21
viewer/native JavaScript checks pass, including coalescing, buffer reuse,
independent requests and source-AP metric rejection.

The first deployment exposed a missing `RoomEngine` delegate for the new
session projection method. Its restart loop was stopped, the facade was fixed,
and an integration regression was added before accepting the corrected
deployment. `v1-startup-failure.log` and the intermediate overlay remain in the
evidence directory; they are not successful trials. Later browser-test harness
errors are likewise retained separately from passing application checks.

Before redeployment, require an idle default room and save both guest source
and native seed/live assets. `recover-v2.py` documents the corrected startup;
`deploy-progressive.py` documents the final overlay's health-gated deployment.
Do not run the initial `deploy.py` or deploy `observation-v1-overlay.tar.gz`:
that intentionally retained intermediate archive is incomplete. Re-run the
test suite and current health/lease gates instead of blindly replaying a
historical deployment script against an operator-owned room.
