# Live room demo

The live room demo combines a reproducible 3D home, dynamic wmediumd RF
conditions, controller telemetry and the reference optimizer in one
presentation. Start here:

- [Operator manual](manual.md) — complete setup, operation, replay,
  troubleshooting and customization instructions.
- [Architecture and design](design.md) — system boundaries, data flow and
  implementation decisions.
- [Viewer reference](viewer.md) — stimulus-only viewer controls and visual
  conventions.
- [Interactive room manual](interactive-room-manual.md) — current live RF
  controls, destination movement, recording, restoration and diagnostics.
- [Fixed-pool world switching](../reference/live-world-switching.md) — loading a
  world immediately updates the lab while retaining the default 20-client appliance.
- [Local and internet access](../reference/room-viewer-remote-access.md) —
  existing HTTP/SSE transport, protected remote access, and a proposed
  local-default connection experience; no runtime changes enabled.
- [Interactive room architecture and improvement plan](interactive-room-plan.md)
  — governing single-writer, causality, state, security, recovery and phased
  acceptance design.

The normal entry point is `gen/demo/room-demo`. The RDK Network Topology view
remains the authority for the controller's current association model, while
the room viewer presents the physical scenario and the wmediumd console shows
the medium's live frame and SNR observations.
