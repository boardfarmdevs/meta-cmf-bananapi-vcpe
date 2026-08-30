# wmediumd performance and CPU scaling

## Outcome

wmediumd remains a single RF/scheduler process with one authoritative
`mac80211_hwsim` generic-netlink endpoint. CPU affinity can isolate that
process on a selected CPU, but it cannot make a single thread execute on
several CPUs at once.

Two changes are accepted:

- the launcher can apply an explicit, optional CPU affinity; and
- active-link telemetry and inactive scenario-override lookups are indexed so
  they no longer scan large bounded tables for every frame.

A second netlink-output thread was implemented and measured, then rejected.
The complete offload delayed transmit-status cookies and caused errors and
packet loss. Offloading only cloned receive frames preserved correctness but
reduced throughput and consumed more CPU because the hwsim socket still had to
be serialized. True per-channel workers therefore require a different kernel
protocol boundary or independent hwsim medium endpoints; process affinity
alone cannot provide them.

## Reproduce the measurements

The benchmark reports CPU as a percentage of **one logical CPU**, not of the
whole host. It also records RSS, context switches, netlink receive drops,
wmediumd packet/queue counters when the Console API is available, and a
per-client traffic result.

RDK lab:

```sh
cd gen/tests
./wmediumd-performance.py --mode idle --duration 30
./wmediumd-performance.py \
  --mode ping --duration 20 --ping-interval 0.02 --client-limit 20 \
  --output /tmp/wmediumd-rdk-20x50pps.json
```

prplMesh lab:

```sh
tests/wmediumd-performance.py --mode idle --duration 30
tests/wmediumd-performance.py \
  --mode ping --duration 20 --ping-interval 0.02 --client-limit 18 \
  --output /tmp/wmediumd-prpl-18x50pps.json
```

The ping tests use only the WLAN path. The RDK target is `10.0.0.1`; the
prplMesh target is `192.168.77.1`.

## Test environment

Measurements were taken on rev140 with both labs in separate LXD virtual
machines. The RDK VM had six vCPUs and 6 GiB RAM; the prplMesh VM had four
vCPUs and 8 GiB RAM. RDK used 20 clients and 25 provisioned radio identities.
prplMesh used 18 active clients. Each loaded client sent one ICMP echo every
20 ms unless stated otherwise.

The samples below are short controlled comparisons, not hardware capacity
certification. Absolute values vary with beacon timing and the current mesh
state; the direction and size of the lookup improvement were reproduced in
both independent labs.

## Results

### RDK lab

| Variant | Workload | wmediumd CPU | Frames/s | Packet loss | Netlink errors |
|---|---:|---:|---:|---:|---:|
| original lookup, unpinned | idle | 11.65% | 396 | n/a | 0 |
| original lookup, pinned | idle | 11.60% | 412 | n/a | 0 |
| indexed lookup, pinned | idle | 11.15% | 412 | n/a | 0 |
| original lookup, unpinned | 20 x 50 pkt/s | 31.66% | 3,931 | 0.035% | 0 |
| original lookup, pinned | 20 x 50 pkt/s | 26.75% | 4,463 | 0.035% | 0 |
| indexed lookup, pinned | 20 x 50 pkt/s | 26.86% | 4,945 | 0.121% | 0 |
| rejected RX-clone worker | 20 x 50 pkt/s | 33.25% | 3,957 | 0.112% | 0 |

`perf` confirmed the mechanism rather than only the aggregate result:

- `wmd_get_link_snr` fell from 3.58% of samples to below the reported hot
  list after the zero-override fast path;
- active-link telemetry lookup fell from 2.34% to 0.69%; and
- sampled CPU-clock events for the comparable load fell by about 15.5%.

The optimized daemon processed about 10.8% more frames than the pinned
pre-index daemon at essentially the same CPU in the 50-packet/s run. Packet
loss remained small in all accepted runs; the difference between 0.035% and
0.121% is within the variation of these short samples and is not treated as a
regression without a longer repeated trial.

The exact committed `wmediumd.patched` artifact was then redeployed and run
again at the same offered rate. It used 25.37% CPU, processed 4,154 frames/s,
reported no netlink errors or receive drops, and delivered 14,892 of 14,906
echoes (0.094% loss). This confirms the packaged binary rather than only the
temporary profiling build.

### prplMesh lab

| Variant | Workload | wmediumd CPU | Packet loss | Mean client RTT |
|---|---:|---:|---:|---:|
| original lookup, unpinned | idle | 11.93% | n/a | n/a |
| indexed lookup, unpinned | idle | 9.40% | n/a | n/a |
| indexed lookup, pinned | idle | 10.17% | n/a | n/a |
| original lookup, unpinned | 18 x 50 pkt/s | 23.50% | 0.032% | 5.31 ms |
| indexed lookup, unpinned | 18 x 50 pkt/s | 21.10% | 0.019% | 4.54 ms |
| indexed lookup, pinned | 18 x 50 pkt/s | 20.76% | 0.032% | 4.84 ms |

The same patch reduced loaded CPU by 10.2% and idle CPU by 21.2% in the
prplMesh lab. Pinning after that had only a small loaded effect and slightly
worse idle CPU, reinforcing that affinity is useful for isolation and
repeatability rather than as a throughput feature.

## RDK overload boundary

The traffic rate was increased without changing the 20-client topology:

| Offered rate | Observed frames/s | CPU | Loss | Queue at end | Netlink errors/s |
|---:|---:|---:|---:|---:|---:|
| 50 pkt/s/client | 4,945 | 26.86% | 0.12% | 19 | 0 |
| 56 pkt/s/client | 5,334 | 27.64% | 0.36% | 77 | 0 |
| 67 pkt/s/client | 5,390 | 30.13% | 19.75% | 714 | 1,108 |
| 100 pkt/s/client | 5,817 | 32.49% | 66.88% | 1,876 | 1,927 |

The knee is between roughly 56 and 67 packets/s per client for this topology
and VM. The failure occurs well below 100% user-space CPU: scheduler depth,
hwsim pending-frame state, serialized netlink output, and kernel receive work
become the constraint. At 67 and 100 packets/s, adding CPU affinity or another
user thread cannot repair the overloaded single kernel endpoint.

The daemon recovered after traffic stopped: the queue returned from 1,876 to
four entries within eight seconds, with no netlink receive drops. The errors
are nevertheless a hard signal that those offered loads are outside the
accepted operating envelope.

## Affinity controls

RDK, before starting or restarting the medium:

```sh
WMEDIUMD_CPU_AFFINITY=5 gen/wmediumd/wmediumd-up.sh up
gen/wmediumd/wmediumd-up.sh status
```

prplMesh:

```sh
PRPL_WMEDIUMD_CPU_AFFINITY=3 scripts/radio-lab.sh restart-medium
scripts/radio-lab.sh status
```

Affinity is deliberately optional. A portable default cannot assume which
CPU is free or how many vCPUs a foreign host provides.

## Scaling recommendation

For the current 20-client research profile, keep the indexed single-thread
daemon and optionally reserve one CPU for repeatable experiments. For 50 to
100 clients:

1. define an offered-load acceptance profile rather than multiplying the
   current per-client packet rate blindly;
2. gate tests on queue delay/depth, netlink errors and loss, not CPU alone;
3. reduce avoidable broadcast/multicast and observer polling before changing
   the simulation model;
4. profile large idle topologies for remaining station/VIF lookup growth; and
5. if higher aggregate frame rates are mandatory, design a kernel-supported
   channel-sharding interface with one authoritative registration per shard.

The last item is a protocol and architecture project. It is not safely
achieved by starting several stock wmediumd processes against one hwsim radio
pool.
