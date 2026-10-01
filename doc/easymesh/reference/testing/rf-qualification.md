# RF property qualification records

[Testing reference](README.md) · [RF property coverage](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/reference/rf-property-coverage.md)

The RDK lab's live qualification of the RF properties that easymesh-medium's
[RF property coverage](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/reference/rf-property-coverage.md)
maps to rooms: native counter pressure, native load actions, the room catalog
campaigns and native recovery at cold room initialization, with the prplMesh
comparisons made alongside. These are dated records, kept as written; the
property-to-room contract is the medium's, and prplMesh's own records are in
prplmesh-lab's [RF property coverage](https://github.com/boardfarmdevs/prplmesh-lab/blob/main/reference/radio/rf-property-coverage.md).

## Native counter pressure qualification

The initial asymmetric room produced partial echo delivery but zero AP
retries/TX failures/RX drops. This is not a Banana Pi HAL mapping stub:
`rdk-wifi-hal/platform/banana-pi/platform.c:1179` maps
`NL80211_STA_INFO_TX_FAILED`, `RX_DROP_MISC` and `TX_RETRIES` to
`cli_ErrorsSent`, `cli_RxErrors` and `cli_RetransCount` respectively.
OneWifi `source/apps/em/wifi_em.c:363` copies these into STA traffic stats;
`source/webconfig/wifi_easymesh_translator.c:1966` exports errors/retransmissions.
`optimizer/load_capture.py` decodes native TLV `0xA2`; `load_observer.py`
derives bounded deltas, not medium counters. Paths/lines identify the inspected
RDK 6.1 build sources; the wifi-emulator platform is not this active HAL.

The medium's `0022-wmediumd-independent-reverse-ack.patch` uses rate index zero
and a ten-byte reverse ACK. The room's approximately 5 dB near-AP reverse SNR
can still carry that robust ACK while long uplink data is lost. Frames never
injected into the AP need not increment kernel RX drops. Held reverse-loss
mode remains unsupported/unqualified; this experiment adds no native
counter-mapping patch.

The bounded [native counter acceptance](https://github.com/boardfarmdevs/meta-cmf-bananapi-vcpe/blob/main/gen/tests/native-retry-counter-acceptance.py)
adds stronger supported *pulsed* downlink/ACK impairment on the currently
associated Default client, independent of room geometry. It compares kernel
and native deltas, confirms ownership before/after each trial, restores exact
frequency overrides and restarts the unchanged room service:

```sh
PYTHONPATH=gen/optimizer:configurator python3 gen/tests/native-retry-counter-acceptance.py \
  --stack rdk --yes-change-lab --seconds 8 \
  --shadow-counter-policy gen/optimizer/configs/load-counter-guard-policy.yaml \
  --output /tmp/native-counter-shadow-new
```

Shadow checks replay consecutive actual native reports at receipt time through
the **same** counter evaluator used by load policy. They retain message IDs,
monotonic windows, raw deltas, transport, actual medium instance and association.
No utilization, RCPI, hop count or target is invented. `clear` means only
counter eligibility; `pressure` vetoes load balancing. This is not a complete
load-steer qualification or proof that a quieter AP repairs the impairment.

The helper records counter qualification, RF/association/service restoration
and final room health separately. Its bounded read-only health check must
recover the initial expected client count; starting a service alone is not
proof of healthy ownership. The tested association is checked before resuming
the room optimizer, which may legitimately steer afterward.

RDK demo-a follow-up observed kernel-matched ACK-loss deltas of 1,229 retries
and 63 TX failures; a native 157/s retry window exceeded the unchanged 100/s
limit. Data-loss also produced pressure; baseline/recovery checks were clear.
RX drops remained zero; its positive-pressure case is unit-only. TX failures
were nonzero but below the configured 10/s veto. Raw evidence is retained in
`test-results/rdk-rf-counter-followup/native-2.json`, not embedded here.

## Native load action qualification

The `rf-actions` suite section runs three separate bounded cases on healthy
paused Default-20: guarded load balancing, retry-pressure suppression with an
otherwise eligible quieter target, and weak-signal rescue despite pressure.
Use `gen/tests/load-policy-acceptance.py --help` for direct diagnostics.
The optional `--policy` selects the checked-in counter-guard policy;
`--counter-case clear|pressure|rescue` selects the case.

Only the target private 2.4 GHz radio changes channel. Real UDP demand and
read-back-verified pulsed downlink loss provide stimuli, never fabricated
native utilization/counters. Thresholds and hold times remain unchanged.
The driver requires fresh native evidence, captured source/target-specific
BTM transitions, native ownership and receiver data after verified steering.
Pressure must veto an otherwise safe target across advancing counter reports.
Missing evidence or insufficient load cannot pass.

The action deadline and the following twenty-second settling observation are
separate bounded windows. Cleanup restores channel, exact RF overrides,
client frequency lists/associations, owned traffic/routing and room service;
fresh Default-20 and unchanged native process identities are required.
Detailed JSON/JSONL remains in guest `test-results/rf-actions-*` when run by
the suite. Earlier failed runs remain separate evidence.

### Current action evidence and remaining gates

These bounded diagnostics preserve production policy thresholds and are not
clean-source release acceptance. Clear-case suite traffic uses
two real 12 Mbps senders with 1,400-byte payloads; actual native occupancy,
not requested traffic, determines eligibility.

| Case | RDK | prpl |
| --- | --- | --- |
| Clear counters, quieter different-channel target | Pass with actual source-AP broadcast demand: utilization 213 versus target 9, unchanged ten-second hold, clear counters, matching BTM, 3.419 s target verification, delivered traffic and fresh Default restoration. | Pass: utilization 213→16, RCPI 148→144, matching BTM, 0.681 s native verification, 74 positive post-verification receiver intervals and 20.68 s settling. |
| Retry-pressure veto | Earlier pass: utilization 241/11, 182 retries/s, three causal vetoes, no BTM and 21.99 s settling. Latest two-hop repeat fails stimulus qualification; see follow-up below. | Two 1400-byte repeats pass: first qualified source/target loads 215/13 and 210/14, retries 128/s and 132/s; 14/15 causal vetoes, no BTM and twenty-second settling. The 512-byte repeat fails stimulus qualification. |
| Weak-signal rescue during pressure | Latest repeat passes: RCPI 102→144, 7.849 s observed hold against the unchanged five-second minimum, matching BTM, 3.489 s target verification and 20.25 s settling. | Repeat passes: RCPI 102→144, unchanged 5.041 s signal hold, matching BTM, 2.033 s target verification and 20.56 s settling. |

All action runs restored RF, channels, associations and Default-20 without
native process changes. prpl's subsequent 90-second traffic/memory check,
after 20 seconds warm-up, measured zero controller or fronthaul RSS growth:
controller 43.07 MiB, fifteen fronthauls at most 14.36 MiB. This check had
20 active clients, not a new 100-client qualification.

Raw evidence is under `test-results/guarded-load-followup/` in each checkout.
`rdk-clear-2-read-only-audit.json` replays the saved decisions and hashes the
original evidence; it is not a fresh rerun. Next isolate background occupancy
from the impaired subject and preserve its ownership long enough to observe
the production hold. Never lower thresholds, fabricate load or credit an
uncommanded roam. `rf-actions` remains a qualification gate with known failures,
not an all-green regression claim.

## Room catalog qualification and open failures

Current bounded RDK fixes and preserved failures are listed in
[room acceptance](https://github.com/boardfarmdevs/meta-cmf-bananapi-vcpe/blob/main/doc/easymesh/reference/testing/room-acceptance.md#candidate-admission-and-isolated-beacons).
All three geometry rooms now pass together with enabled HAL 0044, including
isolated backhaul beacons, traffic, Default restoration and unchanged native
identities. Counter-manifest and guarded clear also pass; the latter uses
actual source-AP broadcast traffic and verifies native BTM in 3.419 seconds.
The original full suite remains **81 passed, six failed, one skipped**;
targeted fixes do not rewrite its results. Cold candidate completeness and
cross-run repeatability remain open. Both failed
ordinary RF rooms now pass a fresh load/Play/convergence rerun, including healthy
Default restoration and unchanged native identities. The failed soak ran zero
churn workloads; its subprocess diagnostics are now retained.

prpl's newer suite passes all geometry rooms. Its five ordinary-room loading
failures pass a targeted rerun after adding the trusted `/usr/local/bin` client
tool path. Its new pressure/rescue qualification passes with real source-AP
broadcast demand and partial-loss voice traffic; this is not RDK qualification.

### Bounded qualification follow-up

Evidence lives under `test-results/qualification-followup/` on each canonical
checkout; older failed reports are retained unchanged.

- Browser cue expiry passes ten offline repetitions per stack. Each expired
  cue is removed immediately; one animation-frame relayout replaces repeated
  synchronous layouts. The six-second lifetime and eight-second test bound
  are unchanged. Run headless browser tests with `DISPLAY` unset.
- RDK's explicit 100-client preflight passes initial/final full health,
  ownership, traffic, native RCPI and process checks without native restarts.
  The repeat after native 0208 deployment takes 154.755 seconds, with 100/100
  traffic success, zero added medium drops and a converged Default-20 afterward.
  Evidence: `qualification-followup-final-preflight/20260924T170721Z-p0-preflight/`.
  The new `--soak-preflight-only` suite option records `soak/p0-preflight`,
  zero churn workloads and `acceptance_eligible:false`; it cannot claim a soak.
- Native 0208 reports terminal partial/empty candidate responses separately
  from transport loss. Existing receipt timestamp/MID/RUID identify completion;
  no new data-model members or fabricated measurements are added. The CLI
  returns HTTP 503, `native_completed:true`, valid rows and missing keys rather
  than waiting for absent rows after native completion. Genuine transport loss
  retains the eight-second HTTP 504 bound. Extracted native/HTTP fixtures pass;
  native and CLI builds pass and are hot-installed with verified rollback
  copies. One live partial response reports its missing keys in 604 ms.
  The underlying intermittent HAL omission remains unproven. 0193 is preserved
  and retry candidate 0206 remains held.
- After controller replacement, the first room service attempts encounter
  inactive-client preflight while the model repopulates. The first HTTP-ready
  branch test reaches ten healthy clients but complete candidates for only
  nine (38 measurements); no clients exceed the policy margin. It correctly
  fails before Play and restores Default successfully. This is not a cold
  convergence pass. Both stacks' topology UIs serve the corrected expiry asset.
  The incomplete client is `sta_static_04` (`02:00:00:00:06:00`), still associated
  to Ext-1 with RCPI 134. The prompt partial reply demonstrates the contract fix;
  it does not establish the cause of that client's missing candidate coverage.

The newer `test-results/cold-metrics-followup/` repeats remain red. Branch
initial convergence eventually passes, but moving the leaf extenders leaves
all four backhaul stations disconnected during the observation window, despite
operating backhaul/fronthaul APs. The earlier warm three-room pass therefore
does not establish repeatability. Isolation and parent-handover repeats stop
before Play with only 9/10 and 8/10 clients candidate-complete; both restore
Default within the unchanged gate. All native process identities are unchanged.
The branch run misses its restoration gate but later returns to healthy,
converged Default-20; that later recovery does not rewrite the failed verdict.
Native logs and `rdk-candidate-failures.json` separate admission-busy/not-ready
503s, a terminal partial response and real 504s. Backhaul disconnection is a
separate failure from incomplete initial measurements, not a rendering delay.
The intended 13-dB branch links exceed the native candidate floor (RCPI 50),
so lowering native thresholds or changing the room again is not justified by
these observations. Rev140 also runs two unrelated VMs with elevated host load;
they remain untouched, and contention is context rather than a proven cause.

The pressure harness compares the real policy with a non-actuating shadow on
identical snapshots, changing only counter-guard enablement. A causal witness
requires fresh native pressure to veto the same otherwise eligible target that
the shadow would select after the unchanged ten-second load hold. Unexecuted
proposals never become pending; actual steering/BTM remains forbidden throughout
the twenty-second negative settling window. Continuous pressure for ten seconds
is not a production-policy requirement: intermittent pressure resets its hold.
The subject must remain on the source AP throughout; disappearance or an
uncommanded roam fails the negative check rather than counting as a veto.

prpl's repeat-qualified fixture uses two offered 12-Mbps, 1200-byte uplinks,
300 offered source-AP broadcasts/s and alternating 2-dB/healthy RF every 250 ms.
Its 512-byte pressure repeat fails stimulus qualification before actuation;
1400-byte CS6 downlink pressure passes twice with 14/15 causal veto witnesses,
no BTM, twenty-second settling and 5,179/5,127 delivered datagrams. The prpl
suite now uses 1400 bytes for pressure only. Rescue retains 512 bytes and a
usable 32-dB serving link, passing again with 2.033-second target verification.
Actual packet rates can be substantially lower than offered demand; only
native measurements qualify the policy. Evidence is in prpl's
`test-results/qualification-repeat/`, including the failed 512-byte attempt.
AQM/Console NG confirm TID7/voice; PHY retry-rate chains were not captured.
No native utilization, counters, thresholds or rate masks are injected. Both
checks restore Default-20, fresh metrics and unchanged native identities.
RDK rescue previously passed the same partial-loss/voice stimulus with 500 source-AP
broadcasts/s. Pressure-only qualification passes with 1400-byte voice payloads
and 1000 broadcasts/s; merely increasing broadcast demand with 512-byte
payloads did not establish the held opportunity. The successful trial records
three causal veto witnesses, stable medium RSS and no additional netlink drops
(76,482 before and after). The suite now supplies these stack-specific fixtures.
A preceding pressure attempt fails source association before any workload and
restores cleanly; such preparation failures are not native-policy failures.
The later `qualification-repeat/qualification-repeat-pressure-2/` does not
repeat that pass: source utilization peaks at 204/255, with only two pressure
decisions in 22 cycles and no fully held shadow opportunity. Its source has
two backhaul hops versus one in the passing trial; the target has one. This
is insufficient stimulus under a different native path, not a demonstrated
policy regression or a controlled latency comparison. No BTM is submitted;
RF, Default-20 and native identities restore successfully. Host contention
and path differences need separate control before making a causal claim.
The first rescue repeat verifies native reassociation in 2.717 seconds, then
fails immediately on post-steer `Error_Not_Ready`. The action driver now uses
the room's existing one-second bounded admission retry for explicitly refused,
unsubmitted requests. It records `native_admission_wait_seconds`; transaction
timings include any wait. HTTP 504, generic 503 and terminal partial results
are not safe admission retries. Policy, action and observation gates are unchanged.
The next `qualification-repeat-rescue-admission/` passes: 3.489-second native
verification, 20.25-second settling and the first complete fresh snapshot
sampled 16.856 seconds after verification. This two-hop-to-one-hop run has
49 successful queries and no busy response, so it does not itself demonstrate
live recovery through the new retry branch. Unit tests cover both explicit
refusal codes and rejection of other errors. Cleanup restores all native
identities, RF and fresh Default-20; no native binary is changed by this fix.
Stopping the room restores the full provisioned pool: saved setup snapshots
contain 100 native clients, not twenty. Only two generate explicit unicast
workloads. New reports expose `native_clients_at_workload_setup`; these are not
isolated two-station RF environments.

### Earlier campaign evidence

The earlier bounded campaign checks **24 ordinary rooms plus three
geometry/backhaul rooms** on each stack. Ordinary rooms exercise load, initial
policy convergence, Play, native associations/traffic and the two browser views.
Passing the configured steering policy does not mean every client must be on
the mathematically strongest AP: hysteresis, eligibility and dwell still apply.

| Gate | RDK | prpl |
| --- | --- | --- |
| Ordinary catalog | 24/24 passed in `catalog-rdk-2/report.json`, with healthy Default-20 restoration and unchanged native identities. Recovered native 503 queries remain recorded performance events. | 19/24 passed initially in `catalog-prpl/report.json`; all five failures then passed in `band-prpl-fixed/report.json`, including Default restoration and unchanged native identities. This is combined evidence, not one clean full-catalog pass. |
| `backhaul-branch-formation` | Failed initial 60-second convergence **before Play**: ten clients present, only 36/40 candidate observations and nine clients checked at the deadline. Default restoration passed. | Feature checks passed in the combined geometry run. |
| `backhaul-parent-handover` | Scenario and Default restoration passed. | Feature checks passed in the combined geometry run. |
| `backhaul-isolation-recovery` | Failed initial convergence **before the outage was played**: incomplete candidate coverage (34/40, seven clients checked). Default restoration passed. This does not establish an outage-recovery failure. | Failed after return: nine of ten room clients reported; later Default only 17/20. Ext-4's reported 6 GHz inventory was absent and final recovery failed. |

The prpl ordinary-room load failures affected `band-ap-counter-roam`,
`band-upgrade-24-5`, `band-upgrade-5-6`,
`received-discovery-recovery` and `received-same-band-roam`.
Privileged clients share the guest's user namespace; blindly re-entering it
with `nsenter --user` returns `EINVAL`. The shared band-settings fix compares
namespace identities, omits that flag only for a verified shared namespace,
and retains it for RDK's unprivileged clients. Missing identity fails closed;
PID/start-time checks and mount/net/PID/root/working-directory entry remain.

Both browser drivers now await completed fullscreen entry/exit. This prevents
selecting the hidden Play button or toggling fullscreen back on during cleanup.
The original prpl catalog also failed restoration through that harness race;
a separate restoration receipt and targeted rerun record recovery. Original
reports are not rewritten as passes.

The prpl geometry failure is distinct from the repaired band-settings issue.
All mesh nodes recovered connectivity and their fronthaul APs remained present.
The three missing Default clients still had kernel links on Ext-4's 6 GHz BSSs
and each passed three probes; reporting nevertheless omitted them. Native
inventory versus adapter reconciliation was unresolved in that run, not an
assumed RF/association loss. Manual restart of **Ext-4's native processes only** followed
the failed run; subsequent room startup failed its inactive-client preflight.
That manual action is not automatic recovery or test acceptance.
The newer synchronized prpl run passes all three geometry rooms and Default
restoration without changing native identities; it does not rewrite this failure.

Evidence in each checkout remains under `test-results/guarded-load-followup/`:
ordinary reports above; RDK `backhaul-rdk/`,
`backhaul-parent-handover-rdk/`, `backhaul-isolation-recovery-rdk/`;
prpl `backhaul-prpl/`, `catalog-prpl-restoration.json`,
`prpl-isolation-topology.json` and `prpl-manual-recovery.log`.
These diagnostics used recorded working-tree fixes and are **not fresh-import,
clean-source VM acceptance**. Preserve their identities and failed evidence.

### Next build and test gates

1. Runtime sources are synchronized to RDK `2d64df1` and prpl `76b8569`, with
   previous guest edits preserved in named stashes. New working-tree changes
   still need a committed checkpoint before clean-suite acceptance. RDK's
   hot-installed native components require newly built BPI images for future
   reproducible VMs; current diagnosis reuses the existing VM.
2. The synchronized prpl run passes all three geometry rooms, pressure and
   rescue. RDK's native recovery/reporting qualification remains separate;
   do not substitute those prpl passes for RDK evidence.
3. Qualify RDK cold candidate completeness with the terminal-response contract;
   keep policy/deadlines unchanged. Browser expiry and full-roster preflight
   now pass bounded checks, not a new catalog or soak campaign.
4. Retain prpl's two repeat-qualified 1400-byte pressure fixtures and passing
   512-byte rescue. Recheck RDK pressure/rescue repeatability without
   manufacturing utilization, relaxing thresholds or crediting an unsolicited
   roam as an optimizer action. Keep each stack's qualified workload explicit.
5. Only after those gates, qualify optional medium visibility `-F` and priority
   `-Q` modes separately. Both deployed binaries passed their isolated `-T`
   selftests, but those do not enable or live-qualify either mode.

The new checkpoint and optional remote-access tooling do not fix these remaining
native/fixture issues. Full-suite failures remain visible; no known-failure
exemptions, longer convergence windows or relaxed assertions are added here.

## Native recovery during cold room initialization

### Native backhaul recovery follow-up

The synchronized branch playback exposes a separate OneWifi recovery defect:
an unrooted former parent and a usable gateway can tie at scan RSSI. After
two timed-out connections, the global retry budget discarded the complete
scan. Rescanning reset all per-candidate counters, repeatedly selecting the
same unusable parent without trying the gateway. Root admission correctly
rejected the former parent; disabling that protection is not the fix.

OneWifi patch `0039-preserve-backhaul-recovery-candidate-budget.patch` retains
the scan during autonomous reconnect timeouts. Existing per-candidate limits
still bound attempts and exhaustion triggers a fresh scan. Explicit preferred
parent/fallback transactions retain their existing limits and timers. Extracted
native regressions fail four new cases before the patch and pass 30/30 after it.
The extender binary builds and is installed on the four test extenders, but
live recovery qualification is not yet complete. One follow-up fails initial
fresh-candidate convergence before Play; the next passes initial readiness
and plays, but only Ext-1/2/3 have rooted paths at the unchanged recovery gate.
Ext-4 remains parentless. Do not credit partial recovery or unit coverage as
successful live branch recovery.

Restarting native extender processes also loses applied reporting policy.
Controller policy readback remains populated, and posting identical policy
through `/api/v1/wifipolicy` skips native dispatch: HTTP success is not proof
of renewed agent delivery. During explicit baseline recovery, the AP reporting
interval was temporarily changed from 5 to 6 seconds and restored to 5;
steering thresholds were untouched. Native serving reports then return.
The patched controller binary was retained; a deliberate controller restart
during recovery changes its process identity, not its code. Held patch 0192
was not enabled. Automatic restart-policy recovery remains a separate gap.

Evidence is under `test-results/synchronized-rf/`: `branch-offhost/` records
the original root-loss failure; `onewifi-recovery-before.json` and
`onewifi-recovery-after.json` record native regressions;
`geometry-recovery-policy-restored/` records the post-patch initial candidate
failure with healthy ten-client links/APs, unchanged native identities during
the check and successful converged Default-20 restoration. Its host trace
averages 80.87% CPU busy (peak 88.47%) at at most 73 °C, with the browser on
another host. Shared-host contention is recorded, not asserted as the sole
cause or hidden by longer deadlines. Unrelated VMs remain untouched.
`branch-recovery-ready-baseline/` records the subsequent partial branch recovery
and missed Default convergence gate; native identities remain unchanged during
that run. Default later has twenty active clients and six nodes, but this does
not retroactively pass the candidate-completeness deadline.

The next bounded checks are retained in `test-results/rf-continuation/`.
`branch-checkpoint/` again stops before Play because fresh candidates are
incomplete. `branch-full/` passes initial readiness and recovers Ext-4 through
Ext-2, but Ext-3 remains parentless at the unchanged gate. Both restore a
converged Default-20 without native process changes during their checks.
Thus the remaining recovery defect is not specific to Ext-4. Native logs show
Ext-3 exhausting its two attempts at Ext-1 immediately before Ext-1 becomes
rooted, then spending full timeouts on other candidates. Faster propagation
of actual authentication/association failure is an investigation, not yet a
qualified fix. Admission, beacons and convergence deadlines remain unchanged.

### Candidate transport retry qualification

The bounded branch packet capture proves that some client candidate queries
receive neither ACK nor response during native backhaul disconnection. Do not
attribute those timeouts to rendering or infer a missing response from
rate-limited journal gaps alone. Backhaul-owned queries and all-rejected ACKs
must be distinguished from missing client-query replies.

Held retry patch 0206 additionally needed cancellation repair: after four
local send failures its MID remained zero, so cancellation skipped clearing
the exhausted retry counter and left the radio pending. The extracted native
regression reproduces that failure and now passes cancellation/reset after
both transmitted and unsent queries, while preserving unrelated radio states.
The four-send/two-second bound, original command deadline and freshness gates
are unchanged; this does not extend an HTTP request's eight-second deadline.

An incremental diagnostic controller build missed header-dependent objects
after the metrics class layout changed. Its handover report is an invalid
artifact qualification attempt, not evidence about retry correctness. The
known-good UAF-patched controller was restored and Default-20 reconverged.
Use a clean native rebuild for header/ABI changes: this Yocto configuration
disables automatic header dependency tracking. Keep 0206 out of normal image
builds until a consistently rebuilt controller passes bounded coexistence
qualification. No ASan campaign or VM rebuild is required for that check.

The subsequent clean build recompiles all 106 controller objects and its
AL-SAP dependency, retains UAF 0193, and passes Default-20 readiness before
`rf-continuation/retry-clean-handover/`. That check still fails initial room
readiness before Play: all mesh nodes have parent/root traffic and operating
APs, but the model shows nine clients and only four complete client candidate
sets. Default RF restores, but full recovery also misses its 60-second gate.
Native identities remain unchanged throughout the check. This does not prove
retry causality or return-handover safety; 0206 remains held, and the previously
qualified UAF-patched controller is restored afterward. Retry/cancellation,
admission, terminal completion/HTTP and documentation regressions all pass.
After rollback, Default-20 again has a healthy complete model and converged
fresh candidate coverage. That later recovery does not change the failed
test verdict. Diagnostic source changes are reverted to the enabled recipe;
clean rebuilding removes objects compiled against the held retry class layout.
