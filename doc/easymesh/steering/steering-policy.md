# Steering policy approach

## Purpose

This document defines how steering-policy experiments should work in the
EasyMesh LXD/hwsim/wmediumd lab. The objective is to change the simulated RF
environment in a controlled way, observe the metrics seen by EasyMesh, apply a
well-defined steering decision, and verify the resulting 802.11v roam.

The central distinction is:

> An EasyMesh Policy Configuration is not a complete optimization algorithm.

EasyMesh standardizes the policy parameters sent to agents, the metrics agents
report, and the messages used to request steering. It does not standardize the
controller algorithm that decides whether a client should move or which target
BSS is best. In this lab, that decision logic is a separate controller-side
optimization strategy.

EasyMesh also does not define a generic policy language made from composable
`IF condition THEN action` primitives. The standard defines protocol messages,
TLVs, field semantics, and required behavior at the Controller/Agent boundary.
How a controller represents and evaluates its own optimization strategy is
outside that boundary.

## The three configurations

The word *policy* is easily overloaded. The complete experiment has three
separate configurations:

| Configuration | Responsibility | Owner |
| --- | --- | --- |
| RF scenario | Changes link quality over time | wmediumd configurator |
| EasyMesh agent policy | Reporting rules, steering permission, thresholds, and exclusions | EasyMesh controller, deployed to agents |
| Optimization strategy | Decides whether, when, and where to steer | Controller-side experiment runner |

They must remain separate. In particular, changing a wmediumd link must not
directly issue a steer: the changed RF conditions must first be measured and
reported, then evaluated by the optimization strategy.

## Standard primitives and their boundary

For steering, EasyMesh gives an implementation three groups of standardized
protocol primitives:

| Function | EasyMesh primitive | What the standard defines |
| --- | --- | --- |
| Capability discovery | AP and client capability TLVs | Whether an Agent supports agent-initiated RCPI steering and whether a STA supports mechanisms such as BTM |
| Agent configuration | Multi-AP Policy Configuration Request carrying Steering Policy and Metric Reporting Policy TLVs | Agent permissions, exclusions, thresholds, and reporting behavior |
| Observation | AP Metrics, Associated/Unassociated STA Link Metrics, Beacon Metrics, channel-scan and topology messages | Measurement and network-state exchange |
| Steering action | Client Steering Request in Steering Mandate or Steering Opportunity mode | How the Controller asks an Agent to attempt steering |
| Result/convergence | 1905 Ack, Client Steering BTM Report, Steering Completed, topology and association updates | Protocol completion and resulting network state |

These are protocol primitives, not optimizer building blocks. The standard does
not define primitives for:

- Candidate scoring or ranking.
- Minimum target improvement.
- Consecutive-sample or dwell requirements.
- Ping-pong prevention and post-steer cooldown.
- A named conservative, balanced, or aggressive profile.
- The controller's policy storage format, API, or rule language.

An internal controller rule such as the following is consequently valid but is
not an EasyMesh object:

```text
IF current RCPI < 80 for three samples
AND target RCPI >= current RCPI + 20
AND cooldown has expired
THEN send a Client Steering Request naming that target
```

Only the observations entering this rule and the action leaving it cross the
EasyMesh-standardized boundary.

## Intended closed loop

```text
                  configure reporting, constraints, and autonomy
              +--------------------------------------------------+
              |       Multi-AP Policy Configuration Request       |
              v                                                   |
         EasyMesh agent                                           |
              |                                                   |
 wmediumd --> simulated RF --> OneWifi/hwsim measurements         |
                                  |                               |
                                  | Multi-AP metric reports       |
                                  v                               |
                         Controller data model                    |
                                  |                               |
                                  v                               |
                         Optimization strategy                    |
                       "Should this STA move?"                    |
                                  |                               |
                                  | Client Steering Request       |
                                  v                               |
                         Source agent / OneWifi                   |
                                  |                               |
                                  | 802.11v BTM Request           |
                                  v                               |
                              Client STA                          |
                                  |                               |
                                  +---- result and new metrics ---+
```

This is a feedback system. A successful test is not merely a successful BTM
request; the controller model and subsequent metrics must converge on the
client's new association.

## EasyMesh agent policy

The existing `em_cli` **Policy Settings** page exposes the real EasyMesh policy
path. Its `/api/v1/wifipolicy` endpoint invokes `get_policy` and `set_policy` in
the controller. The intended `set_policy` flow is:

```text
em_cli -> controller policy data model -> PolicyList database
                                      -> Multi-AP Policy Configuration Request
                                      -> agent -> OneWifi WifiEMConfig
```

The relevant agent-policy elements are:

- AP metrics reporting interval.
- Per-radio STA RCPI reporting threshold and hysteresis.
- AP channel-utilization reporting threshold.
- Inclusion of STA traffic, link, and status metrics.
- Local-steering and BTM-steering disallowed STA lists.
- Per-radio agent-initiated steering mode.
- Per-radio RCPI and channel-utilization steering thresholds.

The per-radio steering mode values are:

| Value | Meaning |
| ---: | --- |
| `0` | Agent-initiated steering is disallowed; Controller-requested steering remains available |
| `1` | RCPI-based agent steering is mandated when the Agent advertised the required capability |
| `2` | RCPI-based agent steering is allowed, but the Agent is not required to perform it |

The word *mandated* in value `1` refers to enabling the Agent's local RCPI
behavior. It must not be confused with a Controller-originated Client Steering
Request in **Steering Mandate** mode.

For an Agent following the standardized RCPI-based steering rules, EasyMesh
requires an attempted steer when all three of these conditions hold:

1. The measured uplink RCPI for the STA falls below the configured per-radio
   RCPI Steering Threshold.
2. The STA is not in the Local Steering Disallowed STA List.
3. The Agent has identified a suitable target BSS.

The first two conditions are concrete standard behavior. The third marks the
implementation boundary: the Agent uses implementation-specific mechanisms to
decide which BSS is suitable. It may consider link metrics, information from
other Agents or the Controller, the RCPI and channel-utilization thresholds,
and BSS association allowance. EasyMesh does not prescribe a target scoring
formula, minimum improvement, dwell time, hysteresis, or cooldown.

The Channel Utilization Threshold is therefore an input available to the
Agent's implementation-specific suitability decision. It is not standardized
as a mandatory Boolean trigger such as `RCPI below X AND utilization above Y`.

The two exclusion lists also have narrow meanings:

- **Local Steering Disallowed STA List:** prevents autonomous Agent steering of
  a listed STA. A Controller Steering Mandate may still request that STA be
  steered.
- **BTM Steering Disallowed STA List:** prevents use of 802.11v BTM for a listed
  STA. It selects the permissible execution mechanism; it is not a blanket
  prohibition on every form of steering.

RCPI uses the 0--220 representation. Its approximate relationship to received
power is:

```text
dBm = (RCPI / 2) - 110
```

For example, RCPI `80` is approximately `-70 dBm`, and a difference of 20 RCPI
units is approximately 10 dB.

The Metric Reporting Policy is a reporting primitive, not an instruction to
steer. Crossing its STA RCPI or AP utilization reporting threshold causes the
applicable metrics to be reported; it does not by itself require a steering
decision. A reporting threshold and a Steering Policy threshold may have the
same numeric value while serving different purposes.

The ID in a radio-specific policy row is a radio RUID. It is not a station MAC,
despite the current UI validation text. The experiment should use discovered
RUIDs explicitly and should not use the UI's `ff:ff:ff:ff:ff:ff` shortcut until
its on-wire semantics are validated.

### Applying agent policy

In the web UI, a section's **Save** button changes the page's working copy. The
global **Apply Policy Settings** button performs the POST. For automation, use:

1. `GET /api/v1/wifipolicy`.
2. Modify only the intended device and RUID entries.
3. `POST` the complete returned policy array.
4. Read it back and verify the downstream state described below.

A radio-steering entry has this shape:

```json
{
  "id": "02:00:00:32:7f:c0",
  "steeringPolicy": 0,
  "utilizationThreshold": 60,
  "rcpiThreshold": 80
}
```

An HTTP success response alone is not proof of deployment. The current web
backend launches `set_policy` without checking its returned status.

## Controller optimization strategy

The optimization strategy consumes measured state and emits a steering action.
It should be deterministic, named, versioned, and small enough that an operator
can understand why every decision was made.

The strategy is internal to the Controller and does not have to be encoded as a
Multi-AP Policy Configuration TLV. It may be represented by a small experiment
configuration, code, or a later management API. Regardless of its internal
form, it should consume EasyMesh-observed state and issue an EasyMesh steering
action.

EasyMesh provides two Controller action modes:

- **Steering Mandate:** the Controller directs the Agent to attempt steering
  the specified STA, normally toward the specified target BSS.
- **Steering Opportunity:** the Controller provides a time window in which the
  Agent may decide whether to steer. The Agent's decision and target handling
  remain implementation-specific.

The baseline lab strategy uses Steering Mandate because it makes target
selection and pass/fail attribution deterministic.

A strategy definition needs at least:

- The metrics it consumes.
- A trigger condition.
- Candidate eligibility rules.
- A required improvement over the current BSS.
- A persistence/dwell requirement.
- Hysteresis and post-steer cooldown.
- Client and BSS exclusions.
- The steering request mode and timers.
- Success and failure criteria.

The first strategy should be deliberately simple.

### Baseline strategy: `low-rcpi-gradient-v1`

```text
Input:
    associated STA RCPI and current BSSID
    candidate BSS visibility/RCPI
    controller association state

Trigger:
    current BSS RCPI < 80 (-70 dBm)
    for 3 consecutive valid reports

Candidate:
    same intended fronthaul/SSID
    STA can see the target BSS
    candidate RCPI >= current RCPI + 20 (about 10 dB)

Stability:
    candidate remains eligible for 10 seconds

Protection:
    STA is not on the BTM-steering-disallowed list
    controller model agrees with the STA's current BSSID
    no steer for this STA during a 60-second cooldown

Action:
    invoke the existing EasyMesh Client Steering Request path
    in Steering Mandate mode, using steer_sta/steer.sh and the
    selected target BSSID

Success:
    BTM report status 0
    STA associates to the target BSSID
    controller STAList converges to that association

Failure:
    request/ACK timeout, non-zero BTM status, no reassociation,
    or controller model fails to converge within the experiment timeout
```

The exact numbers are starting values, not universal Wi-Fi recommendations.
They must be experiment inputs so that runs are repeatable and comparable.

## Initial operating mode: controller-led steering

The first experiments should isolate one decision maker:

```text
Agent-initiated steering policy = 0 (disallowed)
Controller optimization strategy = enabled
```

This prevents an agent from steering independently while the controller policy
is being measured. Agent policy is still used to enable the required metric
reporting and to carry exclusion lists.

Mode `0` does not disable the Controller's Client Steering Request primitive.
It disables only the additional Agent-initiated RCPI steering behavior, making
it the cleanest mode for testing a Controller optimization strategy.

The existing commanded-steering path is already proven end to end:

```text
controller steer_sta
    -> 1905 Client Steering Request
    -> source agent
    -> OneWifi RawFrame Tx
    -> 802.11v BTM Request
    -> STA reassociation
    -> BTM report and topology/association convergence
```

The experiment runner should reuse this path. It must not introduce a second
steering protocol.

## RF scenario definition

The wmediumd configurator should describe RF conditions independently of the
optimization strategy. A useful first scenario is a controlled crossover:

```text
Phase 1 - baseline:
    AP-1 strong, AP-2 weak; hold until metrics are stable

Phase 2 - ramp:
    gradually weaken STA<->AP-1 and strengthen STA<->AP-2

Phase 3 - crossover:
    AP-1 crosses the policy trigger; AP-2 exceeds the candidate margin

Phase 4 - hold:
    keep the gradient stable long enough for dwell, steer, and convergence

Phase 5 - optional reverse:
    reverse the gradient only after cooldown, to test hysteresis/ping-pong
```

Each applied RF change must be timestamped. wmediumd SNR/link configuration is
an input to the radio model; the decision must use the RCPI/RSSI actually
observed through OneWifi/EasyMesh, not assume that the configured SNR is the
reported RCPI.

## Deployment sequence

### 1. Establish a stable baseline

- Bring up the controller, agents, client, hwsim, and wmediumd.
- Verify all expected BSSs and associations.
- Verify the wmediumd log has no unknown-sender errors.
- Verify the controller association model matches `iw dev wlan0 link`.

### 2. Deploy the EasyMesh agent policy

- Select each target device in `em_cli`.
- Use actual discovered RUIDs for radio-specific rows.
- Set agent-initiated steering to `0` for controller-led tests.
- Enable the metric interval and per-radio link metrics needed by the strategy.
- Configure the exclusion lists.
- Apply the complete policy.

### 3. Prove policy propagation

Verify all of the following before changing RF conditions:

```text
em_cli GET       returns the requested values and RUIDs
PolicyList       contains the intended persisted rows
controller log   Policy Configuration Request sent
agent log        Policy Configuration Request received
1905 exchange    matching ACK returned to the controller
OneWifi log      WifiEMConfig received and monitoring configured
metric reports   arrive at the expected interval
```

### 4. Start the optimizer in observation mode

Before allowing actions, run the strategy in dry-run mode. It should log the
input metrics, trigger state, candidate ranking, exclusion checks, and the
decision it would make. This proves that the reporting and threshold semantics
are understood without moving the client.

### 5. Run the RF scenario with actions enabled

- Start one named wmediumd scenario.
- Enable the same named/versioned optimization strategy.
- Allow at most one outstanding steer for a STA.
- Record every decision and protocol outcome.
- Stop or reset cleanly at the end of the scenario.

## Decision state machine

```text
 STABLE
   |
   | current RCPI below trigger
   v
 DEGRADED
   |
   | consecutive-report and dwell requirements satisfied
   | viable target exceeds improvement margin
   v
 ELIGIBLE
   |
   | issue Client Steering Request
   v
 STEER_PENDING -----------------------+
   |                                  |
   | BTM accept + association change  | reject / timeout
   v                                  v
 VERIFYING                          FAILED
   |                                  |
   | model and metrics converge        | log reason; do not loop rapidly
   v                                  |
 COOLDOWN <---------------------------+
   |
   | cooldown expires
   v
 STABLE
```

Every transition must have a timestamp and a reason. This is essential for
distinguishing policy behavior from RF, protocol, or model-convergence defects.

## Required run record

One experiment timeline should contain:

```text
scenario name and version
strategy name and version
agent policy values and RUIDs
wmediumd link changes
reported RCPI/utilization samples
current association and candidate set
policy state transitions
decision and reason
Client Steering Request message ID
1905 ACK
BTM response/status
actual client BSSID
controller STAList BSSID
cooldown start/end
final verdict
```

This record is the primary experiment artifact. Screenshots and selected logs
are supporting evidence, not the source of truth.

## Agent-led steering: follow-on mode

A later experiment can isolate agent-initiated behavior:

```text
Agent steering policy = 1 (mandated) or 2 (allowed)
Controller optimization strategy = observation only
```

In that mode, the agent is expected to act on the deployed RCPI/utilization
policy and report the result. Under policy value `1`, the normative RCPI trigger
is current uplink RCPI below threshold, the STA not locally disallowed, and a
suitable target identified by the Agent. Target suitability remains
implementation-specific. The current implementation is not ready for this test:
the agent forwards the policy to OneWifi, but the inspected OneWifi source only
consumes the metric-reporting portion. The per-radio steering parameters are
decoded but are not used by an active steering evaluator.

The same is true of OneWifi's separate band-steering configuration schemas: the
current source maintains configuration maps, but no reusable runtime decision
engine was found behind them.

Agent-led testing should therefore remain disabled until policy consumption and
the resulting locally initiated steering path are implemented and verified.

## Current gaps to close

Before the lab can claim policy-driven steering, it needs:

1. A stable wmediumd scenario configurator with named ramp/step/hold scenarios.
2. Reliable policy deployment status from the web API; HTTP success must reflect
   the controller command result.
3. Correct UI terminology and RUID selection for radio-specific policies.
4. Evidence for every policy hop: database, CMDU, ACK, OneWifi application, and
   resulting metrics.
5. A small controller-side evaluator for the baseline strategy, initially with
   dry-run and single-action modes.
6. A unified timestamped run record.

The running lab inspected on 2026-08-13 had an empty `PolicyList`, no
radio-specific arrays returned by `/api/v1/wifipolicy`, and zero per-radio
steering/RCPI/utilization policy values. The rev140 build work tree contains
newer default-policy creation logic, but defaults must not be assumed active;
deployment must be proven using the checks above.

## Non-goals for the first implementation

- Do not create a second general-purpose policy API.
- Do not create a large policy language or policy database.
- Do not describe controller rules as EasyMesh policy TLVs; only their
  observation and action boundaries are standardized by EasyMesh.
- Do not couple wmediumd directly to `steer_sta`.
- Do not run controller-led and agent-led steering simultaneously.
- Do not treat the `em_cli` Wireless Settings presets named conservative,
  balanced, or aggressive as EasyMesh policies; they are currently web-process
  state and are not connected to the EasyMesh policy path.
- Do not infer success from an HTTP response or 1905 ACK alone.

## Standard references

The standards boundary described here follows the Wi-Fi EasyMesh Specification:

- Section 7.3: policy configuration.
- Sections 11.1 and 11.2: Controller Steering Mandate and Steering Opportunity.
- Sections 11.3 and 11.3.1: Agent-initiated RCPI-based steering.
- Section 11.4: implementation-specific target-BSS determination.
- Section 11.5: steering mechanisms.
- Section 17.1.8: Multi-AP Policy Configuration Request message.
- Section 17.2.11: Steering Policy TLV.
- Section 17.2.12: Metric Reporting Policy TLV.

Reference: [Wi-Fi EasyMesh Specification 6.0 (archived PDF)](https://web.archive.org/web/20260102042057id_/https://ducndc.github.io/assets/documents/networking/Wi-Fi_EasyMesh_Specification_v6.0.pdf).
The archived file was verified on 2026-08-13 as a 215-page PDF authored by
Wi-Fi Alliance (5,236,746 bytes, SHA-256
`de9b58c4b57b65c4039f53aa697d75995a2f959b42207d3f89f5a25b81d40231`).

## Acceptance criteria for the first policy experiment

The initial controller-led experiment is complete when a Wi-Fi expert can:

1. Select a named RF crossover scenario and a named steering strategy.
2. Deploy and independently verify the EasyMesh reporting/constraint policy.
3. Run once in dry-run mode and see why a steer would or would not occur.
4. Run with actions enabled and observe exactly one correctly targeted steer.
5. Correlate RF change, reported metrics, policy decision, protocol messages,
   client roam, and controller-model convergence in one timeline.
6. Repeat the same scenario with materially equivalent results.

That provides a stable base for comparing thresholds, hysteresis, dwell times,
candidate margins, and later, more sophisticated optimization strategies.
