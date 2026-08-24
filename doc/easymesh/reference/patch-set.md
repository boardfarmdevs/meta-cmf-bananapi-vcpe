# Consolidated EasyMesh patch set

## Purpose

This reference classifies the patches used by the current container/hwsim
EasyMesh layer. A patch belongs here only when it enables the virtual platform
or fixes a demonstrated defect in an owning product component. Scenario
tooling, deployment automation, and tests remain separate host infrastructure.

## Scope

The current source series contains EasyMesh patches through `0114`, IEEE1905
patches through `0006`, libwebconfig patches through `0011`, OneWifi patches
through `0018`, and Wi-Fi HAL patches through `0026`, plus the log4c
category-factory serialization fix. Never infer image content from the host
checkout; record the image filename, hash, and source revision used to build it.

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

Patch headers contain the failure trace, packet/log evidence, and ownership
rationale.

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
43. make an explicit complete policy submission an idempotent runtime replay;
44. serialize the controller's shared Autoconfiguration Search/WSC model
    boundary and validate Profile TLVs;
45. serialize asynchronous per-radio WSC subdoc delivery through OneWifi apply
    completion and bounded callback recovery;
46. service lost-M2 recovery from self-clearing radio protocol state after the
    shared orchestration command has ended;
47. preserve that per-radio recovery ownership when either device-init or
    retained-identity configuration-renewal reaches its generic command TTL;
48. recover a OneWifi subdoc whose orchestration command ended before its
    callback was delivered;
49. complete a successful OneWifi callback at its own BSS-configuration
    terminal state instead of waiting for a later Topology Query; and
50. preserve IEEE1905 measurement age end to end and publish an explicit
    fresh/stale/unknown backhaul-signal contract to the WebUI; and
51. join that exact current backhaul metric into the Mesh Devices endpoint and
    refresh the visible device cards without rebuilding the topology layout.

The ordered series is replayed against pristine pinned source before each Yocto
component or image build. The current source series ends at `0114`; the
role-specific artifact boundary is recorded under **Build and acceptance**.

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

Acceptance requires the expiry unit test in the target harness, clean builds
for both BPI roles, an RF-isolation test that observes the standard Topology
Notification, and verified restoration of every modified wmediumd pair.

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
| `0013` | add the multi-client read-only pair/frequency endpoint used by the hwsim HAL |
| `0014` | add bounded host-only frame/outcome, active-link, radio/frequency, VIF and event telemetry for the Go Console |

`gen/wmediumd/build-wmediumd.sh` applies this series to pinned upstream source;
`wmediumd-up.sh` runs its ten-test internal acceptance suite before launch.

## Build and acceptance

The accepted role-specific images and hashes are listed only in
[current state](../current-state.md). A build is accepted when both role
images come from the recorded source revision and the clean deployment passes
model, metrics, backhaul, traffic, restart, steering, Console, and restoration
gates. The exact build and runtime procedures are in
[operations](../guide/operations.md).

## Remaining engineering debt

- Replace fixed CLI tree storage with a length-tracked serializer.
- Generalize steering ACK routing into an outstanding-transaction table.
- Consolidate authorized WDS creation into one implementation owner.
- Make FULL versus DELTA associated-client inputs explicit.
- Retain transaction-level command/completion journaling for raw-frame
  provider delivery failures.
- Generalize the current 15-second Associated Clients reconciliation cadence
  and capacity policy for larger topologies; it is now active defense in depth,
  not missing functionality.
- Generalize exact BSS-key reconciliation beyond the current authoritative
  per-device update boundary if future partial-radio protocol inputs require a
  different FULL/DELTA contract. The current controller-only restart and cold
  chain/branch tests pass `5/15/50/24` exactly.
