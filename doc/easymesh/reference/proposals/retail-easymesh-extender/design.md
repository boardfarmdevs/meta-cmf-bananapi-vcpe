# A retail EasyMesh extender on the RDK lab's controller

**Status:** Proposed experiment; nothing connected yet. Discovery evidence only.

**Prepared:** 25 September 2026.

**Device:** TP-Link RE653BE, supplied by the user. Hardware revision and firmware
version not yet recorded.

## 1. Question

Does an unmodified, off-the-shelf EasyMesh extender onboard to the RDK lab's
EasyMesh controller over a wired port, and appear in its topology next to the
lab's native agents and the OpenSync pods that EMOSA hands to it?

This is an interoperability experiment between two vendors' implementations. It
is not part of the room model or the room qualification (§5).

## 2. What is already established

A passive capture on rev130 shows the RE653BE searching for a controller over
Ethernet while in extender mode with EasyMesh enabled. No controller was present.

| Item | Observed |
| --- | --- |
| Capture | rev130 `/home/rev/easymesh-captures/re653be/` (`EASYMESH-1905-REPORT.md`, `discovery-snapshot.pcapng`, decoded frames, packet table, statistics); snapshot SHA-256 `c62f4cef9ba4a15c61d1dec4382c74712fae87d0f8477bc253917679097e4490` |
| Link | Host USB Ethernet (ASIX AX88179B) in an isolated network namespace, no IP, no controller, no uplink |
| Window | 1,179 packets over 685 s, 25 September 2026 13:23:49–13:35:14 PDT |
| 1905 AL MAC | `6c:4c:bc:58:28:35` (also the Ethernet source) |
| AP-Autoconfiguration Search (`0x0007`) | one per band, 2.4 GHz and 5 GHz, every 5.0 s, no backoff; first 58 s after link-up |
| Search TLVs | AL MAC, Searched Role Registrar, Frequency Band, Supported Service Multi-AP Agent, Searched Service Multi-AP Controller, Multi-AP Profile **2** |
| Topology Discovery (`0x0000`) | every 60 s |
| Framing | multicast `01:80:c2:00:00:13`, no VLAN tag, search relay bit set, no fragmentation |
| No 6 GHz search | not proof the device lacks 6 GHz |
| Other traffic | ARP (it announces `192.168.0.254`), mDNS, ICMPv6, and **DHCP Offers/ACK sent by the extender** (its own setup DHCP server) |

Not established: any controller response, WSC (M1/M2), credential handling,
capability report, or whether the firmware accepts a controller from another
vendor. TP-Link documents EasyMesh with its own routers; cross-vendor
onboarding is exactly what the experiment tests.

## 3. How it would attach

The RDK lab VM `rdk-emosa` (rev120) already has a wired port into the gateway's
LAN: the VM bridge `br-emosa` is `bpibroadband`'s `eth2`, a member of `brlan0`
(emosa-lab `deploy/rdk-lab`, `lab.sh lanport`). EMOSA's agents and its gateway
tunnel point (`em-gtp`) sit on it; it is the port meant for wired extenders.

```
 RE653BE Ethernet ── USB NIC on rev120 ── bridged into rdk-emosa's br-emosa
                                           └─ bpibroadband eth2 ∈ brlan0 ── RDK controller
```

1. A free wired interface on rev120 (for example the same USB adapter, moved
   from rev130), added to `rdk-emosa` as a bridged NIC on `br-emosa` or passed to
   the VM and enslaved there.
2. **First passive:** capture EtherType `0x893A` on `br-emosa` with the extender
   connected but the controller's answers not yet expected to succeed; confirm the
   searches arrive unchanged (same TLVs, no VLAN, relay bit).
3. **Then live:** the RDK controller answers searches it can serve. Expected, not
   yet observed: AP-Autoconfiguration Response (`0x0008`), M1 and M2
   (`0x0009`), Topology Query/Response, AP Capability, policy and channel
   exchanges, as with the lab's own extenders.

## 4. Risks and lab effects

- **Its DHCP server.** In setup mode the extender answers DHCP (it sent Offers and
  an ACK in the capture) and announces `192.168.0.254`. On `brlan0` it could lease
  addresses to lab clients. Before connecting, confirm it stops serving DHCP in
  extender mode with an upstream present, or keep it on a filtered port
  (`ebtables` dropping DHCP server replies from its MAC) until it does.
- **Real RF.** Its radios are real, not on wmediumd. It appears in the controller
  topology and em_cli but not in the room model; the simulated clients cannot
  reach it, real devices near rev120 can. Once configured it broadcasts the lab's
  SSIDs over the air with the lab's passphrases.
- **Profile and security.** It advertises Profile 2; the lab's controller and M2
  settings are WPA2-PSK. A Wi-Fi 7 device may insist on WPA3 for some bands.
- **Topology limits and names.** It attaches over Ethernet under the controller,
  like the OpenSync pods. Patch 0211 raised the controller's topology children
  per node from 5 to 16. em_cli numbers Ethernet agents Agent-N in traversal
  order, and the lab relies on Agent-1 being the gateway's co-located agent;
  0212 numbers OpenSync pods apart (Pod-N), but a retail agent is an ordinary
  EasyMesh node and can still take Agent-1. Identify the gateway's agent by
  identity rather than order before relying on names with it connected.
- **Controller state.** The room preflight counts the controller's model rows
  exactly (devices, radios, BSSes, associations). A retail agent adds rows that
  stay after it leaves; remove them with em_ctrl stopped (the same way the
  EMOSA pods' rows were removed) before any room run.
- **Capture contents.** Capture files of the live exchange contain WSC encrypted
  settings and device identities. Keep them outside the repository, as now.

## 5. Scheduling and acceptance

Run it outside room qualification: with the room service stopped, or after the
room suite, then restore the controller model (§4). Suggested order: after the
EMOSA room integration and its 24-room qualification.

Acceptance, each with retained 1905 captures:

1. The controller answers its search and completes M1/M2; the extender applies
   the lab's SSIDs (visible over the air).
2. It appears in the controller topology and em_cli with its own identity, next
   to the gateway's agent, the four lab extenders and the OpenSync pods.
3. A real client associates to it and reaches the lab's network through
   `brlan0`.
4. Optional: the controller steers a real client to or from it (Client Steering
   Request `0x8014`, BTM).

A failure at any stage is recorded with its capture, not worked around in the
controller.
