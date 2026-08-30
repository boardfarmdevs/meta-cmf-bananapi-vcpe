# Steering and policy experiments

## Current truth

Commanded EasyMesh steering works. An autonomous steering policy is not yet
proven.

The optimizer is a completely external host-side component. No BPI
EasyMesh, agent, OneWifi or WebUI process performs candidate selection or makes
the steering decision. See [optimizer](optimizer.md).

The commanded crossover baseline uses an independent RF gradient and an
explicit `steer.sh` call. A passive run with the same gradient is the control.
Only a decision produced from observed metrics can be attributed to an
optimizer.

Metrics policy activation covers all five mesh devices and 15 radios. The
accepted profile requires live RCPI for all 20 fronthaul clients and fresh
signal for all four extender backhauls. See [metrics](../reference/metrics.md).

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

The host checkout also provides a name-aware adapter. It resolves both operands
from the live topology and, unless overridden, selects the target fronthaul BSS
on the client's current SSID and band:

```sh
gen/steer.sh sta-03 extender-2
gen/steer.sh sta-03 agent-1       # colocated agent in bpibroadband
gen/steer.sh --band 6 sta-03 extender-2
```

The `STA-xx` suffix is hexadecimal and is the same stable identity shown under
the client icon in the WebUI. `Controller` is the control-plane node and has no
WLAN BSS; `agent-1`, not `controller`, is the valid colocated radio target. The
adapter prints its resolved STA MAC, target BSSID, SSID and band before it calls
the controller's MAC-level `/usr/bin/steer.sh`. Use `--dry-run` to resolve and
display the command without sending a steering request.

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

The matrix runner persists unique transaction IDs, command output, and observed
link/database/API completion. Diagnose a failed transaction from that journal;
blind duplicate BTM retries are not permitted.

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

The explicit steer is the transport/action baseline against which optimizer
decisions are compared.

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
