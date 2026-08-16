# 0815-codex EasyMesh patch stack

## Intent

0815-codex is an independent reconstruction of the container/hwsim EasyMesh
layer. It starts at `6d87e23`, the last repository commit before the first
EasyMesh-related WiFi HAL build patch, and re-establishes the lab in a small
number of reviewable commits.

The target is Linux 7.0 tri-band hwsim, LXD controller/extender containers,
multichannel wmediumd, four extenders and ten clients. A clean deployment must
converge without service restarts, nudges or hidden forced-state transitions.

## History

| Commit | Responsibility |
| --- | --- |
| `24a95d9` | x86 controller/extender machines, image and container platform |
| `112a73f` | WiFi HAL and libhostap core fixes plus single-phy hwsim adaptation |
| `6fe294f` | OneWifi build/configuration and reliable association export |
| `dd0a091` | ieee1905 and unified-wifi-mesh onboarding/topology/steering fixes |
| `bc6a98a` | hwsim, wmediumd, client and deployment tooling |
| `a9441a2` | lab documentation |
| `d4dca04` | ordered core series and root orchestration fix replacing forced recovery |

The hashes above describe the initial reconstruction. Subsequent fixes remain
separate commits so their build and runtime evidence is visible.

## Patch classes

### Core product fixes

These are not hwsim policy. They correct component behavior and should be
tested for upstreaming:

- malformed nl80211 ACL encoding;
- AP/backhaul credential selection;
- uninitialized supplicant and MLO object handling;
- invalid MLO link IDs and management-frame BSSID selection;
- reflected DEL_STATION event loops;
- WSC WPA2-Personal mapping and per-radio 6 GHz SAE/PMF selection;
- AES final-block output and BTM allocation bounds;
- steering serialization, source-VAP selection, state restoration and ACK/MID
  ownership;
- associated-client event/snapshot export and returning-client publication;
- single-association model reconciliation;
- registrar crypto refresh for every M1;
- association notification during onboarding;
- maximum-length association-frame SQL encoding;
- command cancellation and per-command completion in the orchestrator.

### hwsim/single-phy adaptations

These must remain gated from a physical MediaTek build:

- namespace-independent phy/interface discovery;
- capabilities rather than physical-platform defaults for ACL and management
  subscription;
- 20 MHz concurrent 2.4/5/6 GHz channel contexts on one wiphy;
- explicit Linux 7.0 6 GHz regulatory setup;
- non-MLO behavior where the BPI model would otherwise assume an MLD;
- bridge operstate and post-authorization WDS timing;
- multichannel hwsim/wmediumd registration and frequency isolation.

### container integration

These replace facilities normally supplied by a complete product image:

- stable AL-MAC/RUID identity across ordinary redeploy;
- idempotent MariaDB initialization;
- explicit LAN, ieee1905 socket and wireless-backhaul readiness;
- Linux-bridge selection when OVS userspace is absent;
- controller WebUI and steering helper packaging;
- Boardfarm WAN/DHCP bridge integration.

### observable recovery

The bounded M1 retransmission is retained. Packet loss is legitimate and WSC
must recover, but every resend is logged and bounded. It must eventually be
tied to an explicit WSC transaction generation and terminal health result.

## Deliberate removals from 0814

| Reference change | 0815 decision |
| --- | --- |
| HAL `0006-disable-ieee80211h` | Removed. It was an exploratory START_AP hypothesis superseded by the decoded malformed ACL request. |
| OneWifi `0009` cipher/PMF copy | Removed. libwebconfig `0002` is the linked implementation and sole owner. |
| reference OneWifi reassociation patch | Replaced by the active implementation which refreshes the map, checks diff insertion and publishes the pending update. |
| controller `0020 wsc_m2_sent` forced state | Removed. Live evidence showed it fired milliseconds after M2. New `0026` fixes the cancelled-command deadlock it was bypassing. |
| reference controller `wsc_m1_pending` forced state | Not imported. Prior M1 capability is not proof that current configuration was applied. |
| reference single wmediumd patch | Replaced by the tested nine-patch multichannel/control-socket series. |

Patch number gaps are intentional provenance markers. They make comparison
with 0814 unambiguous and prevent an old patch number from acquiring a new
meaning.

## Ordered unified-wifi-mesh series

`EASYMESH_CORE_PATCHES` in the bbappend is the sole ordering authority. The
reference accumulated `SRC_URI` additions in several distant sections, making
actual application order difficult to see. The 0815 list is dependency ordered:

1. cross-build and WSC mapping;
2. disabled-radio and crypto/memory correctness;
3. steering serializer and its tests;
4. steering state, source VAP and ACK/report flow;
5. CLI and model reconciliation;
6. startup and disabled-radio lifecycle;
7. bounded WSC loss recovery;
8. topology leader, registrar and association-event root fixes;
9. generic orchestration cancellation/completion.

The complete list has been replayed in that order against pristine pinned
unified-wifi-mesh source before the Yocto build.

## Acceptance gates

A build is not accepted merely because packages compile. A clean deployment
must show:

- controller/co-located agent plus four extenders fully represented;
- fifteen radios and fifty BSSs;
- ten clients associated, addressed and exported through the API;
- zero OneWifi, em_agent, em_ctrl and em_cli restarts;
- no controller forced-state recovery message;
- bounded M1 retry only when required, with every radio completing WSC;
- client-to-gateway traffic;
- repeated cross-AP and return steering with link, database and API agreement;
- a wmediumd RF crossover scenario with atomic apply/readback/restore and no
  daemon restart;
- a later persistent/cold-start audit, not only the initial clean-deploy gate.

The same image hashes, layer commit, kernel, container identities and test
results must be recorded for each accepted run.

## Remaining debt

- Replace the fixed CLI tree buffer with a length-tracked serializer.
- Replace steering-specific ACK routing with a general outstanding-transaction
  table.
- Consolidate WDS creation into one owner after authorization.
- Replace service polling and full re-onboarding after OneWifi restart with
  explicit readiness and versioned configuration replay.
- Make FULL versus DELTA associated-client input explicit in libwebconfig.
- Diagnose same-identity live extender replacement and persistent-VM topology
  reconstruction before enabling unattended resume-and-test.

