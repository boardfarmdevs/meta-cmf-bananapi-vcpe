# Lab startup and topology formation

This reference describes the exact startup transaction used by the portable
20-client RDK EasyMesh and prplMesh laboratories. It separates three things
that are easy to confuse:

1. provisioning permanent containers and radio identities;
2. starting processes and admitting nodes into the EasyMesh model; and
3. selecting a wireless backhaul parent or a fronthaul AP.

wmediumd supplies frame delivery and RF conditions. It does **not** choose an
EasyMesh parent, assign a client to an AP, or create the topology shown by a
Web application.

## Final topology at a glance

Both accepted 20-client profiles contain one Controller with a colocated
Agent, four external Agents, ten private clients, and ten IoT clients. Both
currently use a 5 GHz/channel 36 wireless-backhaul star:

```text
                               EasyMesh Controller
                                       |
                              colocated root Agent
                            5 GHz mesh_backhaul AP
                         /          /       \          \
                  Extender-1  Extender-2  Extender-3  Extender-4
                       |           |           |           |
                       +--- private_ssid and iot_ssid ------+
                                20 WLAN clients

               hwsim frames from every radio pass through wmediumd
```

The RDK WebUI draws the Controller and its colocated `Agent-1` as two nodes
joined by an Ethernet edge. The prplMesh UI presents the same functional
combination as one Controller node. RDK consequently shows six mesh-model
nodes while prplMesh shows five; this is a presentation/modeling difference,
not an extra physical mesh node.

## Common VM and radio boundaries

The downloadable artifact is a thin Ubuntu 24.04/Linux 7.0 LXD virtual
machine. On first boot it has the source, images, patched kernel/hwsim support,
and systemd units, but no nested lab-node containers. The outer host only runs
the VM and exposes the UI ports. Inside the VM:

- the guest kernel owns `mac80211_hwsim` and the complete radio pool;
- nested LXD containers run the Controller, Agents, and clients;
- every provisioned radio has a stable identity derived from its permanent
  hwsim MAC, independent of transient `phyN` or `wlanN` enumeration;
- nested containers have LXD autostart disabled; the lab lifecycle service,
  rather than LXD previous-power restoration, owns startup order; and
- userspace wmediumd is the default accepted medium backend.

The stable inventory is larger than the set of radios currently sending
frames. A configured but stopped radio remains a known identity. It is
**dormant**: no process in its container transmits frames, so wmediumd has
nothing to deliver for it. A radio need not be deleted from and re-added to the
medium merely because its container stops and starts.

## RDK EasyMesh: first boot from an empty VM

The RDK 20-client appliance contains 25 nested instances when complete:

```text
1 bpibroadband + 4 bpiap extenders + 20 wlan-client containers = 25
```

One BPI hwsim wiphy emulates the MediaTek-style single-wiphy device. OneWifi
creates the 2.4, 5, and 6 GHz AP/VAP interfaces on that wiphy. The four
extenders additionally create `wifi1.3` as the 5 GHz backhaul STA. The final
wmediumd inventory therefore contains 25 base radio identities, even though
the EasyMesh Controller model contains 15 logical radios and 50 BSS records.

### System startup order

On a clean imported VM, systemd runs these stages:

```text
network and LXD/Docker
        |
        +--> easymesh-hwsim-pool.service
        |      create/name the persistent hwsim pool
        |
        +--> boardfarm-lab.service
        |      create br-wan101 and start DHCP/NAT containers
        |
        +--> easymesh-thin-firstboot.service
        |      verify source/image hashes
        |      provision and accept the 25-instance lab
        |
        `--> easymesh-lab.service
               consume the one-time running-state handoff
               perform final acceptance without reconstructing again
```

Boardfarm is infrastructure, not part of EasyMesh. It supplies DHCP and NAT on
`br-wan101`; `bpibroadband` attaches its WAN to that bridge and receives the
`erouter0` address used for Internet reachability.

The one-time provisioning itself is deliberately incremental:

1. Stop any partial medium, clients, or BPI instances left by an interrupted
   first boot.
2. Create and start `bpibroadband`; preserve its `/nvram` identity; wait for
   WAN, OneWifi, both IEEE 1905 paths, Controller, colocated Agent, CLI, and the
   initial Controller database model.
3. Create and start `bpiap`; wait for its tri-band WSC/onboarding model and its
   physical `wifi1.3` backhaul.
4. Create and start `bpiap-001`; wait for the same gates.
5. Start wmediumd temporarily with the incomplete three-BPI roster at
   `SNR=40`.
6. Create the first five private-client containers and wait for association,
   DHCP, and Controller visibility.
7. Create `bpiap-002`, refresh wmediumd so its permanent radio is present, and
   wait for complete onboarding.
8. Create `bpiap-003`, refresh wmediumd again, and wait for complete
   onboarding.
9. Complete the 20-client pool. The pool stops wmediumd while new hwsim radios
   are being added, lets the kernel's built-in hwsim medium carry this bounded
   provisioning traffic, and starts wmediumd once with the final 25-radio
   matrix.
10. Wait for exactly ten `private_ssid` and ten `iot_ssid` clients, enable
    periodic metrics reporting, and write the one-time handoff.
11. `easymesh-lab.service` verifies the already-running 25 instances and
    accepts the handoff. It does not stop and rebuild the lab a second time.

The current `rdkeasymesh-20-0901` evidence recorded hwsim setup at 06:42:32
UTC, Boardfarm readiness at 06:43:11, EasyMesh provisioning from 06:43:11 to
07:01:56, and final first-boot acceptance at 07:02:14 on 2026-09-02.

### Ordinary RDK guest reboot

After first boot, permanent definitions and `/nvram` identities already
exist. The normal cold-reconstruction transaction is:

1. Start/verify Docker, nested LXD, Boardfarm, `br-wan101`, DHCP, and NAT.
2. Stop wmediumd, stop every managed client and BPI container, and reclaim only
   transient VAPs. This removes any LXD previous-power-state ambiguity.
3. Start `bpibroadband` and all four extenders in a bounded overlap. The
   containers may launch together, but readiness remains ordered: first the
   Controller/colocated Agent, then all four completely onboarded extenders.
4. Require the Controller database to converge to 5 devices, 15 radios, and
   50 BSS records.
5. Enable the initial EasyMesh metrics-reporting policy.
6. Start 20 client containers in bounded parallel batches and require physical
   association plus DHCP for every client.
7. Start userspace wmediumd once with the complete permanent 25-radio roster
   and default `SNR=40`.
8. Require 20 unique fronthaul clients, 24 associated STA records (20 clients
   plus four backhaul STAs), 20 current RCPI values, stable process restart
   counts, a stability window, and client traffic.

Before step 7, mac80211_hwsim's built-in kernel delivery permits onboarding
and association. Once wmediumd registers, it owns simulated delivery and
applies the controlled multichannel RF model. wmediumd has a fixed base-radio
roster for that run and learns the dynamic OneWifi VAP/BSSID aliases from live
frames. It does not continuously rediscover LXD containers.

### Why the RDK topology becomes a star

The default RDK startup does not ask wmediumd to draw a star and it does not
run a hidden topology optimizer. The root Agent's 5 GHz `mesh_backhaul` AP is
the usable parent during ordinary extender onboarding. Each extender receives
credentials through WSC and its `wifi1.3` STA associates to that gateway BSSID.
An extender's own backhaul AP is intentionally lazy and is not selected as a
parent during this default transaction. Controller readiness also precedes the
extender readiness gates, reinforcing the direct-parent result.

The observed live topology confirms the result: all four extenders report the
same upstream BSSID, `02:00:00:12:18:6f`, owned by `Agent-1`, on 5 GHz/channel
36.

RDK multihop is a separate, explicit operation. The multihop test:

1. enables a prospective parent extender's lazy backhaul AP with
   `Device.WiFi.AccessPoint.14.ForceApply`;
2. discovers that AP's live BSSID;
3. writes it to the child extender's `Device.WiFi.STA.2.Bssid` through RBUS;
4. waits for the real `wifi1.3` association and forwarding; and
5. verifies that the Controller's protocol-derived topology reports the same
   parent.

`star`, `branch`, and `chain` are therefore real backhaul associations, not
WebUI arrangements or simulated wmediumd links. `restore` explicitly returns
all four children to the gateway BSSID.

## prplMesh: first boot from an empty VM

The prplMesh 20-client appliance also creates 25 nested containers:

```text
1 prpl-controller + 4 prpl-agent containers + 20 prpl-client containers = 25
```

Its radio model differs from RDK. The Controller/colocated Agent and each
external Agent receive three independent hwsim wiphys, one per band. Clients
receive one wiphy each:

```text
5 mesh nodes * 3 radios + 20 client radios = 35 assigned radios
40-radio pool - 35 assigned radios             = 5 dormant spares
```

### System and mesh startup order

`prplmesh-lab.service` starts after networking and nested LXD. On first boot,
its thin-image preparation requires an empty nested inventory and then:

1. Loads `mac80211_hwsim` with 40 radios, three channels, 6 GHz regulatory test
   support, and the userspace-medium backend. Each host interface is renamed
   `prpl-rNN` from its permanent radio MAC.
2. Creates the Controller, four Agent, and 20 client containers and attaches
   their permanent assigned wiphys. All definitions retain
   `boot.autostart=false`.
3. Starts wmediumd **before any mesh node** with the complete 40-radio
   configuration. The 35 assigned identities and five spare identities are
   already in the matrix. Until their containers/interfaces send frames, they
   are dormant; the five spares remain dormant for the entire 20-client run.
4. Starts and configures `prpl-controller`, publishes its three radios and
   credentials, and waits five seconds for the Controller path.
5. Starts Agents 1 through 4 sequentially. Container launch can optionally be
   overlapped, but radio setup and EasyMesh admission remain serialized to
   avoid concurrent nl80211/libbwl state mutation. Each Agent must become
   visible in NBAPI and connected to its Controller before the next admission
   completes.
6. Starts clients in batches of ten. Each client setup applies its SSID and an
   explicit allowed-band/frequency constraint, then waits for both physical
   association and NBAPI ownership. If the physical link exists but the model
   misses the event, the bounded recovery performs one disconnect/reconnect.
7. Starts the shared wmediumd Console, the loopback NBAPI topology adapter, and
   the Controller UI; waits for ports 8090, 8091, and 8092; runs first-boot
   acceptance; and removes the first-boot marker.

The current `prplmesh-20-0901` first boot ran from 06:52:55 to 07:09:08 UTC on
2026-09-02. An ordinary guest reboot skips container creation and first-boot
acceptance, but repeats the controlled medium, Controller, serialized Agent,
client, and UI startup sequence using the same permanent identities.

### Why the prplMesh topology becomes a star

Here the star is completely declarative and deterministic. The appliance has:

```text
DEFAULT_TOPOLOGY=star
```

For `star`, `parent_backhaul_bssid()` maps every external Agent to mesh node
zero, selects node zero's 5 GHz radio, and calculates its backhaul BSSID. The
Agent setup receives that exact BSSID and configures its backhaul supplicant to
use it. Every Agent therefore joins the Controller/colocated Agent on
5 GHz/channel 36.

Selecting `branch` or `chain` changes only this parent-BSSID mapping. It does
not renumber radios, rebuild the permanent roster, or rely on a wmediumd RF
trick:

```text
star:   Controller -> {E1, E2, E3, E4}
branch: Controller -> E1 -> {E2, E3}; E2 -> E4
chain:  Controller -> E1 -> E2 -> E3 -> E4
```

## How fronthaul clients select an AP

Backhaul parent selection and client AP selection are independent. The star
does not imply that clients must use the root. Every node advertises the same
`private_ssid` and `iot_ssid` on its available bands. A client's
wpa_supplicant scans eligible BSSs and selects an AP based on its allowed band,
observed candidates, signal/order, and association timing.

At baseline, wmediumd gives eligible links the same default `SNR=40`. No
optimizer has run, and no startup policy assigns client X to extender Y.
Consequently:

- the configured band can be deterministic;
- the initial AP owner within that band is an emergent association result; and
- the exact client-to-Agent distribution may differ after another cold start
  even while all acceptance criteria continue to pass.

The configurator, steering command, or optimizer can subsequently introduce
different link conditions and/or issue a BTM steering request. The authoritative
result is the physical association plus Controller ownership, not the command
acknowledgement or a drawn line.

### RDK client-band policy

For the 20-client profile, private ordinals 1 through 8 and all ten IoT clients
use `band=auto`. Private ordinal 9 is constrained to 2.4 GHz and private
ordinal 10 uses 6 GHz with SAE. In the current baseline, every `auto` client
selected 5 GHz, producing 18 clients on channel 36, one on 2.4 GHz/channel 6,
and one on 6 GHz/channel 1.

The current observed AP ownership is:

| RDK node | Clients |
| --- | --- |
| Agent-1 | `sta-03`, `sta-05`, `sta-06`, `sta-0d`, `sta-0e`, `iot-11`, `iot-12` |
| Extender-1 | `iot-15`, `iot-18` |
| Extender-2 | `iot-10` |
| Extender-3 | `sta-07`, `sta-0b`, `sta-0c`, `iot-14`, `iot-16`, `iot-17` |
| Extender-4 | `sta-04`, `sta-0a`, `iot-0f`, `iot-13` |

The displayed suffixes come from the stable hwsim/client MAC identities; they
are not the private/IoT cohort ordinal used by the pool builder.

### prplMesh client-band policy

prplMesh alternates private and IoT containers and applies the same explicit
ten-client band pattern independently to each cohort:

```text
cohort ordinals 1,7       -> 2.4 GHz
cohort ordinals 2,3,5,8,9 -> 5 GHz
cohort ordinals 4,6,10    -> 6 GHz
```

The current result is therefore exactly four clients on 2.4 GHz/channel 6,
ten on 5 GHz/channel 36, and six on 6 GHz/channel 5. AP selection within each
allowed band was still performed by wpa_supplicant. The current observed
ownership is:

| prplMesh node | Clients |
| --- | --- |
| Controller/Agent | `sta-04`, `sta-10`, `iot-02`, `iot-03`, `iot-07`, `iot-10` |
| Extender-1 | `sta-01`, `sta-03`, `sta-05`, `sta-09`, `iot-05`, `iot-06`, `iot-08` |
| Extender-2 | `sta-06`, `sta-08`, `iot-01`, `iot-04`, `iot-09` |
| Extender-3 | `sta-02` |
| Extender-4 | `sta-07` |

## What “current topology” means

The startup target is deterministic at the inventory, identity, SSID, band,
and backhaul-parent levels. It is intentionally not deterministic at the
initial fronthaul AP-owner level under an equal-SNR world. The current WebUI
topology is reconstructed from live Controller data after onboarding; the
wmediumd Console independently reconstructs active RF ownership from
infrastructure data and acknowledged association traffic. Agreement between
the physical link, Controller model, and Console is the acceptance condition.

The current stars are therefore well-defined:

- **RDK:** default controller-first onboarding to the gateway backhaul BSSID;
  explicit RBUS parent selection is used when a test requests multihop.
- **prplMesh:** explicit `DEFAULT_TOPOLOGY=star` parent-BSSID mapping during
  every Agent startup.
- **Both:** wmediumd transports and modifies frames but does not select the
  parent or decide where a client associates.
