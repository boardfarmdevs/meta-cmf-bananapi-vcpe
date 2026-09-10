# Use an installed lab

[Home](../README.md) · [Addresses and baseline](../current-state.md)

1. Start the existing VM if stopped; use [operations](operations.md). Do not
   import another appliance merely because the host rebooted.
2. Open the live room and network topology side by side using the addresses in
   current state. Wait for the default twenty clients and six mesh roles.
3. Load **One Client Handover**. Loading automatically applies its eleven-client
   world to the fixed lab pool. Wait for load completion and fresh measurements.
4. Press **Play**. Track the walker's actual AP in both views; the dashed
   strongest-simulated link is not a completed association.
5. Ctrl-click any client to select the traffic probe. Pause or drag a device
   to inspect a change; use fullscreen in either view as needed.
6. Reload **Home A Private Client Room Walk** to return to the twenty-client
   default. Leave it paused, with no control lease or fault.

Use the [room manual](../live-room-demo/README.md) for controls and failure
interpretation, and [room catalog](../reference/rooms/catalog.md) for other demos.

For a separate native acceptance test, stop the room first so its RF writer
does not race the test, then run `gen/tests/health-audit.sh` inside the guest
checkout. Restore the room service afterward even on failure. This is a
disruptive test, not a prerequisite for every browser visit.

Do not run a carousel, manual RF-bias steer or second configurator while the
room owns the medium. Named steering outside a room is documented in
[commanded steering](../reference/optimizer/commanded-steering.md).
