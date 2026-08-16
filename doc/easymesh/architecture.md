# EasyMesh on LXD + mac80211_hwsim — architecture

How the Banana Pi RDK-B EasyMesh stack runs on x86 in LXD containers with
simulated Wi-Fi, and how a controller, an extender, and a client form a real
WLAN network with no wired shortcut.

- Build host: `rev140` · Runtime host: `rev150`
- See also: [deploy-and-test.md](deploy-and-test.md) · [steering.md](steering/steering.md)
  · [wmediumd-multichan.md](wmediumd-multichan.md) · [patches.md](patches.md) ·
  building: [../build](../build)

## The substitution

The layer takes the physical Banana Pi R4 RDK-B broadband build and retargets
it to x86 packaged as an LXC rootfs. Only the radio hardware and the RF
environment are simulated — the RDK-B services still create APs, associate,
exchange 802.11 management frames, bridge traffic, and send IEEE 1905.1 CMDUs
over a real mac80211 data path.

```text
Physical Banana Pi lab            LXD/hwsim lab
------------------------          ----------------------------------
BPI controller board              bpibroadband LXD container
BPI extender board                bpiap LXD container
MT7988 Wi-Fi hardware             mac80211_hwsim simulated radio
RF propagation                    (optional) wmediumd link/interference model
on-board kernel + processes       shared rev150 kernel + container processes
client phone/laptop               Alpine wlan-client LXD container
```

The smallest healthy topology: one `bpibroadband` controller (which also runs a
**colocated** EasyMesh agent), one `bpiap` extender, and one `wlan-client`
station. More extenders/clients use the same design.

## Concepts

**EasyMesh (Multi-AP).** A **controller** owns the desired policy and topology
model (SSIDs, security, steering requests); an **agent** operates AP radios,
reports capability/topology, and applies the controller's configuration.
`bpibroadband` is both controller and a colocated agent; `bpiap` is agent-only.

**Fronthaul vs backhaul.** Fronthaul is the client-facing Wi-Fi (`private_ssid` /
`test-fronthaul`, plus `iot_ssid`). Backhaul connects an extender upstream
(`mesh_backhaul` / `test-backhaul`): the extender's 5 GHz managed STA (`wifi1.3`)
associates to the controller's 5 GHz backhaul AP (`wifi1.1`) on channel 36.

**IEEE 1905.1.** EasyMesh control rides 1905 CMDUs (EtherType `0x893a`; discovery
via `01:80:c2:00:00:13`). Identities are distinct:

```text
AL-MAC   an EasyMesh / IEEE 1905 device
RUID     one radio represented by that device
BSSID    one AP service (VAP) on a radio
STA MAC  a client or backhaul station interface
```

A node's identity is the tuple **{AL-MAC, RUID-set}** — preserve or regenerate it
as a unit. Reusing old RUIDs under a new AL-MAC makes the controller treat a
redeploy as colliding with a dead node (a known redeploy limitation).

**LXD** gives each container its own userspace on the shared `rev150` kernel. The
deploy helper builds a per-container profile with one hwsim NIC (renamed `wlan0`
inside), any needed veths, a persistent `/nvram` volume, and image provenance.
The radio is attached `nictype=physical`, which moves the whole wiphy into the
container netns.

**mac80211_hwsim** creates software radios driven through normal `nl80211`. The
host loads one pool: `mac80211_hwsim radios=24 channels=2`. `channels=2` lets one
wiphy hold two channel contexts at once — required for concurrent 2.4 + 5 GHz.

**FEATURE_SINGLE_PHY.** The BPI image projects **one** physical wiphy into three
logical radio slots. This is a hard invariant: give each BPI container exactly
one hwsim phy.

```text
        one physical hwsim wiphy
   +------------+------------+
 wifi0        wifi1        wifi2
 2.4G/ch6     5G/ch36      6G (band-dependent)
```

Whether `wifi2` (6 GHz) can operate is a **platform capability**, not a fixed
property of hwsim:

- **Legacy 6.8 host (the default lab):** the applied regulatory domain marks
  6 GHz `NO-IR` (an AP may not beacon), so `wifi2` is modelled but disabled, and
  the baseline runs 2.4 + 5 GHz only.
- **7.0 host:** loading hwsim with `regtest=5` selects `custom_03`, under which
  6 GHz is **IR-capable (0 NO_IR)** and a 6 GHz AP beacons on 5975 with no kernel
  patch — proven standalone end-to-end (hostapd `AP-ENABLED`, STA SAE-H2E + PMF +
  4-way handshake). See
  [6ghz.md](6ghz.md) (appendix).
  EasyMesh **tri-band** on 7.0 is not yet validated — the layer still disables
  `wifi2` for `HWSIM_RADIO` builds and forces WPA2 defaults (both need to become
  capability-aware; see [TODO.md](TODO.md) items 2–3).

The lever that opens 6 GHz is the **regdomain selection** (`regtest=5`/`custom_03`),
not the kernel version per se; 7.0 just maps `HWSIM_REGTEST_CUSTOM_WORLD` to
`custom_03` out of the box.

**wmediumd (optional).** Bare hwsim delivers frames with a **flat** signal — every
AP looks equally strong, so there is no gradient for roaming/coverage policy to
act on. wmediumd is the userspace medium model (per-link SNR, delivery, ACK,
interference) that provides a real gradient. The default lab runs **without** it;
the multichannel-capable build + config generator + a one-line hwsim kernel
relaxation are carried in this layer's `gen/` (`gen/hwsim`, `gen/wmediumd`) —
see [wmediumd-multichan.md](wmediumd-multichan.md).

## Lab topology

Only the controller has wired WAN/LAN (from a boardfarm slot). The extender's
mesh and client paths are entirely wireless.

```text
                                 rev150 LXD host
   boardfarm WAN                                              wlan-client
    br-wan105                                                (Alpine, hwsim wlan0)
        | erouter0                                                 ))  fronthaul
 +------+-------------------------------------------+              ))
 | bpibroadband                                     |         +----+------------+
 |  EasyMesh controller --- OneWifiMesh DB (MariaDB)|         | bpiap extender  |
 |  colocated agent --- OneWifi/HAL --- 1 hwsim phy |   ))))  | EasyMesh agent  |
 |  brlan0: wifi0/wifi1 private_ssid,               |  5 GHz  | OneWifi/HAL     |
 |          wifi1.1 mesh_backhaul AP  --------------+--WDS/4addr-- wifi1.3 STA   |
 +--------------------------------------------------+  backhaul| wifi0/wifi1 APs |
                                                               +-----------------+
   +----------------------------------------------------------------------+
   | host kernel: cfg80211 + mac80211 + mac80211_hwsim                     |
   | host process (optional): one multichannel wmediumd for all radios     |
   +----------------------------------------------------------------------+
```

The client's `eth0` is management only — a data-path test must bind to `wlan0`.
Do **not** wire the extender to the controller's LAN bridge: their `brlan0`
domains are already joined by wireless backhaul, and a second wired path forms an
Ethernet loop.

## Processes and boundaries

Localizing a failure means knowing the boundaries.

**rev150 host:** `lxd`; `cfg80211`/`mac80211`/`mac80211_hwsim`; optionally
`wmediumd`.

**bpibroadband:** `OneWifi` (data model + HAL); `ieee1905` ×2 (`ieee1905_em_ctrl`,
`ieee1905_em_agent`); `onewifi_em_ctrl` (controller logic); `onewifi_em_agent`
(colocated agent); `mariadbd` (`OneWifiMesh` DB); `onewifi_em_cli` (web UI + CLI,
port 8888).

**bpiap:** `OneWifi`; `ieee1905_em_agent`; `em_agent`.

hostapd and the backhaul supplicant are embedded behind OneWifi/HAL — they are
not separate `ps` entries. Only the Alpine client runs a standalone
wpa_supplicant.

```text
browser ─HTTP:8888─ onewifi_em_cli ─libemcli/TLS:49153─ onewifi_em_ctrl ─ MariaDB
                                                              │ AL-SAP (unix)
                                                        ieee1905 controller
                                                              │ 1905 / 0x893a over WLAN
                                                        ieee1905 agent
                                                              │ AL-SAP
                                                        onewifi_em_agent
                                                              │ RBus WebConfig.Data.Subdoc.South
                                                              │  + RawFrame action API (BTM Tx/Rx)
                                                            OneWifi ─ nl80211 ─ mac80211_hwsim ─ wmediumd
```

## Code map

Names differ across source, recipes, services, and logs:

| Responsibility | Source project / class | Runtime name |
|---|---|---|
| Multi-AP controller | `unified-wifi-mesh`, `em_ctrl_t` | `onewifi_em_ctrl` / `em_ctrl.service` |
| Multi-AP agent | `unified-wifi-mesh`, `em_agent_t` | `onewifi_em_agent` / `em_agent.service` |
| 1905 transport | `ieee1905` + `libalsap` | `ieee1905_em_ctrl` / `ieee1905_em_agent` |
| Wi-Fi manager | `ccsp-one-wifi` (+ `-libwebconfig` translator) | `OneWifi` / `onewifi.service` |
| driver integration | `rdk-wifi-hal` | linked into OneWifi |
| AP/STA state machines | hostapd/wpa_supplicant embedded by the HAL | no separate daemon |

**Where a fix belongs** — choose the lowest layer that owns the broken contract:
malformed TLV / retry / routing / state eligibility → `unified-wifi-mesh`;
EasyMesh↔webconfig/action conversion → the `unified-wifi-mesh` agent adapter;
decoded config / cache / VAP service / queue → `ccsp-one-wifi`; VAP-to-interface
mapping, mgmt headers, nl80211 attrs, embedded hostapd/supplicant, kernel error
propagation → `rdk-wifi-hal`; AL socket / 1905 Ethernet delivery →
`ieee1905`/`libalsap`; an unsupported *simulated-radio* capability → an explicitly
`HWSIM_RADIO`-gated workaround (only if the defect isn't real on hardware); LXD
device / volume / stale wiphy / namespace lifecycle → deploy tooling. Don't hide
a real correctness bug behind a hwsim guard.

**Central mental model:** EasyMesh decides and communicates desired mesh state;
OneWifi converts desired Wi-Fi state into service operations; the HAL converts
those into hostapd/supplicant + nl80211 work; the kernel + hwsim (± wmediumd)
determine what actually happens. **Success at one boundary is never proof of
success at the next** — diagnose bottom-up. Per-patch detail: [patches.md](patches.md).

## Control plane vs data plane

**Control:** `em_ctrl → (AL-SAP) → ieee1905 → 0x893a CMDUs over backhaul →
ieee1905 → em_agent → (RBus WebConfig) → OneWifi/HAL`.

**Data:** a client's frames go `wlan0 → bpiap fronthaul AP → bpiap brlan0 →
bpiap wifi1.3 backhaul STA → (4-address/WDS on ch36) → controller wifi1.1.staN
WDS port → controller brlan0 → DHCP/gateway 10.0.0.1`. Association alone is
insufficient: the extender's backhaul STA must be a `brlan0` member and the
controller must create and forward an AP_VLAN/WDS port for it, or management
frames flow while client data/DHCP/EAPOL/1905 do not.

## How the mesh forms

Each layer depends on the one below.

```text
L7 client data works through the extender
L6 client associates to provisioned fronthaul
L5 topology/device/radio/BSS model synchronizes
L4 controller sends WSC M2; agent applies SSIDs/security
L3 agent sends AP-Autoconfiguration Search + WSC M1
L2 IEEE 1905 frames cross the wireless bridge
L1 extender backhaul STA associates; WDS bridge forwards
L0 hwsim radios/channels, containers, services (± wmediumd) exist
```

Onboarding sequence: `mesh_backhaul` beacons → extender STA auth/assoc/4-way →
controller creates the WDS port and both sides forward → AP-Autoconfiguration
Search (0x0007) / Response (0x0008) → WSC **M1** (agent radio identity + caps) →
WSC **M2** (controller-selected SSID/security/role) → agent validates RUID,
converts to WebConfig, drives OneWifi/HAL to create VAPs → topology/BSS/metrics
reports → controller updates `OneWifiMesh`. (WSC here is the config exchange
embedded in AP-autoconfiguration, not a consumer WPS button.)

## Current state and limits

**Proven medium/radio foundation.** hwsim runs 24 radios / two channel contexts;
one wiphy per BPI carries concurrent 2.4 + 5 GHz VAP families. The multichannel
wmediumd registers, mediates radios across container netns, handles multiple
BSSIDs, learns active frequency per owned VIF, suppresses off-channel ACKs, and
isolates interference by center frequency; its deterministic gates pass. No
wmediumd redesign is indicated by the remaining EasyMesh issues.
(See [wmediumd-multichan.md](wmediumd-multichan.md).)

**Working.** A correctly-deployed fresh single-phy extender associates, completes
M1/M2, reaches topology synchronization, and applies fronthaul config. A client
that associates — including on the controller's **colocated agent** — is reported
to the controller data model (`/api/v1/clients` active, `STAList Associated=1`);
this colocated-agent full-list reporting path was fixed (ccsp-one-wifi-libwebconfig
0001, see [patches.md](patches.md)). Commanded client steering works end-to-end
via the shipped `steer_drv`/`steer.sh` (see [steering.md](steering/steering.md)).

**Still converging.**
- **Issue E (per-radio first-onboard race):** one arbitrary radio can miss its
  first-pass M2/config; a re-onboard applies the rest. Not a wmediumd loss.
- **Issue B (redeploy identity):** a new AL-MAC with inherited old RUIDs is a
  proven onboarding blocker. Clean-baseline defense = coherent identity handling;
  durable fix = preserve-or-regenerate the whole {AL-MAC, RUID-set} tuple.
- The controller does not yet reap every dead device (hardening, separate from
  the RUID-collision cause).
- 6 GHz is excluded operationally **on the 6.8 lab**; on a **7.0 host** 6 GHz is
  IR-capable and beacons standalone (proven — see
  [6ghz.md](6ghz.md) (appendix)),
  but EasyMesh tri-band there is still gated by the layer's unconditional
  6 GHz-disable + WPA2 forcing ([TODO.md](TODO.md) 2–3). The hwsim/wmediumd
  multichannel capability is a disposable kernel relaxation + a locally built
  wmediumd, not a productized package.
- The DB can represent desired/configured VAP state before every netdev is up —
  reconcile SQL rows with live `iw`/bridge/association evidence.

For reliable experiments: start from a clean, identity-consistent single-phy
deploy, 2.4 + 5 GHz only, pass each layer's health gate, then add clients,
attenuation, or steering.
