# Room and topology manual

[Documentation home](../README.md) ·
[Room catalog](../reference/rooms/catalog.md) ·
[Current deployment](../current-state.md)

## Open and control

Open both views side by side; no `?mode=` is required. Built-in Help contains
the detailed controls and evidence boundaries.

- **Load world** applies geometry, RF and presence immediately; wait for completion.
- **Play / Pause** controls scripted movement. Dragging remains available.
- **Ctrl-click any client** selects the traffic probe, without steering it.
- Station names remain visible; drag the black properties label out of the way.
- Drag the **grey divider** to resize panels. Widths persist separately per view.
  Arrow keys adjust; double-click resets. Mobile panels remain stacked.
- The **room name** shares the topology header, including fullscreen. Unavailable
  room data marks it **last observed**. Hover over the follow checkbox for status.
- **Full screen** expands either drawing; Esc exits.
- **Follow room layout** tracks committed coordinates in the room's default
  camera orientation. Controller stays near Agent-1; clients stay with their AP.
  Diagram dragging switches to manual; checking resumes. Camera orbit is local
  to the room, not shared with topology.
- AP groups pack around visible bubbles and fit with a **six-pixel margin**,
  preserving orientation. **Optimize Layout** also tightens manual arrangements.
- Restore the default twenty-client world and leave it paused before handoff.

Worlds change active presence within the provisioned pool, without rebuilding
the VM. Absent clients disappear from the converged roster. Disabling
**fronthaul** does not disable backhaul. Resizing/packing never changes RF.

## Read the views correctly

| Indication | Meaning |
| --- | --- |
| Room position and strongest simulated link | World/RF prediction, not native association |
| Actual solid link | Observed serving AP or backhaul parent |
| Thin dashed link | Strongest simulated eligible link, not proof of steering |
| Red / yellow / green bars | Weak / intermediate / strong known signal |
| Grey bars | Unknown or stale measurement, not a measured zero |
| Extender signal | Backhaul uplink to its actual parent |
| Fronthaul disabled | Client-facing AP unavailable; mesh uplink may still work |
| Network topology | Controller-reported ownership; verify independently for tests |

Both views share signal thresholds. The best eligible AP need not provide
green/maximal SNR: walls, distance, band, SSID and policy still matter.
RDK/prpl inventory mappings differ; compare identities, not drawing ordinals.

## Optimizer activity

Roam cues show six seconds of history without delaying association rendering.
`FROM` marks the previous location, not another connected client. Teal means an
accepted **BTM request**, not proven delivery/causation; pink means **reported
non-BTM**; grey means **unknown**. Missing BTM evidence does not prove non-BTM.

Check authority: external policy requesting native BTM is not a native optimizer.

“Reading” means collection; “stable/converged” means the last qualified
evaluation. Auto BTM permits requests, not immediate movement. Inspect epochs,
freshness, targets, decisions and terminal verification.

**Measurements unavailable** pauses decisions, not interaction. Preserve errors
and retry information; never substitute stale candidates or treat grey as zero.

A star can be correct with protected startup backhaul. See
[coordination](../reference/rooms/architecture.md) for profiling, assistance and
modeled-backhaul experiments.

## Safe use and troubleshooting

Use one operator lease and RF writer. Pause may still collect/steer; stop the
room service before standalone native experiments.

On failure, preserve faults/journals. Check service health, world/epoch, actual
station links and freshness; do not erase ownership or fabricate topology.
See [remote access](../reference/rooms/access.md).

For a correctness claim, use [room acceptance](../reference/testing/room-acceptance.md).
A screenshot, accepted API request or interesting animation is not a pass.
