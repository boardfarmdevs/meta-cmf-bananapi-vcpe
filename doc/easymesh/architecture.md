# Architecture

## What is simulated

The physical Banana Pi R4 platform is replaced by x86 RDK-B userspace in LXD.
The radio and propagation environment are simulated; the Wi-Fi, bridging,
IEEE 1905.1, WSC, topology and steering protocol paths remain real.

```text
physical platform                 evaluation lab
-------------------------------   --------------------------------------
BPI controller board              bpibroadband LXD container
BPI extender board                bpiap[-NNN] LXD container
MT7988 radios                      mac80211_hwsim wiphy
radio propagation                 patched multichannel wmediumd
phone/laptop                      WNM-capable wlan-client LXD container
board kernel                      shared Linux 7.0 VM/host kernel
```

`bpibroadband` contains an EasyMesh controller and a colocated agent. Each
`bpiap` is an agent-only extender. The accepted scale is four extenders and ten
client stations.

## Topology

```text
                             Linux 7.0 runtime

 Boardfarm WAN/DHCP                                             WebUI/API
 br-wan105                                                        :8888
      | erouter0                                                     |
 +----+--------------------------------------------------------------+--+
 | bpibroadband                                                         |
 | controller -- MariaDB model -- em_cli                                |
 | colocated agent -- OneWifi -- HAL -- one hwsim wiphy                  |
 | brlan0: 2.4/5/6 GHz fronthaul + wireless backhaul AP                 |
 +-------------------------+---------------------------------------------+
                           )) 5 GHz 4-address/WDS backhaul
 +-------------------------+---------------------------------------------+
 | bpiap[-NNN] extender: agent -- OneWifi -- HAL -- one hwsim wiphy      |
 | brlan0: backhaul STA + 2.4/5/6 GHz fronthaul                          |
 +-------------------------+---------------------------------------------+
                           )) fronthaul
                    wlan-client[-NNN]

 host/VM kernel: cfg80211 + mac80211 + patched mac80211_hwsim
 host/VM process: one patched wmediumd for every active hwsim radio
```

Only the controller has a wired WAN leg. Do not connect an extender to the
controller LAN: wireless backhaul already joins their bridge domains and a
second path creates a loop. Client `eth0` is management-only; WLAN tests must
use `wlan0`.

## Radio model

Every BPI container receives exactly one hwsim wiphy. `FEATURE_SINGLE_PHY`
projects it into three logical EasyMesh radios:

```text
one hwsim wiphy
|-- wifi0    2.4 GHz, channel 6
|-- wifi1    5 GHz, channel 36
`-- wifi2    6 GHz, 20 MHz, operating class 131
```

This is a hard invariant. Three physical wiphys are not equivalent and break
OneWifi's single-phy assumptions.

The official lab uses Linux 7.0.0-28 with `radios=24 channels=3 regtest=5`.
`regtest=5` selects the 6 GHz-capable `custom_03` regulatory domain. 2.4, 5 and
6 GHz have been validated together. Linux 6.8 is no longer an official runtime
target because its 6 GHz regulatory and multi-context behavior differs.

Bare hwsim gives every link a flat signal. wmediumd owns RF delivery,
interference and per-radio-pair SNR. Frequency belongs to the active VIF, not to
the parent wiphy; the multichannel patches isolate simultaneous 2.4/5/6 GHz
contexts.

## Identities

```text
AL-MAC    one IEEE 1905/EasyMesh device
RUID      one logical radio owned by that device
BSSID     one AP service on a radio
STA MAC   a client or backhaul station interface
```

A device identity is `{AL-MAC, RUID set}`. Preserve all of it when restarting
the same logical device, or regenerate all of it with `bpi.sh -F`. Reusing old
RUIDs under a new AL-MAC creates a stale-device collision.

## Processes and interfaces

| Boundary | Interface |
| --- | --- |
| browser to CLI/UI | HTTP on controller port 8888 |
| `em_cli` to controller | libemcli/TLS command channel |
| controller/agent to 1905 | local AL-SAP socket |
| controller to agents | IEEE 1905.1 CMDUs, EtherType `0x893a` |
| agent to OneWifi | RBus WebConfig subdocs and raw-frame actions |
| OneWifi/HAL to kernel | embedded hostap/supplicant plus nl80211 |
| hwsim to wmediumd | generic netlink registration/frame transport |
| configurator to wmediumd | Unix `SOCK_SEQPACKET`, `/run/wmediumd-control.sock` |
| controller model | MariaDB database `OneWifiMesh` |

Runtime ownership:

| Component | Services/processes |
| --- | --- |
| controller | `em_ctrl`, `ieee1905_em_ctrl`, MariaDB |
| colocated/remote agent | `em_agent`, `ieee1905_em_agent` |
| Wi-Fi management | `onewifi`; HAL and hostap state machines are embedded |
| UI/CLI | `em_cli` / `onewifi_em_cli` |
| client | standalone WNM-enabled `wpa_supplicant` |
| medium | host/VM `wmediumd.patched` |

## Onboarding sequence

```text
1. hwsim wiphy enters the container namespace.
2. OneWifi creates the controller backhaul/fronthaul VAPs.
3. Extender backhaul STA associates and completes the four-way handshake.
4. Authorized WDS/AP-VLAN interfaces join brlan0 and forward.
5. Agent sends AP-Autoconfiguration Search; controller responds.
6. Agent sends WSC M1 with RUID and capabilities.
7. Controller sends WSC M2 with SSID, security and role.
8. Agent converts M2 to WebConfig and OneWifi creates its VAPs.
9. Topology, radio, BSS and client reports converge in the controller model.
```

The controller model gate is not interchangeable with service readiness. A
healthy scaled lab must show five agents, fifteen radios, fifty BSSs and ten
active clients.

## Control and data planes

Control:

```text
em_ctrl -> AL-SAP -> ieee1905 -> WLAN -> ieee1905 -> em_agent
        -> RBus/WebConfig -> OneWifi -> HAL/nl80211
```

Client data through an extender:

```text
client wlan0 -> extender fronthaul AP -> extender brlan0
 -> extender backhaul STA -> controller WDS port -> controller brlan0
 -> DHCP/gateway/WAN
```

Association without an authorized forwarding WDS path is not success: control
frames may be visible while DHCP and data fail.

## Failure localization

Diagnose from the bottom up:

```text
radio/channel/regulatory state
-> AP and backhaul association/security
-> WDS and bridge forwarding
-> IEEE 1905 transport
-> WSC M1/M2 transaction
-> WebConfig/OneWifi application
-> topology/radio/BSS/client model
-> steering decision and BTM outcome
```

Place a fix at the lowest owner of the broken contract. A malformed nl80211
attribute belongs in HAL; protocol transaction state belongs in
unified-wifi-mesh; unsupported simulated-radio behavior belongs behind an hwsim
feature gate; namespace and persistent-volume lifecycle belongs in `gen/`.

## Current boundaries

- Clean deployment, commanded steering and unattended VM cold-boot
  reconstruction are validated at four extenders and ten WLAN clients.
- The wmediumd configurator safely controls radio-pair SNR; frequency-keyed
  same-wiphy band steering is not implemented.
- One historical RBUS raw-frame provider delivery miss succeeded on immediate
  retry. It has not recurred across 143 post-AL-SAP-fix commanded steers and is
  now covered by transaction-level command/completion journals; no duplicate
  BTM workaround is present.
- No autonomous steering evaluator is currently proven. The planned decision
  engine is completely external to the BPI containers; see
  [optimizer.md](optimizer.md) and [steering.md](steering.md).
