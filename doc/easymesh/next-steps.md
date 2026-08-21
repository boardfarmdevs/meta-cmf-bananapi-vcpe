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
   - The 12-hour alternating carousel/outage soak remains deliberately
     deferred; do not treat the three cold runs as a substitute.
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
   remains intentionally unmeasured until the deferred soak is authorized.

Exit gate status: **P0 functional acceptance is closed.** In addition to the
earlier three-run gate, the final metrics/uptime image passed a fresh rev130
cold reconstruction on 2026-08-20 in 866 seconds with `5/15/50/14`, 10/10
live clients, 10/10 non-zero RCPI and association uptime, a 120-second stable
window, zero monitored restarts and 10/10 traffic. All five BPI containers had
exactly one `snmp_subagent`, and the controller logged zero AP Metrics Response
validation failures. The 12-hour churn test is a deliberately deferred
long-duration characterization task; it is not a blocker for starting P1 and
must not be claimed as completed.

### P1 — Freeze the optimizer integration contract

The optimizer remains a host-side Python component. Do not put policy logic in
the BPI images.

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

The current `/topology`, `/clients`, RCPI reporting and `steer.sh` provide much
of the vertical slice. The main open interface question is trustworthy target
quality. Build a capability matrix for Associated STA Link Metrics, AP Metrics,
Beacon Metrics and Unassociated STA Link Metrics. Where a standard measurement
exists but is not exposed, add only a read-only EasyMesh adapter. Never replace
missing candidate measurements with wmediumd SNR.

Exit gate: `observe` records fresh current and candidate facts; `act` performs
one bounded steer; neither policy code nor wmediumd truth crosses the adapters.

### P2 — Build a replayable policy harness

Create `gen/optimizer/` with four execution modes:

| Mode | Purpose |
| --- | --- |
| `capture` | Record raw observations and outcomes without a policy |
| `replay` | Feed a previous observation stream to policy code deterministically |
| `recommend` | Run live policy state but never issue a steer |
| `act` | Issue and verify actions after all safety gates pass |

Each decision record needs the input snapshot, age of every measurement,
candidate filters, scores, prior state, selected action or explicit no-action
reason, policy/configuration hash and outcome. Make the policy core a pure
function over snapshot plus prior state so algorithms can be compared offline.

Exit gate: replaying a run produces byte-equivalent recommendations and state
transitions without a live lab.

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

1. Write the EasyMesh measurement capability/exposure matrix.
2. Implement optimizer `observer`, normalized snapshot and recorder.
3. Run a passive crossover and prove reported RCPI follows RF without reading
   wmediumd from the optimizer.
4. Implement the threshold/hysteresis policy in replay and recommend modes.
5. Wrap `steer.sh` in the actuator/verifier transaction.
6. Add the first topology manifest and measure 4/10 versus 8/20 resource use.
7. Automate a result bundle containing configuration, observations, packet
   capture indexes, service health, actions, outcomes and medium restoration.

The first policy decision should follow item 4, not precede items 1–3.
