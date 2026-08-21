# EasyMesh external optimizer

This package is the first P1 implementation of the architecture in
[`doc/easymesh/optimizer.md`](../../doc/easymesh/optimizer.md). It runs on the
lab host, not in a BPI image.

Implemented now:

- raw endpoint records plus normalized immutable snapshots from `/topology`,
  `/clients`, `/devices` and `/bsses`;
- explicit unknown freshness and missing candidate-measurement handling;
- a pure threshold/margin/hold/dwell/cooldown decision engine;
- explicit association-timeout outcome and bounded exponential failure backoff;
- an opt-in band-upgrade baseline that still selects an exact BSSID and applies
  target RCPI, maximum-loss, hold, dwell and cooldown gates;
- a deterministic closed-loop golden-world test double with accept, reject and
  ignore client behavior;
- deterministic replay state;
- a hash-chained JSON-lines experiment journal;
- a narrow `gen/steer.sh` actuator and bounded association verifier; and
- unit, adapter, replay and existing two-AP configurator-scenario tests.

The scenario preparation layer also expands ten checked-in golden RF worlds,
five independent traffic profiles, policy configurations and seeds into a
hash-verified case matrix. Missing lab abilities remain explicit per-case
blockers. The live observer never reads simulated RF truth.

The live controller API currently serializes `client_metrics.last_updated` at
read time; it is not the exact report timestamp. It also does not expose target
link quality. Consequently live `recommend` and `act` safely emit no action
until P1 adds trustworthy read-only freshness and candidate-measurement
adapters. Recorded fixtures may contain those facts when their source is a real
EasyMesh measurement such as a Beacon Metrics Response. wmediumd SNR is never
accepted as an optimizer observation.

For offline algorithm tests only, `simulate` intentionally translates a
verified golden world through a declared receiver-noise/RCPI sensor model into
synthetic EasyMesh-shaped snapshots. Its records use `simulated://` and
`simulated_*` sources and state `live_observer_compatible: false`. This is a
policy test double, not evidence that the controller reported a measurement.

## Install and test

```sh
cd gen/optimizer
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
pytest
```

Capture live read-only snapshots:

```sh
em-optimizer observe \
  --base-url http://127.0.0.1:8888 \
  --count 30 --interval 1 \
  --journal /tmp/em-observe.jsonl
```

Run deterministic replay after a journal contains normalized snapshots with
trustworthy candidate facts:

```sh
em-optimizer replay \
  --input /tmp/em-capture.jsonl \
  --policy configs/threshold-policy.yaml \
  --journal /tmp/em-replay.jsonl
```

Use `configs/band-upgrade-policy.yaml` to compare conservative 2.4-to-5 and
5-to-6 BSSID upgrades. Live recommendations remain inhibited until the
candidate adapter supplies fresh per-BSSID measurements; band inventory alone
is never treated as link quality.

Run a deterministic band-walk with one client ignoring BTM requests:

```sh
python3 -m optimizer.cli simulate \
  --world ../wmediumd/configurator/worlds/golden/home-a-band-walk-small.world.json \
  --policy configs/band-upgrade-policy.yaml \
  --initial-band 2.4 \
  --client-behavior sta_static_01=ignore \
  --output /tmp/home-band-sim.json
jq '{truth_boundary, summary}' /tmp/home-band-sim.json
```

The same command and inputs produce the same simulation hash. Do not use this
output as a live result claim.

Generate recommendation-only backhaul and channel-width plans from example
observation documents:

```sh
python3 -m optimizer.cli backhaul-plan \
  --input scenarios/examples/backhaul-observations.json \
  --output /tmp/backhaul-plan.json
python3 -m optimizer.cli width-plan \
  --input scenarios/examples/radio-environment.json \
  --output /tmp/width-plan.json
```

The backhaul baseline scores fresh undirected edge/band alternatives using
SNR, PHY rate, utilization, retries and configurable band bonuses, then returns
a maximum-utility loop-free spanning tree. It supports 2.4, 5 and 6 GHz;
2.4 GHz has a default penalty but remains available when needed for
connectivity. The width baseline covers 20/40/80/160 MHz and explains clean
2.4 GHz, radar-risk, congestion and clean-6 GHz recommendations. Neither
command changes a radio or backhaul link.

`act` requires both a policy-produced recommendation and the explicit
`--yes-act` flag. At the present interface stage it remains inhibited by
unknown freshness/missing candidate metrics during ordinary live observation.

Build and inspect the scenario matrix:

```sh
python3 -m optimizer.cli matrix \
  --spec scenarios/home-suite.json \
  --output scenarios/generated/home-suite.matrix.json
jq '.summary' scenarios/generated/home-suite.matrix.json
```

See [`optimizer-scenarios.md`](../../doc/easymesh/optimizer-scenarios.md) for
the pseudo-home, traffic plan, band-steering and backhaul boundaries.
