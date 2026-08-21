# Optimizer scenario and experiment suite

## Objective

The suite creates a reproducible pseudo-world in which RF, traffic and policy
are independent axes. It is preparation for policy research and P4 scale
acceptance, not an ML algorithm and not evidence that an unavailable control
has been implemented.

```text
P Agent layouts x M mobility/RF worlds = reusable golden RF sequences

golden RF sequence x N traffic profiles x K policies x S seeds
                              |
                              v
                  deterministic case matrix
                              |
              +---------------+----------------+
              |                                |
        runnable today                 blocked with exact
        on accepted scale               missing capabilities
```

The RF values and traffic schedule are evaluator truth. The optimizer may
observe only measurements reported through EasyMesh. It must not read the
world file, wmediumd matrix or intended path as a candidate score.

## Checked-in pseudo-worlds

Sources are under `gen/wmediumd/configurator/worlds/`; generated timelines are
under `worlds/golden/`.

| World | Agents / clients | Purpose |
| --- | ---: | --- |
| stationary | 5 / 10 | passive small-profile control |
| slow walk, layout A | 5 / 20 | ten fixed and ten moving clients crossing several cells |
| slow walk, layout B | 5 / 20 | repeat the identical paths with different Agent placement |
| border hover | 5 / 12 | repeated cell/wall-threshold crossings and ping-pong pressure |
| flash crowd | 5 / 20 | ten clients appear together from 20–50 seconds |
| disappear/reappear | 5 / 12 | per-client liveness and stale-state cleanup |
| fast transit | 5 / 12 | candidate opportunity shorter than a costly roam |
| asymmetric link | 5 / 11 | station-originated SNR is deliberately weaker than AP-originated SNR |
| extender loss/recovery | 5 / 10 | one Agent becomes fully attenuated and later returns |

The two layouts and nine worlds are small enough to review and deterministic
enough to reuse. They contain complete directed station/Agent fronthaul and
Agent/Agent backhaul values for 2.4, 5 and 6 GHz at each tick. They do not
change meaning after a client roams.

Walls add a fixed 5 dB for each proper straight-line crossing. This deliberately
creates abrupt measurement changes without pretending to model diffraction,
reflection, material or antenna orientation accurately. Seeded shadowing is
available, but the first goldens use zero random shadowing so geometry and wall
effects remain directly explainable.

## Traffic axis

Traffic is defined separately in
`gen/optimizer/scenarios/traffic-profiles.json`:

| Profile | Driver | Status |
| --- | --- | --- |
| idle keepalive | none | available |
| latency probe | `ping` every 200 ms | available |
| constant load | `iperf3` | specified, not accepted |
| staggered bursty applications | `iperf3` | specified, not accepted |
| synchronized traffic flash crowd | `iperf3` | specified, not accepted |

`traffic-plan` expands a selected matrix case into container-bound command
arrays. It never embeds shell fragments and records its own hash. Execution and
capacity acceptance of the `iperf3` driver remain a separate task, so those
cases stay blocked instead of silently becoming ping tests.

## Build and inspect the matrix

```sh
cd gen/wmediumd/configurator
worlds/build-goldens.sh --check
python3 -m pytest -q

cd ../../optimizer
python3 -m optimizer.cli matrix \
  --spec scenarios/home-suite.json \
  --output scenarios/generated/home-suite.matrix.json
python3 -m pytest -q

jq '.summary, .coverage' scenarios/generated/home-suite.matrix.json
jq -r '.cases[] | select(.status == "blocked") |
  [.id, (.missing_capabilities | join(","))] | @tsv' \
  scenarios/generated/home-suite.matrix.json
```

The initial matrix contains 64 cases: 5 runnable and 59 blocked. The count is
not a quality score. It shows that the Cartesian core and specialized scenario
families exist while preserving the present lab boundary.

Create the runnable stationary latency plan for rev130:

```sh
case_id='cartesian-home--home-five-agent--stationary--latency-probe--threshold-policy--seed-1701'
python3 -m optimizer.cli traffic-plan \
  --matrix scenarios/generated/home-suite.matrix.json \
  --case "$case_id" \
  --bindings scenarios/rev130-small-bindings.json \
  --output /tmp/stationary-latency.traffic.json
jq '{status, duration_ms, events: (.events | length), plan_sha256}' \
  /tmp/stationary-latency.traffic.json
```

The role binding is explicit: gateway, four extenders and ten fixed clients map
to the current rev130 container names. A larger world fails plan compilation
until its additional roles have real containers and a profile is accepted.

## Capability boundaries by scenario family

| Family | Present foundation | Required before a valid live claim |
| --- | --- | --- |
| ordinary client steering | atomic RF, current RCPI, BTM action and association verifier | candidate-link measurements with trustworthy receipt time |
| band steering | per-band calculated world values and BSSID/band inventory | frequency-qualified wmediumd control plus fresh per-BSSID candidate measurements |
| pre-association steering | scenario and expected behavior | bounded probe-response control and failsafe semantics |
| BTM `NoDisconnect` | action and outcome model | clients that deterministically accept, reject or ignore BTM |
| load steering | traffic schedules | accepted `iperf3` driver and timestamped AP/BSS load metrics |
| backhaul topology | directed Agent/Agent values in every world | backhaul metric observer and safe topology/band action adapter |
| channel width | location and traffic axes | representative 20/40/80/160 MHz hwsim operation and action adapter |
| scale | generated 5/20 RF worlds | reproducible container manifests and accepted resource envelope |

### Band steering is a BSSID decision

The checked-in world calculates different 2.4, 5 and 6 GHz reach. Today,
wmediumd's live control key is `(source radio, destination radio)`, while every
BPI hwsim wiphy carries frames on all three frequency contexts. Therefore a
selected world band can be projected for a single-band experiment, but 2.4,
5 and 6 GHz cannot simultaneously have different controlled SNR for the same
pair. True band-steering tests require a key such as `(source, destination,
frequency or channel context)` and matching readback/restore semantics.

The optimizer then ranks target BSSIDs using reported candidate measurements.
It does not simply choose the label “5 GHz” or “6 GHz.” A 2.4-to-5 or 5-to-6
case remains blocked until both RF and measurement requirements exist.

### Backhaul topology is a slower, separate loop

Backhaul selection should be represented as a weighted graph whose vertices
are Agents and whose possible edges have band, measured signal/SNR, rates,
retry cost, utilization and stability. A slow optimizer can compare connected,
loop-free trees while penalizing churn and weak upstream bottlenecks. Five or
6 GHz preference and 2.4 GHz failsafe are policy hypotheses, not hard-coded
facts.

The current configurator computes those potential edge values but does not
apply them: `.wmd` export keeps `protect backhaul`. This prevents a client
steering scenario from accidentally partitioning the mesh before a safe
backhaul transaction and verifier exist.

### Channel width and field behavior

The current hwsim lab operates at an effective 20 MHz width. Location-specific
40/80/160 MHz policies may be designed and replayed, but throughput claims are
blocked until those widths are represented and measured. Likewise, BTM
`NoDisconnect` is a normal outcome rather than a protocol failure; experiments
must record it, apply backoff and avoid blind retries. It becomes deterministic
only after clients can be assigned accept/reject/ignore behavior.

## Acceptance progression

1. Keep the current 5-Agent/10-client small profile green.
2. Add a traffic executor and accept latency, constant-load and burst evidence.
3. Expose measurement receipt time and real target-BSSID measurements.
4. Run threshold policy in recommend mode against stationary, crossover,
   border and fast-transit cases.
5. Enable exactly one live bounded steering transaction and score its outcome.
6. Generate and accept the 5/20 profile, then medium and stress manifests.
7. Add frequency-qualified RF before calling any result a band-steering test.
8. Add backhaul and width action adapters as separate safety domains.

Every promotion updates `capabilities-current.json`; matrix regeneration then
moves only genuinely supported cases from `blocked` to `runnable`.
