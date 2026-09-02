# Thin-appliance bring-up comparison

## Purpose

This experiment compares first use of the universal 0831 RDK EasyMesh and
prplMesh thin LXD appliances. It measures the complete path from starting the
importer through provisioning and accepted service state. It is not a pure
stack benchmark: the two guests ran on different hosts, and their radio and
container models are intentionally different.

The comparison is useful for answering three operational questions:

1. Does a clean external artifact reconstruct without an operator nudge?
2. Where is time spent before the first accepted lab is available?
3. Does first-boot provisioning unnecessarily repeat normal runtime work?

## Test inputs

| Item | RDK EasyMesh | prplMesh |
| --- | --- | --- |
| Artifact | `rdkeasymesh-0831-thin.tar` | `prplmesh-0831-thin.tar` |
| Archive SHA-256 | `c090f63ec2d9dd350111b68077d6eb951e706dbbfe52c9692a2dd5402701c675` | `9ef007df292742ebc8c36e9405d71810c8754e7f1f802baa58b68cd9bf45f598` |
| Packaged source | `9729ca4ed89a15c91538292eaf41d6880dd97f29` | `4eb6bcc32beff12e90328660fcd10970a4694a16` |
| Outer host | rev150, Ryzen 7 8745HS, 8 cores/16 threads, 25 GiB RAM | rev120, i7-10710U, 6 cores/12 threads, 62 GiB RAM |
| Guest | Ubuntu 24.04/Linux 7 LXD VM | Ubuntu 24.04/Linux 7 LXD VM |
| Medium | userspace wmediumd | userspace wmediumd |

Both archives and their inner payloads passed their supplied SHA-256 checks.
Any previous evaluation VM was deleted before each profile. The importers were
started within one second of one another. The tests retained all protocol,
traffic and stability acceptance gates supplied by each appliance.

## 20-client profile

The 20-client run began at 2026-09-01 21:43:33 PDT.

| Measurement | RDK EasyMesh | prplMesh |
| --- | ---: | ---: |
| Outer import/VM creation | 3 min 09 s | 7 min 33 s |
| Guest first-boot provisioning | 25 min 09 s | 16 min 34 s |
| Import start to accepted first boot | 28 min 22 s | 24 min 07 s |
| Final nested instances | 25/25 running | 25/25 running |
| Client traffic | 20/20 pass | 20/20 pass |
| Mesh model | 5 devices, 15 radios, 50 BSS records | controller plus four agents accepted |
| Client telemetry | 20/20 RCPI present | topology and steering acceptance pass |
| Service restarts during accepted RDK runtime | zero | not directly comparable |

RDK first provisioning created and started the complete roster. The service
dependency chain then invoked its ordinary cold-start transaction, stopped the
20 clients, and reconstructed the already running lab. That second transaction
took 377.5 seconds, including a 120-second stability hold. Its measured phases
were:

| RDK phase | Time |
| --- | ---: |
| Infrastructure | 0.2 s |
| Quiesce and radio reset | 21.9 s |
| Mesh launch | 2.0 s |
| Controller readiness | 69.0 s |
| Extender convergence | 40.8 s |
| Metrics policy | 20.3 s |
| Client start and readiness | 31.9 s |
| Medium startup | 32.0 s |
| Convergence and acceptance | 152.5 s |
| Evidence | 7.1 s |

prplMesh instead spent about 364 seconds defining the complete dormant
inventory, onboarded four agents at a fixed cadence of approximately 89
seconds, started all 20 clients in about 31 seconds, and completed roughly 155
seconds of acceptance. It did not perform the same obvious whole-roster second
reconstruction.

## 20-client steady-state snapshot

The following is a point-in-time snapshot after both first boots passed. PSS
was not collected for every process, so guest `used` and outer LXD memory are
capacity observations rather than per-component attribution.

| Measurement | RDK EasyMesh | prplMesh |
| --- | ---: | ---: |
| Outer LXD current memory | 4.79 GiB | 7.37 GiB |
| Guest used memory | 2.18 GiB | 2.51 GiB |
| Guest available memory | 5.50 GiB | 5.17 GiB |
| Guest filesystem allocated bytes | 6.59 GB | 34.19 GB |
| wmediumd CPU at snapshot | 9.7% | 17.0% |
| wmediumd RSS | 3.3 MiB | 4.0 MiB |
| Console RSS | 12.6 MiB | 12.4 MiB |

The higher prplMesh medium and guest footprint is consistent with its explicit
per-band wiphy model. The RDK BPI model has one hwsim wiphy per mesh device and
projects three logical RDK/EasyMesh radios from it. prplMesh uses separate
virtual radios for its bands, so client count alone does not represent equal
kernel-radio or medium state. See
[MediaTek single-wiphy radio model](../reference/single-wiphy-radio-model.md).

## 50-client profile

The 50-client run began at 2026-09-01 22:13:44 PDT.

| Measurement | RDK EasyMesh | prplMesh |
| --- | ---: | ---: |
| Outer import/VM creation | 2 min 53 s | 6 min 40 s |
| Guest initial provisioning | 33 min 25 s | 29 min 02 s |
| Import start to initial provisioned roster | 36 min 56 s | 35 min 42 s, accepted |
| Final nested instances | 55/55 running | 55/55 running |
| Result | **fail after duplicate reconstruction** | **pass** |
| Import start to final result | 45 min 33 s | 35 min 42 s |

The RDK provisioning unit reached 55/55 running instances at 05:50:39Z. Its
normal runtime then immediately stopped the roster, briefly reduced it to one
running instance, and reconstructed all 55. The second transaction failed at
05:59:16Z because the controller model did not converge before its bounded
gate: 49 live topology clients and 53 associated records were present. This is
not counted as an accepted 50-client result, even though the initial
provisioning roster was complete.

The redundant RDK transaction consumed another 8 minutes 37 seconds before
failure. Before the final convergence timeout, its measured phases included
30.1 seconds for quiesce/radio reset, 69.2 seconds for controller readiness,
35.3 seconds for extenders, 20.2 seconds for metrics policy, 42.7 seconds for
clients, and 53.7 seconds for medium reconstruction. None of those operations
was necessary merely to validate the state just created by thin provisioning.

prplMesh finished at 05:49:26Z with all 55 instances and its complete
first-boot acceptance marked `PASS`. Its steady-state point snapshot showed
11.36 GiB outer LXD memory, 4.53 GiB guest used memory, 7.08 GiB guest
available memory, and 70.85 GB allocated guest filesystem bytes. These larger
values must be interpreted with its separate per-band virtual-wiphy model and
different host, not as a direct RDK regression.

## Elimination of RDK's second reconstruction

The duplicate RDK transaction is an appliance lifecycle defect, not required
EasyMesh convergence. The thin provisioning helpers must start each node to
assign and validate its permanent hwsim identity. Throwing that accepted state
away immediately adds latency and creates avoidable radio, protocol and model
churn.

The corrected service path creates a one-use marker in `/run` after thin
provisioning. The normal runtime accepts it only when all of these agree:

- selected client profile and exact `clients + 5` instance count;
- every expected instance is running;
- packaged repository revision is exact;
- selected medium backend is healthy;
- live WLAN client count is exact; and
- the controller has exactly five mesh devices.

On success, the runtime consumes the marker and preserves the running roster;
its existing `ExecStartPost` still performs the complete final lab health
check. If any invariant fails, it consumes the invalid marker and executes the
ordinary cold reconstruction. Because `/run` is volatile and the marker is
one-use, later service restarts and guest reboots retain normal cold-start
semantics.

## Conclusions

- Both 20-client universal thin artifacts reconstructed a complete accepted lab
  without an operator nudge.
- Thin archive size alone did not predict first-use duration. Provisioning and
  protocol gates dominated import time.
- The different hosts and radio models prevent treating the elapsed-time or
  memory columns as a controlled implementation benchmark.
- The RDK duplicate lifecycle transaction was real, measurable, and removable
  without weakening final acceptance.
- A future artifact refresh should include the handoff fix and the current
  prplMesh Console/UI service layout. The present 0831 artifacts remain the
  immutable baseline for this comparison.
