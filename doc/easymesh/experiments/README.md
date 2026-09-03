# Experiment catalog

Audience: operators and researchers selecting a reproducible lab experiment.

Every experiment starts and ends with the normal health gate. Run only one
wmediumd writer at a time, retain its inputs and journal, and require exact
medium restoration before accepting the result.

## Select an experiment

| Question | Experiment | Primary evidence |
| --- | --- | --- |
| Can clients visibly move among APs under controlled RF? | [Client carousel](scenarios/client-carousel.md) | RF generations, station links, topology transitions, restoration |
| Do clients recover when one extender becomes unreachable? | [Extender outage](scenarios/extender-outage.md) | client/AP ownership, aging, traffic, recovery |
| Can backhaul form a chain or branch rather than a star? | [Multihop backhaul](scenarios/multihop-backhaul.md) | bSTA link, parent BSSID, controller edge, backhaul signal |
| How are private and IoT cohorts provisioned and scaled? | [Client scale](scenarios/client-scale.md) | cohort counts, radio capacity, topology, traffic |
| How long do complete 25- and 55-container lifecycle transactions take? | [Lifecycle performance](lifecycle-performance.md) | systemd wall time, phase timings, topology, metrics, traffic, restart counts |
| How do clean RDK and prplMesh thin appliances reconstruct? | [Thin-appliance bring-up comparison](thin-appliance-bringup-comparison.md) | import, provisioning, acceptance, resource snapshot, lifecycle duplication |
| Does the lab remain stable under repeated churn? | [Soak acceptance](scenarios/soak-acceptance.md) | duration, restarts, memory, drops, candidate RCPI, restoration |
| How is an optimizer evaluated across deterministic worlds? | [Optimizer scenarios](optimizer-scenarios.md) | replay inputs, decisions, scores, action outcomes |
| How do I add an optimizer input or algorithm? | [Optimizer development](optimizer-development.md) | tests, schemas, journals, live ladder |

The command-by-command 0902 appliance check, including bounded failures that
must not be hidden during a demonstration, is recorded in
[0902 scenario validation](results/scenario-validation-0902.md).

## Common lifecycle

```text
preflight health
  -> capture source, images, topology, policies and medium
  -> compile/dry-run scenario
  -> apply one bounded writer
  -> observe station + EasyMesh + Console + traffic
  -> record decision/action/outcome
  -> restore captured medium
  -> final health and provenance
```

## Evidence minimum

Every retained run should identify:

- repository revision and image SHA-256 values;
- kernel, topology, client cohorts, and active policy settings;
- scenario source, compiled sequence, bindings, seed, and timing;
- initial and final wmediumd generation and touched pair readback;
- station association and controller ownership before and after;
- traffic result and service restart counts;
- optimizer input, decision explanation, action, and verification when used;
- final restoration result; and
- timestamps and an explicit pass/fail summary.

## Capability progression

Use the accepted 20-client profile first. The 50-client profile has passed a
bounded cold-reconstruction gate, but its duration gate remains separate. The
intended progression is:

```text
functional baseline
  -> one reversible RF transition
  -> repeated mobility/outage
  -> optimizer replay
  -> live observe
  -> live recommend
  -> one bounded action
  -> duration soak
  -> bounded 50-client cold reconstruction (complete)
  -> 50-client duration acceptance
  -> 100-client stress profile
```

Do not treat an unvalidated larger topology as progress if measurements become
incomplete, wmediumd drops increase, onboarding needs manual intervention, or
cleanup cannot restore the original state.

See [RF simulation](../concepts/rf-simulation.md) for component ownership and
[current state](../current-state.md) for the presently accepted boundary.
