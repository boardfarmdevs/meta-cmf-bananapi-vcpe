# Steering and policy experiments

## Current truth

Commanded EasyMesh steering works. An autonomous steering policy is not yet
proven.

The planned optimizer is a completely external host-side component. No BPI
EasyMesh, agent, OneWifi or WebUI process performs candidate selection or makes
the steering decision. See [optimizer.md](optimizer.md).

The accepted crossover test used an independent RF gradient and an explicit
`steer.sh` call at 42 seconds. The passive run with the same gradient did not
roam. Therefore the result proves commanded steering under RF stimulus, not an
optimizer detecting the crossover.

Metrics policy activation is now complete. Live controller inspection shows 70
persisted policy rows, five per-device AP reporting policies, and metrics and
steering entries for all 15 radios. All ten fronthaul clients have live RCPI
and traffic counters. See [metrics-reporting.md](metrics-reporting.md).

This does not change the optimizer boundary: no verified OneWifi evaluator
consumes those thresholds and selects a target, and the passive crossover still
does not roam. The values configure observation and permitted agent behavior;
they are not the external optimizer's candidate-selection algorithm.

## Commanded steering path

```text
steer.sh STA TARGET_BSSID
  -> steer_drv / em_cli command
  -> controller Client Steering Request (Steering Mandate)
  -> IEEE 1905 source agent
  -> RBus raw-frame action
  -> OneWifi source VAP
  -> 802.11v BTM Request
  -> client reassociation
  -> BTM report + association/topology update
  -> controller DB and WebUI converge
```

The controller image ships:

- `steer_drv "steer_sta OneWifiMesh" payload.json`, the low-level command; and
- `steer.sh STA_MAC TARGET_BSSID [op_class] [channel]`, which resolves current
  placement, validates the target and builds the command payload.

Example, using live MACs from the current deployment:

```sh
lxc exec bpibroadband -- /usr/bin/steer.sh \
  02:00:00:00:03:00 02:00:00:51:38:4f
```

Never copy BSSIDs between clean deployments. Read them from the current
inventory or controller model.

## Steering acceptance

A steer passes only when all planes agree:

1. controller command succeeds;
2. source agent receives the request and returns the matching 1905 ACK;
3. OneWifi transmits BTM from the source VAP;
4. client reports association with the target BSSID;
5. controller `STAList` changes to the same BSSID;
6. WebUI/API placement changes to the same agent; and
7. traffic continues and service restart counters remain unchanged.

The final scaled sample passed 10/10 operations. An earlier three-round matrix
passed 30/30. Link convergence averaged about 1.1 seconds in the final sample;
DB/API convergence averaged about 2.5 seconds.

One later immediate-return request exposed a rare residual: the controller
request and 1905 ACK succeeded and the raw-frame setter returned success, but
the OneWifi provider callback did not occur, so no BTM was transmitted. The
identical command succeeded on retry without a restart. This requires a
transaction-aware observed-completion/root fix, not blind duplicate BTM frames.

## What EasyMesh standardizes

EasyMesh supplies interoperable primitives, not a complete vendor optimization
algorithm:

| Primitive | Boundary |
| --- | --- |
| capability TLVs | whether agents/clients support measurements and steering mechanisms |
| Policy Configuration Request | reporting intervals, RCPI/utilization thresholds, exclusion lists and agent steering mode |
| metric/query/report CMDUs | observations available to a controller decision engine |
| Client Steering Request | controller asks an agent to attempt a steer in Mandate or Opportunity mode |
| BTM and steering reports | protocol outcome and client response |

Candidate ranking, hysteresis, dwell, load weighting, failure backoff,
ping-pong prevention and cooldown are controller implementation choices. They
must not be described as EasyMesh policy TLVs.

Agent steering mode values are conceptually:

| Value | Meaning |
| --- | --- |
| 0 | autonomous agent steering disallowed; controller requests remain allowed |
| 1 | RCPI-based agent steering mandated when capability permits |
| 2 | RCPI-based agent steering allowed but not required |

The first lab optimizer should use mode 0 so there is one decision maker.

## Three independent experiment inputs

```text
RF scenario
  wmediumd link functions over time

EasyMesh agent policy
  reporting interval, thresholds, exclusions, agent mode

controller optimization strategy
  measurement interpretation, candidate choice, state machine, action
```

Changing RF must not directly call `steer.sh`. The optimizer consumes actual
reported metrics; it must not assume configured SNR equals reported RCPI.

## First controller-led policy

Use one deliberately small state machine:

```text
STABLE
  | current AP below trigger
  v
DEGRADED
  | N consecutive reports + dwell
  | target exceeds candidate margin
  v
ELIGIBLE
  | one Steering Mandate
  v
STEER_PENDING ---- reject/timeout ----> FAILED
  | association changes
  v
VERIFYING
  | station, DB and API agree
  v
COOLDOWN
  | cooldown expires
  v
STABLE
```

Initial values should be named experiment inputs, not hidden constants:

```text
current-link trigger
candidate improvement margin
consecutive-report count
minimum dwell
steer timeout
post-steer cooldown
maximum one outstanding steer per STA
```

Run the strategy in observation-only mode first. Log the metrics, candidate
set, exclusions, state transition and decision it would make without sending a
request. Enable actions only after the dry-run transitions match expectation.

## Policy deployment proof

Do not infer deployment from a WebUI HTTP response. Prove every hop:

```text
WebUI/API GET returns intended values and current RUIDs
-> PolicyList contains intended persistent rows
-> controller sends Policy Configuration Request
-> agent receives it and returns matching ACK
-> OneWifi receives the policy/configuration
-> expected metric reports arrive
-> decision engine consumes those reports
```

Inspect current state with:

```sh
lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh \
  -e 'select count(*) from PolicyList'
curl -fsS http://127.0.0.1:8888/api/v1/wifipolicy | jq .
```

WebUI presets called conservative, balanced or aggressive must not be treated
as deployed EasyMesh policies until this complete propagation path is shown.

## Crossover experiment

Use two runs from the same compiled plan:

```text
passive control
  0-10 s baseline, 10-40 s crossover, 40-60 s hold
  no action; verify measurements and no unintended roam

active policy run
  same RF plan and bindings
  optimizer observes, becomes eligible and issues exactly one steer
  verify BTM, association, DB/API convergence and cooldown
```

The earlier commanded test invoked `steer.sh` at 42 seconds during the hold. It
is a transport/action baseline against which the real optimizer should be
compared.

## Required run record

```text
host, source revision, image and wmediumd hashes
scenario source hash and frozen role bindings
agent policy values and RUIDs
reported RCPI/utilization samples
current association and candidates
state transitions with timestamp/reason
steering request mode and message ID
1905 ACK and BTM response/status
station, DB and API BSSID observations
traffic loss and convergence latency
cooldown start/end
medium restoration result
final verdict
```

Screenshots support this record but are not the source of truth.

## Do not combine yet

- Do not run controller-led and agent-led decision makers together.
- Do not couple wmediumd directly to steering action.
- Do not call threshold crossing a policy without observed metric consumption.
- Do not accept command response or 1905 ACK without the actual roam.
- Do not implement agent-led mode until OneWifi policy consumption and its
  locally initiated steering path are verified.
