# RDK EasyMesh immersive room demonstration

`room-demo` compiles a checked-in Golden World against the live RDK lab, runs
it through the existing `wmdcfg` actuator, joins live controller telemetry,
traffic, health and reference-optimizer decisions, and serves the presentation
on the runner's authoritative clock.

Scripted-run browser APIs remain read-only. The separate `interactive` command
exposes a lease-protected, revisioned control API whose sole RF writer applies
and reads back atomic wmediumd generations. Destination walks are server-owned
and support pause, resume and cancel, so browser rendering is never the RF
clock. Accepted live changes can be downloaded as a deterministic compiled
world. `stimulus`, `recommend`, and explicitly confirmed `act` modes separate
optimizer authority from simulated room movement.

See [the full operator manual](../../doc/easymesh/live-room-demo/manual.md).
Interactive operation has a separate
[control and safety manual](../../doc/easymesh/live-room-demo/interactive-room-manual.md).
