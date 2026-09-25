# Proposals and open work

[Reference home](../README.md)

Proposals are not current runtime capabilities. An accepted implementation
belongs in its owning subsystem contract, not in an indefinitely growing plan.

- [Future RF assessment and development plan](easymesh-rf-assessment-and-development-plan.md):
  the [current integration review](easymesh-rf-assessment-and-development-plan.md#current-integration-review)
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

The [virtual RF assessment](../radio/virtual-rf-assessment.md) owns the current
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
