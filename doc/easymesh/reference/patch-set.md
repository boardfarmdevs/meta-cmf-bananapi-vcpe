# Consolidated EasyMesh patch set

## Purpose

This reference classifies the patches used by the current container/hwsim
EasyMesh layer. A patch belongs here only when it enables the virtual platform
or fixes a demonstrated defect in an owning product component. Scenario
tooling, deployment automation, and tests remain separate host infrastructure.

## Scope

The current source series contains EasyMesh patches through `0148`, IEEE1905
patches through `0006`, libwebconfig patches through `0012`, OneWifi patches
through `0025`, Wi-Fi HAL patches through `0034`, host hwsim patches through
`0008`, and wmediumd patches through `0019`, plus the log4c category-factory
serialization fix. Never infer image content from the host checkout; record
the image filename, hash, and source revision used to build it.

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
- request normal 802.11 acknowledgement and retry handling for unicast action
  frames instead of applying `DONT_WAIT_FOR_ACK` to BTM Requests;
- validate and prioritize OneWifi action-frame commands and report a rejected
  queue admission instead of returning unconditional RBUS success;
- preserve signed Agent BTM-dispatch results and log the STA, source BSS,
  target BSS, VAP, and RBUS outcome;
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
- resolve a steering command's owning radio from its authoritative source BSS
  while the transient per-radio STA map is being rebuilt;
- reconcile full Associated Clients reports as authoritative snapshots instead
  of retaining clients omitted by the reporting BSS;
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
  rejecting DML initialization after `getifaddrs()` returns the bridge first;
  and
- select an already-discovered `(BSSID, current SSID)` scan-cache entry for a
  WNM transition candidate before falling back to a BSSID-only lookup, so a
  hidden beacon record cannot mask its matching directed Probe Response
  record.

### Inherited MediaTek single-wiphy contract

The physical BPI platform already represents the integrated MediaTek device as
one Linux wiphy projected by `FEATURE_SINGLE_PHY` into three RDK radios and
three EasyMesh RUIDs. The 2.4, 5 and 6 GHz band PHY/MAC engines can operate
concurrently while sharing device-level firmware, DMA, calibration and reset
resources. This projection is inherited platform behavior, not a downstream
hwsim workaround and not an EasyMesh-stack defect.

The full ownership hierarchy is:

```text
device AL MAC
  -> one Linux wiphy / base-device owner
     -> three logical RDK radios and EasyMesh RUIDs
        -> per-band AP and backhaul VIFs / BSSIDs
           -> associated client identities
```

Consequently, no patch may assume that `wiphy == EasyMesh Radio`, or use a
base-wiphy MAC where a RUID, BSSID, VIF or frequency-qualified link is
required. The detailed platform model and its operational consequences are in
[MediaTek single-wiphy radio model](single-wiphy-radio-model.md).

### hwsim adaptations of that contract

The RDK lab gives each BPI container one hwsim wiphy and makes it satisfy the
same three-logical-radio contract. The following adaptations are virtual-lab
behavior and must remain gated from a physical MediaTek image where noted:

- accept the hwsim wiphy's host-assigned runtime phy index rather than the
  physical interface map's literal `phy_index: 0` (`Wi-Fi HAL 0002/0003`);
- apply hwsim-specific capability/default policy for HE/EHT, SAE and 6 GHz
  while retaining strict-regulatory tri-band operation where Linux 7 supports
  it (`OneWifi 0004` through `0008`);
- let per-VIF `START_AP` establish concurrent channel contexts instead of
  issuing a conflicting radio-wide `SET_WIPHY`, and clamp the validated
  synthetic contexts to 20 MHz (`Wi-Fi HAL 0022`, `OneWifi 0008`);
- suppress hwsim-unsupported ACL or receive subscriptions by build capability
  and avoid treating a configured but unestablished MLD as live;
- source frequency-qualified candidate RCPI from wmediumd's read-only metrics
  endpoint only for `HWSIM_RADIO` (`Wi-Fi HAL 0024`);
- filter or age retained hwsim AP station rows using inactivity and
  medium-authoritative association ownership (`Wi-Fi HAL 0028`, `0030`,
  `0033`);
- restore management-frame/EAPOL registration and operstate after hwsim AP or
  wiphy reconfiguration (`Wi-Fi HAL 0029`, `0031`, `0032`);
- reconcile successful hwsim associated-client diagnostics as authoritative
  VAP snapshots, including an empty withdrawal (`OneWifi 0020`); and
- register, deliver, schedule and observe simultaneous frequency contexts in
  the patched hwsim/wmediumd medium.

`Wi-Fi HAL 0022` is guarded by `FEATURE_SINGLE_PHY`, because both physical and
virtual builds use that platform organization. Its triggering behavior is the
Linux/hwsim channel API, however; it must be validated separately before being
proposed as generic MediaTek behavior. Conversely, the logical one-wiphy to
three-radio projection itself must not be gated away from the physical build.

### Single-wiphy patch-classification matrix

| Boundary | Representative patches | Physical image applicability | Reason |
| --- | --- | --- | --- |
| Runtime phy enumeration | Wi-Fi HAL `0002`, `0003` | hwsim integration | A wiphy moved into an LXD namespace retains a nonzero host allocation index while the BPI map describes its sole device as index zero. |
| Logical radio projection | inherited `FEATURE_SINGLE_PHY` platform code | required | One integrated MediaTek device backs three independently managed RDK/EasyMesh radios. |
| Concurrent synthetic channels | Wi-Fi HAL `0022`; OneWifi `0008` | hwsim constraint, with shared single-phy code path | Per-VIF channel contexts work; a standalone radio-wide channel change conflicts with already active siblings. The 20 MHz clamp is not a physical capability limit. |
| Candidate-link measurement | Wi-Fi HAL `0024` | `HWSIM_RADIO` only | Physical hardware must retain its native non-associated measurement provider; the lab reads frequency-qualified wmediumd SNR. |
| Stale AP peer correction | Wi-Fi HAL `0028`, `0030`, `0033`; OneWifi `0020` | `HWSIM_RADIO` only | hwsim may retain an authorized kernel station after a silent roam; the virtual lab reconciles it with live snapshots and medium ownership. |
| AP receive-path lifecycle | Wi-Fi HAL `0029`, `0031`, `0032` | `HWSIM_RADIO` only | hwsim registration sockets must be released and restored around AP/wiphy restart. |
| BTM transmit reliability | Wi-Fi HAL `0034`; OneWifi `0025`; EasyMesh `0148` | generic | A unicast action frame needs 802.11 ACK/retry handling; queue admission and local dispatch failures must not be reported as success. |
| Signal attribute fallback | Wi-Fi HAL `0025` | generic | `NL80211_STA_INFO_CHAIN_SIGNAL` is optional on any driver; aggregate signal is standard. |
| Provider count and allocation ownership | OneWifi `0021` through `0023` | generic (`0021` consumes active-row semantics) | Live station counts and freeing every radio/VAP allocation are product correctness, not wiphy representation. |
| Medium delivery and telemetry | hwsim `0001` through `0008`; wmediumd `0001` through `0019` | host lab only | The external simulator must carry frequency, base-radio owner, learned VIF, delivery outcome and authoritative association state. |

This matrix is an ownership rule, not merely documentation. A generic memory,
serialization, timer, model, provider or protocol bug remains generic even if
hwsim made it easier to reproduce. A physical-only driver behavior likewise
must not be copied into the simulator without an explicit fidelity goal and a
testable contract.

### Identity invariants across the patch set

| Layer | Stable identity | May change at runtime | Must never be inferred from |
| --- | --- | --- | --- |
| LXD/hwsim host | permanent base-radio MAC/radio ID assigned to a container | namespace-local phy name | enumeration order after module reload |
| Wi-Fi HAL/OneWifi | logical radio index, VAP index and RUID from the platform map | netdev state and channel context | the kernel phy number alone |
| EasyMesh | AL MAC, RUID, BSSID and current STA owner | association and backhaul parent | base wiphy count or proximity |
| wmediumd | configured base owner plus learned VIF and frequency | active link, learned BSSID and frame counters | a MAC pair without frequency |
| optimizer | normalized device/radio/BSS/client identifiers | scores, candidates and actions | raw wiphy topology |

Normal node restart must preserve these identities and must not rebuild the
medium inventory. Recreating the hwsim module, base-radio assignment, RUID set
or `/nvram` is provisioning or destructive recovery, not restart.

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
| Wi-Fi HAL | `recipes-ccsp/hal/rdk-wifi-hal.bbappend` | nl80211, VAP/interface mapping, WDS, management-frame lifecycle, edge-correct association callbacks and hwsim station liveness |
| hostap integration | `recipes-ccsp/rdk-wifi-libhostap/rdk-wifi-libhostap_2.11.bbappend` | embedded AP/STA state-machine safety |
| OneWifi | `recipes-ccsp/ccsp/ccsp-one-wifi.bbappend` | hwsim defaults, tri-band configuration, association deltas, duplicate-AL-MAC interface resolution |
| libwebconfig | `recipes-ccsp/ccsp/ccsp-one-wifi-libwebconfig.bbappend` | EasyMesh/OneWifi translation and client snapshots |
| log4c | `recipes-common/log4c/log4c_1.2.3.bbappend` | thread-safe shared category creation during concurrent startup |
| EasyMesh core | `recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh.bbappend` | onboarding, model, steering, crypto, CLI |
| 1905 | `recipes-ccsp/ieee1905/ieee1905-em.bbappend` | build/startup, AL-SAP transport and topology-change notification |
| BPI system integration | `recipes-rdkb/sysint-broadband/sysint-broadband.bbappend` | self-heal process detection and installed-script corrections |
| SNMP protocol agent | `recipes-ccsp/ccsp/ccsp-snmp-pa.bbappend` | idempotent cross-user subagent replacement |
| Lab station supplicant | `gen/wpa_supplicant/` | WNM-capable client build and exact-ESS hidden-BSS candidate lookup |

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
    refresh the visible device cards without rebuilding the topology layout;
52. resize the topology viewport with the browser while preserving its active
    layout and drag state;
53. release agent command data-model objects at their owning lifecycle
    boundary;
54. resolve the displayed wireless parent from the live backhaul BSS rather
    than assuming every extender is attached to Agent-1;
55. optimize the topology into the available landscape viewport without a
    delayed telemetry refresh moving it again;
56. reconcile each agent Associated Clients report as an authoritative
    per-BSS snapshot;
57. bound and serialize live CLI observability queries;
58. bound periodic controller diagnostics under sustained activity;
59. reconcile authoritative controller client snapshots without retaining an
    omitted old owner; and
60. resolve a steering candidate from its authoritative source BSS while the
    transient per-radio STA map is being rebuilt;
61. reject a fronthaul association owner learned only from an old metrics row;
62. report BTM outcome from topology-synchronized Agent state rather than a
    stale controller-side candidate;
63. stage visible steering cues and shape star/branch/chain layouts without
    losing the authoritative topology;
64. reconcile full client snapshots across retained and live Agent models;
65. complete upstream orchestration-command lifetimes at their owning state;
66. bound DataElements device enumeration and its temporary command models;
67. keep EasyMesh configuration-stage clones lightweight;
68. turn authoritative Agent station snapshots into ordered topology deltas;
69. bound controller station churn while accepting a real cross-band owner;
70. preserve original association time across repeated full snapshots;
71. reconcile an Agent snapshot only against the radio that reported it;
72. complete local reconciliation before emitting its Topology Notification;
73. scope a controller station deletion to the current owning Agent/BSS;
74. preserve the reporting-radio filter in cloned station state;
75. suppress withdrawn station rows from subsequent Topology Responses and
    metrics processing;
76. complete a candidate-link query when its protocol transaction is rejected
    with an ACK rather than leaving the requester pending;
77. serialize all candidate results as arrays, including zero and one result;
78. apply an associated-STA metrics report to its exact BSS owner;
79. reject signal samples that predate the current association epoch;
80. retain an exact-owner backhaul sample through model reconciliation; and
81. use the controller-first landscape layout for branches, with folded chains
    and the centered RDK star override described below;
82. preserve signed local BTM-dispatch failures and emit a correlation tuple
    for the Agent-to-OneWifi action-frame handoff;
83. show segmented client signal meters in the topology;
84. center Agent-1 in a compact RDK star with extenders surrounding it, applying
    the layout on first display and preserving manual positions on refresh;
85. show exact-parent wireless extender signal bars, enlarge client identities
    without changing band/channel text, and place two-line IoT/private cohort
    titles in a reserved bubble sector clear of default client RF paths;
86. replace those split titles with quoted "iot" and "private" labels in dark
    gray and dark blue, with padded placement and a wider clear client-link sector; and
87. fit Optimize Layout to the available viewport without moving manually
    positioned extenders, Agent-1, Controller, or clients.

The ordered series is replayed against pristine pinned source before each Yocto
component or image build. The current source series ends at `0153`; the
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
   query/response/notification state;
5. publish the same convergence event when received evidence recreates an
   expired neighbor; and
6. forward a changed Topology Response to AL-SAP after updating the IEEE1905
   neighbor model, and resolve its remote Agent through the receiving port
   rather than incorrectly treating an interface MAC as an AL MAC.

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
| `0003-mac80211_hwsim-optional-kernel-medium.patch` | add the opt-in in-kernel impaired-medium path while leaving userspace wmediumd and the stock perfect medium as defaults |
| `0004-mac80211_hwsim-kernel-medium-link-matrix.patch` | provide double-buffered, frequency-band-qualified link matrices for atomic scenario changes |
| `0005-mac80211_hwsim-kernel-medium-rate-per.patch` | add optional deterministic rate-aware packet-error behavior |
| `0006-mac80211_hwsim-kernel-medium-timing-observability.patch` | add bounded delay/jitter queues and frame, airtime, drop and timing counters |
| `0007-mac80211_hwsim-allow-128-static-radios.patch` | raise the validated static-radio bound for the 100-client stress profile |
| `0008-mac80211_hwsim-fix-multichannel-monitor-ack.patch` | use the transmitted frame frequency when reporting multichannel monitor ACKs |

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
| `0015` | index configured pairs, VIF owners and active-link telemetry instead of scanning the complete matrix on hot frame paths |
| `0016` | expose authoritative station-to-AP association ownership from observed protocol exchanges |
| `0017` | resolve ownership queries through learned client and AP VIFs while preserving stable base-radio identities |
| `0018` | page large configured-link dumps so control responses remain bounded at 50/100-client scale |
| `0019` | return the original transmit frequency with TX status for multichannel radios whose legacy global channel pointer is unset |

`gen/wmediumd/build-wmediumd.sh` applies this series to pinned upstream source;
`wmediumd-up.sh` runs the medium's internal acceptance suite before launch.

## Build and acceptance

The accepted role-specific images and hashes are listed only in
[current state](../current-state.md). A build is accepted when both role
images come from the recorded source revision and the clean deployment passes
model, metrics, backhaul, traffic, restart, steering, Console, and restoration
gates. The exact build and runtime procedures are in
[operations](../guide/operations.md).

The controller's checked-in `em-cli.tar.gz` Go helper is a versioned recipe
input, not Yocto sstate. Its SHA-256 is
`fc0f610e61392a045215e4d04076468b759fd9f97ab7dcbb83c7b5173d96506b`
(last refreshed in `bc2fcd8`). The 0905 changes do not alter its Go handlers.
The recipe always overlays `index.html`, `script.js`, and `style.css` from
the patched source, so the old static files inside the helper archive cannot
mask the `0150`–`0153` WebUI changes. Changes to production Go sources require
the separate rebuild procedure in the [build guide](../../build/README.md).

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
