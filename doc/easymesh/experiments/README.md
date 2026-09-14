# Testing and experiments

[Home](../README.md) · [Testing reference](../reference/testing/README.md)

Use a dedicated lab and new evidence directory. Preserve versions, world hashes,
native/container identities, timestamps, failed attempts and restoration results.
Only one RF writer may run at a time. The default room is itself a writer.

| Question | Procedure / owning implementation |
| --- | --- |
| Do all rooms load, play and converge in both views? | [Room acceptance](../reference/testing/room-acceptance.md) |
| Does the stopped-room native baseline work? | `gen/tests/health-audit.sh` |
| Can a requested BTM move a real station? | [Commanded steering](../reference/optimizer/commanded-steering.md) |
| Can a private or IoT cohort move reversibly? | `gen/tests/wmediumd-client-carousel.py --help` |
| Can backhaul form a chain or branch? | `gen/tests/multihop-backhaul.sh` (inspect options before mutation) |
| How do I add or evaluate a policy? | [Optimizer development](../reference/optimizer/development.md), [scenarios](../reference/optimizer/scenarios.md) |
| Is the medium/resource path the bottleneck? | [Performance diagnostics](../reference/testing/performance.md) |
| Which room makes a short demonstration? | [Catalog](../reference/rooms/catalog.md) |

## Test order

1. Run source/unit checks for the changed subsystem.
2. Test one bounded scenario and confirm exact medium restoration.
3. Test all affected rooms, then the full catalog when justified.
4. Qualify larger online cohorts or longer durations explicitly, using the same
   100-client-capacity VM. A passing 20-client room does not qualify 50 or 100
   online clients, and bounded room tests are not soak acceptance.

A successful command, 1905 ACK, green UI label or client-side association alone
is insufficient. Require intended physical BSSID, controller ownership,
fresh current-epoch measurements and traffic. Count timeouts as failures, not
missing performance samples.

For live room tests keep the room running and use its API/lease. For standalone
native/scenario tests stop the room service first and restore it afterward.
Do not force native policy compliance with hidden RF bias and call it profiling.
