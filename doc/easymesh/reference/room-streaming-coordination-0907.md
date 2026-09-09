# Streaming coordination and same-frame display audit — 0907

This continues the [initial coordination audit](room-coordination-profiling-0907.md).
Scope remains the RDK candidate VM `rdkeasymesh-20-0907` on rev140, ports
48889/48890/48891. Published services, prpl and rev150 runtimes are untouched.
Controller, agent and wmediumd binaries are unchanged. The native CLI is rebuilt
only to expose the existing guarded steering helper over HTTP. The read-only
medium observer receives a separate error-label correction after catalog testing.

## Changes

### Collection no longer owns the decision loop

`optimizer.streaming.StreamingCandidateProvider` owns one bounded worker.
The native controller still admits only one unassociated-metrics transaction
at a time: this is a verified native command-type limit, not permission to
parallelize libemcli tree ownership unsafely.

Each fully validated radio response publishes its comparisons immediately.
The decision loop consumes them while the remaining AP queries run. It does
not wait for the entire comparison round or for an unrelated client's BTM
verification. An event wakes the consumer; the normal decision cadence is
250 ms, with new passive serving metrics read before evaluating cached targets.

Selection remains fair, same-band and limited to eight clients per round.
All policy decisions and cache mutations stay in the decision thread. The
collector communicates through an ordered queue, rather than sharing mutable
policy state with native-query threads. No unbounded executor backlog is used.

Original native timestamps are preserved. Samples expire after 30 seconds or
the policy's smaller age limit. World epoch, medium instance, role presence,
BSS inventory and observed source-owner versions invalidate incompatible
results. An observed A→B→A ownership transition cannot resurrect an older
queued response. Cancellation prevents further queued native requests; an
already executing HTTP/native transaction must still finish or time out.

Malformed or contradictory native responses fail closed. A transient failed
radio query does not discard another radio's still-valid observations or
relieve any freshness check. Failures remain visible in collection evidence.
Collection busy retries have a 250 ms bound, not the old exponential whole-
optimizer pause. Native sample age is not the same as publication latency.

An improving candidate may now trigger a threshold decision before all APs
have replied. This is deliberately an available-measurement policy, not a
claim that the first improving target is globally optimal. Fleet convergence
still requires complete fresh comparisons and the configured 2 dB margin.
The optimizer remains the external room threshold policy, with five-second
cooldown and failure backoff: it is **not** the BPI autonomous optimizer.

### Coherent active-client health

Policy membership uses the same observed active clients as its candidates.
Known pool clients intentionally made offline are excluded from both, rather
than leaving the unfiltered count to block every online client. The observed
native count is retained as `native_roster_clients` in every evaluation.
Missing expected clients still block steering, and qualification still checks
the unfiltered native topology for ghosts. Filtering is not a native roster
repair and must not be reported as one.

### Control-path overhead

The native steering shell helper resolves source BSSID/device/radio and target
band in **one SQL statement**, instead of three separately launched clients.
It rejects absent or ambiguous rows and still checks the expected source
before submission. Gentle BTM behavior and the native success-status check
are unchanged. No native agent or controller workaround is introduced.

Playback presence batches use at most four independent client-control workers.
Every disconnect is journaled before execution. All successful disconnect
contexts remain active until the one atomic RF generation commits. Entry or
RF failures unwind all entered contexts; reconnect failures are propagated
only after the bounded workers finish. RF socket operations and recovery
ordering are not parallelized unsafely. World-switch and emergency-recovery
paths retain their separate conservative sequencing.

An isolated, non-actuating comparison measured the old lookup path at 159.66 ms,
the single lookup at 149.35 ms, and `lxc exec ... true` alone at 133.84 ms
(ten samples each, medians). Thus SQL consolidation alone did not solve the
dominant container-launch overhead. Both lookup scripts deliberately refused
source-equals-target requests; this test did not submit native BTM commands.

The second deployment adds `/api/v1/steer-native` to the existing CLI process.
It invokes the same `/usr/bin/steer.sh` locally, removing the nested `lxc exec`
launch without adding a service, privileged shell endpoint or alternate
steering mechanism. Inputs are limited to normalized six-byte MAC addresses
and valid 20 MHz operating-class/channel pairs. Only gentle requests are
accepted; the source guard, native status and exit status all remain required.
There is one active submission and no waiting request queue. Busy admission
returns 429; rejected native submissions return 503, not false success.

HTTP request parsing and helper execution do not hold the native tree mutex.
The helper runs in its own process, as before; it does not share libemcli memory
with the Go process. A 15-second timeout kills the helper process group,
including a stuck SQL client, and output is bounded. Availability is advertised
only when both installed helpers are executable. Old servers keep the original
LXC path; an ambiguous HTTP outcome is **not** retried or sent through fallback,
because the native command might already have been accepted.

Action evidence retains HTTP round-trip and server/helper timings separately.
The server timing includes SQL lookup and native submission, not just native
on-air behavior. This endpoint uses the existing trusted-lab API boundary;
do not expose it publicly without the authenticated gateway described in the
internet-access documentation.

### Same-frame rendering

The room previously updated scene objects in one RAF callback, then waited
for the separate render loop's next RAF to submit them. It also submitted
unchanged scenes continuously. With a large fullscreen software-rendered view,
the extra frame was measurable, not a hypothetical optimization.

The coalesced update now submits its scene within that **same RAF**. Camera
and resize operations explicitly mark the scene dirty; the loop renders those
changes without submitting an old scene ahead of a pending update. Station
names, highlights, labels, drag/play behavior and graphic quality are retained.
No lower resolution, faster scenario clock or suppressed metric update is used.

An opt-in `?mode=interactive&profile=1` records a bounded 2,000-entry frame
buffer at `window.__viewer.frameTimings`. Each entry identifies the network
event, receipt time, scene submission and following RAF. The audit separately
checks each native topology response against the SVG's actual owner bindings
on the next RAF. These are browser submission/opportunity timestamps, **not
physical screen scanout or on-air association timestamps**.

## Reproduction and evidence

Artifacts are under `/home/rev/work/coordination-streaming-0907`.
The first run is `20260908T144432Z-private-client-room-walk-interactive`;
the final HTTP-transport run is `20260908T152333Z-private-client-room-walk-interactive`.
`runtime-v10.tar.gz` contains the initial streaming runtime overlay, not a thin
release. `viewer-v11.html` is the same-frame renderer revision; deploying this
static file does not restart the running RF engine, optimizer or native stack.
`runtime-v12.tar.gz` adds HTTP steering and the strict unknown-client guard.
The final CLI SHA256 is
`472a3c2df347e592a04b988bc828b33beb3ab2694d80ac9db7fef2bcdc9eb923`.

- `all-rooms.py`: normal-speed playback, checkpoints, native roster and measured
  policy-margin checks, then default-20 restoration and lease release.
- `browser-audit.js`: both views fullscreen, native-response/SVG owner checks
  and room frame telemetry; screenshots are diagnostic, not the timing clock.
- `medium-monitor.py`: daemon identity, netlink/error counters and queue data.
- `analyze-streaming.py`: validates the event hash chain and separates decision
  observation, collection service, publication, submission and display timings.
- `renderer-matched-ab.js`: compares both renderer versions with the same
  foreground fullscreen browser layout against one live world.
- `room-findings.py`: retains missing, extra and conflicting native owners,
  plus each final policy reason, rather than reducing every failure to SNR.
- `medium-findings.py`: reports interval deltas and explicitly distinguishes
  sampled queue values from an all-frame latency distribution.

The audit browser explicitly removes inherited `DISPLAY` from its environment.
A stale SSH-forwarded display caused ANGLE/SwiftShader initialization failures
in the first browser startup attempts; these were harness failures, not lab
convergence results. The second complete catalog supplies fullscreen browser
coverage; its first shared-browser samples remain separate from the later
independent-foreground timing series. Those failed startup logs are retained.
Screenshots are taken at catalog transitions and can still show the outgoing
world; filenames alone are not authoritative world identities. The continuous
response/SVG checks and timestamped world-application journal are the audit.

### Paired fullscreen render measurement

The matched 30-second same-host, same-world overlap in
`renderer-matched-ab.json` uses **one foreground fullscreen page per browser
instance for both versions**:

| Receipt → browser stage | Previous renderer | Same-frame renderer |
| --- | ---: | ---: |
| Median scene submission | 51.0 ms | 11.2 ms |
| p95 scene submission | 75.6 ms | 34.2 ms |
| Median following RAF | 82.8 ms | 26.5 ms |
| p95 following RAF | 107.0 ms | 48.6 ms |

There were 120 samples per version, both visible, focused and fullscreen, with
no JavaScript errors. This is software-rendered Chromium at 1600×1000, not a
guarantee for every GPU or monitor. Initial shader compilation, screenshots,
world loads and transport time must not be confused with steady frame latency.

The earlier `renderer-ab.json` comparison showed 379.7→9.7 ms but used different
browser layouts (a room/topology pair versus one room page). It is retained as
diagnostic evidence, **not an isolated renderer speedup**. The catalog harness
subsequently uses independent foreground browser instances for the two views;
old shared-browser samples remain identifiable rather than being deleted.

## Qualification status

The second catalog completed on 2026-09-08 at 16:04:20 UTC: **14/14 rooms played
at normal speed**, with both views fullscreen. Twelve final native rosters
matched; only two final snapshots met complete fresh measured-policy-margin
convergence. A final snapshot has a bounded 45-second settle, not unlimited
waiting or forced association. These are qualification failures, not an
optimal-system certification. No new video, thin release or commit is promoted.

| Room | Final native roster | Final measured convergence / reason |
| --- | --- | --- |
| home-a-asymmetric-link | 11/11 | Pass within 2 dB policy margin |
| home-a-band-walk-small | 9/10 | Fail: native topology omits station `0f`, room/metrics still contain it |
| home-a-border-hover | 12/12 | Fail: missing fresh comparisons, pending BTM |
| home-a-disappear-reappear | 12/12 | Pass, also absolute measured best |
| home-a-extender-loss-recovery | 10/10 | Fail: one client in failure backoff |
| home-a-fast-transit | 12/12 | Fail: missing comparisons and failure backoff |
| home-a-flash-crowd | 11/10 | Fail: extra offline `sta_mobile_02` in both observed views |
| home-a-one-client-handover | 11/11 | Fail: one client in failure backoff |
| home-a-private-client-room-walk | 20/20 | Fail: one pending BTM |
| home-a-slow-walk-ten | 20/20 | Fail: missing candidate/current metrics |
| home-a-stationary | 10/10 | Fail: one pending BTM |
| home-b-slow-walk-ten | 20/20 | Fail: incomplete fresh comparisons |
| large-room-extender-evacuation | 12/12 | Fail: pending BTM, cooldown, missing comparisons |
| large-room-perimeter-counter-roam | 12/12 | Fail: pending BTM, cooldown, missing current metric |

The complete journal contains 53,291 events and validates without a hash-chain
error. Timing analysis excludes initial service startup and the final default
restoration: 15:25:40.770363–16:03:18.743231 UTC. It records no room worker errors
or newly observed native process crash. All 122 steering submissions received
native acceptance; 94 verifications succeeded, 18 timed out, nine were discarded
after environment changes, and one remained outstanding at the catalog cutoff.
Acceptance is not association completion. Successful first native target-owner
reports have median 4.895 s and p95 18.466 s from request, not on-air timestamps.

| Measured stage | Median | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Previous streaming/LXC dispatch, 109 actions | 209.197 ms | 267.151 ms | 381.016 ms |
| HTTP dispatch, 122 actions | 73.190 ms | 117.911 ms | 370.598 ms |
| Controller-local helper within HTTP request | 66.057 ms | 103.119 ms | 132.028 ms |
| HTTP round trip minus reported helper time | 1.671 ms | 6.275 ms | 11.554 ms |
| Native candidate publication → decision consumption | 105.702 ms | 196.715 ms | 1,012.786 ms |
| Successful native comparison round service | 5,799.492 ms | 12,143.509 ms | 19,819.147 ms |
| Motion-only RF application, 610 batches | 23.934 ms | 93.965 ms | 345.985 ms |
| Presence-changing RF application, eight batches | 185.409 ms | 605.689 ms | 605.689 ms |

The two catalogs have different warm native association states; their native
convergence outcomes are not a controlled A/B. Dispatch stage measurements and
the non-actuating launch benchmark establish the removed overhead, not a claim
that the native optimizer improved by the same percentage. There were 673 native
busy rounds and 50 timeout rounds; these must not be folded into the successful
round latency distribution or hidden behind a fresh timestamp.

Foreground room receipt→scene submission has median 11.3 ms and p95 21.3 ms
over 6,595 samples. Foreground topology receipt→SVG check has median 16.5 ms
and p95 127.6 ms; its following RAF is median 135.6 ms and p95 268.3 ms.
Thus fullscreen software-rendered topology presentation still has material
overhead. There are no JavaScript errors. Of 9,021 topology response checks,
one differs from its own payload because a newer response arrived before the
same RAF; the SVG exactly matches that newer payload. The raw discrepancy and
its seven-frame context remain in `topology-mismatch-context.json`; unexplained
owner mismatches are zero. This does not repair conflicting native APIs.

The medium monitor collected 1,107 snapshots without a request error and with
one unchanged daemon identity. Interval deltas include 3,769 tracked clone
`EINVAL` errors, **two other netlink errors**, 209,114 ring overwrites and zero
no-receiver drops. Sampled last-frame queue delay is median 0.322 ms, p95
4.622 ms and maximum 16.750 ms. This is not an all-frame histogram. The daemon's
763.824 ms lifetime maximum predates the run and does not increase. Neither
ring overwrites nor a sticky history-gap warning alone proves RF packet loss;
neither can certify that the medium had no effect on native performance.

The candidate is restored to 20 clients and six native topology nodes, paused
at time zero and unleased. The normal 100-action profiling limit and
`Restart=on-failure` are restored, and VM `boot.autostart=false` remains set.
Published port 18891 remains paused and unleased with 20 clients. The native
controller, five agents and wmediumd retain their pre-test process identities.

Tests: 351 Python tests pass, one daemon integration test skips without
`WMDC_TEST_DAEMON`, and 43 subtests pass. All 22 JavaScript checks pass, including
same-RAF submission, unchanged-frame suppression, fullscreen and drag/play
regressions. Steering lookup tests exercise stale-source, ambiguous and missing
inventory. Parallel-presence tests exercise entry failure and RF rollback.
Go helper race tests run 20 times, including response validation, bounded
admission/output, passive-lock independence and process-group timeout cleanup.
The separate medium-observer Go race suite also passes, including its packaging
tests and a regression for the corrected netlink warning.

### Netlink warning correction

The observer described `netlink_other_errors` as non-`EINVAL` errors. That was
incorrect: this counter also includes errors outside the tracked clone category,
including `EINVAL` from another command. The daemon log contains command-3
`Invalid argument` messages. The revised label is "netlink errors outside
tracked clone EINVAL have been observed"; the counters, error severity and
daemon behavior do not change. The web summary names the first bucket explicitly
as tracked-clone `EINVAL`. This is a reporting fix, not a netlink-failure repair.
The replacement observer is deployed only after the catalog closes, with SHA256
`527e462f2ea5b656d17f6b7378b7945d148d032571c75cb2131964c0e401cec6`.
Restarting this observer starts a new observer-history epoch; a cleared gap flag
after that restart must not be mistaken for repairing the preceding run's gaps.

## Remaining limits

No zero-overhead claim is possible. Collection response time, native metric
age, subprocess dispatch, passive API polling, RF application and rendering
must remain separately measured. The new HTTP path removes LXC process-launch
cost but still starts the small local helper. Existing native C command serialization is necessary
until the stack supplies a safe concurrent command/result interface.

Continuous evidence retention also consumes disk and in-memory history over
long runs; this phase does not claim an indefinitely resource-bounded service.
Backhaul RF remains fixed in unassisted client profiling, as documented in the
initial audit. It does not measure native backhaul-parent optimization.

Other CLI handlers still serialize native tree ownership through parts of their
HTTP handling. Slow request bodies or response readers are not qualified here;
the new steering route avoids that lock but does not redesign every old route.
Likewise, event-ring gaps prevent certifying gap-free on-air association timing.
Native candidate service, accepted-but-uncompleted BTM actions, stale ownership,
client behavior and hwsim/netlink rejection causes need separate tracing before
attributing every remaining second solely to the native EasyMesh optimizer.

Before a future thin release, rebuild the checked-in CLI artifact with
`gen/rebuild-em-cli-artifact.sh` and the observer binary using its documented
build procedure. This experiment stages runtime binaries separately; existing
checked-in prebuilt archives are not silently relabeled as updated releases.

Completion still requires bounded long-run evidence retention, slow-peer HTTP
lock qualification, gap-aware RF/association tracing, and a new catalog pass
that resolves or precisely attributes the failures above. Until then, the lab
is an improved measured profiler, not a certified negligible-overhead replica
of real hardware or the native BPI autonomous optimization policy.
