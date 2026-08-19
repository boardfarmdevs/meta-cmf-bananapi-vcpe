# 0815-codex patch set

## Purpose

0815-codex is an independent reconstruction of the container/hwsim EasyMesh
layer. It starts at `6d87e23`, the last commit before the first EasyMesh change,
and reorganizes the work into reviewable ownership boundaries.

0814 remains comparison material only. A patch is retained when it is required
for x86/LXD/hwsim operation or fixes a demonstrated product defect. A patch is
removed when it merely forces state, duplicates another component's fix, or
was an exploratory hypothesis superseded by root-cause evidence.

## Reconstruction history

| Commit | Responsibility |
| --- | --- |
| `24a95d9` | x86 controller/extender machines and LXC images |
| `112a73f` | HAL/libhostap correctness and single-phy hwsim adaptation |
| `6fe294f` | OneWifi hwsim configuration and client export |
| `dd0a091` | 1905 and EasyMesh onboarding/topology/steering fixes |
| `bc6a98a` | hwsim, wmediumd, deployment and client tooling |
| `d4dca04` | ordered EasyMesh series and orchestrator root fix |
| `56cf4a4` | deployment lock ownership fix |
| `ae65be4` | shared wmediumd state outside sticky `/tmp` |
| `95d4990` | wmediumd replacement across tooling checkouts |
| `d22b076` | client creation gated on controller export |
| `73e7c1e` | full bounded model-reconciliation interval |
| `6f30c90` | replacement of legacy pre-control-socket lab daemons |
| `fdf7d13` | portable steering and health acceptance harness |
| `0088993` | heap-size AP Metrics Response construction from model scale |
| `796cd5e` | make WLAN-client cold-boot order runtime-owned |
| `ca17171` | preserve length-delimited AL-SAP messages over stream sockets |

The current engineering images contain the ordered EasyMesh series through
`0046`, defined by repository commit `ca17171`. The Dropbox-packaged 0818
appliance remains an older, separately accepted distribution until its binary
artifacts are deliberately rolled forward.

## Patch boundaries

### Generic product fixes

These are not hwsim policy and are candidates for their owning upstreams:

- correct nl80211 ACL attribute encoding;
- guard uninitialized supplicant/MLO objects and validate MLO link IDs;
- select the interface BSSID for management frames;
- prevent reflected kernel DEL_STATION events;
- create WDS state after authorization rather than before the four-way
  handshake;
- map WPA2-Personal to WPA2-PSK and apply coherent AES/PMF security;
- write the decrypted final AES block into the caller buffer;
- bound BTM action-frame allocation;
- serialize steering from the command parameters and use the source VAP;
- restore steering state and route ACK/BTM reports to the right transaction;
- refresh registrar crypto for every M1;
- publish association changes, including returning clients;
- enforce one current association in the controller model;
- size association-frame SQL encoding for maximum input; and
- complete cancelled orchestrator commands independently; and
- size AP Metrics Responses for the reporting model instead of a 1024-byte
  stack-buffer assumption;
- release CLI response trees, temporary C strings and JSON print buffers at
  their native ownership boundaries;
- drain MariaDB result sets before successful early returns; and
- rebuild the nested topology snapshot after association capability handling
  and before publishing it; and
- preserve every length-delimited AL-SAP SDU when a stream read fragments or
  coalesces messages.

### hwsim and single-phy adaptations

These must remain gated from a physical MediaTek build:

- discover radios/interfaces without physical-platform phy-index assumptions;
- suppress unsupported ACL and management subscriptions by capability;
- project one wiphy into three logical radios;
- use concurrent 20 MHz 2.4/5/6 GHz contexts;
- establish the Linux 7.0 strict 6 GHz regulatory environment;
- avoid assuming an operational MLD when hwsim is non-MLO; and
- register and isolate simultaneous frequencies with wmediumd.

### Container integration

These replace facilities normally supplied by a complete device image:

- x86 machine definitions and LXC rootfs images;
- persistent `/nvram` identity ownership;
- idempotent MariaDB initialization;
- explicit 1905, backhaul and LAN readiness gates;
- Linux bridge operation when OVS userspace is absent;
- controller WebUI and `steer.sh` packaging;
- Boardfarm WAN/DHCP integration; and
- bounded deployment/model convergence rather than restart-based recovery.

## Component ownership

The bbappends are the executable patch inventory. Review these rather than
copying a list from documentation:

| Component | Ordering authority | Main responsibility |
| --- | --- | --- |
| Wi-Fi HAL | `recipes-ccsp/hal/rdk-wifi-hal.bbappend` | nl80211, VAP/interface mapping, WDS, management frames |
| hostap integration | `recipes-ccsp/rdk-wifi-libhostap/rdk-wifi-libhostap_2.11.bbappend` | embedded AP/STA state-machine safety |
| OneWifi | `recipes-ccsp/ccsp/ccsp-one-wifi.bbappend` | hwsim defaults, tri-band configuration, association deltas |
| libwebconfig | `recipes-ccsp/ccsp/ccsp-one-wifi-libwebconfig.bbappend` | EasyMesh/OneWifi translation and client snapshots |
| EasyMesh core | `recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh.bbappend` | onboarding, model, steering, crypto, CLI |
| 1905 | `recipes-ccsp/ieee1905/ieee1905-em.bbappend` | build/startup and AL-SAP transport integration |

Patch headers contain the failure trace, packet/log evidence and ownership
rationale. Patch number gaps intentionally preserve comparison with 0814.

## EasyMesh core ordering

`EASYMESH_CORE_PATCHES` in the unified-wifi-mesh bbappend is the sole ordering
authority. Its dependency order is:

1. cross-build and WSC mapping;
2. disabled-radio and crypto/memory correctness;
3. steering serialization and tests;
4. steering state, source VAP and ACK/report flow;
5. CLI and model reconciliation;
6. startup and disabled-radio lifecycle;
7. bounded WSC M1 recovery;
8. topology leader, registrar and association notification fixes; and
9. generic command cancellation/completion; and
10. scale-safe AP Metrics Response construction;
11. browser-only topology layout and JSON/SVG/PNG export;
12. CLI native-allocation ownership;
13. MariaDB result-set lifetime; and
14. association-to-topology publication ordering;
15. reassociation capability decoding and preservation;
16. serialized CLI native-command lifetime and removal of its unused command
    data model; and
17. controller JSON ownership;
18. live device and client inventory; and
19. two-second change-aware topology refresh for RF and steering experiments;
20. complete metrics policy activation, Profile-3 validation and STA/BSS/radio
    report persistence; and
21. serialize WebUI policy changes across the controller's one-device policy
    state machine; and
22. join detailed live STA metrics to the client inventory and refresh the
    Connected Clients signal presentation every two seconds; and
23. overlay topology station ownership from that same authoritative live
    inventory instead of a second, lossy native-tree traversal; and
24. consume exactly one length-delimited AL-SAP SDU at a time, leaving any
    coalesced successor queued for the next dispatch.

The complete ordered series was replayed against pristine pinned source before
the Yocto image build.

## hwsim and wmediumd series

Kernel-side hwsim patches:

| Patch | Reason |
| --- | --- |
| `0001-mac80211_hwsim-allow-multichannel-wmediumd.patch` | allow wmediumd registration with multiple channel contexts |
| `0002-mac80211_hwsim-6ghz-strict-regd.patch` | backport strict `custom_03` behavior when building an older kernel generation; Linux 7 selects it natively with `regtest=5` |

wmediumd patches, in order:

| Patch | Reason |
| --- | --- |
| `0001` | isolate interference by active frequency |
| `0002` | deliver through the learned VIF owner |
| `0003` | remove per-frame ACK file logging |
| `0004` | schedule frequency contexts independently |
| `0005` | map Linux 7 rate flags correctly |
| `0006` | filter multicast by frequency |
| `0007` | enlarge the netlink receive buffer |
| `0008` | add the atomic scenario-control socket |
| `0009` | honor configured default SNR |
| `0010` | require current transmit-learned frequency evidence before cloning to a receiver |
| `0011` | classify tracked clones rejected during transient receive states without hiding other netlink faults |

`gen/wmediumd/build-wmediumd.sh` applies this series to pinned upstream source;
`wmediumd-up.sh` runs its nine-test internal acceptance suite before launch.

## Deliberate differences from 0814

| 0814 behavior | 0815 decision |
| --- | --- |
| disable ieee80211h to address START_AP | removed; malformed ACL encoding was the decoded root cause |
| duplicate OneWifi cipher/PMF patch | removed; libwebconfig is the effective implementation owner |
| forced controller transition out of `wsc_m2_sent` | removed; it could fire after valid M2 and hid command cancellation deadlock |
| forced `wsc_m1_pending` recovery | not imported; previous capability is not proof of current configuration |
| passive returning-client cache update | replaced by refresh, insertion verification and explicit delta publication |
| one historical wmediumd patch | replaced by the tested eleven-patch multichannel/control protocol series |

The replacement for forced WSC state is EasyMesh patch `0026`: cancelled
commands become terminal, and completion is evaluated per command. Duplicate M1
can therefore cancel obsolete work without leaving the radio permanently busy.

## Build and acceptance

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller | `X86EMLTRBPIBB_rdk-next_20260819032857.rootfs.lxc.tar.bz2` | `e5314430402513823c86c3a29823b4d2fbc9e826f381d0bb9c342364f52b8a9f` |
| extender | `X86EMLTRBPIAP_rdk-next_20260819032857.rootfs.lxc.tar.bz2` | `716ef80633e4b3097f2e77e885b828f195778d457d15090db7d00dc62ddc2449` |

All five images contain the same `onewifi_em_agent` binary
(`3128ed3c2d25bfaf1af6835fd551aa634ed273d3fb0aa8c6872e6627f01f3dd9`).
The earlier deterministic fourth-extender/four-associated-STA stack-protector
failure remained absent through clean deployment and cold-boot reconstruction.

Both rev130 and the rev150 VM reached `5/15/50`, exposed ten live clients in
the topology and
recorded zero service restarts. The VM reconstructed all four extenders and ten
clients after a forced-power-off boot, held the complete state for 120 seconds,
and recorded its model, topology, restart counts, traffic and journal under the
boot-ID acceptance directory. Earlier accepted runs passed 10/10 commanded
steering and a 30/30 extended steering matrix.

Post-image diagnosis added source fixes that were rebuilt and exercised as
targeted runtime binaries before the next full image roll-up:

| Fix | Runtime artifact | SHA-256 |
| --- | --- | --- |
| CLI C/C++ ownership (`0029`) | `onewifi_em_cli` | `54f92b0c41bb798da3cdf6b99d095665299803c57c91a8dead13f9e067e75628` |
| DB result lifetime (`0030`) and topology publish (`0031`) | `onewifi_em_ctrl` | `d2dd39e03c9b4d39b16019898aa0391f4c4a16b2dba280d52d66204e244134fc` |
| DB result lifetime (`0030`) | `onewifi_em_agent` | `9214a28e9222b93060d54f287f26996ae8db0456d582f6632ebab7cf4755a0ab` |
| serialized HTTP/native command bridge (`0034`) | `onewifi_em_cli` | `d5f8e97a24679eadbe01e40a0d89ac7a109528a1114bacd6b722a8c71f637a02` |
| remove unused CLI command data model (`0035`) | `libemcli.so.0.0.0` | `e4cc60152c490f9f3ca0fbfdb9eaecb7b30258bbcddf02c969bb08e76f51b995` |
| release controller JSON output (`0036`) | `onewifi_em_ctrl` | `4b5cc2688671cd1993a2c9a8e3fb1c7334ebc20440edf1d884e2238580203e06` |
| live device/client inventory (`0037`) | `onewifi_em_cli` | `3cf06dabb4294440d47ebd1ac2a36b957ead61489cfe03c2460c800695fe992f` |
| live client RCPI presentation (`0044`) | `onewifi_em_cli` | `68cd5937a2f0d256b1b96d5113fa75582066bc9a8eed48050db615a44f5de4f2` |
| authoritative topology client overlay (`0045`) | `onewifi_em_cli` | `c4b7055b160bd061d3d08324c9e933f7924b9b3625fbbaaf984a862d8b88ec70` |

Before `0030`, the controller's anonymous RSS rose from 49,204 to 51,568 KiB
in 70 seconds under normal AP-metrics traffic. After the fix it held at 21,096
KiB for more than two minutes, then at 22,412 KiB for a further two minutes.
That initial CLI result removed response-tree ownership leaks but did not close
the failure. A longer run showed virtual memory still increasing by about
2.23 MiB per topology request and exhausting the helper's 32-bit address space
at roughly 1,500 requests while RSS remained near 100 MiB. `strace` isolated an
unreleased 2,281,472-byte mapping per native call. The source was an unused
automatic `dm_easy_mesh_t` in both CLI implementations followed by
`get_cmd()->init(dm)`. Under Go/cgo, the expanded C++ stack remained mapped;
the initialization also allocated command maps and a queue not owned by the
command destructor. Patch `0035` removes that dead initialization.

The controller had a separate real heap leak of about 82 KiB per topology
request. Its Network JSON path neither freed the string returned by
`cJSON_Print()` nor recursively deleted the generated tree; `cJSON_free()` on
the root alone orphaned all children. Patch `0036` corrects that path and the
same ownership mistakes in device-test, link-metrics and topology publication.
A temporary experiment disabling the TLS session cache did not change the
growth rate and was discarded.

With `0034`-`0036` deployed, 3,000 concurrent topology requests returned HTTP
200 with unchanged PIDs and zero restarts. After allocator warm-up,
`onewifi_em_ctrl` stayed at 601,844 KiB VmSize, 194,784-194,800 KiB RSS and
582,920 KiB VmData for the entire run. `onewifi_em_cli` stayed bounded: it
settled at 714,576 KiB VmSize, acquired one 8 MiB arena at request 2,500, then
remained flat at 722,772 KiB through request 3,000. Subsequent idle reclamation
reduced controller RSS to 57,660 KiB and CLI RSS to 84,208 KiB.

Patch `0037` replaces the packaged Devices and Clients demonstration records
with a leak-safe mapping of the serialized controller tree. REST detail/list
routes, metric keys and WebSocket initial state all use the same live snapshot;
unknown telemetry renders as `N/A`. Both labs returned 6 live UI nodes and 10
associated clients with no canned MACs. After warm-up, a further 4,000 requests
left CLI VmData fixed at 168,964 KiB (6,000 requests total), with an unchanged
PID and zero restarts.

Patch `0044` keeps topology identity and metrics ownership distinct. The
compact `get_network` model remains the client inventory source; a detailed
`get_sta` query supplies reported RCPI and the CLI joins the two by STA MAC.
`/api/v1/clients` exposes raw RCPI plus its derived dBm value, and the visible
Connected Clients page refreshes every two seconds without overlapping native
queries. The reversible wmediumd RCPI-monitor scenario exercises that path
without injecting values into the controller.

Patch `0045` closes a packaging regression found during a clean 0818 VM
deployment. Five stations were associated and present in both controller
`STAList` and `/api/v1/clients`, while `/api/v1/topology` retained only four
for the full five-minute gate. The topology handler's independent native-tree
walk was the lossy boundary. It now retains device, haul and layout data from
that walk but atomically replaces every node's `STAList` from the successful
live inventory already used by `/clients`. The fix is in the ordered recipe
series and in the separately cross-built `em-cli.tar.gz`; changing patched Go
source alone does not replace that prebuilt helper.

Patch `0046` closes the rare controller association-delivery miss exposed by
the strict two-client carousel. Packet captures proved that two distinct
Topology Notification CMDUs reached the controller bridge 88 microseconds
apart, while `em_ctrl` received only the first. The Rust IEEE1905 endpoint
frames AL-SAP traffic with a four-byte length prefix over a Unix stream. The
C++ receiver previously treated one `recv(64 KiB)` result as one SDU, so a
coalesced second SDU became trailing bytes and was discarded. It now reads the
prefix and exactly the declared body, handles short reads and `EINTR`, and
leaves the next frame queued.

Fresh deployment of the `20260819032857` image pair reached `5/15/50`, ten
live clients, zero service restarts and zero client traffic loss. Three strict
carousel runs (2, 2 and 4 rounds) completed 40 paired group arrivals, or 80
individual client association updates, with physical link, controller parent
and topology API agreement plus verified medium restoration. A clean
commanded-steering matrix passed 10/10. Abrupt loss of `bpiap-003` moved all
four affected clients, restored traffic in 1.842 seconds, restored backhaul in
17.806 seconds and returned the extender to controller-visible ready state in
49.639 seconds without restarting `em_ctrl` or `em_cli`.

Sequence-correlated wmediumd tracing separated the recurring command-2
`EINVAL` output into unknown-frequency startup clones and normal receive-state
drops while stations scan or change channel. Patches `0010` and `0011` prevent
unsupported clones where possible and classify only a tracked clone rejection
as debug-level RF loss. A two-round paired carousel completed ten group moves,
ten restores and exact medium restoration with zero command-2 diagnostics. An
unrelated command-3 diagnostic remained visible, proving the handling is not a
blanket netlink-error suppression.

A subsequent ten-round commanded-steering soak passed 100/100 end-to-end
transactions. Link convergence averaged 1,228 ms (1,848 ms maximum), database
convergence averaged 4,153 ms (5,946 ms maximum), and topology API convergence
averaged 4,176 ms (5,979 ms maximum). All ten clients then passed traffic,
topology remained complete, and every OneWifi, agent, controller and CLI
restart counter remained zero. A further 10/10 run validated the new journal:
ten unique transaction IDs, ten start records, ten completion records and
transaction-prefixed command output.

A subsequent 31-sample, ten-minute hold covered AP shutdown, failed traffic,
topology reconstruction and restart activity. Controller RSS/anonymous memory
moved from 36,956/27,252 KiB to 37,028/27,324 KiB; CLI memory moved from
92,580/78,940 KiB to 92,468/78,828 KiB. The controller briefly reached
79,448 KiB RSS during reconstruction and returned to 37,028 KiB within forty
seconds. Both PIDs and zero-restart counters were unchanged. This is bounded
working-set expansion, not retained per-report or per-request growth.

## Remaining engineering debt

- Replace fixed CLI tree storage with a length-tracked serializer.
- Generalize steering ACK routing into an outstanding-transaction table.
- Consolidate authorized WDS creation into one implementation owner.
- Make FULL versus DELTA associated-client inputs explicit.
- Retain the historical RBUS raw-frame provider miss as a transaction-journal
  trigger. It did not recur in 143 post-fix commanded steers, but that result
  cannot retrospectively prove it shared the AL-SAP stream-boundary cause.
- Add positive model reconciliation as defense in depth for a genuinely lost,
  unacknowledged 1905 Client Association Event. The fixed framing path had no
  association loss across 80 post-fix carousel arrivals; reconciliation should
  protect against transport/process failure rather than mask framing loss.
- Make a controller-service-only restart re-query every already-running agent.
  A diagnostic controller restart temporarily reconstructed only `5/15/36`;
  re-onboarding the absent agent restored the required `5/15/50`. Full VM boot
  reconstruction remains a separate, previously accepted path.
