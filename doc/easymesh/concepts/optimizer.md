# External optimizer

Audience: Wi-Fi researchers deciding how to introduce or evaluate steering
logic.

Purpose: describe the optimizer boundary and the safe path from observations to
actions. The detailed schemas and implementation are in
[the architecture reference](../reference/optimizer-architecture.md), while
extension procedures are in
[optimizer development](../experiments/optimizer-development.md).

## Ownership boundary

The optimizer is a separate host-side component. It is not hidden inside the
BPI controller, Agent, WebUI, wmediumd, or configurator.

```text
wmediumd/configurator  -> controlled RF world
EasyMesh APIs          -> topology, BSS, client and metrics observations
optimizer              -> normalize, validate, decide and journal
steering adapter       -> exact bounded EasyMesh action
station + controller   -> independent outcome verification
```

EasyMesh provides standardized policy configuration and action primitives. The
optimizer supplies the decision logic that chooses whether and when to use
them. This distinction lets researchers compare algorithms without modifying
the controller for every experiment.

## Current implementation

The checked-in Python package provides:

- normalized snapshots from recorded or live EasyMesh inputs;
- strict completeness, freshness, and identity validation;
- current-link and same-band candidate RCPI collection;
- deterministic replay;
- a simple threshold/hysteresis baseline policy;
- observe, recommend, and explicitly enabled act modes;
- an adapter to `gen/steer.sh` using exact BSSID targets;
- association verification, cooldown, backoff, action limits, and journals;
- unit tests and scenario integration tests.

It is a research harness, not a completed autonomous field policy. The current
baseline deliberately remains interpretable so later algorithms can be
compared against it.

## Inputs and actions

An actionable client observation needs:

- stable client identity and SSID cohort;
- current AP, BSSID, band, and fresh current-link metric;
- complete eligible candidate measurements for that decision cycle;
- topology and BSS ownership consistent with the observed association;
- policy configuration and health gates permitting an action; and
- enough history to apply hysteresis, cooldown, and backoff.

The first action surface is client steering to one exact BSSID. Backhaul
topology, channel selection, and channel width are valuable research areas but
belong to slower, separately gated action loops.

## Safe modes

```text
observe     collect and normalize; never decide or act
recommend   collect candidates and explain a decision; never act
act         require explicit opt-in, then send and verify bounded actions
replay      evaluate the same recorded world repeatedly without a live lab
```

Incomplete or stale observations must produce no action. A successful command
is not a successful decision until the real station link, controller model,
traffic, and post-action stability agree.

## Research progression

1. Establish deterministic RF and traffic inputs.
2. Freeze normalized observations as replay fixtures.
3. Score a no-action and simple threshold baseline.
4. Run the policy in observe and recommend modes on the live lab.
5. Permit one action and verify it end to end.
6. Add mobility, threshold-hover, flash-crowd, band, and backhaul scenarios.
7. Compare algorithms using the same scenarios, seeds, and scoring contract.
8. Increase clients only after correctness and resource gates remain stable.

Candidate novel mechanisms may include adaptive hysteresis, dwell prediction,
client-specific compliance memory, load-aware utility, coordinated multi-client
actions, and slower weighted-graph backhaul selection. Each needs an
interpretable baseline and explicit failure behavior.

## Start here

- [Run and extend the optimizer](../experiments/optimizer-development.md)
- [Optimizer scenarios](../experiments/optimizer-scenarios.md)
- [Full architecture and interface contracts](../reference/optimizer-architecture.md)
- [Steering policy boundary](steering-policy.md)
- [Current implementation and limitations](../current-state.md)
