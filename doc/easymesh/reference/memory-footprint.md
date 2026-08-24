# bpibroadband memory-footprint assessment

## Purpose and conclusion

This assessment establishes the current memory cost of the RDK-B EasyMesh
controller image while a complete virtual lab is reconstructed. It measures the
whole `bpibroadband` container and attributes the userspace footprint to the
EasyMesh, Wi-Fi and supporting RDK-B processes.

The measured five-agent, ten-client lab was comfortably bounded by its 1 GiB
LXD limit. The routine small profile has since grown to 20 clients, so the
numbers below remain the accepted cold-bring-up baseline rather than a
20-client capacity measurement:

| Measurement | Result |
| --- | ---: |
| cgroup peak, including userspace and charged kernel memory | 311.57 MiB |
| highest sampled cgroup working set | 306.00 MiB |
| converged cgroup working set | 266.10 MiB |
| highest sampled sum of process PSS | 326.57 MiB |
| converged sum of process PSS | 281.95 MiB |
| swap used | 0 |
| cgroup pressure, limit or OOM events | 0 |

The structural footprint reductions proposed below remain design proposals;
their savings are projections rather than measured results. Correctness fixes
for retained periodic telemetry state are now implemented separately. They
remove unbounded growth without changing the intended steady-state model.

Cold bring-up creates a temporary controller allocation pulse while agent,
radio and BSS records are configured. The pulse is released after convergence.
This run found no retained bring-up growth. It is not, however, a substitute
for the deliberately deferred 12-hour stability acceptance.

The current image includes the SNMP self-heal process-detection fix and must
retain exactly one `snmp_subagent` during memory testing. It also includes the
four ownership fixes described under [retained-growth diagnosis](#retained-growth-diagnosis-and-fix).

## Retained-growth diagnosis and fix

A later five-agent, 20-client run exposed genuine growth that the original
15-minute cold profile was too short to reveal. After several days,
`OneWifi` reached approximately 403 MiB PSS and an extender `em_agent` reached
approximately 293 MiB PSS. Log files, the bounded journal, persistent maps,
command queues, topology cardinality and `/nvram` growth were ruled out.

Allocator inspection established that the agent was retaining about 434 KiB
of live allocations in 53 seconds during periodic AP-metrics processing. The
growth was in the main malloc arena, while its persistent station, scan,
command and executor maps remained bounded. Source and ownership tracing then
identified four independent leaks:

| Component | Retained object | Fix |
| --- | --- | --- |
| OneWifi EasyMesh publishers | the separately allocated `webconfig_encode()` result, plus removed client-stat entries | release encoded data through `webconfig_data_free()` on success and error paths and free removed entries |
| EasyMesh agent | decoded station/scan objects and temporary command data models | give `dm_easy_mesh_t::deinit()` complete ownership cleanup, deep-copy cloned station objects and release temporary decoder models |
| libwebconfig AP-metrics decoder | the parsed cJSON tree on every successful periodic report | transfer the tree to a local owner and call `cJSON_Delete()` on every exit path |
| libwebconfig AP-metrics decoder | temporary per-BSS station-traffic and station-link arrays left after translation | release all decoded report arrays at the translation ownership boundary and on partial-decode failure |

The corrected controller and extender images were rebuilt together and
deployed fresh on rev130 with four extenders and the routine 10-private plus
10-IoT client profile. Mesh onboarding converged without service restarts. An
external 25-minute diagnostic wrapper interrupted the resumable scale helper
while it was creating client 20; running the same helper without that wrapper
completed immediately to `5/15/50/24`. All service restart counters remained
zero, all 20 WLAN data paths passed, and the wmediumd Console reported healthy
bounded telemetry with all 25 radios identified.

The post-fix samples below begin after full client convergence. `em_agent`
PSS is shown in KiB. Before the final decoder-array fix, a residual slope of
about 1.4 MiB/hour remained after the much larger command-model leak was
removed. The final acceptance window crosses repeated AP-metrics reports and
is compared with both diagnosed slopes.

| Node | Start | 14m38s | Change |
| --- | ---: | ---: | ---: |
| colocated agent | 29,541 | 29,540 | -1 |
| extender 1 | 30,209 | 30,203 | -6 |
| extender 2 | 30,318 | 30,318 | 0 |
| extender 3 | 30,184 | 30,164 | -20 |
| extender 4 | 30,127 | 30,131 | +4 |

Controller `OneWifi` PSS increased from 22,816 to 24,938 KiB during this
fresh-image window, but detailed mapping evidence distinguishes that from the
fixed heap leak. Its `[heap]` mapping remained 924 KiB; VM size, data size,
thread count and file-descriptor count remained bounded. The newly resident
pages were in an existing 24,948 KiB anonymous executable/BSS mapping. The
largest symbol in that mapping is the fixed `client_assoc_stats` array at
about 13.6 MiB, followed by fixed Wi-Fi manager, webconfig, VAP and
interworking state. Periodic client processing first-touches these reserved
pages. This is bounded footprint/high-water behavior and remains a candidate
for structural footprint reduction, not an unbounded ownership leak.

This result demonstrates removal of the previously measured linear agent leak
over a bounded post-convergence interval: the largest absolute endpoint change
was 20 KiB. It also separates fixed `OneWifi` first-touch behavior from heap
growth. It is not a replacement for the deferred long-duration acceptance run.
Acceptance is based on loss of the sustained station-count-proportional heap
slope, not on demanding byte-for-byte PSS constancy.

## Measured configuration

The available baseline was measured on rev130 during one controlled cold
reconstruction and sampled through final convergence.

```text
container             bpibroadband
container memory      1024 MiB, no swap
container CPUs        2
RDK-B userspace       x86/core2-32 evaluation build
host kernel           Linux 7.0.0-28
final model           5 devices / 15 radios / 50 BSS / 14 associated STAs
physical WLAN clients 10
sample duration       901.834 seconds
samples               129
sampling target       nominally every 5 seconds
```

The 14 associated STA model records comprise ten WLAN clients plus four
wireless-backhaul STA interfaces. They do not mean that 14 client containers
were running.

The instrumented cold reconstruction completed in 823 seconds. The profiler's
repeated `/proc/*/smaps_rollup`, model, and storage probes add measurement cost.

Evidence is retained on rev130 at:

```text
/home/rev/easymesh-lab/0824-clean/evidence/memory-footprint/
/home/rev/easymesh-lab/0824-clean/evidence/memory-footprint/20260825-postfix/
```

The profiler is [bpibroadband-memory-profile.py](../../../gen/tests/bpibroadband-memory-profile.py).
It is read-only and runs on the LXD host.

## Whole-container behavior

| Point | Process PSS | Summed process RSS | LXD cgroup |
| --- | ---: | ---: | ---: |
| initial complete lab | 288.34 MiB | 520.57 MiB | 270.81 MiB |
| maximum sampled process PSS | 326.57 MiB | not used as a total | 304.04 MiB |
| maximum sampled cgroup | 322.97 MiB | not used as a total | 306.00 MiB |
| final complete lab | 281.95 MiB | 499.28 MiB | 266.10 MiB |

Summed RSS double-counts shared mappings and is included only to explain why
ordinary `ps` output appears much larger. PSS apportions shared mappings and is
the useful process-attribution measure. The cgroup value is the authoritative
memory charged to the container. The two need not match exactly because file
pages may be charged to one cgroup while PSS is apportioned among every process
mapping them.

The maximum sampled PSS occurred with two extenders configured and 35 BSS
records. The maximum sampled cgroup value followed with three extenders and 38
BSS records. The cgroup's `memory.peak`, which catches changes between samples,
was 311.57 MiB. All `memory.events` counters remained zero:

```text
low 0  high 0  max 0  oom 0  oom_kill 0  oom_group_kill 0
```

At convergence the cgroup contained approximately 219.0 MiB anonymous memory,
25.5 MiB file-backed memory and 20.5 MiB kernel memory. Shared-memory and other
`memory.stat` fields overlap these categories and must not be added again.

## Process attribution

The following table is the final complete-lab state. PSS is the primary value;
RSS is shown for comparison.

| Process or service | PSS MiB | RSS MiB | Role |
| --- | ---: | ---: | --- |
| `em_cli` | 81.03 | 87.72 | Go/cgo WebUI and native CLI bridge |
| MariaDB | 42.48 | - | persistent EasyMesh model |
| `em_agent` | 28.75 | - | colocated EasyMesh agent |
| `em_ctrl` | 22.92 | 30.05 | EasyMesh controller |
| OneWifi | 15.90 | - | radio, BSS and client management |
| `CcspPandMSsp` | 9.76 | - | RDK-B data-model support |
| systemd-journald | 5.76 | - | bounded volatile journal |
| `gwprovapp` | 5.65 | - | gateway provisioning support |
| IEEE1905 agent | 3.57 | - | agent 1905 transport/topology |
| IEEE1905 controller | 3.45 | - | controller 1905 transport/topology |
| all remaining RDK-B/OS processes | 62.68 | - | platform services |
| **all userspace processes** | **281.95** | **499.28** | |

The directly involved Wi-Fi/EasyMesh processes are OneWifi, `em_ctrl`,
`em_agent`, `em_cli`, and both IEEE1905 processes. Their aggregate behavior was:

| Point | Wi-Fi/EasyMesh | MariaDB | Other RDK-B/OS |
| --- | ---: | ---: | ---: |
| initial | 158.17 MiB (54.9%) | 42.19 MiB (14.6%) | 87.98 MiB (30.5%) |
| sampled PSS peak | 198.59 MiB (60.8%) | 42.38 MiB (13.0%) | 85.60 MiB (26.2%) |
| final | 155.62 MiB (55.2%) | 42.48 MiB (15.1%) | 83.85 MiB (29.7%) |

The direct Wi-Fi/EasyMesh processes plus their MariaDB model therefore account
for 198.10 MiB, or 70.3% of converged process PSS.

## Bring-up allocation behavior

The largest bring-up change was in `em_ctrl`:

| State | `em_ctrl` PSS | anonymous PSS | virtual size |
| --- | ---: | ---: | ---: |
| final | 22.92 MiB | 20.74 MiB | 219.39 MiB |
| sampled peak | 67.79 MiB | 65.58 MiB | 323.74 MiB |

The peak is almost entirely anonymous/private-dirty memory. It correlates with
agent and BSS configuration and returns to the original range. Client
onboarding is a much smaller contributor than extender/radio/BSS creation.

`em_cli` is the largest steady process. Its PSS ranged from approximately 74.9
to 81.0 MiB in the accepted profile and instant snapshots. A detailed
`memdetail.sh` snapshot attributed 68.5 MiB of its 74.9 MiB PSS to anonymous
memory and 6.4 MiB to file-backed mappings.

Binary and object-file inspection identified the principal cause. The native
CLI declares this static table:

```cpp
em_cmd_t em_cmd_cli_t::m_client_cmd_spec[] = {
    // 31 command entries
};
```

Each `em_cmd_t` embeds a complete `dm_easy_mesh_t`, including its fixed-capacity
device, radio, BSS, STA and policy collections. The table therefore reserves a
complete maximum-sized mesh data model for every command descriptor, even
though the descriptors primarily need a command type, name and parameters.

| Binary observation | Size |
| --- | ---: |
| `em_cmd_cli_t::m_client_cmd_spec` | 76,138,976 bytes (72.61 MiB) |
| one `em_cmd_t` table element | 2,456,096 bytes (2.34 MiB) |
| executable `.bss` | 76,196,996 bytes (72.67 MiB) |
| executable `.noptrbss` | 33,690,560 bytes (32.13 MiB) |
| executable total BSS reported by `size` | 109,887,560 bytes (104.80 MiB) |

The command table accounts for almost the entire ordinary `.bss` section. A
separate minimal Go 386 probe using the comparable standard-library runtime had
approximately the same 32.13 MiB `.noptrbss`, but only about 53 KiB of ordinary
`.bss`. This distinguishes the Go runtime's large virtual reservation from the
additional application-owned command table. BSS and virtual-size figures must
not be reported as physical savings; the projected PSS reduction below is
bounded using the pages observed resident in the running process.

The table remained bounded in the 3,000/6,000-request stress tests
documented in [patch-set.md](patch-set.md). It is a large fixed baseline rather
than evidence of continuing request-by-request growth.

## Projected memory-reduction patches

The following patches are candidates for future implementation and individual
measurement. None is present in the current images. Ranges account for
allocator behavior, shared pages and pages reserved virtually but not resident.

| Priority | Proposed patch | Measured starting point | Projected PSS reduction | Confidence and risk |
| --- | --- | ---: | ---: | --- |
| P1 | Replace the 31 full `em_cmd_t` entries with immutable lightweight descriptors and construct or reuse one full command for the serialized request | `em_cli` 74.9-81.0 MiB PSS; table 72.61 MiB static | **58-65 MiB** | High-confidence cause; low-to-medium implementation risk |
| P2 | Add an embedded/lab MariaDB profile with smaller buffer pool, connection, table and per-thread caches, disabling unused instrumentation only after verification | MariaDB approximately 42.4 MiB PSS for 55.6 KiB of logical EasyMesh tables and indexes | **10-20 MiB** | Medium confidence; low risk when changed one setting group at a time |
| P3 | Replace selected fixed-capacity `dm_easy_mesh_t` collections in `em_ctrl` and `em_agent` with topology-sized storage | controller plus agent approximately 51-53 MiB steady PSS; controller also has a released bring-up pulse | **5-15 MiB combined** | Preliminary estimate; medium-to-high protocol and lifetime risk |
| P4 | Split the Go WebUI service from the native CLI bridge and make the on-device WebUI optional | residual CLI/WebUI cost expected after P1 | **8-15 MiB when the WebUI is disabled** | Conditional and partly overlaps the CLI footprint; medium architectural risk |
| P5 | Remove or conditionally build unused OneWifi evaluation features and buffers | OneWifi approximately 16 MiB PSS | **2-5 MiB** | Low confidence until feature-level attribution; medium regression risk |

### P1: lightweight command descriptors

P1 has the best return and the clearest root cause. The static array should
contain only immutable lookup data, conceptually:

```cpp
struct em_cmd_descriptor_t {
    em_cmd_type_t type;
    const char *name;
    em_cmd_params_t params;
};
```

The execution path would create one owned `em_cmd_t`, or reuse one scratch
instance, after selecting the descriptor. Retaining one complete command would
reduce static virtual storage by about 70.27 MiB compared with retaining all 31.
The projected physical reduction is deliberately lower, 58-65 MiB, based on
the resident anonymous mapping and process PSS. Existing `emExecMutex`
serialization must remain in force; returning a mutable reference to a shared
command outside that critical section would introduce races.

The expected steady `em_cli` PSS after P1 is approximately 10-17 MiB. That is a
forecast, not an acceptance limit. Validation must exercise every CLI command,
the WebUI topology and client APIs, policy configuration, steering, concurrent
HTTP requests, and the existing repeated-request memory tests.

Moving the Go `main` package to a source directory without adjacent C++ files
is useful packaging cleanup, but is not an independent 72 MiB saving:
`libemcli` contains the same command-table definition. The data structure must
be fixed at its owner to remove the resident baseline.

### P2-P5: follow-on work

MariaDB is the next isolated target. Its approximately 42.4 MiB PSS is large
relative to the stored model, but the 10-20 MiB range must be established by a
configuration matrix covering cold reconstruction, concurrent reads, topology
persistence and restart recovery. Replacing MariaDB with another database is
not justified before this lower-risk tuning is measured.

Dynamic controller/agent model storage can reduce the steady footprint and
perhaps the controller's temporary bring-up pulse, but it changes ownership,
pointer lifetime and protocol-processing paths. It should follow P1 and P2 and
be divided into separately reviewable collection conversions.

The optional external WebUI and OneWifi reductions are deployment choices,
not prerequisites for the lab. P4 must not be added to P1 as though the two
estimates were fully independent, and P5 needs symbol, heap and feature-level
evidence before a patch is proposed.

P1 and conservative P2 tuning together project a **68-85 MiB** reduction on
`bpibroadband`. Adding P3 could raise the projected reduction to approximately
**75-100 MiB**. These totals exclude P4 and P5 to avoid overlap and unsupported
addition. They must remain labelled projected until rebuilt images reproduce
the functional acceptance suite and new PSS/cgroup profiles quantify the
result.

## Persistent and volatile storage

| Area | Observed result | Interpretation |
| --- | ---: | --- |
| `/var/lib/mysql` | 3.40 MiB | stable through reconstruction |
| logical `OneWifiMesh` tables and indexes | 55.6 KiB | 5/15/50/14 model is small |
| `/nvram` | 1.26 MiB | stable; includes configuration and packaged WebUI assets |
| `/rdklogs` | 0.18-2.25 MiB | volatile tmpfs files rotate during bring-up |
| `/tmp` | 1.48-1.58 MiB | volatile helper/UI files |
| system journal | grows to and holds at 20 MiB | bounded by the journald configuration fix |

The largest `/nvram` objects are immutable WebUI/static schema assets rather
than changing EasyMesh state. A production image can move immutable assets to
the read-only root filesystem and reserve persistent storage for configuration.

`/rdklogs`, `/tmp` and the journal are volatile in this lab. They consume memory
or page cache while resident, not persistent flash. During the measured boot,
the journal grew from 4 MiB to its configured 20 MiB ceiling and then held. The
largest current-boot EasyMesh journal contributors were approximately 802 KiB
from `em_ctrl`, 257 KiB from `em_agent`, and 36 KiB from `em_cli`.

## Embedded-device interpretation

This experiment is evidence for the evaluation software stack, not a final
Banana Pi production-memory specification:

- the RDK-B userspace is a core2-32 image running in LXD on an x86 host;
- a physical target has different kernel drivers, hardware services, shared
  libraries, allocator behavior and reserved memory;
- the virtual WebUI is colocated with the controller and is the largest steady
  userspace process;
- the measured ten-client/four-extender topology is smaller than the current
  20-client routine profile and the intended 50/100-client scale envelope;
- 15 minutes covers cold reconstruction and convergence, not long-term leak
  behavior.

Within those boundaries, a 512 MiB application budget appears feasible for the
measured topology: the observed cgroup peak is 311.57 MiB, leaving about 200 MiB
before a 512 MiB limit. That is a preliminary engineering margin, not a product
recommendation. A final memory SKU decision needs the same profile on physical
target hardware, at maximum supported agent/client scale, with production log
retention and failure recovery active.

## Recommended follow-up

1. Repeat the profile on the physical MediaTek Banana Pi build and compare each
   major process rather than only the total.
2. Add a 512 MiB LXD acceptance run after the functional P0 work is stable;
   require zero pressure/OOM events and preserve recovery margin.
3. Measure maximum supported agent, BSS and client scale and derive marginal
   MiB per agent, radio, BSS and client.
4. Prototype P1 alone on a review branch, rebuild both relevant packages, and
   compare steady and repeated-request PSS before considering the other
   reduction candidates.
5. Test MariaDB tuning as a configuration matrix and retain only settings that
   pass cold reconstruction, persistence and restart recovery.
6. Use Go heap/runtime metrics after P1 to attribute the smaller residual
   `em_cli` footprint rather than treating virtual BSS as resident memory.
7. Move immutable WebUI assets out of `/nvram` in the production filesystem
   layout.
8. Extend the accepted two-interval SNMP check with an explicit forced recovery
   and verify that it still leaves exactly one daemon and no wrapper.
9. When the duration run is authorized, complete the defined 12-hour
   churn/steady-state test and compare start, post-churn and final PSS by
   service; do not report a growth result before the final summaries are
   written.

## Reproducing the profile

Start the profiler on the LXD host, then run a cold reconstruction in another
terminal. Use a timestamped result directory outside the source tree for
long-term evidence.

```sh
cd /home/rev/easymesh-lab/0824-clean/meta-cmf-bananapi-vcpe

./gen/tests/bpibroadband-memory-profile.py \
  --duration 900 \
  --interval 5 \
  --storage-interval 120 \
  --output-root tmp/test-results/bpibroadband-memory
```

```sh
cd /home/rev/easymesh-lab/0824-clean/meta-cmf-bananapi-vcpe
./gen/tests/p0-cold-reconstruction.sh
```

Preserve `samples.jsonl` and `summary.json`. Report cgroup memory as the
container total, PSS for process attribution, and RSS only as a per-process
diagnostic. Never add RSS across the process table as a memory budget.
