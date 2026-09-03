# Controlled thin-appliance comparison

## Result

The RDK EasyMesh and prplMesh 20-client thin appliances both reconstructed a
complete lab from an external archive without an operator nudge. On the same
rev140 host, run sequentially with identical VM allocations, prplMesh reached
accepted state in 20 min 16.410 s and RDK reached it in 21 min 46.226 s. The
89.816 s difference is 6.9% of the RDK result and is too small to establish a
general performance ranking from one run.

The experiment did expose meaningful architectural differences:

- RDK imported 2 min 37.753 s faster, but its guest first-boot work took
  3 min 51 s longer.
- The classified RDK processes used 525.34 MiB PSS; the classified prplMesh
  processes used 243.99 MiB PSS. These groups are not component-for-component
  equivalents, but the 53.6% reduction is large enough to justify deeper
  attribution.
- The outer prplMesh QEMU process had 2.21 GiB more PSS, despite its lower
  classified process PSS. QEMU PSS includes guest RAM shared mappings and page
  cache, so it is a capacity observation rather than application attribution.
- The early steady-state CPU sample was higher for prplMesh, primarily in
  wmediumd and hostapd. RDK spent less CPU in wmediumd in this short sample.
- The final prplMesh distribution archive is 25.3% smaller than the RDK
  archive.

These results show that both appliances are operational. They do not show that
one EasyMesh implementation is categorically faster, smaller, or more mature.

## Controlled method

Both tests ran on rev140, one at a time. The competing lab VM and build
container were stopped before each run. Each appliance was imported from its
distribution archive, assigned the 20-client profile, allowed to complete its
own first-boot and acceptance gates, sampled twice, and then shut down and
deleted before the other stack was started.

| Condition | Value |
| --- | --- |
| Outer host | rev140, Intel Core i7-1260P, 16 logical CPUs, 62.4 GiB RAM |
| Host software | Ubuntu kernel 5.15.0-139, LXD 5.21.7 LTS, ZFS storage |
| Guest allocation | 6 vCPU, 8 GiB RAM |
| Guest software | Ubuntu 24.04, Linux 7.0.0-30 |
| Profile | 20 WLAN clients, five mesh nodes, 25 nested containers |
| Simulated medium | userspace wmediumd |
| Execution order | RDK first, prplMesh second; never concurrent |
| Repetitions | one cold run per stack |

The measured end-to-end interval starts immediately before the importer and
ends when all stack-specific acceptance gates pass. Import time, guest
first-boot time, and accepted-state detection were independently timestamped.

## Reproducibility inputs

| Item | RDK EasyMesh | prplMesh |
| --- | --- | --- |
| Archive | `rdkeasymesh-0902-thin.tar` | `prplmesh-0902-thin.tar` |
| Archive size | 2.28 GiB | 1.70 GiB |
| Archive SHA-256 | `bad1d3148b904ff393a286007548900fd43bc291199b1497279cc501e22225fa` | `e75c0ca932378eba8017108e6c68ab86b97e9554d3bff18ca9517f74651d951e` |
| Inner image SHA-256 | `47a8ff809e0cad4bc10606f82178219651542d1da8fef4167288120166f1bec8` | `922975420288c44d76f0c1be5ddf186447928993756e442811ba8fc56c34b7e8` |
| Package source | `108ac6559f1993a7388fa690c71476921e87c8dc` | `8d0c1f77dbddc316b21d1fac2105cd13f08c1d6a` |
| Runtime base | same as package source | `55f1fb76e37d1bfb7f86524be297647d9267c4cb` |

The final prplMesh archive was repacked after the successful run to identify
the complete importer-fix revision. Its inner VM payload did not change; the
inner-image hash above is the payload used for the test.

## Bring-up timing

| Measurement | RDK EasyMesh | prplMesh | Difference |
| --- | ---: | ---: | ---: |
| Archive import and VM creation | 4 min 11.406 s | 6 min 49.159 s | RDK 2 min 37.753 s faster |
| Import return to accepted state | 17 min 34.820 s | 13 min 27.251 s | prplMesh 4 min 07.569 s faster |
| Recorded guest first boot | 16 min 49 s | 12 min 58 s | prplMesh 3 min 51 s faster |
| Import start to accepted state | **21 min 46.226 s** | **20 min 16.410 s** | prplMesh 1 min 29.816 s faster |
| Controlled shutdown | 22.933 s | 29.569 s | RDK 6.636 s faster |

Both guests finished with 25 of 25 nested containers running. The RDK
first-boot report recorded zero initial and 25 final instances. Its runtime
then consumed the one-use thin-provisioning handoff in 318 ms instead of
performing a second reconstruction. prplMesh recorded one continuous staged
transaction:

| prplMesh phase | Elapsed |
| --- | ---: |
| Define the thin inventory | 3 min 32.766 s |
| Start and converge mesh | 6 min 54.240 s |
| Start clients | 22.747 s |
| Start wmediumd Console | 0.605 s |
| Start topology adapter | 1.799 s |
| Acceptance suite | 2 min 05.803 s |
| Finalize | 0.224 s |

The current RDK timing record exposes total first-boot time and the final
handoff but not equivalent internal provisioning phases. Adding matching RDK
phase boundaries is required before attributing its additional 231 seconds.

## Functional acceptance

Both results are accepted runs, not merely `RUNNING` container counts.

### RDK EasyMesh

- 25/25 nested containers running;
- five active mesh nodes, 15 radios, 50 BSS records, and 24 association
  records in the controller model;
- 20 live clients with unique controller ownership and expected IPv4
  addresses;
- 20/20 clients reaching the controller over the data plane;
- fresh backhaul signal for all four extenders;
- valid preserved NVRAM identity for every mesh node; and
- zero OneWifi, agent, controller, or CLI service restarts.

### prplMesh

- 25/25 nested containers running;
- one controller, four agents, and 20 clients in an accepted star topology;
- ten `private_ssid` and ten `iot_ssid` clients;
- four clients on 2.4 GHz, ten on 5 GHz, and six on 6 GHz;
- representative private/5 GHz and IoT/6 GHz BTM steering passing with
  physical association, NBAPI ownership, and BTM response in agreement;
- 20/20 clients reaching the controller over the data plane; and
- process-cardinality, runtime-footprint, provenance, Console, and Controller
  UI gates passing.

No packet capture was needed for the accepted runs because the topology,
steering, telemetry, and traffic gates did not disagree. A capture should be
triggered when one of those gates fails or when a timing outlier needs protocol
attribution; capturing every successful run would add evidence volume without
answering a current failure question.

## Process memory at accepted state

PSS is used for application attribution because it apportions shared pages.
RSS is retained for operational familiarity but double-counts shared pages
when summed. Values below were collected from every relevant process in every
nested container plus the guest-host wmediumd, Console, topology adapter, and
UI processes.

| Measurement | RDK EasyMesh | prplMesh |
| --- | ---: | ---: |
| Classified processes | 43 | 46 |
| Total PSS | **525.34 MiB** | **243.99 MiB** |
| Total private memory | 502.39 MiB | 201.40 MiB |
| Summed RSS | 636.55 MiB | 409.69 MiB |
| Threads | 205 | 77 |
| File descriptors | 617 | 987 |
| Guest available memory | 5.54 GiB | 5.13 GiB |
| Outer QEMU PSS | 5.83 GiB | 8.04 GiB |

The principal classified PSS groups were:

| Process group | RDK EasyMesh | prplMesh |
| --- | ---: | ---: |
| Mesh agent processes | 145.48 MiB | 46.97 MiB |
| Mesh controller | 34.97 MiB | 24.43 MiB |
| CLI/WebUI | 83.77 MiB | 7.27 MiB controller UI + 21.38 MiB adapter |
| Wi-Fi manager/AP daemon | 117.76 MiB OneWifi | 15.60 MiB hostapd |
| Supplicants | 58.91 MiB | 102.44 MiB |
| IEEE 1905 | 27.92 MiB | 11.79 MiB |
| Database | 43.03 MiB | no separate database process |
| wmediumd | 1.21 MiB | 2.02 MiB |
| wmediumd Console | 12.29 MiB | 12.09 MiB |

This table explains which components merit investigation; it is not a direct
component equivalence. RDK projects three logical EasyMesh radios from one
hwsim wiphy per BPI, while prplMesh uses distinct per-band wiphys and a
different hostapd/supplicant process model. See
[Single-wiphy radio model](../reference/single-wiphy-radio-model.md).

## Early steady-state CPU sample

The second snapshot was collected 60.830 s after the RDK snapshot and 81.642 s
after the prplMesh snapshot. CPU is reported as average use of one logical CPU
during that interval.

| Measurement | RDK EasyMesh | prplMesh |
| --- | ---: | ---: |
| All classified processes | 17.0% | 26.3% |
| As share of six-vCPU guest capacity | 2.8% | 4.4% |
| wmediumd | 10.0% | 13.6% |
| OneWifi or hostapd | 4.2% | 9.1% |
| Mesh agents | 0.7% | 2.1% |
| PSS change during interval | -6.15 MiB | +0.24 MiB |

This short, early-life sample is suitable for detecting gross load and process
growth. It is not an idle-power benchmark and should not be extrapolated to a
long soak or a traffic-loaded profile.

## Appliance defects found during the comparison

The first three prplMesh import attempts exposed portable-appliance wrapper
defects. They did not reach prplMesh protocol testing:

1. The importer tried to override proxy devices that the trimmed backup did
   not contain. Import now tolerates absent packaged proxies.
2. LXD assigned a different guest management address while proxies retained
   the image's old address. Import now discovers the running appliance address
   and targets the proxies at it.
3. The LXD agent became reachable before the guest had installed its default
   route. Import now waits a bounded 120 seconds for management routing.

The corrected import completed unattended with both external HTTP endpoints
returning 200. Regression coverage exercises absent proxy devices, a changed
address, and delayed route availability. The failed attempts are retained
separately from the accepted evidence and are not included in timing or
resource results.

## Interpretation and next measurements

The strongest conclusions from this run are operational:

- both thin appliances are independently reconstructible and reach substantive
  protocol and traffic acceptance;
- RDK's former duplicate post-provisioning reconstruction is absent;
- prplMesh spends longer importing but less time in guest provisioning;
- RDK has materially higher classified application PSS;
- prplMesh has higher outer VM residency and higher early CPU load; and
- the packages and collectors are now suitable for repeated controlled trials.

A decision-grade performance comparison should run at least five cold trials
per stack, randomize their order, record median and spread, and add controlled
idle and traffic-loaded windows. It should also add matching phase timing to
RDK and outer-LXD cgroup accounting to both collectors. The 50- and 100-client
profiles should use the same method only after the 20-client repetition is
stable; scale results must not be mixed with different hosts or simultaneous
VM contention.

## Evidence and collection

Raw evidence is retained on rev140 under:

```text
/home/rev/easymesh-comparison/0903/
  host-baseline.txt
  rdk/
  prpl/
  prpl-import-failure/
  prpl-proxy-failure/
  prpl-network-wait-failure/
```

The common schema-v1 collector is available in both repositories:

```text
RDK:  gen/tests/lab-performance-snapshot.py
prpl: tests/lab-performance-snapshot.py
```

Example from inside either appliance VM:

```sh
sudo ./gen/tests/lab-performance-snapshot.py \
  --stack rdk --profile 20 --label ready --output /tmp/ready.json

sudo ./tests/lab-performance-snapshot.py \
  --stack prplmesh --profile 20 --label ready --output /tmp/ready.json
```

The two collector files are byte-identical. They record host memory, nested
LXD state, normalized first-boot and lifecycle timing, per-process and grouped
PSS/RSS/private/swap values, threads, file descriptors, and cumulative CPU
seconds. A later snapshot provides a bounded CPU and memory delta.
