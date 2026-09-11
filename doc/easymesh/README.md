# RDK EasyMesh lab

Run real RDK-B controller, agent and client software in LXD containers, with
hwsim radios and wmediumd providing reproducible RF conditions. Start with one
guide; the reference is for implementation details, not required reading.

## Start here

| Task / subsystem | Guide |
| --- | --- |
| Open the running lab; find releases and limitations | [Current state](current-state.md) |
| First use | [Quickstart](guide/quickstart.md) |
| Deploy, start, stop or recover | [Operations](guide/operations.md) |
| Understand the processes and radio model | [Architecture](concepts/architecture.md) |
| Use the room and network topology | [Room manual](live-room-demo/README.md) |
| Choose a demonstration | [Room catalog](reference/rooms/catalog.md) |
| Understand or develop steering policy | [Optimizer](concepts/optimizer.md) |
| Diagnose RF and measurements | [RF simulation](concepts/rf-simulation.md), [radio reference](reference/radio/README.md) |
| Open LXD UI or Grafana, including outer-VM metrics | [Monitoring](reference/observability/monitoring.md) |
| Test changes and measure convergence | [Testing](experiments/README.md) |
| Find detailed contracts or proposed work | [Categorized reference](reference/README.md) |

The [system explorer](https://boardfarmdevs.github.io/meta-cmf-bananapi-vcpe/explorer/)
is an illustrative, revision-pinned architecture presentation, not live lab
telemetry. [Its source guide](../../gen/explorer/README.md) explains publication.

## Keeping this documentation small

- Update the owning subsystem guide; do not add a report for every fix or chat.
- Keep URLs, deployed identity, artifact locations and open limitations in
  [current state](current-state.md), not repeated throughout the manuals.
- Put reusable contracts in the relevant reference category. Link them from
  its index; proposals belong under `reference/proposals/` and say **Proposed**.
- Put JSON, logs, screenshots, videos and dated acceptance reports beside
  release/test evidence, outside this documentation tree. Retain source/world
  hashes and failures there. Git history holds superseded narratives.
- When a proposal ships, replace its plan with the actual contract and remove
  completed milestones. Do not create a second “final” or “latest” document.
- Component READMEs own installation and CLI details; operator guides link
  instead of copying them. Keep short shared UI semantics aligned with prplMesh;
  backend commands and limitations stay in their owning repository.
- Run `python3 gen/tests/test_documentation.py` before submitting docs changes.
  It checks local links, reference navigation and introductory-document budgets.
