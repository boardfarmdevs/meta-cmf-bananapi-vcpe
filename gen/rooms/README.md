# The RDK lab's live room

`room-service` starts the room service, which is easymesh-optimizer's `room_service`
package (this lab pins the repository as `gen/optimizer`): it compiles a
checked-in Golden World against the live RDK lab, runs it through the `wmdcfg`
actuator, joins live controller telemetry, traffic, health and the optimizer's
decisions, and serves the presentation on the runner's authoritative clock.

This directory is the lab's side of it: the launcher (`room-service`, which the VM's
`easymesh-room-service.service` runs), the room manifests (`manifests/`: the
default rooms, the rooms with the wired extender, with the OpenSync pods, the
load-aware and counter-guard profiles) and the role bindings (`bindings/`: which
container plays which room role), and the tests of these (`tests/`). The room
service's own tests are in easymesh-optimizer (`tests/room`).

Scripted-run browser APIs remain read-only. The separate `interactive` command
exposes a lease-protected, revisioned control API whose sole RF writer applies
and reads back atomic wmediumd generations. `stimulus`, `recommend`, and
explicitly confirmed `act` modes separate optimizer authority from simulated room
movement.

See [the room operator manual](../../doc/easymesh/room-service/README.md)
and [coordination contract](../../doc/easymesh/reference/rooms/architecture.md).
