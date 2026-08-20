# RDK-B Unified Wi-Fi Mesh and prplMesh evaluation

Initial comparison: 2026-08-18

Current 0815 status updated: 2026-08-19

Status: engineering assessment; not a certification claim

## Executive answer

Yes. A production-quality EasyMesh implementation is expected to maintain an
authoritative notion of Agent reachability and to reconcile topology when an
extender disappears. The exact WebUI presentation and retention time are
product decisions: an implementation may immediately remove the node, mark it
disconnected and retain it for history, or do both in two stages. What is not a
complete design is to retain a failed extender indefinitely with no reachable,
stale, or disconnected state.

prplMesh 6.0.1 demonstrates the expected division of responsibility:

1. each Agent transmits IEEE 1905 Topology Discovery every 60 seconds;
2. an Agent expires a neighbor after the discovery timeout plus a short grace
   period and sends a Topology Notification;
3. the Controller queries the changed topology;
4. the Controller compares the reporting Agent's neighbor list with its model,
   handles the lost backhaul station, and removes the missing Agent from both
   its database and northbound data model; and
5. a separate, optional network-health task provides a 120-second last-seen
   check, while internal Agent process and Controller-connectivity heartbeats
   cover different failure domains.

The original 2026-08-18 assessment found the same gap in the pinned RDK-B
source: it had topology messages and an administrative `RemoveDevice`, but no
automatic liveness-to-active-topology lifecycle. The first RF tests confirmed
that an isolated extender remained visible for 60-90 seconds.

That gap is now closed by the 0815 patch set, without placing a timeout in the
WebUI. IEEE1905 ages only from received evidence and publishes normal Topology
Notifications for expiry and reappearance. Unified Wi-Fi Mesh probes the
affected Agent with a bounded standard Topology Query, suppresses only active
publication when it receives no answer, retains persistent identity, and
restores the same device on valid returning traffic. The accepted RF test
removed the node in 59.181 seconds and restored it 15.198 seconds after exact
medium restoration.

## Scope and evidence levels

The compared versions are:

| Item | Version examined |
| --- | --- |
| original 0815-codex comparison | `b939a03`, branch `codex/0815-clean` |
| RDK Unified Wi-Fi Mesh base | `c0e72a31c96cc63cc366fcf2b628132185985d2a`, 2026-07-21 |
| current 0815 EasyMesh modifications | ordered patches through `0055`; IEEE1905 through `0005` |
| prplMesh | release `6.0.1`, `8ceef1b0f70a90c4b30b9ce57a99d064283f9638`, 2026-06-25 |

The terms used in the tables are deliberate:

- **Lab-proven** means observed in the 0815 hwsim/wmediumd system.
- **Present** means a substantive implementation path exists in the examined
  source. It does not mean every standard test has passed.
- **Claimed** means the owning project's current official documentation makes
  the claim, but it was not independently reproduced here.
- **Not proven** means source may contain models, message definitions, or
  partial handlers, but the end-to-end behavior has not been established.

This was a source, documentation, history, and existing-test-evidence review.
prplMesh was not built or run on the BPI lab, and neither implementation was
run through a Wi-Fi Alliance certification suite for this report.

## These are two different EasyMesh implementations

The current BPI lab uses RDK Central's **Unified Wi-Fi Mesh** Controller and
Agent, integrated with OneWifi. prplMesh is a separate Controller and Agent
implementation from the prpl Foundation. prplMesh can target RDK-B, but that
does not make it the implementation currently running in these containers or a
drop-in replacement for the existing OneWifi/RBus/WebConfig integration.

```text
0815 RDK-B path

WebUI / em_cli / external optimizer
             |
       Unified Wi-Fi Mesh Controller -- MariaDB
             |
            AL-SAP
             |
          IEEE 1905
             |
       Unified Wi-Fi Mesh Agent
             |
       RBus + WebConfig
             |
          OneWifi
             |
  RDK Wi-Fi HAL + embedded hostap/supplicant
             |
      nl80211 / hwsim / wmediumd


prplMesh path

USP / Ambiorix NBAPI / prplmesh_cli / UCC
             |
       prplMesh Controller task pool + data model
             |
      prplMesh IEEE 1905 transport
             |
         prplMesh Agent
             |
 BPL + BWL abstraction (WHM, nl80211, DWPAL[D], dummy)
             |
    hostapd / wpa_supplicant / platform Wi-Fi manager
```

The RDK design places platform Wi-Fi ownership firmly in OneWifi and its HAL.
The prplMesh design contains more Controller policy machinery and a broader
platform abstraction inside the project. This distinction drives most of the
feature and maturity differences below.

## Extender liveness side by side

### prplMesh normal topology path

The prplMesh Agent `TopologyTask` is active independently of the optional
health-check feature. It sends Topology Discovery every 60 seconds, timestamps
discovered neighbors, expires an unrefreshed neighbor after the specification
timeout plus three seconds, and emits a Topology Notification. Its Controller
delays destructive comparison until an initial 65-second grace has passed,
then removes a previously known neighbor that is absent from the reporting
Agent's 1905 Neighbor Device TLV.

```text
extender RF/backhaul loss
        |
        v
parent Agent stops receiving child's Topology Discovery
        |
        | discovery timeout + grace
        v
parent removes 1905 neighbor and sends Topology Notification
        |
        v
Controller sends Topology Query; parent reports current neighbors
        |
        v
Controller verifies this is not a re-parenting event
        |
        +-- child found below another parent --> keep/reconcile
        |
        `-- child absent --> disconnect subtree + remove Agent/DM instance
```

There are additional but distinct defenses:

- the IEEE 1905 transport ages its own packet-forwarding neighbor map after 70
  seconds;
- an optional Controller `network_health_check_task` examines extender-radio
  last-seen state after 120 seconds and clients after 140 seconds; it is off by
  default in the 6.0.1 controller ODL; and
- Agent-local heartbeats detect failed monitor/AP-manager subprocesses, while
  the Agent's Controller-connectivity task probes a silent Controller.

This is a good architecture because packet routing, process supervision,
topology truth, and long-term health are not confused with one another.

### Current RDK-B path

The pinned base Unified Wi-Fi Mesh discovery state/receive functions remain
empty, and the explicit `RemoveDevice` command remains an administrative
deprovisioning operation. The 0815 implementation adds liveness at the correct
existing boundaries rather than calling that destructive command:

```text
extender RF/backhaul loss
        |
        +--> clients detect beacon loss and reassociate       [works]
        +--> OneWifi/Agent publish new client association     [works]
        +--> Controller and WebUI move client parent          [works]
        +--> IEEE1905 expires received-neighbor evidence       [works]
        +--> normal Topology Notification reaches AL-SAP       [works]
        +--> Controller probes and suppresses active Agent     [works]
        `--> returning traffic republishes same identity       [works]
```

The manual remove operation is still useful for administrative deprovisioning,
but it is not used for liveness. Neither the browser nor wmediumd declares a
device dead; received IEEE1905 evidence and the controller probe own that
decision.

### What “full implementation” should mean here

The standard protocol supplies topology discovery, notification, query, and
response primitives. A product Controller still chooses presentation and
retention policy. For this lab and eventual production behavior, the sound
state model is:

```text
ONLINE
  | missed protocol liveness deadline
  v
SUSPECT               keep forwarding/model changes conservative
  | confirmed absent from parent topology or repeated query failure
  v
DISCONNECTED          publish status; invalidate current radio/BSS placement
  | configurable retention expires
  v
REMOVED                delete active topology; retain event/history if desired

Any valid message / successful re-onboarding with the same AL-MAC
reconciles identity and returns the device to ONLINE.
```

The current implementation publishes only the active view: the device remains
visible during the IEEE1905 aging/probe interval, then disappears without its
persistent identity being deleted. A future northbound `SUSPECT`/`DISCONNECTED`
state could render a grey intermediate node, but that presentation is not
required to truthfully remove and restore the active topology today.

## General stack comparison

### Architecture, platform integration, and operations

| Area | RDK-B Unified Wi-Fi Mesh on 0815 | prplMesh 6.0.1 | Assessment |
| --- | --- | --- | --- |
| Controller/Agent roles | Separate Controller and Agent binaries; colocated Agent on gateway | Controller-only, Agent-only, or combined mode | Equivalent role model |
| 1905 transport | Separate RDK `ieee1905` processes reached through AL-SAP | Integrated project transport/broker and TLVF message library | prplMesh has tighter end-to-end ownership |
| Wi-Fi owner | OneWifi, libwebconfig, RDK Wi-Fi HAL, embedded hostap/supplicant | BWL/BPL with WHM, nl80211, DWPAL, DWPALD, and dummy backends | RDK is stronger for the existing BPI integration; prplMesh is broader within its ecosystem |
| Platform targets | This layer is an RDK-B/BPI plus x86 LXD integration | Officially targets prplOS/OpenWrt and RDK-B across multiple SoCs | prplMesh is more portable as a standalone project |
| Persistence | MariaDB Controller model plus RDK `/nvram`; required several container lifecycle fixes | Runtime Controller DB plus Ambiorix data model; optional persistent client DB with explicit aging | Both support persistence; prplMesh exposes more lifecycle policy |
| Northbound | `em_cli`, libemcli/TLS, RBus/WFA Data Elements, local HTTP API/WebUI | Ambiorix/TR-181 NBAPI, USP-facing data model, `prplmesh_cli`, legacy BML/CLI, UCC | prplMesh has the more complete management API surface |
| Topology UI | Integrated and lab-proven; live data, two-second change-aware refresh, layout and export | Separate topologyViewer exists and consumes Ambiorix HTTP data | RDK lab UI is more directly usable for this experiment |
| Deployment | Repeatable LXD and thin VirtualBox/Vagrant lab with Boardfarm WAN/DHCP | Production platform builds plus Docker/dummy, certification, and Boardfarm test environments | Different strengths; 0815 is better prepared for this exact simulation |

### EasyMesh control-plane functions

| Function | RDK-B Unified Wi-Fi Mesh on 0815 | prplMesh 6.0.1 |
| --- | --- | --- |
| WSC M1/M2 onboarding | **Lab-proven** at four tri-band extenders; 0815 fixes lost M2, registrar reuse, disabled-radio, and concurrent onboarding defects | **Present** and extensively exercised by certification/Boardfarm infrastructure; includes burst coalescing and controller-restart renewal |
| Credential/BSS synchronization | **Lab-proven** for 2.4/5/6 GHz fronthaul and 5 GHz backhaul | **Present**, including BSS configuration reporting and current security modes |
| Topology query/response/notification | **Lab-proven** for onboarding, associations, expiry and same-identity return; 0815 adds received-evidence aging plus bounded controller probe/suppression | **Present**, including neighbor discovery, re-parent filtering, disconnect events, and Agent removal |
| Explicit device removal | **Present** through `RemoveDevice` command and DB/model orchestration | **Present** internally through topology reconciliation and NBAPI event/model handling |
| Wired backhaul | Controller WAN/LAN and wired platform paths exist; remote-Agent wired onboarding is **not proven** in this lab | **Present/claimed**, including explicit wired-parent inference |
| Wireless backhaul | **Lab-proven**, 4-address/WDS over 5 GHz | **Present**, with backhaul manager, wired preference/fallback, and optimization tasks |
| Multi-hop/daisy chain | Source model can represent topology; 0815 acceptance is a star topology, so **not proven** | **Present** as a hierarchy with daisy-chain controls and IRE optimization; not reproduced here |
| Failed Agent recovery | **Lab-proven**: clients move, isolated Agent leaves active topology, exact RF restore returns the same identity, and client ownership reconverges | Topology aging/removal and renewed onboarding are **present** |
| DPP/EasyConnect onboarding | Substantial configurator/enrollee, chirp, encapsulated DPP, GAS, and 1905-security source exists; **not proven** in 0815 | DPP infrastructure and flows are **present**; not reproduced here |
| R5/R6 scope | Repository describes R5; current source also contains MLD, DPP, and newer message/data-model work. The BPI profile is not certified by this report | Foundation claims R1-R5 support with R6 in development; 6.0.1 contains significant R6 certification and MLO work, but this report does not claim full R6 completion |

### Clients, metrics, steering, and optimization

| Function | RDK-B Unified Wi-Fi Mesh on 0815 | prplMesh 6.0.1 |
| --- | --- | --- |
| Client association/disassociation | **Lab-proven**; one-association invariant and returning-client publication fixed in 0815 | **Present**, with association/disassociation and failure events in Controller DM |
| Client capability | Query/report and association-frame parsing **present**; capability preservation across roam fixed in 0815 | **Present**, including HT/VHT/HE/EHT-related data-model work |
| AP/STA/link metrics | AP metrics, associated/unassociated STA metrics, beacon metrics, traffic statistics, and queries are **present**; scale buffer fixed in 0815 | Broad periodic/on-demand metrics collection is **present**, with Controller DB/NBAPI publication |
| Channel scan | Message, model, command, and result paths are **present**; not a core 0815 acceptance item | **Present** with Agent scan task, cached results, NBAPI trigger, and certification tests |
| Commanded client steering | **Lab-proven** through EasyMesh Steering Mandate, source-VAP BTM, ACK/report, reassociation, DB/API, and traffic verification | **Present** through client-steering and BTM tasks, CLI/NBAPI triggers, and steering history/statistics |
| Autonomous client selection | **Not implemented/proven**. Passive RF crossover does not steer; `src/network_optimiser` builds only `test_tr181.cpp` | Built-in `optimal_path_task`, association handling, band/client roaming, and measurement-based ranking are **present**, but steering defaults are off |
| Agent steering policy TLV | Storage/UI, per-device deployment, ACK handling and metrics-policy consumption are **lab-proven**; no autonomous evaluator has been proven | Policy configuration and thresholds are **present** in Controller configuration and Agent reporting paths |
| Load balancing | No operational evaluator in the current BPI path | A load-balancer task exists, but prplMesh's own 6.0.1 documentation says the actual steering call remains commented/TODO; do not count it as complete |
| Backhaul optimization | External design only in this lab | IRE/backhaul optimal-path tasks are **present** and enabled/disabled through Controller configuration |
| External optimizer integration | Intended through live topology/metrics plus command APIs; current clean approach is the documented external optimizer | NBAPI and task controls allow external management; official material also describes proprietary/third-party algorithm integration |

This policy distinction matters. prplMesh contains actual decision tasks in
the Controller. RDK Unified Wi-Fi Mesh contains the protocol and command
machinery needed by an external decision engine, but the directory called
`network_optimiser` is not such an engine: its build target contains only an
interactive RBus/TR-181 test program for Controller ID, colocated Agent ID,
SSID setting, and topology subscription.

### Radio, spectrum, security, and data-plane features

| Function | RDK-B Unified Wi-Fi Mesh on 0815 | prplMesh 6.0.1 |
| --- | --- | --- |
| 2.4/5/6 GHz | **Lab-proven concurrently** on one hwsim wiphy projected into three logical radios | 6 GHz/tri-band support is **claimed/present**; exact hwsim single-phy setup was not tested |
| Channel preference/selection | Query, report, selection request/response, and operating-channel report paths are **present**; the lab intentionally fixes channels | Controller and Agent channel-selection tasks, preference reports, and dynamic selection are **present** |
| DFS/CAC/channel availability | Models and several capability/message paths are **present**; hwsim lab does not prove production radar/CAC behavior | DFS/CAC, Zero-Wait DFS hooks, channel scan, spatial reuse, static puncturing, and AFC/available-spectrum work are **present**, with platform dependencies |
| Wi-Fi 7/MLO | AP/bSTA/associated-STA MLD models, configuration messages, and TID-to-link data are **present**; 0815 deliberately runs non-MLO hwsim, so **not proven** | Extensive AP/bSTA MLD, affiliated-link, EHT, 320 MHz, and R6 work is **present** in 5.2/6.0 releases; hardware behavior not reproduced here |
| VBSS | No equivalent complete VBSS task/message family was found in the examined RDK source | Optional Controller/Agent VBSS creation, movement, cancellation, key/context, and NBAPI paths are **present** |
| WPA2/WPA3/PMF | **Lab-proven** for the selected backhaul/fronthaul profile; 0815 fixes WPA2 mapping, 6 GHz security upgrade, cipher, and PMF translation | WPA2/WPA3, transition/compatibility modes, PMF, and RSN overriding paths are **present** |
| 1905 security/DPP | Considerable source implementation is present; **not lab-proven** | DPP and secured onboarding infrastructure is **present**; current docs still identify some R6 RSN data-model work as incomplete |
| Traffic separation/VLAN | Data elements and protocol structures exist; **not accepted** in the current lab | **Present** with Agent VLAN plumbing and repeated fixes; behavior is platform/interface dependent |
| Service prioritization/QoS | Source/data-model scope exists; **not accepted** in the current lab | R3 QoS, service prioritization, tc-based OSPv2 handling, and R6 SCS/MSCS work are **present**, with backend-specific limits |

### Quality, testing, and maturity

| Area | RDK-B Unified Wi-Fi Mesh on 0815 | prplMesh 6.0.1 |
| --- | --- | --- |
| Upstream unit CI | GitHub build and unit-test workflows; 95 test source files in the examined tree | Unit/static checks plus dummy/CRAM and platform jobs |
| Certification infrastructure | Message validation and device-test code exist; no equivalent in-repository, release-indexed certification matrix was found | In-repository R1/R2/R4/R6 certification configuration/tests and UCC integration |
| System tests | 0815 adds repeatable deployment, health, steering, outage, cold-boot, wmediumd control, and scale acceptance | Boardfarm plugin/tests, dummy Docker flows, nightly hardware/certification-oriented CI |
| Exact simulated lab evidence | Four extenders, ten clients, 5/15/50 model, tri-band, cold restart, 30/30 extended steering, dynamic RF outage and recovery | Not evaluated against our patched hwsim/wmediumd environment |
| Patch burden | 0815 carries substantial generic, container, and hwsim fixes over a rapidly changing upstream | Larger mature project with long release history, but also many platform branches, task flags, and known partial features |
| Documentation | Upstream manual is brief and partially stale; 0815 documentation supplies most operational truth | Broader architecture, configuration, flow, NBAPI, release, and test documentation |

prplMesh is therefore the stronger general reference implementation and a
useful source of behavioral design. It is not automatically the lower-risk
choice for the current experiment: replacing the running stack would require a
new RDK/BPI Wi-Fi adaptation, containerization work, tri-band hwsim validation,
wmediumd integration, and a new stability campaign.

## Implications for the BPI experiment

### Keep the current stack for the immediate optimizer work

The lab's purpose is to evaluate steering policy under controlled RF gradients.
For that goal, 0815 already provides the scarce assets:

- repeatable tri-band RF simulation;
- stable multi-Agent onboarding;
- real EasyMesh commanded steering;
- live association and topology observation;
- controlled wmediumd updates and restoration; and
- reproducible scale, reboot, traffic, and memory acceptance.

prplMesh has a richer Controller, but migrating now would postpone policy
experiments in favor of redoing platform integration. It should be used as a
behavioral and architectural comparison, not treated as an immediate stack
replacement.

### Retain the completed liveness boundary

The current 0815 implementation deliberately chose the smallest coherent
topology lifecycle, not a lab-specific removal hook:

1. the existing IEEE1905 process transmits Topology Discovery every 30 seconds;
2. its monotonic neighbor time is refreshed only by received evidence;
3. the 60-second garbage collector publishes normal Topology Notification for
   expiry and reappearance through multicast and local AL-SAP;
4. the Controller probes the affected AL-MAC once with a standard Topology
   Query and suppresses an unanswered device from active publication;
5. any valid return clears suppression without deleting/recreating persistent
   identity; and
6. association events remain authoritative while periodic Associated Clients
   TLVs repair a missing event and reject ambiguous competing ownership.

A northbound `SUSPECT`/`LastSeen` state and parent-neighbor-list comparison are
still useful product refinements, especially for multi-hop topology. The
current star lab instead uses direct query response as its re-parenting guard.

The 0815 wmediumd outage acceptance now requires and passes:

```text
backhaul link loss
-> clients leave and appear under surviving APs
-> Agent leaves active topology after IEEE1905 aging plus controller probe
-> WebUI automatically renders the change
-> RF restore causes real backhaul association and onboarding
-> the same logical Agent returns without duplicate radios/BSSs/clients
-> traffic, PIDs and restart counters remain healthy
```

### Do not copy prplMesh code directly into the RDK component without review

The architectural behavior is reusable as a design reference. Direct source
reuse needs an explicit legal and maintainership decision: Unified Wi-Fi Mesh
is Apache-2.0, while prplMesh source is primarily BSD-2-Clause-Patent and has
component-level license metadata. An independent RDK implementation of the
standard lifecycle is likely easier to review and upstream.

## Final assessment

| Question | Answer |
| --- | --- |
| Should a full implementation detect a vanished extender? | **Yes.** At minimum it must expose authoritative disconnected/stale state and reconcile active topology. |
| Does EasyMesh prescribe the exact WebUI timeout and deletion policy? | **No.** The protocol provides topology/liveness primitives; presentation and retained history are product choices. |
| Does prplMesh implement the required lifecycle? | **Yes, materially.** It has periodic discovery, neighbor aging, notification/query reconciliation, Agent removal, disconnect events, and optional health checks. |
| Does the current BPI RDK stack implement it? | **Yes, in the 0815 layer.** Received-evidence aging, normal notification, bounded controller probing, active-topology suppression and same-identity restoration are lab-proven. The pinned upstream base alone still lacks this complete lifecycle. |
| Is prplMesh generally more feature-complete? | **Yes at the Controller/reference-stack level**, especially lifecycle, NBAPI, built-in optimization tasks, platform abstractions, and certification infrastructure. It still contains disabled-by-default and explicitly partial features. |
| Should the lab migrate to prplMesh now? | **No.** Continue with the stable 0815 platform and external optimizer work, upstream/refine the new generic lifecycle, and use prplMesh as a design and behavior reference. |

## Primary sources

RDK Central:

- [Unified Wi-Fi Mesh repository and R5 scope](https://github.com/rdkcentral/unified-wifi-mesh)
- [Exact examined discovery implementation](https://github.com/rdkcentral/unified-wifi-mesh/blob/c0e72a31c96cc63cc366fcf2b628132185985d2a/src/em/disc/em_discovery.cpp#L93-L170)
- [Exact examined manual RemoveDevice analysis](https://github.com/rdkcentral/unified-wifi-mesh/blob/c0e72a31c96cc63cc366fcf2b628132185985d2a/src/ctrl/dm_easy_mesh_ctrl.cpp#L3273-L3363)
- [Network optimiser build target](https://github.com/rdkcentral/unified-wifi-mesh/blob/c0e72a31c96cc63cc366fcf2b628132185985d2a/src/network_optimiser/Makefile.am#L24-L39)
- [Network optimiser test program](https://github.com/rdkcentral/unified-wifi-mesh/blob/c0e72a31c96cc63cc366fcf2b628132185985d2a/src/network_optimiser/test_tr181.cpp#L28-L61)
- [OneWifi architecture and responsibilities](https://github.com/rdkcentral/OneWifi)
- [RDK OneWifi/EasyMesh integration guide](https://wiki.rdkcentral.com/spaces/RDK/pages/378374596/OneWifi)

prpl Foundation:

- [prplMesh project scope and feature overview](https://prplfoundation.org/prplmesh/)
- [prplMesh 6.0.1 release](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/releases/6.0.1)
- [6.0.1 Agent topology discovery and neighbor aging](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/6.0.1/agent/src/beerocks/slave/tasks/topology_task.cpp#L45-128)
- [6.0.1 Controller topology reconciliation](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/6.0.1/controller/src/beerocks/master/tasks/topology_task.cpp#L942-998)
- [6.0.1 IEEE 1905 transport neighbor aging](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/6.0.1/framework/transport/ieee1905_transport/ieee1905_transport_packet_processing.cpp#L35-76)
- [Controller configuration, task behavior, and documented limitations](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/6.0.1/documentation/prplMesh-configuration.md)
- [6.0.1 changelog](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/6.0.1/CHANGELOG.md)
- [BWL backend selection](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/6.0.1/common/beerocks/bwl/CMakeLists.txt)
- [Controller NBAPI model](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/tree/6.0.1/controller/nbapi)
- [Boardfarm test architecture](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/6.0.1/documentation/prplMesh-test-boardfarm.md)

Local 0815 evidence:

- `doc/easymesh/architecture.md`
- `doc/easymesh/patch-set.md`
- `doc/easymesh/steering.md`
- `doc/easymesh/wmediumd-extender-outage.md`
- `recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh.bbappend`
