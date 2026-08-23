# Next steps: steering-policy research program

## Goal

Use the container, hwsim and wmediumd lab to derive and compare steering
policies that improve client experience—not merely to demonstrate that a
Steering Request can move a station.

The lab should make large, repeatable experiments inexpensive: clone extender
and station containers, bind their radios deterministically, run the same RF
and traffic workload against several policies, and preserve enough evidence to
explain every decision. wmediumd is the independent stimulus and experiment
oracle. It must never tell the policy which AP to choose.

## Priorities

Work in the order below. A lower item may be prototyped early, but it must not
be used to claim policy quality until the preceding acceptance gates pass.

### P0 — Make experiment results trustworthy

1. Close remaining controller-state consistency defects.
   - **Closed for the reproduced carousel miss:** packet capture showed both
     Topology Notifications at the controller, 88 microseconds apart. The
     AL-SAP stream receiver discarded a coalesced second length-delimited SDU.
     Patch `0046` preserves message boundaries and passed 80 individual
     post-fix carousel arrivals without physical/controller/API disagreement.
   - Keep phased carousel restoration as useful load shaping and retain the
     strict paired burst as a regression for the fixed transport boundary.
2. **Bounded acceptance complete; recurrence trigger retained:** 143 post-fix
   commanded steers (33 earlier targeted operations, a 100-operation soak and
   a ten-operation journal acceptance) produced the BTM, physical roam and
   matching controller/API completion without the historical provider miss.
   This supports—but cannot retrospectively prove—the AL-SAP framing defect as
   the shared cause. Both matrix runners now assign a run/transaction ID and
   persist command output plus observed completion. Do not add blind retries;
   use that evidence to root-cause any recurrence.
3. **Closed:** complete controller liveness/aging behavior for a fully
   RF-isolated extender.
   - IEEE 1905 ages only from received evidence, publishes typed expiry and
     reappearance events, and emits the normal Topology Notification through
     Ethernet and the local AL-SAP path.
   - Unified Wi-Fi Mesh performs a bounded standard Topology Query probe,
     suppresses only active publication while retaining identity, and restores
     the same device on valid returning traffic.
   - A rev130 RF test moved the affected client in 5.464 s, removed the isolated
     extender from the API in 59.181 s, restored the exact 210-link medium,
     republished the extender in 15.198 s, and held 10/10 physical/API client
     agreement for 75 s with no restart or traffic failure.
4. Keep reboot reconstruction, zero service restarts, medium restoration,
   topology agreement and client traffic as mandatory pre/postflight gates.
   - **Three-run reconstruction gate closed on 2026-08-19:** consecutive runs
     passed in 805, 800 and 802 seconds with `5/15/50/14`, 10/10 live clients,
     a 120-second stable window, zero monitored restarts and 10/10 traffic.
   - The attempted three-target duration runs exposed soak-harness boundaries
     and were stopped. They are not acceptance results. The corrected 12-hour
     definition remains deliberately deferred; do not infer a duration result
     from the three cold runs. See [soak-acceptance.md](soak-acceptance.md).
5. **Closed:** sequence-correlated tracing identified command-2 `EINVAL` as
   unsupported startup clones and valid cloned frames rejected during normal
   scan/channel receive-state gaps. wmediumd now requires current frequency
   evidence and downgrades only its own tracked transient clone rejection.
   A two-round paired carousel converged and restored with zero command-2
   diagnostics while an unrelated command-3 error remained visible.
6. **Cold-reconstruction footprint closed; long-growth gate deferred:** the
   15-minute whole-container profile sampled one complete cold reconstruction.
   The 1 GiB `bpibroadband` cgroup peaked at 311.57 MiB and converged at
   266.10 MiB with no swap, pressure, limit or OOM events. Converged aggregate
   process PSS was 281.95 MiB; `em_ctrl`/`em_cli` were 22.92/81.03 MiB PSS.
   Bring-up allocator pulses were released. See
   [memory-footprint.md](memory-footprint.md). PSS growth from hour 1 to hour 12
   has not been accepted and will have no result until a future authorized run
   writes passing final summaries.

Exit gate status: **P0 functional acceptance is closed.** In addition to the
earlier three-run gate, the final metrics/uptime image passed a fresh rev130
cold reconstruction on 2026-08-20 in 866 seconds with `5/15/50/14`, 10/10
live clients, 10/10 non-zero RCPI and association uptime, a 120-second stable
window, zero monitored restarts and 10/10 traffic. All five BPI containers had
exactly one `snmp_subagent`, and the controller logged zero AP Metrics Response
validation failures. On 2026-08-23 the expanded rev130 profile additionally
passed a fresh `5/15/50/24` deployment, cold chain, cold branch and
controller-only restart with 20/20 clients. The 12-hour churn test remains a
deferred characterization task; it was not a blocker for starting P1 and must
not be claimed as completed until future final summaries pass.

### P1 — Freeze the optimizer integration contract

The optimizer remains a host-side Python component. Do not put policy logic in
the BPI images.

**Same-band vertical slice accepted 2026-08-21:** `gen/optimizer` contains the
controller observer, immutable Snapshot v1, pure threshold policy, replay
state, append-only journal, narrow actuator and verifier. Associated and
same-band candidate RCPI now carry controller receipt time. A ten-client live
cycle performs seven bounded Unassociated STA Link Metrics transactions and
returns 40 exact-BSSID candidates without reading scenario truth. The isolated
crossover produced one recommendation and one bounded act converged in 3.04
seconds. An ignored BTM becomes an explicit association-timeout outcome with
bounded exponential failure backoff, so `NoDisconnect` cannot cause blind
retry loops. The remaining measurement boundary is exact-BSSID cross-band
evidence plus client capability; live band-upgrade action stays inhibited.

```text
EasyMesh observations                  EasyMesh actions
topology + association ----+       +-> steer.sh initially
associated-STA metrics -----+       |   authenticated API later
AP/channel utilization -----v-------+
candidate measurements --> optimizer --> verifier --> experiment journal
                              ^              |
                              +-- state -----+

wmediumd scenario --> hwsim/WLAN --> reported measurements
       `---------------- evaluator-only truth ----------------'
```

Implement three narrow adapters:

- `observer`: immutable, timestamped topology, association, client capability,
  associated-link, candidate-link and AP-load facts;
- `actuator`: exactly one validated `steer(STA, target BSSID)` transaction; and
- `verifier`: client link, controller model, API parent, traffic and protocol
  result convergence.

The current `/topology`, `/clients`, `/bsses`, associated RCPI reporting,
`/unassoc_sta_query` and `steer.sh` provide the same-band vertical slice. The
main open interface question is trustworthy cross-band target quality and
client capability. Continue the capability matrix for Beacon/Probe evidence
without changing the boundary: where a standard measurement exists but is not
exposed, add only a read-only EasyMesh adapter. Never replace missing candidate
measurements with wmediumd SNR.

Exit gate: `observe` records fresh current and candidate facts; `act` performs
one bounded steer; neither policy code nor wmediumd truth crosses the adapters.

### P2 — Build a replayable policy harness

**Core harness complete:** `gen/optimizer/` exposes the following execution
modes. Continue adding policies and adapters without creating a second runner.

| Mode | Purpose |
| --- | --- |
| `observe` | Record raw controller inputs and normalized snapshots without a policy |
| `evaluate` | Validate and evaluate one team-supplied Snapshot v1 |
| `replay` | Feed a previous observation stream to policy code deterministically |
| `recommend` | Run live policy state but never issue a steer |
| `act` | Issue and verify actions after all safety gates pass |
| `simulate` | Exercise the same policy core with explicitly synthetic observations |

Each decision record needs the input snapshot, age of every measurement,
candidate filters, scores, prior state, selected action or explicit no-action
reason, policy/configuration hash and outcome. Make the policy core a pure
function over snapshot plus prior state so algorithms can be compared offline.

Exit gate status: hash-chain validation and deterministic replay are covered by
the package tests. New policy plug-ins must retain byte-equivalent
recommendations and state transitions without a live lab.

### P3 — Establish baselines before claiming novelty

Implement and freeze these reference policies:

1. strongest reported candidate with no hysteresis;
2. RCPI threshold plus margin, hold, dwell and cooldown;
3. load-aware weighted utility using RCPI and AP utilization; and
4. no-steering control.

Run each against the same seeds and frozen scenario plans. These policies
provide the lower bound and reveal whether a proposed mechanism improves QoE
or merely issues more steering commands.

Exit gate: the threshold policy detects a two-AP crossover in recommend mode,
issues exactly one steer in act mode, avoids a return ping-pong and beats the
no-steering control on predefined metrics.

### P4 — Scale the infrastructure cheaply and predictably

**20-client implementation reached immediate acceptance on rev130
2026-08-23:** the count-driven pool now provisions ten private and ten IoT
clients, resumes healthy partial cohorts, registers wmediumd once and exposes
cohort identity to inventory, optimizer tests and the WebUI. All 20 clients
passed association, controller export and zero-loss traffic. RF-churn/duration
acceptance is still required before P4 small is fully closed. The next profile
is 50 clients on a 64-radio pool; 100 clients needs a validated 105-radio hwsim
path. See [client-scale.md](client-scale.md).

Replace fixed container lists with a topology manifest:

```yaml
lab:
  controller_agents: 1
  extenders: 8
  clients: 40
  bands: [2.4GHz, 5GHz, 6GHz]
  seed: 1701
```

The generator should allocate deterministic container names, MAC addresses,
hwsim radios, channel contexts and wmediumd matrix entries, then onboard nodes
through the existing gates. Add `scale-up`, `scale-down`, `status` and
`destroy-generated` operations without changing the accepted small baseline.

Measure the real capacity curve because cost is not zero:

- VM CPU, memory and boot time;
- controller model and CLI memory;
- onboarding and reporting latency;
- wmediumd frame rate, matrix size and control-generation time;
- event loss under simultaneous associations; and
- maximum stable extenders/clients for each host profile.

The wmediumd radio-pair matrix grows quadratically, while container and
controller work grow differently. Publish supported profiles rather than an
unbounded `N` claim.

Exit gate: small, medium and stress profiles are one-command reproducible and
have explicit resource and stability envelopes.

### P5 — Create the policy scenario and score library

**Scenario sources and capability-gated matrix started 2026-08-20:** ten
golden RF worlds cover stationary, slow walk, AP placement, border hover,
flash crowd, disappearance, fast transit, asymmetric links and extender loss.
The tenth moves the original ten-client profile for band experiments. Five
independent traffic profiles and two policy baselines produce a 148-case
initial matrix. With the five-Agent/20-client mixed cohort accepted, 56 cases
are capability-runnable and 92 remain blocked. The runnable label means that
all declared mechanisms exist; it is not a claim that every combination has
completed live acceptance. Blocked cases record the missing
measurement, RF, traffic, response-control or scale capability. See
[optimizer-scenarios.md](optimizer-scenarios.md). Scoring and live execution
remain open. A deterministic offline closed-loop runner now converts verified
goldens through a declared synthetic sensor model, runs the real threshold or
band-upgrade policy, changes association state for accepted BTM actions, and
models reject/ignore outcomes. It accelerates policy development but cannot
promote any live controller capability.

The pre-association family now has a pure bounded state machine: only clients
with known higher-band support can have 2.4 GHz responses suppressed, and both
a time cap and probe-count cap force a cooldown-protected 2.4 GHz failsafe.
Live execution still requires a narrow OneWifi probe-response control adapter.

Each scenario must have a passive control and deterministic seeds:

| Scenario | What it isolates |
| --- | --- |
| two-AP crossover | threshold, margin and reaction time |
| slow walk past several APs | dwell, hysteresis and ping-pong resistance |
| fast transit | whether steering is worthwhile before the opportunity passes |
| asymmetric uplink/downlink | direction-aware measurements and scoring |
| congested strong AP vs clear weaker AP | load/quality trade-off |
| client flash crowd | coordinated load redistribution and event capacity |
| extender RF loss/recovery | failure response and re-entry control |
| stale/delayed metrics | uncertainty handling and safe no-action behavior |
| BTM reject/non-BTM client | capability filtering and failure backoff |
| mixed stationary/moving clients | fairness and per-client state isolation |

Primary outcomes are application availability, packet loss, latency, time
below an RCPI/QoE floor, goodput, fairness and recovery time. Steering count,
failures, ping-pongs, control traffic and convergence latency are costs. Report
distributions and confidence intervals across seeds, not only averages.

### P6 — Derive novel mechanisms

Explore novel work only after the baselines and observation path are stable:

- **uncertainty-aware utility:** penalize stale, sparse or contradictory
  measurements instead of treating every number as exact;
- **roam-cost-aware control:** learn the per-client disruption cost and steer
  only when predicted benefit exceeds it over a useful horizon;
- **trend/prediction policy:** use RCPI slope and movement persistence to act
  before service collapse without chasing brief fades;
- **cohort-aware coordination:** serialize or jointly plan client moves so a
  target AP is not overloaded by simultaneous individually-good decisions;
- **resilience-aware steering:** include extender/backhaul health and expected
  recovery, not just fronthaul signal;
- **adaptive hysteresis:** tune margin/dwell per mobility class and recent
  steering outcome; and
- **safe contextual learning:** learn ranking parameters in recommend/replay
  mode, with a deterministic safety envelope controlling live actions.

For each mechanism, write the hypothesis and failure conditions before the
algorithm. Compare it to every baseline on held-out scenarios and seeds. A
mechanism is useful only if its QoE gain survives its steering and complexity
costs.

## Delivery sequence

| Milestone | Demonstrable result |
| --- | --- |
| M0 — accepted appliance | import, reboot, `check`, WebUI and current tests pass |
| M1 — observation vertical slice | live, fresh current/candidate/link/load facts are recorded |
| M2 — baseline shadow mode | crossover produces one explained recommendation and no action |
| M3 — baseline closed loop | one end-to-end policy steer with cooldown and full verification |
| M4 — scalable profiles | repeatable 4/10, 8/40 and capacity-limit experiments |
| M5 — scenario benchmark | all baseline policies scored across the scenario library |
| M6 — novel policy study | at least one mechanism beats frozen baselines on held-out runs |
| M7 — product-facing interface | authenticated observation/action API and portable result bundle |

## Immediate two-sprint backlog

1. **Initial matrix complete:** keep it current as the read-only adapters are
   tested.
2. **Initial slice complete:** observer, normalized snapshot, raw recorder and
   deterministic replay exist; add correlated candidate result exposure next.
3. Run a passive crossover and prove current and candidate reported RCPI follow RF without reading
   wmediumd from the optimizer.
4. **Replay implementation complete:** threshold/margin/hold/dwell/cooldown
   tests produce one crossover recommendation; live recommend remains safely
   inhibited until item 3 supplies fresh candidate facts.
5. **Adapter skeleton complete:** `steer.sh` actuation and association/traffic
   verification are tested with fakes; enable live act only after item 3 and
   the remaining health gates pass.
6. Add the first topology manifest and measure 4/10 versus 8/20 resource use.
7. Automate a result bundle containing configuration, observations, packet
   capture indexes, service health, actions, outcomes and medium restoration.
8. **Scenario preparation complete for the first corpus:** keep the ten
   goldens, five traffic profiles, two policy baselines and generated capability
   matrix deterministic;
   implement only the adapters needed to move blocked cases to runnable.

The first policy decision should follow item 4, not precede items 1–3.
