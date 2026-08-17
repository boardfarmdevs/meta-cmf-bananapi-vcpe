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

The accepted images contain runtime source through `73e7c1e`. Later host-side
commits refine lifecycle management, tests and documentation without changing
those image contents.

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
  stack-buffer assumption.

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
10. scale-safe AP Metrics Response construction.

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
| one historical wmediumd patch | replaced by the tested nine-patch multichannel/control protocol series |

The replacement for forced WSC state is EasyMesh patch `0026`: cancelled
commands become terminal, and completion is evaluated per command. Duplicate M1
can therefore cancel obsolete work without leaving the radio permanently busy.

## Build and acceptance

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller | `X86EMLTRBPIBB_rdk-next_20260817000406.rootfs.lxc.tar.bz2` | `32f9edc1983d81c3acd3f6c324447f811a36eabbe377a59648f03aaf280a2383` |
| extender | `X86EMLTRBPIAP_rdk-next_20260817000406.rootfs.lxc.tar.bz2` | `88eb66c0cff613aae471a4917ba838b558f0ec141eb4d8e02b4e8cf19356671f` |

All five images contain the same `onewifi_em_agent` binary
(`ff23b56982d6124dd0fd3dc7450c5c394963a6a24c46ec3684c7f4a50bcbe706`).
The earlier deterministic fourth-extender/four-associated-STA stack-protector
failure remained absent through clean deployment and cold-boot reconstruction.

Both rev130 and the rev150 VM reached `5/15/50`, exported 10/10 clients and
recorded zero service restarts. The VM reconstructed all four extenders and ten
clients after a forced-power-off boot, held the complete state for 120 seconds,
and recorded its model, topology, restart counts, traffic and journal under the
boot-ID acceptance directory. Earlier accepted runs passed 10/10 commanded
steering and a 30/30 extended steering matrix.

## Remaining engineering debt

- Replace fixed CLI tree storage with a length-tracked serializer.
- Generalize steering ACK routing into an outstanding-transaction table.
- Consolidate authorized WDS creation into one implementation owner.
- Make FULL versus DELTA associated-client inputs explicit.
- Root-cause the rare RBUS raw-frame provider delivery miss.
- Decode and eliminate the repeated netlink command-2 `EINVAL` diagnostics
  emitted by wmediumd during normal WLAN activity. They occur on both labs and
  have not correlated with registration, traffic, steering or restore failure.
