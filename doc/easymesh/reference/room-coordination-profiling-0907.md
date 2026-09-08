# Room coordination and unassisted profiling — 0907

## Scope and interpretation

This audit targets the RDK candidate VM `rdkeasymesh-20-0907` on **rev140 only**:

- Room: `http://192.168.2.140:48891/viewer/?mode=interactive`
- Native network topology: `http://192.168.2.140:48889/`
- Medium observer: `http://192.168.2.140:48890/`
- Evidence on the development host: `/home/rev/work/coordination-profiling-0907/`.

The published 18889/18891 services, rev120/prpl, rev150 runtimes and released
thin archives are not promoted by this audit. The native EasyMesh controller,
agents and wmediumd are not rebuilt to improve a benchmark score. The controller
and medium retain their running instances; intentional AP-loss scenarios still
exercise the existing agent lifecycle. The CLI/API adapter is rebuilt against
the existing target library and sysroot.

**This is not a zero-overhead or real-hardware-equivalence certification.**
RF stimuli, native measurement receipt, policy decisions, command acceptance,
association reporting and browser display are different milestones. An API
submission is not a successful handover; an attractive modeled AP is not
evidence that the client accepted a BTM request.

The optimizer used here is the **external room threshold policy**, not an
autonomous BPI optimizer. Unassisted mode profiles its interaction with native
EasyMesh measurement and steering facilities. To profile a different optimizer,
replace/disable this policy rather than running two steering authorities.

## Coordination changes

### Candidate waits no longer block every API

Previously `serializeAPIRequests` held a global native API mutex throughout an
unassociated-STA HTTP transaction, including up to eight seconds waiting for a
protocol response. Topology, client and device readers queued behind it.

The adapter now separates three responsibilities:

1. A bounded candidate admission coordinator owns candidate transactions.
2. Each native command and its entire C result-tree lifetime remain exclusive.
3. Protocol polling waits release native access, so passive readers can proceed.

Native command rejection is checked before waiting for metrics. An explicit
rejection returns HTTP 503 with the actual native status; it must not become a
misleading eight-second "missing response" timeout. Context cancellation stops
further polling and releases admission. It cannot safely interrupt a C call
already executing. Queue capacity is 32; no unbounded request fan-out is used.

`GET /api/v1/coordination` advertises the limit and its reason. The Python
collector negotiates it; old or malformed capability responses retain the safe
single-query default. Successful/timeout candidate responses include
`coordination.native_queue_ms`, `native_service_ms`, `native_calls` and
`elapsed_ms`. Passive responses expose `X-Lab-Native-Queue-Ms`.

**A native limit was demonstrated, not assumed away.** A five-agent parallel
trial allowed only three of fifteen candidate transactions to complete. Native
`em_ctrl_t::handle_unassoc_sta_metrics_query` rejects a second command of that
type while the first is in progress, regardless of agent. Consequently the
qualified adapter advertises one active candidate command, with reason
`native_controller_command_type_single_flight`. Raising the limit without
changing and independently qualifying native orchestration is incorrect.
The failed parallel trial remains in `api-after.json`; it is not the final build.

### Simultaneous motion uses one RF generation

Playback previously applied each moved role separately. A ten-client frame
could expose intermediate geometries and incur ten sets of baseline/readback
and recovery-journal work.

Playback now prepares all changed roles, deduplicates directed/frequency-qualified
links and commits one atomic wmediumd generation for the frame. Presence changes
retain disconnect/reconnect and crash-recovery behavior. Accepted role events
share the committed generation; failure rolls back unapplied geometry or uses
the existing fault/restore path. Manual single-role updates use the same code.

Playback pacing is start-to-start rather than "one second plus transaction
time". Overload is not hidden by skipping presence or pause checkpoints.
`playback.rf.applied` records affected roles, generation and measured elapsed
milliseconds. A one-second RF scenario tick is still a discrete stimulus, even
when the camera animates smoothly at a higher frame rate.

### Observation, rendering and verification

- Profiling room topology and client metrics refresh at 250 ms; native topology
  and its independent client-metric stream poll at 250 ms while visible. Every
  stream remains single-flight. Profiling no longer inherits the assisted
  room's three-second metric refresh cadence.
- A subsequent cache audit found that fast HTTP polling still reused native
  inventory/topology/client responses for **1,500 ms**. The shared read-cache
  limit is now **100 ms**, advertised as `native_read_cache_ttl_ms` by
  `/api/v1/coordination`. Fast delivery of an old cached response was not evidence
  of fast native-state visibility. The shorter cache was separately load-tested
  before restarting full-catalog qualification.
- Native topology remains authoritative for membership and serving BSSID.
  Metrics are joined only to matching ownership; geometry never fabricates a
  successful association. Existing requestAnimationFrame coalescing and GPU
  buffer reuse are retained.
- Optimizer retry wakeups use the event-store condition rather than a 100 ms
  loop that repeatedly checks RF state. Clock/state readers no longer deep-copy
  the full event projection just to inspect a scalar.
- In profiling, up to five outstanding outcomes are verified concurrently using
  the shared fresh topology projection. A client that takes 40 seconds or refuses
  does not impose a 40-second verification barrier on every subsequent client.
  Membership/world changes cancel obsolete verifications; command submissions
  still obey native acceptance and the explicit action budget.
- Convergence distinguishes **within the configured 2 dB policy margin** from
  **absolute strongest measured AP**. Empty fleets, missing candidates and stale
  measurements do not count as demonstrated convergence.
- Profiling uses fair rolling groups of at most eight clients on one band.
  Each group obtains native AP comparisons without waiting for every other
  band/client. The bounded cache preserves original native timestamps and
  expires at 30 seconds or the policy's smaller freshness limit. Source owner,
  band, SSID, BSS inventory, world and daemon identity changes invalidate cached
  comparisons. An unavailable group does not block other groups with valid
  measurements; malformed native identity still fails closed.

## Unassisted versus assisted operation

The previous `--request-only` host steering path was not an unassisted profiler.
It could prepare scans, wait, escalate, and execute inside a temporary RF boost
transaction. Fast assisted-demo timings must not be attributed solely to
EasyMesh behavior under the displayed room matrix.

Use the explicit RDK profiling option from inside the LXD lab VM:

```sh
cd /home/easymesh/git/meta-cmf-bananapi-vcpe
gen/demo/room-demo interactive --mode act --yes-act --profiling \
  --max-actions 100 --listen 0.0.0.0:8891 \
  --output-root /home/easymesh/easymesh-evidence/room-runs
```

Stop the existing room service first and ensure no operator owns its lease.
Do not run two room writers. The profiler keeps the fixed 20-client container
pool and six-node topology; worlds can make a subset unavailable.

In profiling:

- One gentle native BTM command is submitted through the controller helper.
  There is no temporary 60 dB target boost, forced client scan, disassociation
  escalation, preview delay or host steering wait loop.
- The controller helper verifies the expected source before submitting. Its
  driver reports `steer_drv_status=...` and returns nonzero for native rejection;
  the actuator also rejects missing/ambiguous status. Only a later native
  association plus traffic verification establishes success.
- Kernel traffic-probe fallback does not manufacture fresh current-link metrics
  for the optimizer. Native timestamps and native candidate identities remain
  authoritative. The separately selected traffic probe still generates its
  documented test traffic; this is not a completely passive experiment.
- Ordinary movement does not invalidate an entire in-flight candidate round or
  reset policy state simply because the simulator knows a new RF generation.
  World/membership/daemon identity and metric-age checks remain enforced.
  Loading a different world resets policy state and discards obsolete pending
  verifications; ordinary motion in the same world does not.
- `--adaptive-backhaul` is intentionally incompatible: the external RDK parent
  selector must not masquerade as native EasyMesh backhaul optimization.
  This also retains the baseline backhaul RF matrix: this mode isolates **client
  steering**, not moving-backhaul RF or native backhaul-parent optimization.
  Do not interpret a stationary star in this mode as a native parent-selection
  result for the displayed extender geometry. The assisted adaptive-backhaul
  demo remains a separate experiment.
- The UI/evidence identify `unassisted-btm` and `external-room-threshold-policy`.
  Without this option, existing assisted-demo behavior remains available and is
  labeled separately. This native actuator is RDK-specific, not a tested prpl
  profiling transport.

## Measured API improvement

The same bounded workload runs three rounds of five candidate requests with
concurrent topology, client and device readers. Measurements include HTTP
transport from the development host, not just in-process handler time.

| Measurement | Before | Coordinated, old 1,500 ms cache | Final 100 ms cache |
|---|---:|---:|---:|
| Topology median | 5,385.7 ms | 4.24 ms | 44.03 ms |
| Topology p95 | 5,767.3 ms | 38.02 ms | 56.89 ms |
| Topology maximum | 5,767.3 ms | 47.49 ms | 67.32 ms |
| Client-read maximum | 5,744.3 ms | 43.24 ms | 76.85 ms |
| Device-read maximum | 5,780.8 ms | 52.83 ms | 72.89 ms |
| Candidate successes | 15/15 | 15/15 | 15/15 |
| Candidate median, including admission | 3,025.0 ms | 2,863.4 ms | 3,000.62 ms |

These results remove a demonstrated **external API head-of-line block**. They
do not imply that native candidate collection or client convergence became
instantaneous. The original coordinated rounds generated 194 successful topology/client/device reads;
the independent-agent trial that timed out 12/15 queries was rejected.

The final cache comparison (`api-cache1500.json`, `api-cache100.json`) repeats
the same three rounds after the first full-catalog run. Both obtain 15/15
candidate responses and zero passive errors; the 100 ms build performs 169
successful topology/client/device reads. It intentionally spends more work on
fresh native reads instead of minimizing HTTP latency with old cached data.

During these approximately 16-second runs on the six-vCPU, 8 GiB candidate VM,
CLI CPU increases from 10.3% to 18.0% of **one core**, controller CPU from 13.4%
to 24.5%, and wmediumd remains around 9%. The combined increase is approximately
0.19 core, not 19% of the six-core VM. CLI RSS stays approximately 97–99 MB.
These are short-run process-counter measurements, not a long-term capacity
guarantee; raw counters are in `cache-cpu-comparison.json` and its source samples.
CPU figures come from guest `/proc` process counters, not demonstration values
in dashboard cards.

## Whole-catalog qualification

The final 100 ms-cache run completed **all 14 worlds** from 09:27:00 to
10:02:47 UTC on 2026-09-08, at normal playback speed. **This is not an all-room
convergence or near-instant-system pass:** 13 final rosters match, and four
worlds demonstrate the measured policy margin within the observation window.
The harness handles automatic checkpoints while checking native topology and
the room projection. It records
initial, moving, checkpoint and final membership, measured policy-margin
convergence, native metric age, API duration, and browser screenshots/labels.

The acceptance harness allows bounded initial/final observation windows rather
than forcing associations to manufacture a pass. Asymmetric reception,
disappearance, AP loss and fast transit may legitimately fail best-AP
convergence; record the reason instead of replacing missing metrics with modeled
SNR. Intentional pause-and-settle time is separate from scenario playback time.

Final samples use up to 45 seconds of post-playback settling. The counts below
are expected online clients / unique native clients / clients with completed
fresh comparisons. "Yes" means within the configured 2 dB margin, not a clean
health/actuation pass or necessarily the absolute strongest AP.

| World | Counts | Within margin | Remaining observation |
|---|---|---|---|
| Home A asymmetric link | 11 / 11 / 11 | Yes | One alternative is only 1 dB stronger |
| Home A band walk, small | 10 / 10 / 6 | No | Missing current/candidate metrics and pending steering |
| Home A border hover | 12 / 12 / 9 | No | Incomplete comparisons and pending steering |
| Home A disappear/reappear | 12 / 12 / 0 | No | Native agent crash; candidate coverage absent at final sample |
| Home A extender loss/recovery | 10 / 10 / 10 | No | One stronger AP remains |
| Home A fast transit | 12 / 12 / 10 | No | Stronger AP and incomplete comparisons |
| Home A flash crowd | 10 / 11 / 9 | No | Native topology retains an unavailable client |
| Home A one-client handover | 11 / 11 / 11 | Yes | Measured margin reached |
| Home A private-client room walk | 20 / 20 / 20 | Yes | Measured margin reached |
| Home A slow walk, ten movers | 20 / 20 / 10 | No | Missing comparisons and pending steering |
| Home A stationary | 10 / 10 / 10 | Yes | Last policy decision still carries a client-count guard |
| Home B slow walk, ten movers | 20 / 20 / 0 | No | Missing current/candidate metrics |
| Large-room extender evacuation | 12 / 12 / 12 | No | Ten stronger APs; last policy decision has a count guard |
| Large-room perimeter counter-roam | 12 / 12 / 11 | No | One client's comparisons remain incomplete |

The flash-crowd scenario does exercise 10 → 20 → 10 online roles. A modeled
departure is not permission to delete a still-reported native association from
the topology. Membership loss, native reporting and policy health are separate
observations; this is why a measured fleet-margin result alone is insufficient
for the full acceptance gate.

### End-to-end evidence

- Motion-only RF batches: 610 samples, median **22.91 ms**, p95 **76.52 ms**,
  maximum **183.68 ms**. Presence-changing batches are separate: eight samples,
  maximum **1,452.29 ms**, including client disconnect/reconnect preparation.
  That preparation still uses sequential client-control commands and is not
  an instantaneous multi-client power transition.
- Room network publication age when sampled: median **142.40 ms**, p95
  **271.09 ms**, maximum **424.59 ms**. This measures publication freshness,
  not the age of the radio measurement or an on-air-to-pixel latency.
- Successful AP-comparison rounds: median **5.57 s**, p95 **13.59 s**. There
  are also **26 native response timeouts** and **904 quick native-busy
  rejections**. The latter must not be mixed into a flattering "fast collection"
  median. Native candidate-lock queue time is cumulative across a transaction's
  calls: median **28.63 ms**, p95 **191.86 ms**.
- All **84** submitted native BTM requests are accepted; **79** verify association
  and traffic, **four** time out, and **one** verification is discarded after a
  world change. Submission overhead has median **213.54 ms**, p95 **280.56 ms**.
  Submissions remain sequential, although outcome verification is concurrent.
  Successful verification takes median **3.63 s**, p95 **10.34 s**; the old-cache
  run's median is **4.66 s**. These are different action populations, not a
  paired proof that native handover itself accelerated.
- Native metric age across sampled clients has median **5.75 s**, p95
  **8.97 s**, and a stale outlier of **912.78 s**. Old timestamps are retained
  and excluded from fresh-policy evidence, not relabeled as new data.
- Both views remain fullscreen in **1,969** browser observations, with no page
  errors. No duplicate STA entries occur in the inspected native/DOM samples.
  Screenshot work creates sampling gaps up to **7.19 s**. The 1 Hz DOM audit
  matches 231 native ownership transitions, but ten transitions are not matched
  within their comparison windows. This is not a frame-latency certification;
  finer instrumentation is needed to distinguish capture gaps from display lag.
- The medium retains the same daemon instance over **1,069** successful reads.
  There are zero new non-EINVAL netlink errors or no-receiver drops, but **4,357**
  clone-EINVAL increments still require classification. Sampled last queue delay
  has p95 **4,622 µs**, maximum **22,844 µs**. The **763,824 µs** lifetime maximum
  does not increase. Event-ring overwrites increase by **225,546**; ring overwrites
  are not synonymous with lost packets. Existing sticky history-gap health does
  not establish a loss-free observation stream.
- All **32,170** recorded events validate their hash chain. There are no room
  service restarts, lease-renewal errors or harness faults. Unit/regression checks:
  **327 passed, one skipped, 43 subtests**, **21 JavaScript checks**, and Go race
  checks repeated **20** times. The skip requires an explicit `WMDC_TEST_DAEMON`;
  the live catalog tests the actual candidate daemon separately.

The first complete run, using the old 1,500 ms cache, played all 14 worlds from
08:45:01 to 09:20:27 UTC on 2026-09-08: 12 final rosters matched and six worlds
demonstrated final policy-margin convergence. It is retained in
`all-rooms-cache1500/` and `analysis-v8.json`; the 100 ms cache receives a separate
complete catalog run. These are sequential runs on a retained native lab, not
identical boot/association initial conditions, so do not attribute every
convergence difference to the cache change.

The second run exposed a **native gateway-agent segmentation fault** at
09:34:53 UTC. The guest kernel records `onewifi_em_agen` faulting at address
`0xc` inside `onewifi_em_agent`; the gateway agent restarts at 09:35:27 UTC.
This occurred during the client disappear/reappear world, not an intentional
AP shutdown. `native-kernel-faults.log` and `native-agent-restart-v9.log` retain
the available evidence. The controller and medium remain running; the agent
binary was not rebuilt by this audit. This establishes a native process failure,
not its root cause or proof that all accompanying delay is native.

The running and Yocto-built agent share build ID
`b506e6ea52f8ae5ab07987eea6cc5506f2c6fb38`. Symbol lookup places image offset
`0x86d60` in `em_metrics_t::create_ap_metrics_tlv(unsigned char*, dm_bss_t&)`.
The faulting instruction dereferences `0xc(%eax)`; the matching source loop in
`src/em/metrics/em_metrics.cpp:1976` assumes a current command exists when
reading AP-metric parameters. This is consistent with a null current-command
context, but command-lifetime tracing is still needed to establish why it
disappeared. `native-agent-fault-symbols.log` contains the source/disassembly.
Do not "fix" a profiler by silently dropping those reports or injecting fake
fresh measurements. A lifetime-safe fix here belongs to the native stack and
needs separate qualification.

Evidence:

- `api-before.json`, `api-final.json`: final comparative API measurements.
- `api-cache1500.json`, `api-cache100.json`, `cache-cpu-comparison.json`: the
  subsequent read-cache comparison; `api-cache100.json` is the final API build.
- `all-rooms/report.json`, per-world JSONL: full playback and native membership.
- `browser-audit.jsonl`, per-world PNGs: actual DOM labels and both fullscreen
  states. Headless focus emulation is a capture-harness requirement, not a lab
  timing change. Initial failed fullscreen attempts are retained separately.
- `medium-monitor.jsonl`: read-only medium counters. Lifetime maxima and old
  netlink errors must be distinguished from new errors during this run.
- `all-rooms-pre-driver-fix/`: interrupted, invalid intermediate qualification.
  The first driver adapter incorrectly parsed a human-readable tree as JSON;
  it was replaced with the native status scalar and regression-tested before
  restarting the catalog. Those earlier "submission failed" results are not
  native EasyMesh failures.
- `analysis-v9.json`, `live-events-v9.jsonl`: final aggregate measurements and
  the closed, hash-verified journal. `analysis-v8.json` is the prior complete run.

## Final deployment state

Only the rev140 candidate is updated. Its room service remains explicitly in
`--profiling` mode, with the normal **100-action budget** and
`Restart=on-failure`; the temporary 1,000-action test budget is removed.
The default world, **20 online clients**, **six logical mesh nodes**, paused
playback at zero and no operator lease are verified. VM `boot.autostart` remains
`false`. The published room remains Home B, 20 clients, paused at zero, unleased;
no rev120/prpl or rev150 runtime is changed.

The native CLI SHA256 is
`4968c56d138410abe7678ecae1d9344341dbfc94c53edeccf2b31d4d40011e0c`.
`final-runtime.json` captures the restored state and negotiated cache bound.
The source overlay is retained locally and synchronized to the canonical
`codex/0905-clean` source on rev140 after conflict checking and backup.

## Remaining limits and release gate

There is still real work to distinguish before calling this a near-instant
optimizer profiler:

1. Native unassociated metrics are single-command-at-a-time and can time out
   after acceptance. Multi-radio, whole-fleet collection can span seconds or
   tens of seconds. This is not evidence of an eight-second rendering delay.
2. A rolling group still needs comparisons from its candidate APs. Original
   native sample age, collection duty cycle and the 30-second cache bound must
   remain visible; caching cannot turn an old measurement into instant truth.
3. Client BTM decisions, native orchestration, scanning/association and native
   membership reporting remain distinct delays. A client may decline a target;
   the profiler deliberately does not override that decision with RF assistance.
4. Native topology/metrics polling and SSE/browser delivery have nonzero cost.
   HTTP sample timestamps are not on-air association timestamps. The medium
   observer's ownership evidence is not an interchangeable native BSSID event.
   The configured native associated-metric reporting period is five seconds;
   a 250 ms browser poll does not generate a new radio measurement every 250 ms.
5. Synchronous durable journaling, bounded radio-frame queues, hwsim/netlink
   delivery and host scheduling need measured headroom. A historical medium
   counter alone cannot prove a current drop or a latency guarantee.
6. The external room threshold policy, its 2 dB gain gate, five-second
   post-action cooldown and bounded failure backoff still affect decisions.
   Rolling groups evaluate after their AP comparison round, not after each
   individual AP response. The LXC/native-helper submission also has measurable
   overhead. These are exposed limits, not time attributable solely to EasyMesh.
7. The candidate uses the wmediumd daemon's multi-client read-only socket, not
   the alternative Python kernel-medium metrics proxy. That alternative proxy
   serves a connected reader synchronously and is not qualified by this run.
   Neither this run nor passing unit tests certifies all possible backends.

**No new MP4s are produced by this audit.** The requested optimal-system gate
is not met: native command-lifetime failure, measurement gaps, residual external
dispatch/presence overhead and capture timing uncertainty remain. Native
non-convergence by itself can be a valid profiling result; it is the inability
to certify the full timing/health chain that prevents an "optimal, instantaneous"
demonstration. Existing MP4s are unchanged, not renamed or presented as new.

Before making a new thin release, apply both CLI patches and rebuild the
checked-in `em-cli.tar.gz` from the patched Go sources using
`gen/rebuild-em-cli-artifact.sh`. A normal native C++ build does not itself
refresh that prebuilt Go helper. This audit's staged CLI binary is not a newly
published thin archive. Keep native/static payloads and room sources aligned,
then rerun health, no-lease/default-world and restart checks before promotion.
