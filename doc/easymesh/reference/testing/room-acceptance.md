# Room correctness and convergence acceptance

[Testing reference](README.md) · [Expected room features](../rooms/catalog.md)

Run every advertised room sequentially within each lab; independent RDK and
prpl runs may overlap across hosts. This is bounded feature testing, not a soak
or intrinsic stack-speed ranking. A targeted `--world` run is not full coverage.

## Preparation

1. Reserve the lab. Save initial room/service configuration, native/container/
   medium identities and source revisions. No other operator lease or RF writer
   may be active. Do not alter native policy, metrics intervals or VM resources.
2. Copy the **deployed guest's** `gen/wmediumd/configurator/worlds/golden/*.world.json`
   to the observer evidence directory. Match hashes to the loaded world.
3. Copy `gen/tests/room-feature-guest-audit.py` and
   `gen/tests/room-feature-rf-audit.py` into the guest's `/tmp/`, keeping names.
4. Use an installed Playwright/Chromium and preferably a separate observer.
   If colocated, restrict only owned browser GPU threads with `--observer-cpus`,
   using valid CPU IDs. Record host CPU/pressure/temperature/throttle counters
   with `gen/tests/room-feature-host-monitor.py` before, during and after.
5. The room's default 100-action cap is session-wide. A complete catalog may
   exceed it. Save the unit and, if needed, create a **named temporary runtime**
   drop-in under `/run/systemd/system/` that copies the original `ExecStart`
   with only `--max-actions 2000` changed. Clear the old ExecStart in the
   drop-in, daemon-reload and restart **only the room**, outside measurement.
   Verify twenty-client readiness and the chosen cap. Remove only this drop-in
   and restore the original configuration after testing.

Do not discard an RF journal or restart native services to make a case pass.
Keep failures and incomplete runs in separate evidence directories.

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

A continuously moving target need not be strictly converged every instant.
Record one-second target sampling cadence and actual gaps; screenshots can
slow sampling. Do not infer continuous failure across unobserved intervals.

For presence worlds, inspect exact MAC sets in both views and kernel links at
settled boundaries. During fronthaul loss require no clients on the disabled
role after five seconds while backhaul remains connected. Check directional
RF gains against the asymmetric golden via the read-only midpoint audit;
reject samples crossing epochs. Protected startup backhaul need only match
the connected actual tree, not form geometric branches.

## Execute

New reports identify `convergenceCriterion=configured-steering-policy`.
`policyConverged` includes roster, ownership, freshness and completeness checks;
`optimizerPolicySatisfied` is only the policy's raw verdict. The separate
`strongestApConverged` and `strongerClientGaps` preserve the stricter diagnostic.
Missing metrics, incomplete decision coverage or an RF fault cannot pass either
qualified verdict. Older reports retain their original strongest-AP criterion.

From this repository on an observer able to SSH to the physical host:

```sh
node gen/tests/test-room-feature-acceptance.js
node --check gen/tests/room-feature-acceptance.js
export PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright-core
export CHROMIUM_PATH=/absolute/path/to/chromium/chrome
node gen/tests/room-feature-acceptance.js --yes-act --flavor rdk \
  --host rev140 --vm rdkeasymesh-20-0908 \
  --room-url http://192.168.2.140:48891/ \
  --topology-url http://192.168.2.140:48889/ \
  --worlds /absolute/path/to/deployed-goldens \
  --output /absolute/path/to/new-results --native-audits 1 \
  --initial-timeout 60 --checkpoint-timeout 45 --final-timeout 90
node gen/tests/room-feature-report.js /absolute/path/to/new-results \
  /absolute/path/to/deployed-goldens > audited-summary.json
```

Replace deployment arguments as needed. Add `--observer-cpus CPU_LIST` when
sharing a lab host. Repeat `--world WORLD_ID` only for explicitly targeted
runs; omit it to enumerate the live catalog. Use independent output directories,
browsers and host samplers for simultaneous backends. Inspect the harness's
nonzero exit and report; completing playback alone is not acceptance.

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

## Current qualification

September 11, 2026, canonical `codex/0908-clean`: RDK on rev140,
prpl on rev150. This is one pass through each advertised room, including Play,
fullscreen room/topology inspection, roster/presence transitions, RF readback,
native owner agreement and final policy convergence—not a soak or a
hardware-speed comparison. Test bounds are initial **60 s**, checkpoint
**45 s**, final **90 s**, with a five-second stable hold. Steering margins,
native reporting intervals and lab resources are unchanged. The temporary
2000-action qualification cap is restored to the normal 100 afterward.

### RDK results

The rev140 retest, **22:24–22:55 UTC**, passes **14/14 complete room gates**:
every initial, checkpoint and final gate, Play, scene/roster checks, physical
presence and native/rendered owner agreement. Native/container/medium identities
remain unchanged; there are no SSE gaps or browser errors. This is the current
RDK qualification, superseding the earlier failed diagnostic runs.

The deployed worktree includes native patches through **0183**, Wi-Fi HAL
through **0038**, wmediumd through **0024**, and the corrected room action queue.
No native services restart during the catalog run. prpl is not changed or
retested in this RDK-only continuation.

| Room | Overall | Initial / final first policy convergence, seconds |
| --- | --- | --- |
| `home-a-stationary` | Pass | 2.04 / <0.02 |
| `home-a-one-client-handover` | Pass | 20.24 / 18.28 |
| `large-room-extender-evacuation` | Pass | 31.49 / 24.26 |
| `large-room-perimeter-counter-roam` | Pass | 32.37 / 21.26 |
| `home-a-asymmetric-link` | Pass | 11.16 / 8.10 |
| `home-a-band-walk-small` | Pass | 23.26 / 17.21 |
| `home-a-border-hover` | Pass | 35.39 / 31.38 |
| `home-a-disappear-reappear` | Pass | 26.32 / <0.02 |
| `home-a-extender-loss-recovery` | Pass | 11.17 / 4.06 |
| `home-a-fast-transit` | Pass | 20.21 / 23.30 |
| `home-a-flash-crowd` | Pass | 8.11 / 9.12 |
| `home-a-private-client-room-walk` | Pass | 41.54 / <0.02 |
| `home-a-slow-walk-ten` | Pass | 28.38 / 23.36 |
| `home-b-slow-walk-ten` | Pass | 40.58 / 30.45 |

These are first-convergence times; passing also requires the unchanged
five-second continuous hold before the deadline. The run verifies **153/153**
submitted actions, with **zero failed verifications**. Request-to-verification
p50/p95/max is **2.538/6.648/7.629 s**. Submission p50/p95 is **59/76 ms**;
candidate transaction p50/p95 is **520/1040 ms**; publication wait p50/p95
is **85/130 ms**. RF apply p50/p95 is **9.1/26.8 ms**.

The fixes cover four boundaries:

- **Presence and management delivery:** capability updates cannot resurrect
  departed clients; confirmed medium departures survive stale downlink traffic.
  HAL frame sockets cannot block or race teardown, and hostapd uses the normal
  disabled association-comeback test override.
- **Current RF and candidates:** fronthaul samples the confirmed serving
  uplink's simulated matrix RF rather than an idle peer's last-packet RSSI.
  Backhaul retains kernel RSSI. This is modeled RF, not a newly received packet.
  Candidate collection remains fair across roaming clients and requires each
  client's complete fresh same-band comparison before choosing a target.
- **Native command completion:** admitted queries dispatch without an extra
  timer wait; ready candidate/BTM reports can complete during capability
  reporting without corrupting radio state or another command's ACK ownership.
- **Unsent action bookkeeping:** a full five-verification queue no longer marks
  an unsent client pending. Previously this imposed a false 40-second timeout
  plus backoff. Only an action passing dispatch guards enters pending state.
  A nine-client regression reproduces the old failure and verifies immediate
  eligibility when a slot opens. Actual timeout/cooldown/backoff limits stay
  unchanged.

Regression validation passes **489 Python tests**, **133 subtests** and all
**25 JavaScript regression scripts**; four environment-dependent Python tests
are skipped. The compiled native/HAL fixtures and clean component builds pass.

The focused evacuation/perimeter/home-B run also passes **3/3**, with **66/66**
verified actions. The full run still records **six native candidate HTTP 504
timeouts** and **89 busy admission attempts**, including 81 successful
readmissions. Recovery occurs within all room gates; this is **not** a claim
of timeout-free collection, instant convergence or zero observer overhead.
Epoch cancellations are recorded separately from native failures.

Default restoration passes with twenty clients and six logical mesh roles,
first convergence **44.44 s** plus the hold. The room is paused at time zero,
unleased, fault-free and back at its normal 100-action cap. Diagnostic capture
is stopped and `hwsim0` is down. No new tar or box is created.

During this run, rev140 peaks at **11.44% sampled CPU**, has at least
**51.47 GiB available RAM**, and reaches **89°C sampled temperature**, with
**zero package throttle-counter increase** across 184 host samples.
No Yocto build or packet capture overlaps qualification. These remain
deployment measurements, not intrinsic hardware-stack performance.

Evidence on rev150: `/home/rev/work/rdk-rooms-fix-0911/all-rooms-10/`
contains `results/`, `audited-summary.json` and the time-filtered
`host-monitor.jsonl`. `focused-6/` holds the targeted pass;
`phantom-pending-negative.log` and `phantom-pending-positive.log` retain
the regression proof. Earlier failed/interrupted runs remain separate,
not relabeled as passes. Source fixes are mirrored to the canonical rev140
`codex/0908-clean` worktree.

### prpl results

All **14/14 rooms pass**. The run verifies **148/148** submitted steering
actions, with no failed verifications. Request-to-verification p50/p95 is
**0.948/1.196 s**; RF apply p50/p95 is **6.8/32.3 ms**. One real 30-second
candidate-collection gap occurs during extender-loss/recovery and recovers
within its room gate; epoch-superseded collections are cancellations, not
additional measurement failures.

| Room | Initial / final first policy convergence, seconds |
| --- | --- |
| `home-a-stationary` | 6.87 / <0.02 |
| `home-a-one-client-handover` | 4.05 / 2.02 |
| `large-room-extender-evacuation` | 12.13 / 9.10 |
| `large-room-perimeter-counter-roam` | 13.18 / 1.02 |
| `home-a-asymmetric-link` | 16.14 / <0.02 |
| `home-a-band-walk-small` | 24.23 / 7.07 |
| `home-a-border-hover` | 22.29 / 12.11 |
| `home-a-disappear-reappear` | 9.11 / <0.02 |
| `home-a-extender-loss-recovery` | 5.07 / <0.02 |
| `home-a-fast-transit` | 5.05 / 5.05 |
| `home-a-flash-crowd` | 6.07 / <0.02 |
| `home-a-private-client-room-walk` | 10.19 / <0.02 |
| `home-a-slow-walk-ten` | 7.09 / 13.17 |
| `home-b-slow-walk-ten` | 22.28 / 15.22 |

These clocks start at the settling gate, not at a client's first movement.
A near-zero final value means it was already converged when that gate began;
the stable hold is additional. Native identities remain unchanged.

Stationary and one-client handover retain one **2-RCPI** stronger-AP gap
(`02:00:00:10:04:00`, `candidate_gain_too_small`). They pass configured
policy, not absolute-strongest-AP convergence; the other final gates satisfy
both. No steering margin was reduced to turn these cases green.

An independent read-only topology observer records 22 identity changes across
360 decoded responses: decoded-response-to-SVG-bound identity p50/p95 is
**21.9/28.2 ms**. This excludes native model-commit time, waiting for the next
poll, paint timing and animation completion. It does not justify an instantaneous native
telemetry claim.

Raw reports, events, screenshots and failed diagnostic runs remain outside
Git in `/home/rev/work/rf-correctness-0911/` on rev150:
`prpl-rooms/results/`, `prpl-rooms/audited-summary.json`,
`prpl-render/report.json`. Native RF reporting and synthetic load latency
are separate checks in the [RF assessment](../radio/virtual-rf-assessment.md).

### Remaining qualification boundaries

- prpl: trace the recovered 30-second candidate gap during extender recovery;
  a passing room deadline does not make that gap disappear.
- Common: instrument native model commit, publication/polling and actual
  browser paint separately before claiming controller-to-screen latency.
  The current SVG identity observer measures only one component.
- RDK diagnostics: preserve journal suppression and packet-capture counters.
  A post-failure capture cannot prove what happened before it started, and
  rate-limited journals cannot prove an unlogged transmission never occurred.
- Keep failed native actions, short presence-window mismatches and incomplete
  candidate snapshots in the results. Do not increase timeouts, weaken
  freshness or force clients onto targets to manufacture convergence.
