# Proposals and open work

[Reference home](../README.md)

Proposals are not current runtime capabilities. An accepted implementation
belongs in its owning subsystem contract, not in an indefinitely growing plan.

- [Future RF assessment and development plan](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/proposals/rf-assessment-and-development-plan.md):
  the [current integration review](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/proposals/rf-assessment-and-development-plan.md#current-integration-review)
  prioritizes shared RF access and backhaul explanations before new physics.
  It reviews the external feature summary without adopting its unverified
  branches. The original M0–M9 plan remains below, historically pinned to
  `a41216d`; its capability table is not current deployment evidence.
  **Proposed work, not implemented.**
- [Neighbor-network rooms](neighbor-rooms/design.md): preserved design and
  illustration from the supplied archive; discovery/contention fidelity levels,
  external AP actors and scenario acceptance gates. **Proposed, not implemented.**
- [A retail EasyMesh extender on the RDK controller](retail-easymesh-extender/design.md):
  a TP-Link RE653BE seen searching for a controller over Ethernet (Profile 2,
  captured on rev130); how to attach it to `rdk-emosa`'s wired LAN port, its
  risks (its own DHCP server, real RF, Agent-1 naming, controller model rows)
  and acceptance. **Proposed experiment, not run.**
- [Rooms: design and implementation plan](rooms-convergence/design.md): each
  lab runs everything in its own VM on its own host, reached only through the
  Tailscale gateway; this repository becomes the single source of the room
  code, configurator and catalog that prplmesh-lab vendors; the room builder
  joins each lab at `/builder/` with session rooms; GitHub Pages stays the
  offline playground. **Proposed, not implemented.**
- [Optimizer workbench](optimizer-workbench/design.md): an optimizer developer
  uploads a Python policy that turns telemetry snapshots into steering and
  measurement decisions, develops it offline against replayed lab journals, and
  selects it for room runs on the RDK and prplMesh labs; the policy contract,
  sandbox, registry, scorecard and a later Data Elements view.
  **Proposed, not implemented.**

The [virtual RF assessment](https://github.com/boardfarmdevs/easymesh-medium/blob/main/docs/reference/virtual-rf-assessment.md) owns the current
radio-capability audit and completed common/RDK/prpl implementation evidence.
The future RF plan defines proposed follow-on work, not a replacement for that
evidence. Consult the audit before relying on baseline observations in either
proposal; its numbered implementation phases are separate from the plan's M0–M9.

## Priorities to carry forward

| Owner | Work | Completion evidence |
| --- | --- | --- |
| RDK native metrics | Diagnose busy admission and incomplete candidate responses; never mask with stale cache or default retry storms | Timestamped native request/response trace and affected-room rerun |
| RDK 6-GHz association | Correlate BTM, AP refusals, station association and controller publication | Exact target/BSSID/opclass evidence, verified traffic, failures retained |
| prpl metrics interface | Remove whole-second ambiguity with a native sequence ID or higher-resolution timestamp if available | Freshness regression without artificial stale admission |
| Common RF | Qualify fail-closed behavior, overload/drop classification, explicit receiver eligibility and reception-backed measurements | Standalone conformance tests plus a physical reference comparison |
| Common deployment | Consolidate duplicated platform-neutral room/monitoring code only with independent release reproducibility | Both backend unit/import/room gates |
| Hosts | Investigate cooling, throttling and observer load separately from stack logic | Comparable before/after host telemetry |

Larger appliance/inventory refactors are not prerequisites for operating the
current fixed-pool lab. Start with a demonstrated defect and a bounded test,
not another broad architecture proposal. Keep new work items small, assign an
owner and acceptance gate, and remove them when completed. Historical detailed
plans and measurement narratives remain available through Git history.
