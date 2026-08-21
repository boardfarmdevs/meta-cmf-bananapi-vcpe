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

The current source series contains EasyMesh patches through `0067`, IEEE1905
patches through `0005`, libwebconfig patches through `0005`, and OneWifi
patches through `0014`, plus the log4c category-factory serialization fix. The
Dropbox-packaged 0818 appliance remains an
older, separately accepted distribution until its binary artifacts are
deliberately rolled forward. Never infer image content from the host checkout;
record the image filename/hash and the source revision used to build it.

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
  coalesces messages;
- separate IEEE1905 neighbor evidence from locally generated state, publish
  expiry/reappearance through the normal notification path, and reconcile
  controller reachability with a bounded standard Topology Query;
- commit authoritative Client Association Events before optional capability
  enrichment and repair missed multicast events from Associated Clients TLVs;
- prevent stale Agent metrics or ambiguous old-AP snapshots from changing the
  current STA owner;
- service manager and per-radio protocol timers even while their event queues
  remain continuously busy;
  and
- bound and serialize TLS command/result sessions so a failed or overlapping
  WebUI request cannot block every observer route; and
- serialize log4c category creation so concurrent component startup cannot
  corrupt the shared category factory and force a OneWifi restart; and
- detect the non-root SNMP subagent from the root self-heal path so the
  15-minute monitor cannot multiply daemon and wrapper processes; and
- resolve a duplicate extender AL MAC to its Wi-Fi STA interface instead of
  rejecting DML initialization after `getifaddrs()` returns the bridge first.

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
| OneWifi | `recipes-ccsp/ccsp/ccsp-one-wifi.bbappend` | hwsim defaults, tri-band configuration, association deltas, duplicate-AL-MAC interface resolution |
| libwebconfig | `recipes-ccsp/ccsp/ccsp-one-wifi-libwebconfig.bbappend` | EasyMesh/OneWifi translation and client snapshots |
| log4c | `recipes-common/log4c/log4c_1.2.3.bbappend` | thread-safe shared category creation during concurrent startup |
| EasyMesh core | `recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh.bbappend` | onboarding, model, steering, crypto, CLI |
| 1905 | `recipes-ccsp/ieee1905/ieee1905-em.bbappend` | build/startup, AL-SAP transport and topology-change notification |
| BPI system integration | `recipes-rdkb/sysint-broadband/sysint-broadband.bbappend` | self-heal process detection and installed-script corrections |
| SNMP protocol agent | `recipes-ccsp/ccsp/ccsp-snmp-pa.bbappend` | idempotent cross-user subagent replacement |

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
    coalesced successor queued for the next dispatch;
25. reconcile remote-agent reachability after an IEEE1905 topology-change
    indication without deleting persistent device identity;
26. make STA metrics update only a currently associated controller row;
27. apply bounded transport timeouts and reject command-error trees as
    authoritative empty topology;
28. commit association ownership before the optional capability exchange;
29. emit and consume the standard Associated Clients TLV as a 15-second repair
    path for unacknowledged Topology Notifications;
30. service periodic/orchestration timers under continuous event load;
31. serialize controller command result sessions and close abandoned sessions;
    and
32. prevent an unordered conflicting Topology Response snapshot from
    overwriting a newer association-event owner; and
33. service each radio's protocol timer from a monotonic deadline even while
    normal frame and command events keep that radio queue non-empty;
34. keep fallback BSS-label formatting out of the fetched topology model; and
35. clone that model before D3 adds coordinates and resolved link objects; and
36. run explicit layout optimization against those cloned simulation nodes;
37. create reporting defaults for radios restored from persistent state;
38. expose a one-operation deployment of metrics policy to every live radio;
39. preserve and commit the agent profile through asynchronous onboarding;
40. report node and current-association uptime;
41. source the WebUI client inventory from the detailed associated-STA model;
42. synchronize the validated agent profile into every runtime radio object;
    and
43. make an explicit complete policy submission an idempotent runtime replay.

The ordered series is replayed against pristine pinned source before each Yocto
component or image build. The current images contain the complete ordered
series through `0067`.

## IEEE 1905 ordering

The small `ieee1905-em` series is ordered directly in
`recipes-ccsp/ieee1905/ieee1905-em.bbappend`:

1. use the target tuple, rather than the build-host tuple, for the RBUS bindgen
   clang argument;
2. publish established-neighbor expiry from topology garbage collection and
   feed it to the existing multicast Topology Notification transmitter;
3. deliver that same normal Topology Notification to the local higher-layer
   entity through AL-SAP, because a transmitter does not receive its own
   multicast frame;
4. refresh `last_seen` only from received remote evidence, never from local
   query/response/notification state; and
5. publish the same convergence event when received evidence recreates an
   expired neighbor.

The series deliberately separates transport truth from controller policy. A
neighbor that has not supplied received evidence for 60 seconds is removed,
after which a typed `NeighborExpired` event is published outside the database
write lock. The consumer uses the normal Topology Notification transmitter and
also feeds the same standard notification to AL-SAP. The endpoint metadata
identifies the changed neighbor; no private TLV is placed on Ethernet.
`NeighborAdded` follows the same path when the identity returns. Temporary
nodes that never completed topology convergence do not produce expiry events.

The expiry unit test was cross-compiled with the target test harness and passed
inside `bpibroadband`. Clean component builds passed for both
`qemux86bpibroadband` and `qemux86bpiap`. A rev130 wmediumd test then isolated
all 28 directed RF pairs of `bpiap-003`. The transport expired AL-MAC
`02:00:00:00:04:20` after 61.9 seconds and packet capture on
`eth0_virt_peer` recorded the resulting IEEE 1905 Topology Notification
(`0x0001`, message ID 132) from `00:60:2f:da:68:d4` to
`01:80:c2:00:00:13`. The control-socket generation restored every modified RF
pair by verified readback.

EasyMesh patch `0047` completes the higher-layer boundary. It probes the
affected remote Agent once with a standard Topology Query, suppresses an
unanswered identity from active publication after ten seconds, and restores
that same identity on valid returning traffic. It does not call the
administrative `RemoveDevice` path and does not consult wmediumd or the WebUI.

The controller service runs `onewifi_em_ctrl` directly as a foreground systemd
process and sends stdout and stderr to the volatile journal. The image
configures `RuntimeMaxUse=16M` and `RuntimeMaxFileSize=4M`; the active journal
can make `journalctl --disk-usage` report 20 MiB while four 4 MiB archived files
are retained. The unit additionally applies a 1,000-message-per-30-second rate
limit. This replaces the upstream append-only `/tmp/em_ctrl.log`, which grew at
about 39 KiB/s and reached 815 MiB in tmpfs before causing memory-cgroup OOM
kills. The controller therefore retains its 1 GiB deployment limit; increasing
the limit would only defer recurrence of the unbounded log defect.

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
| `0012` | add atomic frequency-qualified SNR overrides with pair fallback and exact clear/readback semantics |

`gen/wmediumd/build-wmediumd.sh` applies this series to pinned upstream source;
`wmediumd-up.sh` runs its ten-test internal acceptance suite before launch.

## Deliberate differences from 0814

| 0814 behavior | 0815 decision |
| --- | --- |
| disable ieee80211h to address START_AP | removed; malformed ACL encoding was the decoded root cause |
| duplicate OneWifi cipher/PMF patch | removed; libwebconfig is the effective implementation owner |
| forced controller transition out of `wsc_m2_sent` | removed; it could fire after valid M2 and hid command cancellation deadlock |
| forced `wsc_m1_pending` recovery | not imported; previous capability is not proof of current configuration |
| passive returning-client cache update | replaced by refresh, insertion verification and explicit delta publication |
| one historical wmediumd patch | replaced by the tested twelve-patch multichannel/control protocol series |

The replacement for forced WSC state is EasyMesh patch `0026`: cancelled
commands become terminal, and completion is evaluated per command. Duplicate M1
can therefore cancel obsolete work without leaving the radio permanently busy.

## Build and acceptance

The current deployment is a clean role-specific roll-up through EasyMesh
`0059`, IEEE1905 `0005`, the generic log4c category-factory serialization fix,
and the SNMP self-heal process fix. The extender additionally contains OneWifi
`0012`. Each role retains its own source revision and artifact hash:

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller (`3c8a41f1fc868cd3ec823ea722430b152e20e4e7`) | `X86EMLTRBPIBB_rdk-next_20260820210038.rootfs.lxc.tar.bz2` | `da74e07dfece8653bc76d9c821324b75cc72e783d85e681f7524554cc671dc6e` |
| extender (`a50a008152c7c3860af73b58af4bb8b944c777e7`) | `X86EMLTRBPIAP_rdk-next_20260820202147.rootfs.lxc.tar.bz2` | `5468a70d0c5345866d2592062575bf8b197466f1970ca25837b9909a40d8ac29` |

All five deployed device images contain the same `onewifi_em_agent` binary
(`ad859de12e6b667c7d7698e53b30658316a7db99c612f322bafe1894534679bb`).
The earlier deterministic fourth-extender/four-associated-STA stack-protector
failure remained absent through clean deployment and cold-boot reconstruction.

Fresh deployment of the exact pair on rev130 reached `5/15/50/14`, exposed ten
live clients, passed 10/10 traffic, held a 120-second stability window, and
recorded zero monitored service restarts. Three live topology responses across
two refresh intervals had the same SHA-256. The rendered model is
`Controller`, colocated `Agent-1`, and `Extender-1` through `Extender-4`.
The deployed asset is `topology-layout-optimized-1`; its live source passed
the layout-model isolation and optimization regression.

### SNMP self-heal correction

Commit `798ad21` fixes a separate long-running RDK-B defect found after the
accepted image pair above. The root `CcspTandDSsp` health monitor used `ps ww`
and the root SNMP launcher used `ps -ww`; neither default process selection
could see `snmp_subagent` after it changed to the `non-root` account. Each
15-minute health pass consequently launched another daemon and retained its
wrapper. Rev130 reached 53 daemons and 52 wrappers; the same periodic pattern
was present on both VM labs.

The fix uses `pidof snmp_subagent` at both ownership boundaries and guards the
launcher's empty first-start result. The pinned source patches applied, both
recipes compiled, and the generated rootfs passed shell syntax and predicate
checks. It is included in the current controller artifact above; the earlier
`20260820171311` staged image is superseded and must not be deployed.

During P0 development, the following fixes were first rebuilt and exercised as
targeted runtime binaries. The table is retained as diagnostic provenance;
all listed source changes are now included in the current full image pair:

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

EasyMesh `0056` was first diagnosed with a targeted stripped agent before the
full roll-up. Its binary hash,
`ad859de12e6b667c7d7698e53b30658316a7db99c612f322bafe1894534679bb`,
is now the same binary present in the current controller and extender images.

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

Patches `0047` through `0059` close the follow-on P0 state, service, and
presentation boundaries:

| Patch | Root-cause boundary |
| --- | --- |
| `0047` | turn a normal IEEE1905 neighbor change into bounded controller reachability probing and active-topology suppression/restoration |
| `0048` | prohibit periodic metrics from inserting or moving a stale STA owner |
| `0049` | bound controller-command TLS I/O so one failed peer cannot hold the serialized WebUI bridge forever |
| `0050` | return HTTP 503 for command/status trees instead of publishing a false empty topology |
| `0051` | commit the mandatory association notification before optional client-capability completion |
| `0052` | emit and consume Associated Clients in periodic Topology Responses as a standard repair path |
| `0053` | service manager timers under continuous event-queue load |
| `0054` | serialize the controller's shared asynchronous command/result session |
| `0055` | retain the newer association-event owner when an old AP returns an ambiguous snapshot |
| `0056` | service per-radio protocol timers under continuous frame/command load so bounded WSC M1 recovery can execute |
| `0057` | render fallback IEEE labels without mutating the fetched topology model, so an unchanged two-second poll does not recreate an optimized graph |
| `0058` | clone the fetched topology before D3 mutates render nodes and links, eliminating the remaining one-time post-optimize redraw |
| `0059` | release and settle D3's cloned simulation nodes during Optimize Layout instead of changing only viewport scale around still-fixed nodes |
| `0060` | create complete default metrics-policy records for radios reloaded from persistent state |
| `0061` | deploy a complete metrics policy to every live device/radio through one WebUI/API operation |
| `0062`-`0063` | preserve the reported agent profile through both device-model commit paths |
| `0064` | carry agent boot uptime and current client-association uptime to the API/UI |
| `0065` | use the detailed associated-STA model as the live client inventory and metric source |
| `0066` | synchronize the validated Profile-3 value into all runtime radio objects before metrics validation |
| `0067` | replay a complete explicitly submitted policy even when desired database state is unchanged |

The controller service drop-in also copies packaged WebUI assets over the
persistent `/nvram/static` files on every start. The earlier no-clobber copy
made a correct new image continue serving the previous image's JavaScript after
an identity-preserving redeploy.

OneWifi `0012` closes the matching extender convergence defect. The extender
uses the same AL MAC on its backhaul STA and `brlan0`; `getifaddrs()` ordering
could therefore return the bridge first. The old DML lookup rejected that
non-Wi-Fi interface and never published complete VAP/backhaul metadata, so the
WebUI temporarily rendered generic green `Agent-*` links before later state
repaired the graph. If the first match is unusable, `0012` searches the
OneWifi interface map for the same MAC on a STA VAP. A live experiment changing
only the bridge MAC made the old lookup succeed immediately, proving the
duplicate-address selection boundary. The rebuilt four extenders all returned
DML success and published their three fronthaul plus backhaul records.

The supporting OneWifi/libwebconfig changes distinguish a live FULL
association snapshot from retained driver history. IEEE1905 `0003`-`0005`
make locally detected expiry and reappearance visible to the controller through
the normal Topology Notification path and ensure only received evidence extends
a neighbor lifetime.

P0 development deployments reached `5/15/50`, ten live clients, zero service
restarts and zero client traffic loss. Three strict
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

After the full `20260820022527`/`20260820023708` roll-up, an operator demo
rehearsal on rev130 passed a named manual steer, one full ten-client carousel,
RF-only expiry and return of `bpiap-003`, dynamic RCPI cycling, and a complete
identity-preserving stop/start. The final independent audit reported
`5/15/50/14`, 10/10 topology clients, 10/10 traffic and zero monitored
restarts.

A clean artifact-only rev120 VM then failed two cold reconstructions on the same
boundary: `bpiap-001` transmitted all three initial M1 messages, received M2 on
5 and 6 GHz, but never retried the lost 2.4 GHz exchange while normal events
kept that radio queue busy. Patch `0056` moves the per-radio timeout to a
monotonic deadline serviced between queued events, allowing the bounded M1
recovery in `0021` to run. With the targeted `0056` agent in all four extenders,
two consecutive identity-preserving cold reconstructions passed
`5/15/50/14`, 10/10 topology clients, a 120-second stable window, zero
monitored restarts and 10/10 traffic.

A subsequent 31-sample, ten-minute hold covered AP shutdown, failed traffic,
topology reconstruction and restart activity. Controller RSS/anonymous memory
moved from 36,956/27,252 KiB to 37,028/27,324 KiB; CLI memory moved from
92,580/78,940 KiB to 92,468/78,828 KiB. The controller briefly reached
79,448 KiB RSS during reconstruction and returned to 37,028 KiB within forty
seconds. Both PIDs and zero-restart counters were unchanged. This is bounded
working-set expansion, not retained per-report or per-request growth.

The completed P0 RF-outage acceptance then moved the affected client in
5.464 seconds, observed backhaul loss in 2.011 seconds, removed the isolated
extender from active topology in 59.181 seconds, restored the exact 210-link
medium, returned the same identity in 15.198 seconds, and held all ten physical
and API client owners in agreement for 75 seconds. Traffic passed 10/10 and
the monitored controller PIDs/restart counters did not change.

Three consecutive cold reconstructions passed in 805, 800 and 802 seconds with
`5/15/50/14`, 10/10 live clients, a 120-second stable window, zero monitored
restarts and 10/10 traffic. A separate instrumented reconstruction established
a 311.57 MiB cgroup peak and 266.10 MiB converged footprint under the 1 GiB
controller limit, with no swap or memory-pressure/OOM event. See
[memory-footprint.md](memory-footprint.md). The 12-hour churn/steady-state run
is explicitly deferred and is not implied by these bounded results.

The final metrics/uptime image (`20260821015142`) was then installed on rev130.
Its controller artifact SHA-256 is
`ba5b7ea8aabed018d614781450523037624f63a504afc4f8bc7f9b8794d810b2` and
its extender artifact SHA-256 is
`32ae5b9d3d10ad301490219882044e69451c36aff97c68b8bfaf3057e3166e35`.
An untouched cold run first exposed a remaining timing boundary: policy was
deployed at complete mesh-model state, but one agent completed its operational
transition later and lost the volatile reporting timer, leaving RCPI at 8/10.
The lab startup now performs the same idempotent complete-policy replay after
live-client convergence. A fresh 866-second run passed `5/15/50/14`, 10/10
clients, 10/10 RCPI and association uptime, 120 seconds stable, zero monitored
restarts and 10/10 traffic. Every BPI container had one `snmp_subagent`, and
the controller recorded zero AP Metrics Response validation failures.

## Remaining engineering debt

- Replace fixed CLI tree storage with a length-tracked serializer.
- Generalize steering ACK routing into an outstanding-transaction table.
- Consolidate authorized WDS creation into one implementation owner.
- Make FULL versus DELTA associated-client inputs explicit.
- Retain the historical RBUS raw-frame provider miss as a transaction-journal
  trigger. It did not recur in 143 post-fix commanded steers, but that result
  cannot retrospectively prove it shared the AL-SAP stream-boundary cause.
- Generalize the current 15-second Associated Clients reconciliation cadence
  and capacity policy for larger topologies; it is now active defense in depth,
  not missing functionality.
- Make a controller-service-only restart re-query every already-running agent.
  A diagnostic controller restart temporarily reconstructed only `5/15/36`;
  re-onboarding the absent agent restored the required `5/15/50`. Full VM boot
  reconstruction remains a separate, previously accepted path.
