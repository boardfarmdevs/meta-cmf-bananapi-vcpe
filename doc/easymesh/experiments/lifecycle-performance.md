# Lifecycle performance

## Outcome

Bounded parallel lifecycle management reduced complete 25-container cold
reconstruction from 15 minutes 18 seconds to 6 minutes 21 seconds, and the
55-container reconstruction from 26 minutes 8 seconds to 6 minutes 50 seconds.
Complete shutdown now takes 32 to 43 seconds rather than 95 to 127 seconds.

These are complete service transactions, not just `lxc start` latency. Start
time includes controller and extender readiness, all client associations and
DHCP leases, medium startup, metrics convergence, a 120-second stability hold,
traffic verification, zero-restart checks, and evidence capture.

| Profile | Medium | Serial start | Parallel start | Reduction | Serial stop | Parallel stop | Reduction |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 mesh + 20 clients (25 containers) | userspace wmediumd | 917.6 s | 381.2 s | 58.5% | 126.8 s | 31.7 s | 75.0% |
| 5 mesh + 50 clients (55 containers) | experimental kernel medium | 1568.3 s | 409.6 s | 73.9% | 95.0 s | 42.7 s | 55.0% |

The 55-container timing row is a cold-lifecycle acceptance result for the
optional kernel backend. A separate 50-client userspace-wmediumd bounded cold
reconstruction also passed and is retained under
[`results/kernel-medium-0829/`](results/kernel-medium-0829/README.md), but it
was not the baseline/final pair measured by this lifecycle change. Neither
result is a long-duration 50-client soak claim.

## Implementation

The runtime preserves its dependency gates:

```text
Boardfarm WAN and hwsim ownership
  -> controller start and readiness
  -> four extenders started concurrently
  -> exact 5-device / 15-radio / 50-BSS model
  -> clients started and checked in bounded cohorts
  -> selected medium backend
  -> topology, RCPI, stability, restart and traffic gates
  -> evidence capture
```

The default limits are:

| Operation | Parallelism or timeout |
| --- | ---: |
| Extender start/readiness | 4 |
| Client start/readiness | 10 |
| Client traffic checks | 10 |
| Extender stop | 4 |
| Client stop | 16 |
| Stateless client graceful-stop interval | 2 s |
| Mesh-node graceful-stop interval | 10 s |

They can be overridden through the corresponding `EASYMESH_*` environment
variables. Parallelism is bounded so a larger profile does not issue an
uncontrolled burst of LXD, network-namespace, DHCP, or controller operations.
The controller still starts alone. No client starts until all extenders and the
complete mesh model are ready.

Whole-lab shutdown stops the medium first, stops stateless clients in bounded
batches with a short graceful interval, stops extenders concurrently, and
stops the controller last. All returned PHYs are available before a later
reconstruction reclaims dynamic VIFs.

Every successful transaction writes machine-readable timing to:

```text
<acceptance-state>/last-start-timing.json
<acceptance-state>/last-stop-timing.json
```

The record includes backend, mesh/client/container counts, total elapsed time,
result, and every phase duration. The combined measurement from this evaluation
is [lifecycle-parallel-eval-0829.json](results/lifecycle-parallel-eval-0829.json).

## Final phase measurements

| Phase | 25 containers | 55 containers |
| --- | ---: | ---: |
| Infrastructure | 0.2 s | 0.2 s |
| Quiesce and radio reset | 2.1 s | 4.7 s |
| Controller readiness | 74.9 s | 73.2 s |
| Four-extender convergence | 60.3 s | 60.1 s |
| Initial metrics policy | 20.3 s | 20.3 s |
| Client start, association and DHCP | 28.5 s | 59.4 s |
| Medium startup | 37.0 s | 17.9 s |
| Convergence and acceptance | 150.2 s | 160.8 s |
| Evidence capture | 7.5 s | 12.9 s |

The fixed 120-second stability hold is now the largest part of both accepted
transactions. It is intentionally retained. Container launch is no longer the
dominant cost.

## Acceptance observed

Both final runs completed without an operator nudge. Each reached five mesh
devices, fifteen radios, fifty BSS records, the exact expected associated STA
count, nonzero RCPI for every WLAN client, working gateway traffic for every
client, and zero OneWifi/EasyMesh service restarts. Parallel extender onboarding
passed repeatedly on both medium backends.

These are single-run point measurements on rev140 LXD virtual machines. They
establish a large deterministic improvement, but they are not percentile data
and do not replace repeated reboot or long-duration soak acceptance.
