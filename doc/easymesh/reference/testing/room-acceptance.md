# Room correctness and convergence acceptance

Use default SwiftShader, or hardware-backed `--renderer vulkan` with observer-only
render access. Do not change lab CPU limits or device permissions.

[Testing reference](README.md) · [Expected room features](../rooms/catalog.md)

Run rooms sequentially per lab; independent hosts may overlap. Audit native
state and both foreground views. Targeted passes are not catalog/soak coverage;
unplayed rooms remain unqualified.

## Current RF hardening checks

[RF qualification](../radio/virtual-rf-assessment.md#september-15-reliability-and-priority-qualification)
records cooling/priority profiles and earlier evidence. Historical six-room and
UDP cancellation passes do not erase two controller exits during restoration.
UAF patch 0193's contract/build and bounded reconnect pass; ASan churn was stopped.

### Candidate admission and isolated beacons

Enabled RDK **0207** rejects unready/occupied radios before global admission.
Its native regression fails before and passes afterward, preserving unrelated
ownership. UAF **0193** remains installed. Bounded same-MID retry candidate
**0206** passes fixtures but is held pending return-handover qualification.

Enabled HAL **0044** separates hwsim beaconing from rooted-child admission;
physical platforms/fronthauls are unchanged. Native builds and admission/beacon
fixtures pass, including fail-closed flushing. Typed inventory errors pause
interactive RDK steering; noninteractive checks fail.

Latest bounded RDK evidence in `test-results/targeted-suite-repair/`:

- `counter-manifest/report.json`: passes with
  explicit, verified traffic-subject preparation and original-owner restoration.
- `rf-rooms/report.json`: packet-size counters and received-discovery recovery
  both pass loading, Play, checkpoints, native/view convergence and Default
  restoration, with unchanged native identities. This two-room rerun is not
  a new full-catalog pass or proof of outage repeatability.
- `isolation-hal/report.json`: isolation, beacon availability, return and
  Default recovery pass, with unchanged native identities.
- `geometry-hal-warm/report.json`: all three geometry rooms pass in one run,
  including both branch paths, outward/return parent handover, isolation,
  ten-client convergence, native audits and Default recovery; identities unchanged.
- `geometry-hal-2/report.json`: the earlier post-restart branch attempt fails
  initial convergence before Play. Ten clients and mesh traffic are healthy,
  but only two clients have complete candidate coverage at the final sample;
  an Ext-2 unassociated-metrics query returns HTTP 504. Default recovery passes.
- `load-clear-background/report.json`: guarded balancing passes with actual
  source-AP broadcast traffic: native utilization 213/255 versus target 9/255
  at the decision, production ten-second hold, all three counter guards clear,
  captured BTM and target verification in 3.419 seconds. Post-steer traffic,
  fresh observations, twenty-client restoration and native identity checks pass.
  The suite's RDK clear case now uses this bounded workload.
- `load-clear/` and `load-clear-40/`: routed traffic alone fails to establish
  overload. Raising offered UDP from 12 to 40 Mbps per client does not prove
  radio congestion; the latter peaks at 168/255 against the unchanged 192 gate.
- Pressure/rescue and later browser/preflight evidence are maintained in
  [bounded qualification](../radio/rf-property-coverage.md#bounded-qualification-follow-up).
  Earlier failed workloads remain failed; unrun dependent cases remain blocked.

The HAL library was compiled and installed with verified rollback copies;
that campaign did not change the controller, policy or deadlines.
The native 100-client reconstruction also passes metrics, ownership, traffic
and zero-restart checks. This is diagnostic hot-deployment evidence, not
clean-source image acceptance or proof that the first-room query issue is fixed.

Earlier `test-results/rf-next-*` reports retain failed branch/return and
restoration attempts, including admission-only cold readiness failure. They
do not establish retry candidate 0206 causality and are not rewritten as passes.
HAL 0044 was held until the combined geometry qualification above.

The original branch stimulus offered only 1 dB relay gain, below 6 dB
hysteresis. Its corrected 12 dB divider gives relay/other-child/gateway SNR
13/0/−7 dB, preserving paths, policy and deadlines. The earlier divider run
passed branching but missed Default candidate coverage at 19/20; the new
combined run passes recovery too. Component replacement occurs outside scenarios.

Use assembled native sources, not the layer. The retry fixture still requires
held candidate 0206; the beacon fixture now exercises the enabled HAL patch:

```sh
python3 gen/tests/candidate-query-admission-test.py "$MESH_SOURCE"
python3 gen/tests/unassoc-query-retry-test.py "$MESH_SOURCE"
python3 gen/tests/hal-backhaul-beacon-test.py "$HAL_SOURCE"
```

### RDK threshold and query qualification

September 15, rev140 `rdkeasymesh-0913`: **OneWifi 0029 / EasyMesh 0194**
pass with unchanged native identities and successful policy/survey restoration.
UAF patch 0193 remains installed.

| Check | Result |
| --- | --- |
| Policy receipt/ACK; periodic isolation | Pass: 120 s interval, 128/255 threshold, six-second quiet control |
| Rising 32 → 224 / falling 224 → 32 | Pass: 3.568 / 3.119 s; one target-radio event per crossing |
| AP queries, 2.4 / 5 / 6 GHz | Pass: 10.321 / 6.967 / 11.423 ms; matching MID/BSSID |
| Periodic interval zero | Crossings pass: 2.677 / 2.922 s; no plateau repeats |
| Threshold zero; overlapping queries | Unsolicited reporting stops; three queries return fixture value 224 |
| Controller API, single / three BSSIDs | Native replies: 14.987 / 9.928 ms |
| Invalid API requests | Four rejected without native transmission |
| Periodic/restart audit | Five devices report; leaf recovers 1.607 s after restart returns; controller unchanged |
| Default readiness | Pass: 20 clients, six mesh nodes, 100-client pool; paused/unleased |

Query timings measure agent receipt → controller capture; threshold timings
include provider restart/delta warm-up. Independent one-second sampling continues
with reporting off. Fixtures do not measure physical congestion.

Evidence: `/home/rev/work/rf14-0913/evidence/` on rev150:
`rdk-rf14-implemented-5/`, `rdk-rf14-restart-final/` and retained failures.
From the RDK guest's `gen/`:

```sh
sudo env PYTHONPATH=optimizer:wmediumd/configurator python3 tests/rdk-reporting-policy-acceptance.py \
  --live --extended --root "$PWD" --output /tmp/rdk-rf14-new
```

POST `/api/v1/ap_metrics_query` accepts `{AlMac, BSSIDs}` (1–24 BSSIDs).
**HTTP 202 means submitted**, not completed.
`tests/native-ap-metrics-test.py NATIVE_SOURCE ONEWIFI_SOURCE` checks parser
bounds, handoff, timer-zero/idempotence, thresholds and RBUS validation.
Clean native objects after header changes; deploy matching binaries/libraries.
No full-catalog, soak or ASan claim.

## Preparation

### Native retry counters and AP inspection

September 15 bounded follow-up, evidence on rev150:
`/home/rev/work/rf-counters-0915/evidence/`. Four eight-second downlink trials
per stack pass; 250-ms impairment/recovery pulses avoid prolonged disconnects.
Compare native 1905 counters with AP `iw` counters and sequenced UDP endpoints.

| Trial | RDK retries / TX failures | prpl retries / TX failures |
| --- | --- | --- |
| Strong baseline | 0 / 0 | 0 / 0 |
| Data loss | 1240 / 63 | 866 / 46 |
| Reverse ACK loss | 1228 / 63 | 823 / 45 |
| Recovery | 0 / 0 | 0 / 0 |

Native and driver retry/failure deltas agree exactly. ACK-loss trials deliver
all 3200 datagrams: TX failure does not prove data loss. RDK uses octets,
prpl KiB; reset/wrap/malformed and direction checks are deterministic tests.
RX corruption is not qualified. prpl patch 0022 fixes missing TX/RX mappings.
The harness drains native sampling for two seconds before comparing reports;
that wait is not measured convergence. Earlier failures remain retained.

Deploy CMake-installed prpl libraries, not build-tree files: RUNPATH differs.
After native restarts, verify per-agent reporting intervals and restore the
client roster before starting the room.

From RDK `gen/` or prpl root, substitute `prpl` for the second stack:

```sh
sudo env PYTHONPATH=optimizer:wmediumd/configurator python3 tests/native-retry-counter-acceptance.py \
  --stack rdk --output /tmp/retry-qualification-new --yes-change-lab
```

AP inspectors separate local reports from client-heard advertisements.
Interactive rooms collect AP reports passively, without enabling load steering.
Both live topology checks pass: five APs/30 BSSs, stationary hover, manual layout,
stale/error handling and GET-only requests. Full room WebGL rendering remains
unavailable on this test host. No soak or full-catalog claim.

### Demand and lifecycle follow-up

Evidence directory on rev150: `/home/rev/work/rf-demand-0913/evidence/`.
Run each stack serially; the two hosts may run in parallel.

1. Retain non-turbo/priority profiles, resources and native timers.
2. Check leaf restart, owned-rule restoration and watcher reconnect outside
   measured runs; preserve unrelated firewall rules.
3. Repeat different-channel UDP/BTM three times. Separate submission,
   association and native evidence timing from the mandatory 20-second
   post-verification observation window.
4. Check UDP low/high/off, same-channel no-steer, both endpoints and four
   cancellation paths; leave no traffic/firewall leftovers.
5. Check received-link, cross-band and extender-loss rooms with both views and
   native ownership audits. Restore the paused default twenty-client room
   and hundred-client pool.

No soak or physical-capacity claim follows from these tests. Retain failures
and mark unavailable instrumentation explicitly rather than fabricating timings.

### Demand and lifecycle results

Both `*-rooms-udp-and-regressions/report.json` files pass all six rooms,
initial/play/checkpoint/final gates, independent native audits, unchanged
native/container/medium identities and default-world restoration. This does
not erase the separate failed RDK load-control restorations.

| Bounded observation | RDK | prpl |
| --- | --- | --- |
| Leaf restart command / rule present after return | 3.017 / 0.269 s | 12.791 / 0.155 s |
| Watcher kill/reconnect | 5.030 s | 5.030 s |
| Low/high/off sender actual, Mbit/s | 1.001 / 7.999 | 1.001 / 7.999 |
| Low/high/off receiver goodput, Mbit/s | 1.001 / 7.998 | 1.001 / 7.974 |
| Receiver loss in completed low/high phases | 0% | 0% |
| Pause / source-offline cancellation | 0.291 / 0.597 s | 0.250 / 0.269 s |
| Lease-release / world-change cancellation | 0.289 / 2.016 s | 0.026 / 1.039 s |

Native load timing uses only the two passing RDK guarded runs and the three
prpl repeats plus its passing identity-guard follow-up:

| Timing boundary | RDK | prpl |
| --- | --- | --- |
| Submission call | 89–108 ms | 437–803 ms |
| Target association verification after submission | 0.920–2.175 s | 0.225–0.451 s |
| First fresh target serving sample after verification | 5.491–13.049 s | 1.761–1.945 s |
| First fresh candidate set | 7.535–10.138 s | 0.667–1.352 s |
| First fresh target/source load | 4.723–4.748 / 2.236–4.724 s | 0.668–1.353 / 0.668–2.158 s |
| Complete coherent serving/candidate/load/activity snapshot | 10.139–15.592 s | 2.965–3.215 s |
| Observer / nested candidate query p95 | 2628 / 2402 ms | 573 / 519 ms |
| Load enrichment / policy evaluation p95 | 1.946 / 1.161 ms | 0.727 / 0.284 ms |

These are first sampled evidence bounds, not native arrival times. The
mandatory 20-second observation gate is retained and is not convergence latency.
Do not add nested candidate time to observer time. Native report cadence,
load-hold/dwell policy and host profiles differ; this is not a stack-speed ranking.
RDK post-steer freshness remains variable and requires further diagnosis:
these results do not establish instant measurement availability.

The third guarded pre-fix RDK trial loses its controller and fails readiness
with missing channel reports. Preserve that failure despite patch 0193 and
subsequent successful agent/policy recovery. Both default rooms ultimately
recover with twenty clients, hundred-client pools and no experiment leftovers;
priority persistence remains enabled and outer-VM autostart disabled.

Restart classification is eventual, not a pre-network barrier. Disabled
reconnects do not restore rules; unrelated nftables tables survive. Native
startup is separate: prpl requires its leaf wrapper; RDK needed its existing
metrics-policy replay after the direct restart. Neither recovery belongs in
a steering timing window.

UDP uses existing namespaces and two owned processes. Actual measurement
windows were about three and eleven seconds, not the full scheduled phases.
All four cancellation cases leave no owned iperf3 processes. World-change
latency includes applying the replacement world. Cancelled endpoint JSON was
unusable and remains explicitly unavailable, not zero traffic/loss. Live lease
expiry, shutdown cancellation and nonzero-loss accuracy are not demonstrated
by these cases; their code paths have unit coverage.

Both explicit native-load negative runs pass on unchanged channels, with no
load-directed action. Sampled serving utilization stays within 0–119/255 RDK
and 9–117/255 prpl: this proves acceptable-load suppression, not same-channel
exclusion under overload. Initial signal-directed roams remain allowed.
The temporary load-policy service override is removed afterward.

Native-to-view probes use exact deployed-binary hashes and instruction/DWARF
validation; unknown binaries fail closed. Selected upper clock-bound p95:

| Native RCPI store to Chromium presentation | RDK | prpl |
| --- | --- | --- |
| Room | 463 ms; two native samples | 599 ms; eight native samples |
| Topology | 106 ms; eight clients in one frame | 495 ms; ten native samples |

Room captures emit/receive 70/70 RDK and 352/352 prpl native events; topology
captures 138/138 and 673/673, with zero lost events. Small cohorts, shared
presentation frames, separate workloads and a colocated headless observer
preclude a stack ranking or population tail claim. This excludes RF generation,
complete handovers/animations and a physical display.

Room-campaign host sensors peak at 63°C on non-turbo RDK and 85.5°C on prpl.
RDK's package throttle counter does not increase; the prpl counter is
unavailable. RDK takes 96.047 s to regain default-room readiness after the
negative-control service-profile restoration. This maintenance recovery is
recorded separately from post-steer freshness and is not instantaneous startup.

### RDK post-steer freshness and early ownership

This investigation separates native cadence, API sampling and collection
ordering. The early-owner fix has regression coverage and a same-mode measured
run: complete post-verification evidence improves from **11.715 s to 9.602 s**.
This does not change the native five-second cadence or retroactively clear the
two pre-fix failed trials.

#### Same-trial no-hook baseline

The traced recovery baseline passes with **2471 received/emitted events,
zero lost**. Evidence paths in the outer guest (host mirrors prepend
`/home/rev`) are:

- Analysis: `/work/rf-recovery-0913/evidence/rdk-freshness-baseline-analysis.json`.
- Trace/report: `/work/rf-recovery-0913/evidence/rdk-traced-recovery-fresh-baseline-1/`, including `native-events.jsonl`.
- Acceptance report/cycles: `/work/rf-demand-0913/evidence/rdk-native-positive-recovery-fresh-baseline-1/`.

| Boundary after verification finished | Seconds |
| --- | ---: |
| First exact-target native RCPI store | 1.380 |
| API/collector serving-metric milestone | 3.702 |
| Complete candidate set | 8.614 |
| Target activity / complete snapshot | 11.715 |

The native figure joins this trial's trace and verification in the same guest
monotonic domain; the analyzer's generic native-arrival field remains null.
API/collector milestones are not native receipt times. Candidate sweep median
is 1.960 s, observer excluding candidates 0.222 s, and load enrichment 0.885 ms.
The baseline records target ownership before the first target counter, then
discards that counter at post-sweep enrichment. It consequently waits for
another baseline and the following roughly five-second report interval.

These are **blocking native-benchmark** observations. CLI/native acceptance
currently collect candidates directly; production room collection already
uses `StreamingCandidateProvider`. A two-second direct sweep is not evidence
of two-second production blocking. Candidate time is nested within observer
time, not additive. Earlier activity need not yield earlier completeness
while native candidate rejections remain.

#### Earlier evidence and source attribution

Earlier guarded trials remain under `/home/rev/work/rf-demand-0913/evidence/`.
Run 3 fails restoration and is diagnostic evidence, not a qualifying pass.
Source-AP association rejections persist after steering; HTTP success does not
prove complete candidates. Native handler residual includes protocol waiting.
Do not add nested candidate time to observer time.

Independent zero-loss render traces show roughly five-second same-owner report
cadence and 0.933–11.725 s handoff-to-target-store variability. They use different
controller identities from the guarded trials and cannot provide their native
arrival timestamps. Equal RCPI writes count. The newer same-trial baseline,
not retrospectively joined journals, establishes discarded-counter ordering.

Qualified source is `/home/rev/work/rf-recovery-0913/native-source`:
`src/em/metrics/em_metrics.cpp` validates association and unassociated-query
eligibility; `inc/em_metrics_time.h` subtracts wire sample age rounded upward
to whole seconds. Thus earlier sample timestamps do not establish API delay.
`src/rdkb-cli/candidate_coordination.go` uses a 100 ms cache and one native
command at a time; `src/rdkb-cli/main.go` polls at 100 ms, not the historical
1.5-second cache. Exact RCPI-store `0x89b90` and association-commit
`0xdf99a`/`0xdf9db` qualifications remain in
`/home/rev/work/rf-demand-0913/evidence/probe-profile`; requalify rebuilt binaries.

#### Local hook, evidence and rollout boundary

`NativeLoadProvider.observe_owners(clients, raw)` consumes the complete,
unambiguous controller roster before fallback/publisher/candidate work.
Register `observer.ownership_observer = provider.observe_owners` after
provider construction, before measured cycles or client filtering. Existing
metric publishers remain separate; asynchronous callbacks do not own this
state. No additional sweeps or native queries are introduced.

The shared provider resets observed source/BSSID ownership once, preserving
subsequent target baselines, including sources first seen after real ownership.
It invalidates changed provenance/radio/channel, disappearance and observed
leave/return; intervals cannot bridge transport changes. Original timestamps
remain intact. Activity must start strictly after ownership/context floors
and, for acceptance, verification. Missing/stale data stays unavailable.
Unobserved intervening associations are not proven by polling.

RDK `collection_timing.py`, `observer.py` and `candidates.py` retain request
brackets, partial-failure evidence and retry-separated timings.
`load_observer.py` records early owner floors/discarded receipts in
`raw.load_collection`, retaining them through enrichment.
`gen/tests/metric_freshness_analysis.py` analyzes saved trials and qualified
traces; it distinguishes legacy read bounds, age-adjusted samples, exact
requests and native writes, rejecting cross-trial attribution. Unattributed
candidate records from failed reads are excluded from current-cycle statistics.

Offline tests include `test_metric_freshness_analysis.py`,
`test_collection_timing.py`, `test_load_collection_timing.py`,
`test_owner_observation.py`, `test_owner_hook_wiring.py` and conductor wiring.
Coverage includes blocked/failed sweeps, first-source baselines, invalid
epochs, strict intervals and real single-flight streaming without extra rounds.
Passing these tests does not itself verify acceptance-main registration.

The same-mode traced control preserves identities and zero trace loss; early
ownership precedes the retained target baseline. Candidate readiness remains a
separate milestone. The production controller now includes patch 0193 and no
ASan runtime override. Do not resume extended UAF churn as RF qualification.
Any CLI/benchmark streamer reuse is a separately labeled measurement-mode
change and must preserve one-at-a-time native commands.

### General preparation

1. Reserve the lab; save configuration, native/container/medium identities and
   revisions. Exclude other leases/RF writers; preserve policy, timers and VM resources.
2. Copy deployed `gen/wmediumd/configurator/worlds/golden/*.world.json` into
   evidence and match loaded-world hashes. Copy `gen/tests/room-feature-guest-audit.py`
   and `gen/tests/room-feature-rf-audit.py` into guest `/tmp/`, retaining names.
3. Use Playwright/Chromium, preferably on a separate observer. If colocated,
   `--observer-cpus` restricts only owned GPU threads to valid CPUs. The SSH
   sampler needs two pre-mutation samples and runs through restoration,
   recording CPU/pressure, RAM, temperature and available throttling counters.
   Its stdin closes on shutdown; failure invalidates host coverage.
4. Verify `maximum_actions: null` and rate/oscillation/failure guards with
   `tests/room-final-readiness.py`; never restore the obsolete 2000-action override.
   Preserve explicit operator limits. Profile changes use named temporary
   drop-ins and room-only restarts outside measurement.
5. Exclude builds, exports, backups and maintenance from timing. On LXD timeouts,
   check `fstrim.service` and host/guest I/O pressure: loop-backed discard can
   stall idle guests. Keep maintenance timers enabled; document interruptions
   and rerun separately, never labeling host stalls as stack latency.

Retain failed/incomplete evidence and RF journals; no native restart may turn
a measured failure into a pass.

## Gates

| Phase | Required observation |
| --- | --- |
| Load | Browser selection auto-applies correct world/epoch, resets overrides and commits verified RF |
| Initial settling | Within 60 s after readiness: exact roster, no duplicate MACs, six mesh roles, matching physical/native/rendered ownership |
| Freshness | Current-epoch complete candidate coverage; evaluation and serving metrics at most 30 s old |
| Policy convergence | Complete fresh evaluation satisfies the configured steering margins; this is the pass gate |
| Strongest AP diagnostic | Report stronger same-band candidates and RCPI gaps separately; do not force margin-only roams |
| Stable gate | All required checks hold continuously for five seconds |
| Play | Real browser Play at 1×; monotonic clock, golden positions/presence, actual SVG nodes/parents |
| During motion | Record transient divergence; flag sustained view mismatch over five seconds only with adequate samples |
| Checkpoints | Allow 45 s per explicit pause, then resume on pass or timeout so later segments still run |
| End | Allow 90 s after completion for the same stable gate |
| Integrity | Native/container/medium identities unchanged; no hidden RF assistance, faults, SSE gaps or browser errors |
| Cleanup | Default twenty-client world, paused, no lease/fault; original service/action cap restored |

Moving targets need not continuously converge. At initial/checkpoint/final
settling, four bounded workers audit the complete fixed pool with
`iw dev wlan0 link`: online BSSIDs must match native ownership, offline
clients must disconnect, and missing observations fail. Record audit
`elapsedMs` separately without relaxing 90/60/90-second gates. Older reports
audited only offline clients and selected probes.

Audit before screenshots; retain model timestamp/age to avoid stale-owner
comparisons. Record actual gaps against the one-second sampling target;
unobserved intervals cannot prove continuous failure. Presence worlds require
exact MAC sets in both views and kernel links. Fronthaul loss must empty the
disabled role within five seconds while retaining backhaul. The read-only
midpoint audit checks directional gains against the asymmetric golden and
rejects cross-epoch samples. Protected backhaul must match the actual connected
tree, not geometric branches.

## Execute

The client-only harness lists geometry-backhaul rooms in `separateBackhaulRooms`
and rejects explicit requests for them, preserving room gates.

Reports use `convergenceCriterion=configured-steering-policy`.
`policyConverged` includes roster/ownership/freshness/completeness;
`optimizerPolicySatisfied` is the raw policy verdict.
`strongestApConverged`/`strongerClientGaps` retain stricter diagnostics.
Missing metrics, incomplete decisions or RF faults fail qualification.
Older reports retain their strongest-AP criterion.

From this repository on an observer able to SSH to the physical host:

```sh
node gen/tests/test-room-feature-acceptance.js
node --check gen/tests/room-feature-acceptance.js
export PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright-core
export CHROMIUM_PATH=/absolute/path/to/chromium/chrome
node gen/tests/room-feature-acceptance.js --yes-act --flavor rdk \
  --host rev140 --vm rdkeasymesh-0916 \
  --room-url http://192.168.2.140:49891/ \
  --topology-url http://192.168.2.140:49889/ \
  --worlds /absolute/path/to/deployed-goldens \
  --output /absolute/path/to/new-results --native-audits 1 \
  --initial-timeout 90 --checkpoint-timeout 60 --final-timeout 90
node gen/tests/room-feature-report.js /absolute/path/to/new-results \
  /absolute/path/to/deployed-goldens > audited-summary.json
```

Adjust deployment arguments; use `--observer-cpus CPU_LIST` on shared hosts.
Repeat `--world WORLD_ID` for targeted runs; omit for live catalog enumeration.
Simultaneous backends need separate evidence, browsers and samplers.
Inspect exit/report: completed playback alone cannot pass.

## Short backhaul feature test

The shared short suite runs three 24-second geometry-backhaul rooms through real
load/Play controls and Network Topology. Out-of-band LXD audits uplink BSSIDs
and gateway probes at pause/return. Start from a healthy, unowned default;
native processes, parent BSSIDs and action budgets remain unchanged.

```sh
PLAYWRIGHT_MODULE=/path/to/playwright-core CHROMIUM_PATH=/path/to/chromium \
node gen/tests/room-backhaul-features.js \
  --yes-act true --flavor rdk --host rev140 --vm rdkeasymesh-0916 \
  --room-url http://192.168.2.140:48891 \
  --topology-url http://192.168.2.140:48889 \
  --output /tmp/new-backhaul-feature-results
```

Use new evidence directories; retain RF, policy/clock, parents, native
links/probes and both screenshots. The 0916 harness requires actual branch
formation and handover, not only changed geometry. It checks exact native
process identities and initial/return client kernel ownership. The prpl copy
uses `--flavor prpl`, its own container/interface names, gateway and five
physical data-model nodes while still requiring six logical topology nodes.
Isolation requires −20 dB mesh links with the AP present and strong fronthaul,
an initial upstream probe within 15 s, then disconnected uplink/failed traffic.
Require ten-client return convergence within 60 s before Default.
`--room backhaul-isolation-recovery` selects that case; otherwise run all three.

Each half-script has 35 s; native midpoint checks allow 60 s. Cleanup checks exact default RF and allows 60 s for
twenty clients, six nodes and all-AP gateway probes. Missing evidence/recovery
fails; never hide it with forced parents or native restarts. This is bounded
functionality, not soak or complete native-policy qualification.

### Rev140 short results: 2026-09-14

Initial geometry-only checks passed for all three rooms in a 141-second live run, including
geometry RF application, real Play/checkpoints/return, native-parent authority
and exact fixed-RF restoration. Default recovery passed within its bounded
window: twenty clients, six topology nodes and gateway probes from every AP.
No native process restart or forced parent change was used by the test.

| Room | RF/features | Native observation during the short checkpoint |
| --- | --- | --- |
| Branch formation | Pass after radio-readiness recovery; stricter 91-second retest | Both branches and gateway traffic verified, all ten clients converged at the initial layout and movement checkpoint, both views agreed |
| Parent handover | Pass | No relay handover observed; the moving extender retained Agent-1 |
| Isolation/recovery | Pass, including focused retest | Verified working uplink → disconnection/failed traffic → native recovery after scripted return, then Default recovery |

The initial run exposed two limitations: extender `wifi1.1` AP interfaces
existed but did not report an operating backhaul SSID/channel in these samples;
and controller roster health could remain green while independent uplink
probes failed. Geometry-room loading now applies enabled, unstarted relay APs
and verifies backhaul STA interfaces are administratively up, without selecting
parents. Health also requires all six live topology nodes, not just cached DB
counts. Membership and signal bars still are not end-to-end connectivity proof.

Evidence and both-view screenshots are outside the repository at
`/home/rev/work/release-0913/evidence/backhaul-rooms-20260914-short-01/` on rev150.
`report.json` is the original run; `native-readiness-analysis.json` derives AP
readiness from its saved `iw` output without rerunning or changing the lab.
Review found that the original isolation room's initial one-packet upstream
probe had already failed. That run is retained, but is not a clean on/off
traffic proof. The starting/return position was moved closer to Agent-1 and
the harness gained the explicit initial-reachability gate. A focused 78-second
retest at `backhaul-isolation-20260914-short-02/` in the same evidence parent
passed initial traffic, actual isolation and native recovery within the
20-second return window, followed by verified default-room restoration.
Focused Python checks passed 96 tests and 14 subtests; viewer/browser,
documentation and golden-regeneration checks passed. No full catalog or soak
campaign was run, and the original eighteen golden room files were unchanged.

The missing-extender incident was a real link loss, not room presence removal.
After enabling relay APs and bringing the two down STA interfaces up, native
association selected `extender_3 → extender_1` and `extender_4 → extender_2`
without a BSSID write. These are stable world roles; displayed extender
ordinals can change after rediscovery. The prolonged outage also left both
nodes' client-facing APs inactive. Recovering their OneWifi/agent services and
replaying `/api/v1/metricsreporting/enable` restored APs and serving reports.
Those were explicit incident-recovery operations, not actions hidden inside
playback or the passing test. Radio preparation does not provide automatic
recovery from every native service fault during a long outage.

The stronger branch test requires operating backhaul APs and all six
client-facing APs per node, waits up to 60 seconds for initial client
convergence, then tests Play and waits up to 60 seconds at the checkpoint for
native parents, every AP's gateway probe, ten measured client decisions, and
both views to agree. This avoids mixing unfinished initial-room steering with
movement. The first two stricter attempts failed on client reporting/steering
and candidate-query contention; their evidence is retained, not counted as
passes. The final run passed in **90.756 seconds**, including default restoration
to twenty clients/six nodes. It observed initial convergence after 38.6 seconds
and checkpoint convergence 12.0 seconds after the first checkpoint sample.
The initial tree was already branched: this is a warm playback regression,
not a cold-start branch-formation or proactive backhaul-optimization benchmark.

Evidence is under `backhaul-relay-recovery-20260914/` and
`backhaul-branch-readiness-20260914-short-01/` through `-03/` in the same evidence
parent; `-03/report.json` and its two screenshots contain the passing result.
The readiness/health changes passed 146 focused Python tests plus ten subtests,
and the focused viewer/status/harness checks passed. PrplMesh was unchanged.

## Evidence and restoration

Retain per-room JSON, sampled JSONL, SSE, world hashes, screenshots and a compact
matrix: loaded/final/checkpoint convergence, presence/RF/visual correctness,
verified/failed/unmatched actions, p50/p95/max timing and native identities.
Distinguish collection, submission, verification and rendering intervals.
Absent timestamps are unavailable, not zero; timeouts are censored failures,
not omitted successful samples.

Always remove the named temporary service override, daemon-reload, restore the
original room and verify the default roster, paused time zero, no held lease,
no fault and the original action cap. Stop only owned browsers/host samplers.
For a separate opt-in crash-recovery test, use
`gen/tests/room-recovery-smoke.py --help`; it deliberately kills only the room
process and must be scheduled, not silently included in a normal room pass.

## Opt-in load-policy qualification

Run separately from the default catalog, as root **inside the lab VM** with
the default twenty-client room paused at zero and unleased:

```sh
ROOT=/opt/prplmesh-lab
PYTHONPATH="$ROOT/optimizer:$ROOT/wmediumd/configurator" \
  python3 "$ROOT/tests/load-policy-acceptance.py" --stack prpl \
  --root "$ROOT" --output /tmp/load-policy-new --yes-change-lab
```

For RDK set `ROOT=/home/easymesh/git/meta-cmf-bananapi-vcpe/gen` and `--stack rdk`.
The driver stops only the room, prepares two existing private clients and
two different 2.4-GHz channels, then offers two bounded 12-Mbit/s UDP flows.
Native load/activity and explicitly labeled hwsim candidate reports drive
one load-only BTM to a slightly weaker AP. Require native association
verification, no additional move during settling and positive receiver data.
BTM admission alone is not success; no forced roam repairs a measured failure.

Setup retries, decisions, client control events and receiver intervals are
retained. Cleanup restores RF overrides, channels, client frequency capability,
logging, owned traffic/capture processes and the original service, then checks
fresh twenty-client native metrics. RDK retunes use a single-radio South
subdoc, not global radio Apply or an agent refresh. The driver refuses
mismatched configured/live channels and verifies all three bands and the
unchanged agent PID after each change. Restore the lab before default-room
qualification if preparation or cleanup fails.
Separate preparation/cleanup from timed steering.
Receiver queue draining is not calibrated physical capacity.

## Current qualification

The 0916 catalog has 25 rooms: 22 client-policy and three geometry-backhaul
scenarios. Source `0e1dce8` passes the complete 22-client-room run, independent
report validation, unchanged native identities and default twenty restoration.
Evidence: `/home/rev/work/release-0916/evidence/rdk-clients-final/` on rev150.
Branch and isolation/recovery also pass; the new stronger-parent handover gate
remains unresolved. Retaining a usable old parent is not proof of proactive
strongest-parent steering. No 25/25 or artifact acceptance is claimed.
The new native-backhaul implementation must repeat this catalog on its rebuilt
runtime. Its handover gate also requires role 3 to return to the upper relay
within the original sixty-second return deadline, verified in the native
association and room topology with ten-client traffic/ownership convergence.
See [deployment status](../../current-state.md) for candidate ports and holds.

### Pre-band RF baseline

The September 13 catalogs passed 14/14 on each stack before the additional band,
capacity and geometry rooms. Their native identities, physical ownership, RF
and event checks remain historical evidence, not current coverage. Preserve
their original 60/45/90-second reports and failures rather than substituting
newer successes.

### Catalog performance

Each campaign must retain verified, failed, discarded and unmatched actions;
submission, request-to-verification, RF application and candidate publication
p50/p95/max; unavailable collections; and superseded generations. Different
native/NBAPI transaction boundaries are not interchangeable. Cancellations are
neither successful steers nor native failures. Timeouts remain failed samples.

### Per-room convergence

Report initial/checkpoint/final first policy convergence and the additional
five-second continuously verified hold. Near-zero final time means already
settled, not an instantaneous roam. Preserve absolute-strongest diagnostics:
a qualified policy pass does not require selecting the absolute strongest AP
at every instant. `room-final-readiness.py` uses the same fresh, complete policy
gate; `--require-absolute-best` adds the stricter check. Do not force a target
to make acceptance pass.

### Native metrics → browser presentation

Use the catalog's Playwright/Chromium environment and a new output directory
during scheduled movement. The tool only observes; the catalog or an operator
owns playback. On RDK:

```sh
node gen/tests/controller-render-latency.js \
  --scope metrics --url http://192.168.2.140:48889/ \
  --output /tmp/native-metrics-new --seconds 100 \
  --native-stack rdk --host rev140 --vm rdkeasymesh-20-0908
```

On prpl omit `gen/`, use URL `http://192.168.2.150:8091/`,
`--native-stack prpl --host rev150 --vm prplmesh-20-0908`.
The guest requires root Python/BCC and the exact qualified native binary hash;
the browser profile is **Chromium 139.0.7258.5**. Unknown native builds fail
closed; changed or missing browser trace identities cannot qualify a frame.
Captures own their receiver/browser, last at most 150 seconds with native
tracing, and restore the normal API wrapper before draining pending records.
There is no always-on observer, extra RF query, policy change or RF write.

`--scope associations` retains association-model timing; `--scope metrics`
adds **ordinary serving-link RCPI**, not association events masquerading as
signal updates. RDK probes the instruction following the accepted RCPI store
at file offset `0x89b90`; prpl uses `0x2737c1`. Both read the actual STA and
BSSID from the owning model. prpl's qualified Station/BSS layouts are pinned
by the controller digest. Requalify instruction boundaries and layouts after
native rebuilds; never disable the digest guard.

Join native RCPI transitions to `/clients` decode, exact owner/raw RCPI,
all ten SVG fills and covering Paint. Same-level changes require correct data,
not a nonexistent visual transition; equal reports never reset clocks.
Ambiguity, pre-request owner changes, stale/superseded metrics, timeouts and
incomplete traces fail. Proven request-start→decode changes are in-flight races;
the old-owner commit must still join uniquely, with clock-overlapping
boundaries unqualified.

Paint must match exact renderer/thread/main-frame→commit and hexadecimal
presentation identity, not two animation callbacks. Zero-frame or
missing/duplicate feedback fails. Sources: Chromium's
[presentation callback](https://chromium.googlesource.com/chromium/src/+/139.0.7258.5/third_party/blink/renderer/core/frame/animation_frame_timing_monitor.cc)
and [main-frame pipeline](https://chromium.googlesource.com/chromium/src/+/139.0.7258.5/cc/trees/proxy_main.cc).
Categories `devtools.timeline,blink.user_timing,benchmark` retain required flows
without unrelated `cc` scheduling. Recording: 128 MiB, no loss. JSON export:
512 MiB/30 s, outside latency/CPU windows; its memory is additional.

The following topology figures are retained September 12 baselines, not new
timings of the post-backport prpl dependency. The room profiles below are from
the final September 13 deployment.

| Qualified fullscreen topology baseline | RDK | prpl |
| --- | --- | --- |
| Ordinary RCPI → decoded response joins | 87/87 | 22/22 |
| Changed-meter → frame presentation joins | 49/49 | 7/7 |
| RCPI → presentation p95 interval | 457.11–458.51 ms | 347.20–348.11 ms |
| Maximum presentation upper bound | 499.56 ms | 348.11 ms |
| Maximum RCPI clock uncertainty | 3.27 ms | 2.94 ms |
| Association → presentation joins | 25/25 | 27/27 |
| Association → presentation p95 interval | 305.91–308.61 ms | 206.77–209.02 ms |

RCPI captures use RDK's `home-b-slow-walk-ten` and prpl's
`home-a-private-client-room-walk`; association captures cover evacuation.
Different movement cohorts and small prpl visual counts are **not an intrinsic
stack-speed comparison**. A separate RDK band-walk capture has 79/79 native
metric joins and 44/44 changed-meter frames. Earlier raw captures are retained;
`precision-audit.json` reapplies the conservative timer allowance to recorded
Chromium timestamps without modifying the original reports.

Monotonic clock brackets refresh every ten seconds and include 100 ppm drift
and [0.1 ms browser timer coarsening](https://developer.chrome.com/blog/cross-origin-isolated-hr-timers/)
at both calibration and event endpoints;
latency qualification requires ≤5 ms maximum uncertainty.
Native/perf loss, missing joins, API failures and trace errors fail.
Retain raw native events, clock samples and Chrome traces outside the repo.

#### Observer overhead

On paused, unleased default twenty-client labs, use new evidence and
`--scope overhead --seconds 30 --room-url http://192.168.2.140:48891/`
(prpl URL `http://192.168.2.150:18891/`). This separately qualifies overhead,
not zero-sample latency. Initialize Chrome tracing, then capture 20 s
before/30 s traced/20 s after. Require unchanged room epoch/roles/playback,
process identities, RCPI/associations, native events and zero loss.

Fixed budgets: callbacks p95 ≤2 ms/total ≤1% wall time including 0.2 ms each;
incremental controller/browser CPU ≤5/10 percentage points of **one core**.
Subtract the lower baseline, allowing ±2 scheduler ticks: a stationary
envelope, not a statistical confidence bound.

Both pass (RDK/prpl): controller **1.45/0.00**, browser **0.58/0.48**
percentage points; callbacks **0.115%/0.100%** wall time. Zero means no
detectable increase, not free probing. All windows keep the topology page open;
viewer-opening cost is excluded. Moving windows are not A/B controls; catalog
captures are not uncontended.

Scope is native model-store→headless topology presentation, not scanout,
completed animations, room WebGL, every counter or exact server publication.
Request/decode includes publication/polling/transport. Profiling cannot qualify
failed convergence or prove zero external delay.

### prpl snapshot coherence and candidate diagnosis

The September 13 follow-up reproduces a **different** reporting bug while
playing the perimeter room: `sta-04` appears at its old and new AP in one
topology sample (13 visible clients instead of 12). The room gate correctly
fails despite all 11 steering requests completing. The adapter had merged
independently timed, per-device STA snapshots across the roam.

The fix retains concurrent device metadata reads but obtains all STA
membership in one bounded NBAPI read. It does not guess the winning owner,
deduplicate by RSSI, cache a previous roster, or loosen the duplicate gate.
The focused repaired perimeter run passes, with **11/11** steers verified.
The prpl repository's `reference/observability/topology-adapter.md` documents
the read boundaries.

The preceding **30.36-second candidate gap remains unattributed**. Three
bounded diagnostic perimeter plays show no incomplete collections; the
retained duplicate-view failure is not counted as a room pass. Native packet
captures cover **8,460** unambiguous query/response pairs across the four
extenders, with no missing replies and a maximum observed turnaround of
**21.46 ms**. Pairing uses agent/opclass/station set with exactly one pending
request, not an assumed matching response MID. These observations cannot
explain an earlier uncaptured failure.

The full follow-up catalog does reproduce an availability failure while
loading `home-b-slow-walk-ten`, at **01:50:24 UTC**:

- Agent `prpl-agent-02` receives an operating-class-115 query containing ten
  stations. Its response follows **2.754 ms** later but contains only nine;
  `02:00:00:20:05:00` is missing. The controller-side capture confirms the same
  omission; all five capture interfaces report zero kernel drops.
- The native HAL logs `No wmediumd candidate metric` for that first station.
  The remaining nine reported RSSIs have the preceding station's values:
  the signal-to-client mapping is shifted, not just late.
- The new timeout diagnostic retains RCPI 78 and timestamp
  `2026-09-13T01:50:23Z` unchanged through the last NBAPI read at 01:50:54.140.
  Freshness correctly refuses that stale entry. The next measurement round
  recovers, and the room initially converges in **40.49 seconds**, inside the
  unchanged 60-second bound. The incomplete collection remains a failure.

The previous laboratory HAL's `read_snr` used one `send`/`recv` pair, continued
on a failed receive, and checked frequency but not the echoed source/destination.
An offline fault-injection harness using that exact function reproduces a
missing first metric and misassigned subsequent RSSI when the first `recv`
returns `EINTR`. This proves a transport-handling weakness, **not which errno
occurred live**: that HAL did not log it. Packet turnaround rules out
a 30-second bridge/1905 delivery delay for this particular response, not all
possible native delays or the earlier six-entry failure.

**HAL repair 0015:** interrupted sends/receives retry the same operation within
one shared one-second monotonic exchange deadline. An interrupted receive never
resends its request. Validate response length, protocol, status, frequency and
both echoed MACs; abandon the entire candidate batch on failure, closing its
socket instead of assigning another client's signal. Failed exchanges now log
the requested station, interface, response length and errno. HELLO uses the
same bounded exchange. No freshness interval or optimizer timeout is relaxed.

`tests/candidate-transport-test.py SOURCE` compiles the assembled native reader
and exchange, not a Python reimplementation. Fourteen scenarios cover send and
receive interruption, wrong source/destination/frequency/opcode/status, short
messages, late replies and a bounded signal storm. Real Unix `SOCK_SEQPACKET`
tests include a targeted `SIGUSR1` interruption and a real receive timeout;
successful transactions preserve the two distinct station values. Both the
repository regression and the actual canonical build source pass.

The rev150 deployment replaces only installed `libbwl.so.6.0.0` and refreshes
the internal runtime payload/provenance used by normal lab startup. Its digest
is `f50f5834b65c287cf1513aed583adc48545cb422f83aefbcb5543091eba0a971`.
Controller/agent/fronthaul binaries, qualified RF-load support and reporting
cadence remain unchanged. This is not a new thin release or box.

**Incremental build prerequisite:** check `CMAKE_HOME_DIRECTORY` and the full
patch set, including ABI-changing RF patch 0014, before reusing a build tree.
This host's matching tree is `/opt/prpl-build-0908` with source
`/opt/prplMesh-0908`; the older `/opt/prpl-build-nl80211` is not equivalent.
An initial mismatched-library deployment crashed fronthauls at HAL attachment;
the correctly patched build resolves it. The raw build library also has build
directory RUNPATHs: deploy the CMake-installed library, not `out/lib` directly.
Dependency resolution alone does not prove C++ ABI compatibility. Failed setup
logs remain separate from room qualification. Do not reuse those binaries.

A real stalled/failed exchange can still make native measurement collection
unavailable; fail-closed behavior is intentional. Neither passing tests nor a
later clean catalog proves the cause of the original uncaptured 30.36-second gap.

Candidate timeout transactions now retain the missing entries' baseline and
last parsed signal/timestamp, plus the last-read time, without extra NBAPI calls
or changed timeouts. In a prpl lab VM, as root, capture native evidence with:

```sh
python3 /opt/prplmesh-lab/tests/prpl-candidate-capture.py \
  /tmp/prpl-candidates-new --seconds 180
```

The opt-in collector owns five bridge pcaps and filtered native logs, stops
its processes, and leaves radio/link state untouched. Bounds are 5–2400
seconds and 256 MiB; touching the output directory's `stop` file ends it early.
Require exit zero; inspect packet-drop counts in `*.pcap.stderr` and cleanup in `capture.json`.
Preserve native packets alongside room `events.jsonl`; do not turn a recovered
timeout into a successful collection.

### prpl cold candidate registration

The first passing post-HAL/ubus catalog exposes a separate startup delay:
24 independent `AddUnassociatedStation` calls run serially in the first
stationary-room collection. Their wall span is **3629 ms**, summed RPC time
**3628 ms**, and complete collection **4079 ms**. Native bridge responses are
not responsible for that registration span.

Registration now uses at most **four workers**, only for uncached targets.
Successful registrations are cached on the collecting thread; on failure,
queued work is cancelled and running calls are drained before raising the
error. Only actual successes survive for retry. Generation checks still occur
before each native RPC; no timeout, timestamp guard or policy is relaxed.
Warm rounds create no registration pool and send no registration calls.
Regression tests require concurrent progress, enforce the four-worker limit,
check successful-only caching/retry and reject superseded generations.

In the repeat, a 24-call preflight batch spans **1314 ms**, with four observed
concurrent RPCs and **4912 ms** summed RPC time; its complete collection is
**1896 ms**. These equal-count batches have different room phases and targets,
so this is an observed reduction in serialization, not a controlled end-to-end
speedup claim. The first stationary-room batch now has eight calls rather than
24; its **425 ms** registration span must not be compared as equal work.
The full final catalog, not just this faster cold batch, must pass unchanged.
Raw events and `registration-audit.json` retain counts and timestamp boundaries.

Parallel registration also overlaps identical native query rosters. Responses
do not echo query MIDs, so these bursts cannot support exact per-request latency
joins. `packet-group-audit.json` instead reconciles **17,798 queries and 17,798
responses** by exact agent/opclass/roster, with no outstanding groups or orphan
responses. **331 queries in 140 concurrent groups** are excluded from individual
timing claims; their maximum group-drain span is **40.92 ms**. All five capture
interfaces report zero kernel drops. The older single-pending auditor's
ambiguities and leftover responses are retained, not silently treated as exact
matches. Group counts do not prove request identity within concurrent bursts.

### Playback reply ordering

The first HAL-repaired prpl catalog remains **13/14**, not a pass. All steers
and convergence gates succeed, but one `home-a-slow-walk-ten` frame shows the
zero-second clock with ten clients' one-second positions. Native playback
events are coherent: revision 534 starts at zero, and revision 535 advances
clock and roles together 33 ms later. The viewer's Play HTTP callback could
then apply the older reply's clock alone after the newer SSE event.

The common viewer now applies playback replies, events and interaction
snapshots as revision-ordered clock/role updates. Older revisions and backwards
time within one revision are rejected together; a newer revision can rewind.
A committed world establishes a new revision boundary. Active drags and
acknowledged preview cleanup remain intact. No polling, native restart, delay
or acceptance-tolerance change is added.

`tests/viewer-playback-order-test.js` executes the actual viewer functions with
a deliberately delayed Play response. The previous source reproduces the
0-versus-1000-ms clock failure; repaired source passes, including stale full
snapshots, same-revision clock regression, rewinds, world reset and dragging.
The focused slow-walk room then passes on both labs with **19/19** verified
steers each. The final full catalogs qualify the common viewer on both hosts;
the first failed prpl catalog and before/after regression logs remain retained.

### prpl libubus reentrancy

A subsequent catalog stops qualifying when the native controller crashes in
`libubus:ubus_cmp_id` at approximately **03:35:56 UTC on September 13**. Its
NULL AVL key is recorded by the guest kernel; topology becomes unavailable,
not falsely converged. The run is retained as failed. The existing unseen
Apport report prevented a new core, so the exact live call chain is unavailable.

The lab pins ubus at `13a4438b4ebdf85d301999e0a615640ac4c9b0a8` (2020).
Inspection finds a demonstrable recursive-dispatch defect: a callback can
drain the pending list while its outer iterator retains the next entry.
Object callbacks can also be reentered before returning. The narrow dependency
backport incorporates upstream
[safe pending iteration](https://github.com/openwrt/ubus/commit/2099bb3ad997),
[outer-handler draining](https://github.com/openwrt/ubus/commit/ef038488edc3),
and [nested-object deferral](https://github.com/openwrt/ubus/commit/a72457b61df0).
Queued work drains without waiting for another socket-read event; there is no
new mutex, poll interval, optimizer delay or EasyMesh policy change.

`tests/ubus-reentrancy-test.py UBUS_SOURCE` compiles the actual dispatch
functions with controlled callback/socket boundaries. Five cases check
recursive queue consumption, nested dispatch, an empty socket, an active
outer request and disconnect handling. The old source processes a retired
message twice; repaired source passes all five. The repository fixture is
extracted from the pinned source, and the regression includes that negative
control. This proves the source defect, **not the exact cause of the uncored
live crash**; retain the crash evidence if it recurs.

`patches/ubus/0001-libubus-guard-reentrant-message-dispatch.patch` is applied
by normal builds. Packaging checks the installed dependency's source,
patch-set and library digests against build-time provenance. Normal node
startup refreshes dependencies from the internal payload after stopping native
processes, unlinking old library files before extraction so existing mappings
are not truncated. Existing containers therefore do not retain an older base
image's library. The deployed library digest is
`0506ee044dce344af3325fe04a4277e0d1fd2d7d67ae0f187112165878963214`.
The dependency archive changes only this library and adds its provenance;
controller, agent, fronthaul, hostapd and libubox remain unchanged.
A bounded live probe observes **22,807 object additions / 22,892 removals**
over 180 seconds, with no nonzero returns or lost events; the controller stays
alive. This exercises the dependency path, not every possible crash condition.

### Room WebGL presentation

The common opt-in profiler also covers decoded room network snapshots to
**client gauge materials and association-line geometry, actual WebGL draws,
canvas mailbox preparation, and exact Chrome frame presentation feedback**:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright-core \
CHROMIUM_PATH=/path/to/chromium-139.0.7258.5/chrome \
node gen/tests/room-render-latency.js --url http://192.168.2.140:48891/ \
  --output /tmp/rdk-room-render-new --seconds 65 \
  --native-stack rdk --host rev140 --vm rdkeasymesh-20-0908
```

For prpl omit `gen/`, use `http://192.168.2.150:18891/` and
`--native-stack prpl --host rev150 --vm prplmesh-20-0908`; omit native arguments
for decode-only profiling. Observe separately controlled playback in full screen.
Only the profiler's page enables `?profile=1`; remove it before export.
Default viewers add no observer, queries, pixel readback or synchronous GPU wait.
Pin Chromium/SwiftShader; restrict the owned GPU process to CPUs 0–1/nice 19.

Require one canvas, correct colors/endpoints, actual draws, exact
renderer/thread/main-frame identity and one pre-commit
[`DrawingBuffer::prepareMailbox`](https://chromium.googlesource.com/chromium/src/+/139.0.7258.5/third_party/blink/renderer/platform/graphics/gpu/drawing_buffer.cc).
Missing/duplicate joins, trace/SSE/context loss or API failures fail.
Collapsed exported frames require exact begin-frame ID, unique render interval
and matching duration, never nearest-frame guessing. Markers include observer
work; browser timer uncertainty is ±0.2 ms.

Native joins require digest-qualified serving stores and exact STA/BSSID/RCPI
transitions/frame. Reject ambiguity, repeated transitions, fallback/stale data,
wrong RSSI conversion, uncertainty >5 ms, missing events and empty joins.
Stop native capture before export; retain process/clock evidence. Search is
bounded to 30 s, not assumed identity. SSE may coalesce values, and distinct
RCPI values may share one bar level: these are publication joins, not every
native sample.

| Qualified fullscreen band-walk profile | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| Checked and presented network frames | 259/259 | 259/259 |
| Frames with changed client state | 42 | 54 |
| SSE decode → presentation p95 upper | 323.72 ms | 225.30 ms |
| Maximum decode → presentation upper | 413.19 ms | 318.31 ms |
| Observer callback p95 upper | 0.40 ms | 0.50 ms |
| Observer callback wall-time upper fraction | 0.134% | 0.170% |
| Qualified native RCPI joins | 90/90 | 53/53 |
| Joins changing signal-bar level | 58 | 40 |
| Native RCPI → SSE decode p95 upper | 471.36 ms | 461.21 ms |
| Native RCPI → presentation p95 lower–upper | 758.22–761.26 ms | 634.95–637.48 ms |
| Native RCPI → presentation maximum upper | 781.59 ms | 647.74 ms |
| Maximum joined clock uncertainty | 3.12 ms | 3.05 ms |
| Native events captured / lost | 185 / 0 | 965 / 0 |

Callback budgets remain p95 ≤2 ms/≤1% wall time. Removing layout-forcing
canvas reads reduces the initial 4.10 ms p95 upper to these values; retain
failed/empty captures. The 65-second profiles accompany unchanged catalog gates.
Hosts, native cadence and software GPUs preclude stack-speed ranking.
Receiver CPU is **0.116/0.353 s** over ~67 s (RDK/prpl), with no native/Chrome
loss; reports retain resources. RDK raw evidence passes stricter RSSI conversion.

Scope is **controller RCPI-store→room presentation**, not RF generation,
reception→controller, scanout, pixel-exact framebuffer, completed animations,
every mesh/wall effect or zero external delay. Topology profiling is separate.

### Opt-in policy outcome

Three RDK warm-retune repetitions and the broker-enabled prpl qualification pass with
the production twenty-client pool intact. Native AP metrics/activity drive one gentle BTM to a slightly
weaker, quieter AP on another 2.4-GHz channel. Signal-only remains the default.
Both live-room recommend-mode smoke tests also pass, including owned receiver
shutdown and restoration; these smoke tests authorize no steering.

| Observation | RDK | prpl |
| --- | --- | --- |
| Source → target RCPI | 148 → 144 | 148 → 144 |
| Native utilization, octet 0–255 | 234 → 11 | 234 → 17 |
| Sustained condition before action | 10.053–11.560 s | 5.032 s |
| Request → native verified association | 1.207–1.440 s | 0.719 s |
| Verifier-only interval | 1.157–1.390 s | 0.288 s |
| Additional actions during ≥20 s settling | 0 | 0 |

RDK uses five-second report skew/freshness and a ten-second hold because its
independent native periodic reports arrive staggered. prpl uses one-second
skew/five-second hold. Both AP reports must advance; default room gates and
native reporting intervals do not change. Unknown/stale load never means idle.

Two 12-Mbit/s UDP senders deliver approximately **13.59 → 26.15 Mbit/s RDK**
in receiver windows 5–15 s and 65–75 s. The separate prpl repeat delivers
**12.60 → 24.63 Mbit/s** in the same windows. Later windows include queued
traffic draining and can exceed the 24-Mbit/s offered rate; these are receiver
delivery observations, **not calibrated capacity or steady-state gains**.
Packet activity is not offered demand; wireless hops are not backhaul capacity.

Client control events confirm native BTM reception, scan and association.
Setup scans/roams and retunes occur before timed
steering; cleanup restores them and verifies fresh twenty-client metrics.
The RDK target starts and ends at **6/36/37** (2.4/5/6 GHz); only its
2.4-GHz channel changes. This is not arbitrary radio-configuration qualification.
No forced roam repairs a measured failure; earlier failures remain evidence
in the timeout investigation below.

### Native-load coverage

`tests/native-load-acceptance.py` checks the default lab read-only for twenty
seconds: thirty private/IoT BSS loads, association-matching station counts,
twenty client activities, advancing timestamps, and unavailable data after
receiver shutdown. Run inside the VM with new evidence:

```sh
PYTHONPATH=optimizer python3 tests/native-load-acceptance.py \
  --stack prpl --output /tmp/native-load-new
```

RDK uses `PYTHONPATH=gen/optimizer`, `gen/tests/native-load-acceptance.py`,
`--stack rdk`. No retunes, injected traffic, steering or restarts.

September 12 passes: complete coverage **2.155 s prpl/10.333 s RDK**, requiring
two counters. One owned prpl `uds_broker` AP Metrics Response subscription
covers colocated/four remote APs; RDK uses Ethernet. Provenance distinguishes
`prpl-local-broker`, `prpl-1905-broker`, `ieee1905-ethernet`.

The pinned-source/live-layout-qualified prpl v6 x86_64 little-endian envelope
retains its **whole-second native publication timestamp**, never queue/NBAPI
read time. Reject >5-second/future reports, unsupported envelopes, disconnected
receivers and duplicate/older refreshes. No extra native queries, agents,
services or ports; signal-only starts no collector.

prpl recommend mode exposes local APs and cleans up its receiver on default.
Both UDP/native-BTM checks pass with no further move over twenty seconds.
Evidence: `/home/rev/work/steering-local-ap-0912/` directories `*native-load*/`,
`steering-local-ap-prpl-load-1/`, `rdk-load-3/`,
`steering-local-ap-prpl-room-load/`.

### RDK steering-timeout investigation

Retained failures are specifically:

- **15.178 s:** September 12 17:05:21 UTC, STA `02:00:00:00:03:00`,
  `02:00:00:88:ae:ac` → `02:00:00:da:2e:b2`, channel 1.
- **40.088 s:** 17:10:24 UTC, evacuation STA `02:00:00:00:0d:00`,
  `02:00:00:da:2e:b2` → `02:00:00:c7:08:e5`, channel 6.

Both requests received successful native-helper acknowledgements in about
50 ms, but controller association verification stayed at the source.
The evacuation collector remained fresh and both views agreed; it was not a
forty-second browser repaint delay. The retained records lack synchronized
BTM/client/native-commit evidence for those exact failures. They cannot
distinguish an untransmitted request, client refusal or lost native reporting.
Their root cause therefore remains **unproven**, not fixed by inference.

Three bounded load repeats and two warm evacuation load/play runs now verify
**39/39 steers**, without native resets or relaxed gates. The first two loaded
moves take **1.207 / 1.440 s** from request to verification; transmitted BTM,
token-matched acceptance, target association and native commit are joined.
The previously failing evacuation tuple verifies in **1.490 / 0.886 s**.
Full BTM/acceptance/association/native-commit packet joins cover **37/39**;
two 6-GHz moves have protected action frames without a decoded BTM join.
All native uprobe traces close with matching event counts and zero lost events;
packet captures report zero kernel drops. The shared native-commit tracer now
opens its consumer before attaching probes, closing a startup observability
race without changing native behavior.

Keep the old failures. On recurrence capture all four boundaries before any
reset; API admission is not proof of transmitted BTM. The bounded drivers,
pcaps, client events, native commits and explicit ambiguous joins are in
`/home/rev/work/steering-local-ap-0912/rdk-*` and `rdk-summary.json`.
Single-guest wall/monotonic packet joins are not calibrated compositor timing.

### RDK warm-retune regression

The qualification driver replaces global `ApplyRadioSettings` plus agent
restart/policy replay with `Device.WiFi.WebConfig.Data.Subdoc.South`, using
`radio_2.4G` and a copy of the live `Init_dml` radio configuration. It preserves
all other fields, restores the original auto-channel setting, checks every
band against kernel/native inventory and rejects an agent PID change.

Two underlying reporting defects are fixed: missing OneWifi boolean function
declarations made i386 callers mistake completed radio timers for active ones;
the agent admitted channel reports only during controller channel selection
and considered only the first radio. Single/full-radio callbacks now match
their included radios in operational states; malformed/empty decodes fail closed.
Neither fix changes optimizer policy or invents controller measurements.

Four isolated channel changes plus four load-test changes pass in
**4.296–7.039 s**, without an agent restart or reporting-policy replay.
The 5/6-GHz radios stay at 36/37; all twenty clients regain fresh metrics.
This includes OneWifi's settling/publication timers, not instant retuning.
The initial single-radio attempt timed out after 35 s despite a correct
kernel channel; fixing OneWifi alone exposed the separate native dispatch gate.

Two successful loaded moves have packet traces with zero kernel capture drops.
Request → transmitted BTM takes **0.636–0.876 s**, BTM transmission → target
reassociation response **0.136–0.156 s**, and that response → API verification
**1.163–1.510 s**. These spans are not pure optimizer time; publication and
observation still contribute. Rate-limited journals cannot prove missing
events. The earlier intermittent 15/40-second failures are not yet explained.
Evidence: `/home/rev/work/rdk-retune-steering-0912/`, especially
`single-radio-qualified.json`, `load-2/`, and `load-3/`.

### Extender-loss repair and attribution

Two independent native publication stalls are removed:

1. **OneWifi 0028:** publish pending association deltas after completed control
   events, rather than waiting for the idle-only one-second analyzer.
   The existing encoder, notification path and analytics stay on the control
   thread; the periodic path remains available.
2. **Agent 0186:** advance ready commands after native events, including
   retiring completed work before admitting queued notifications. Preserve
   queue order, exclusive radio ownership and recursive command locking.
   Event dispatch never advances timeout statistics or transient handlers;
   the existing 250-ms timer still owns retries and expiry.

Both OneWifi variants and the agent are rebuilt; only rev140 is deployed.
The agent update preserves running OneWifi processes. Native controller,
HAL, hwsim, wmediumd, supplicant, scan frequencies and PMF timers are unchanged.
No forced roam, shortened security timer or relaxed acceptance gate is used.

Three warm 90-second loss/recovery repeats (`both-1/` through `both-3/`)
pass, followed by the complete 14-room catalog. In every qualified loss run,
the sampled room/topology has no clients on the disabled extender from room
time 25 s until fronthaul restoration at 60 s; backhaul stays connected.
Full-band scanning and the approximately one-second PMF recovery exchange
remain observable.

| Measured boundary | Before | Three warm repaired repeats |
| --- | --- | --- |
| OneWifi association callback → publication entry, median | 448.195 ms | 0.362–0.688 ms |
| Same callback → publication, maximum | 923.286 ms | 3.173 ms across 43 events |
| Native 6-GHz connection complete → controller commit | 524 ms in the failing OneWifi-only repeat | 35–54 ms |
| RF absence acknowledgement → controller commit | 5.115 s in that failing repeat | 4.189–4.610 s |

The first boundary includes callback work, not just queue waiting. Native
function probes use the guest monotonic clock; a sampled offset joins the RF
journal. Topology observations are approximately one second apart, not
compositor timestamps. These are measured deployment intervals, not instant
RF recovery or pure optimizer execution time.

All three repaired repeats have complete agent/controller probe counts with
zero lost events and clean supplicant capture completion. Their management
captures and the full catalog's management/1905 captures have zero kernel drops.
Failed/partial diagnostic captures remain separate from this evidence.

The original post-retune catalog and its focused repeat remain failures:
client `02:00:00:00:0e:00` still appeared on Extender-4 at room time 25 s.
OneWifi-only repeat `after-3/` also fails, showing that removing the first
stall alone was insufficient. The online runner and independent audit share
the unchanged outage gate and exit nonzero on failed or incomplete qualification.

Assembled-source regressions cover immediate publication, pending work,
timeout cadence, radio exclusion, FIFO admission and concurrent completion:

```sh
python3 gen/tests/association-publication-test.py "$ONEWIFI_SOURCE"
python3 gen/tests/orchestrator-ready-test.py "$MESH_SOURCE"
python3 gen/tests/orchestrator-completion-race-test.py "$MESH_SOURCE"
```

### Host headroom and restoration

The owned two-second sampler covers both catalog windows. Expensive frequency
and process attribution are opt-in, off by default. Unsupported counters stay null.

| Full-catalog observation | RDK / rev140 | prpl / rev150 |
| --- | --- | --- |
| Samples / maximum gap | 811 / 2.005 s | 693 / 2.007 s |
| Total CPU p95 / peak | 14.75% / 20.85% | 33.90% / 41.28% |
| Minimum available RAM | 49.96 GiB | 12.74 GiB |
| Peak sampled sensor | 99.00°C | 85.50°C |
| Package throttling duration / measured window | 1788 ms / 1620.73 s | Unsupported, not zero |
| Package throttling time fraction | 0.1103% | Unsupported |
| Sampler elapsed p95 / max | 3.63 / 5.90 ms | 1.59 / 7.14 ms |

rev140 lacks thermal headroom, not RAM or sustained total CPU capacity;
do not infer a need for different hosts/resources. Host power policy is unchanged.

Read-only inventory: NUC12WSKi7/i7-1260P, BIOS 2022-03-22, `intel_pstate`,
`powersave`; hwmon exposes no fan RPM/PWM. Software cannot establish vent,
dust, fan or firmware-profile condition. A separate 90-second paused-default
sample averages **10.15% CPU**, peaks **13.07%/89°C**, and adds **0 ms**
package throttling; the VM averages ~1.5 logical CPUs, not sixteen.
Neither repaired cooling nor sustained overload follows.

The **100°C** junction limit is not an operating target
([Intel specification](https://www.intel.com/content/www/us/en/products/sku/226254/intel-core-i71260p-processor-18m-cache-up-to-4-70-ghz/specifications.html)).
In maintenance, inspect clearance/vents/fan per manufacturer guidance,
firmware Cooling settings and model-specific updates
([ASUS guidance](https://www.asus.com/us/support/faq/1052612/)).
Record changes; no firmware update/reboot during qualification and no VM-limit
workaround. Repeat the same bounded workload/power policy, comparing temperature
and throttling; persistent limit hits need hardware attention.

The observer runs on rev150, so results are deployment observations, not
uncontended comparisons. The final prpl catalog follows its dependency repair;
it is not simultaneous with the final RDK window. A separate 180-second prpl
ubus diagnostic overlaps the preceding pre-registration catalog's first rooms,
not either final native/frame profile.

Both labs return to **20 clients/six logical roles**, default world paused at
zero, no lease/fault, fresh complete metrics and cap 100. Catalog restoration
first converges in **26.36 s RDK / 10.14 s prpl**, then holds.
Separate readiness checks pass in **12.484 s RDK / 10.139 s prpl**.
VM autostart remains disabled. No native restart occurs inside either final
catalog. Only internal startup payloads are refreshed; no thin tar or box is made.

### Evidence and limitations

Latest evidence is on rev150 under `/home/rev/work/hal-room-end-to-end-0913/`:

- `final-status.json`: audited catalogs, profiles, restored readiness and exact scope.
- `rdk-all-rooms-final/`, `prpl-all-rooms-registration/`: final 14-room results, sampled JSONL, fullscreen screenshots, host samples and native packets/logs.
- `rdk-native-room-final/`, `prpl-native-room-registration/`: native events, clock brackets, Chrome traces and strict WebGL presentation reports.
- `prpl-all-rooms-final-2/`: passing pre-registration catalog; `registration-audit.json` preserves observed RPC counts, concurrency and durations across both prpl catalogs.
- `packet-group-audit.json`: final prpl packet counts and concurrent-group bounds, distinct from exact single-request timing.
- `prpl-focused/`, `*-playback-fixed/`: candidate and clock/pose focused checks; `prpl-all-rooms/` retains the 13/14 viewer failure and `prpl-all-rooms-final/` the controller-crash attempt.
- `runtime-member-audit.json`, `ubus-runtime-member-audit.json`: exact internal-payload changes; native HAL/ubus source, build, fault-test and failed-deployment logs remain alongside.
- `rdk-final-readiness-2/`, `prpl-final-readiness-4/`: fresh default twenty-client policy convergence, paused/unleased and cap 100.

Earlier native-RCPI/topology timing and controlled overhead qualification remain
under `/home/rev/work/metric-presentation-0912/`; candidate-gap/adapter evidence
under `/home/rev/work/candidate-room-profiling-0913/`; native load and retained
RDK timeout evidence under `/home/rev/work/steering-local-ap-0912/`.
Extender-loss before/after evidence remains under
`/home/rev/work/extender-loss-fix-0912/`. Raw artifacts stay outside the repos;
failed, empty or ambiguous captures are not relabeled as passes.

Python regressions: **707 passed RDK / 605 passed prpl**. Both execute the
five daemon-integration checks using `WMDC_TEST_DAEMON`; RDK's four VirtualBox
contract checks remain explicitly skipped because Ruby is absent. Common
viewer/profiling JavaScript, documentation links and prpl Go race tests pass.
The actual native HAL passes fourteen fault scenarios; ubus dispatch passes
five callback/queue scenarios plus packaging-provenance negative controls.
Builders are stopped; owned captures end and `hwsim0` returns to DOWN.
The user's `hwsim0.pcap` is untouched. No thin release or box is produced.

### Remaining boundaries

The requested candidate-transport, bounded registration, common playback-
ordering and native serving-RCPI→room-presentation work is qualified above. The
ubus follow-up fixes a demonstrated dependency bug, without proving the exact
call chain of the uncored native crash. Preserve a current core/native trace
before any reset if it recurs; the historical uncaptured prpl gap and RDK
15/40-second failures also remain unattributed, not silently fixed by a pass.

Physical cooling inspection on rev140 requires an operator maintenance window.
Physical PHY/DCF, collisions/interference, reception-backed candidates,
calibrated demand/capacity, other native counters, and true RF-generation-to-
display timing are separate extensions. The qualified boundary starts at the
controller's serving-RCPI store, not reception or RF generation; headless
presentation feedback is not physical scanout. Finite tests do not establish
zero external delay or soak reliability. Packaging remains a separate task.
prpl's whole-second timestamp guard remains necessary until native publication
has sufficient request identity or timestamp precision; freshness is not weakened
to remove that measured wait.
