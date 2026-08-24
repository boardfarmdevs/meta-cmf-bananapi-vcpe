# EasyMesh evaluation lab

Audience: lab operators, Wi-Fi researchers, optimizer developers, and platform
engineers.

Status: current documentation for `codex/0824-clean`.

This lab runs the Banana Pi RDK-B EasyMesh stack in LXD containers, gives each
node a Linux 7.0 `mac80211_hwsim` radio, and uses a patched multichannel
wmediumd as the controlled RF medium. Its purpose is repeatable onboarding,
telemetry, steering, topology, and optimizer experimentation without requiring
a large physical Wi-Fi installation.

## Choose a path

| I want to... | Start here |
| --- | --- |
| Understand what the lab is | [Architecture](concepts/architecture.md) |
| See exactly what works now | [Current state](current-state.md) |
| Use an already installed lab | [Quickstart](guide/quickstart.md) |
| Start, stop, recover, or redeploy it | [Operations](guide/operations.md) |
| Give a live demonstration | [Demonstrations](guide/demonstrations.md) |
| Understand RF simulation | [RF simulation](concepts/rf-simulation.md) |
| Understand steering and policy boundaries | [Steering policy](concepts/steering-policy.md) |
| Develop an optimizer | [Optimizer](concepts/optimizer.md) |
| Select and run an experiment | [Experiment catalog](experiments/README.md) |
| Investigate implementation details | [Technical reference](#technical-reference) |

A newcomer should not read every document. The shortest useful path is:

```text
current state -> architecture -> quickstart -> demonstrations
```

An optimizer researcher should then continue with:

```text
RF simulation -> steering policy -> optimizer -> experiment catalog
```

## Documentation sections

### Guides

Guides contain procedures an operator follows:

- [Quickstart](guide/quickstart.md) validates a running lab and performs the
  first steer and RF experiment.
- [Operations](guide/operations.md) covers deployment, cold and warm starts,
  health gates, VM parity, recovery, access, and troubleshooting.
- [Demonstrations](guide/demonstrations.md) is the audience-facing runbook.

### Concepts

Concept documents explain the system without requiring implementation detail:

- [Architecture](concepts/architecture.md) identifies the processes, radios,
  control plane, data plane, and onboarding sequence.
- [RF simulation](concepts/rf-simulation.md) shows how wmediumd, the
  configurator, the Console, EasyMesh, and the optimizer form a closed loop.
- [Steering policy](concepts/steering-policy.md) separates standardized
  EasyMesh primitives from controller policy decisions.
- [Optimizer](concepts/optimizer.md) defines the external optimizer boundary
  and safe research progression.

### Experiments

The [experiment catalog](experiments/README.md) routes users to the appropriate
mobility, outage, multihop, scale, soak, or optimizer scenario. Detailed
optimizer extension instructions are in
[optimizer development](experiments/optimizer-development.md).

### Technical reference

Reference documents are consulted when implementing or diagnosing a specific
boundary:

- [Consolidated patch set](reference/patch-set.md)
- [Metrics reporting and APIs](reference/metrics.md)
- [Optimizer architecture and contracts](reference/optimizer-architecture.md)
- [wmediumd internals](reference/wmediumd-internals.md)
- [wmediumd configurator](reference/wmediumd-configurator.md)
- [wmediumd Console and telemetry protocol](reference/wmediumd-console.md)
- [Packet capture](reference/packet-capture.md)
- [Memory footprint](reference/memory-footprint.md)

## Documentation rules

- Put the accepted revision, topology, artifacts, and known limitations only in
  [current-state.md](current-state.md). Other documents link to it.
- Put commands in guides or experiment procedures, not in concept documents.
- Put wire formats, APIs, patch ordering, and implementation detail in
  `reference/`.
- Keep raw measurements and completed campaign results with external evidence,
  not in the active user documentation.
- Do not describe a commanded steer as an autonomous policy decision.
- A successful API response, 1905 ACK, or association alone is not an
  end-to-end pass; use the health and acceptance gates.
- Preserve source revision, image hashes, scenario inputs, and result artifacts
  for every claimed experiment.
