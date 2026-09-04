# Commanded EasyMesh steering

This reference describes exactly how `gen/steer.sh` performs one named,
controller-commanded client steer in the RDK EasyMesh lab. It separates the
real EasyMesh steering transaction from the temporary RF preparation used to
make a laboratory demonstration repeatable.

## Purpose and boundary

The command:

```sh
gen/steer.sh sta-05 extender-1
```

means: ask the EasyMesh controller to move the station displayed as `sta-05`
to the fronthaul BSS on `Extender-1` that has the station's current SSID and
band.

The controller and serving Agent still use the normal EasyMesh and IEEE
802.11v path. The script does not rewrite the controller database, directly
change the client's BSSID, or claim that a BTM request can force a client to
move.

The default mode temporarily makes the requested result RF-favorable. Use
`--request-only` when the purpose is to observe the station's unassisted BTM
decision.

## Components and interfaces

```text
operator
   |
   | gen/steer.sh CLIENT TARGET
   v
topology API ---------> resolve STA, serving BSS, SSID, band and target BSS
identity inventory ---> resolve stable client and mesh-radio identities
   |
   v
steering-rf-bias.py
   |
   | atomic, frequency-qualified SNR updates
   v
wmediumd control socket (/run/wmediumd-control.sock)
   |
   v
bpibroadband:/usr/bin/steer.sh STA_MAC TARGET_BSSID
   |
   v
EasyMesh Controller -> serving Agent -> IEEE 802.11v BTM Request -> station
   |
   v
physical link + controller topology verification
```

The RF helper supports both the normal userspace wmediumd control socket and
the optional kernel-medium actuator. Userspace wmediumd remains the default.
For userspace wmediumd, `ControlClient.apply_frequency()` sends the custom
control operation `OP_APPLY_FREQUENCY` (`6`) over the Unix `SOCK_SEQPACKET`
socket. One operation carries the complete generation rather than exposing a
partially changed RF matrix.

## Name and target resolution

The outer script resolves names from live state rather than a static table:

- `sta-05` and `iot-18` map to the stable hwsim station MAC encoded in the
  fifth octet, for example `sta-05` becomes `02:00:00:00:05:00`.
- The requested `sta-` or `iot-` prefix must agree with the SSID reported for
  that MAC. This prevents a valid MAC on `private_ssid` from being addressed
  incorrectly as an IoT client.
- `extender-N` selects that live topology node.
- `agent-1` selects the Agent colocated with the controller. `controller` is
  not a wireless target because it does not represent a fronthaul BSS.
- Without overrides, the target must advertise the station's current SSID and
  band. `--band` and `--ssid` can request another valid combination.
- A full STA MAC and target BSSID can be supplied instead of display names.

Resolution must produce exactly one current station placement and exactly one
target BSS. Missing, duplicate, ambiguous, or already-current targets fail
before the medium or controller is changed.

The target AP interface's live `iw dev` frequency is authoritative. The script
maps that frequency to the IEEE operating class and channel and passes both
explicitly in the controller command. `/api/v1/bsses` is retained as a
diagnostic because its configured channel can differ from the frequency on
which an hwsim AP actually started. This was observed on 6 GHz: the model
reported channel 37 while `wifi2` was live at 5955 MHz, channel 1.

Current fallback values, used only before live resolution, are:

| Band value | Band | Channel | Frequency |
| ---: | --- | ---: | ---: |
| `0` | 2.4 GHz | 6 | 2437 MHz |
| `1` | 5 GHz | 36 | 5180 MHz |
| `3` | 6 GHz | 1 | 5955 MHz |

## Deterministic RF preparation

For `gen/steer.sh`, the values are explicitly passed to
`gen/tests/steering-rf-bias.py`:

| Relationship to the selected client | SNR | Purpose |
| --- | ---: | --- |
| Requested target AP | `+60 dB` | Make the exact target exceptionally strong and reliable. |
| Current/source AP | `+20 dB` | Keep the current association viable so movement is attributable to BTM rather than link loss. |
| Every other mesh AP | `-20 dB` | Remove unintended alternatives and make the requested outcome unambiguous. |

With the lab's modeled noise floor of approximately `-91 dBm`, these values
appear roughly as:

```text
target:  -91 + 60 =  -31 dBm
source:  -91 + 20 =  -71 dBm
others:  -91 - 20 = -111 dBm
```

These are intentionally separated laboratory levels, not a claim that a home
normally has this RF geometry. The relevant invariant is:

```text
target is excellent > source remains usable > all other choices are unusable
```

The helper itself has a `40 dB` source default for direct standalone use, but
the supported `gen/steer.sh` path explicitly overrides it with `20 dB`.

### What is actually changed

The SNR is applied between the selected station's stable hwsim radio identity
and every provisioned mesh-radio identity. Both directions are updated:

```text
station radio -> mesh radio
mesh radio    -> station radio
```

Each update is qualified by the selected frequency. A 5180 MHz steer therefore
does not alter the same pair's 2.4 or 6 GHz behavior. This is essential for the
RDK single-wiphy model, in which one physical simulated radio represents
several logical band contexts.

The operation does not change:

- any other client's links;
- mesh backhaul links;
- OneWifi transmit-power configuration;
- the controller policy or database;
- the target AP's SSID, channel, or BSSID.

### Atomic update and exact restoration

Before applying the bias, the helper reads the base pair matrix and all
frequency-qualified overrides. It accepts the snapshot only if the control
generation remains unchanged across those reads.

It writes the effective prior value and whether it was inherited or explicitly
overridden to a temporary state file, then applies every directional update in
one new generation. Restoration checks that the medium instance has not been
replaced and atomically reinstates those exact values and override flags.

The exit trap restores the medium after success, refusal, timeout, interruption
or most other failures. If exact restoration cannot be proven, the state file
is retained and the command reports a warning instead of silently declaring
success.

## Default execution sequence

1. Read `/api/v1/topology` and resolve the live client and target.
2. Validate the controller and client containers.
3. Resolve stable radio identities from
   `/run/meta-cmf-wmediumd/identity-inventory.json`.
4. Notify the WebUI that a steer is planned, hold the default three-second
   visual preview, and mark the client as moving.
5. Snapshot the selected client's affected frequency-qualified links.
6. Atomically apply target `60`, source `20`, and all others `-20 dB`.
7. Ask the supplicant for an active scan qualified by target frequency,
   BSSID, and SSID. Require one scan-cache record containing both the exact
   BSSID and expected ESS identity.
8. If RF preparation already caused reassociation, skip the unnecessary BTM
   request. Otherwise run
   `/usr/bin/steer.sh STA_MAC TARGET_BSSID OPCLASS CHANNEL` inside
   `bpibroadband`, using the live target AP state rather than a configured but
   stale channel value.
9. The controller sends the EasyMesh Client Steering Request. The serving
   Agent acknowledges receipt, builds the station-facing BTM Request, and
   submits it through OneWifi's prioritized raw-action-frame queue.
10. Wait up to ten seconds for `iw dev wlan0 link` to show the exact target
    BSSID.
11. Wait for the controller and WebUI topology to show the same ownership.
12. Restore the exact pre-test RF matrix.

Controller command execution is bounded and is not blindly retried after an
ambiguous timeout because the controller may already have transmitted the
request.

## Hidden-SSID candidate handling

`iot_ssid` is intentionally hidden. A hidden beacon can create a scan-cache
record with an empty SSID, while a matching directed Probe Request and Probe
Response create a second record for the same BSSID with `iot_ssid`. Packet and
station-cache evidence from the rev140 20-client lab demonstrated both records
at the same time.

For the recorded 5 GHz failure, the AP path was not the failed boundary: the
target received a Probe Request containing `iot_ssid` and transmitted a Probe
Response containing the complete SSID. hwsim and wmediumd delivered that
exchange correctly.

That finding must not be generalized to every band. A later 5955 MHz capture
showed the 6 GHz `wifi2.2` IoT BSS receiving an exact directed Probe Request
without transmitting its own matching Probe Response; the primary private BSS
responded instead. Hidden-IoT steering on 6 GHz therefore remains a separate
AP/multi-VAP discovery defect. Private-SSID 6 GHz steering is validated after
using the target AP's live channel, and hidden-IoT steering on 5 GHz is
validated by the SSID-qualified supplicant lookup.

The stock wpa_supplicant 2.10 WNM path selected a BTM candidate with a
BSSID-only lookup. When that lookup returned the empty hidden-beacon record,
the existing and correct same-ESS check rejected the candidate even though an
SSID-qualified record was present. The lab's recorded supplicant patch changes
only candidate lookup order:

1. look up `(candidate BSSID, current SSID)`;
2. fall back to the legacy BSSID-only lookup if no such record exists;
3. retain the existing SSID, security, profile, and policy checks.

The patch does not invent an SSID, trust a nominated BSSID blindly, weaken the
ESS boundary, force a roam, or make `iot_ssid` visible. It is built by
`gen/wpa_supplicant/build-wnm-supplicant.sh` and installed as
`/usr/local/sbin/wpa_supplicant-wnm` in lab client containers.

The serving Agent also gives the BTM candidate list 50 beacon intervals of
validity. At the lab's 100 TU beacon interval this is about five seconds,
rather than the former 102 ms. This permits a standards-compliant station to
finish an active scan; it does not extend the host script's verification
timeout or make the request mandatory.

## BTM delivery and acknowledgement

The EasyMesh 1905 ACK confirms that the serving Agent received the Client
Steering Request. It does not prove that the later 802.11 action frame was
admitted to OneWifi's asynchronous queue, accepted by nl80211, delivered over
the medium, or accepted by the station. The host wrapper therefore continues
to verify the physical association and controller ownership independently.

The original Wi-Fi HAL passed `noack=1` for every action frame. For a unicast
BTM Request this set `NL80211_ATTR_DONT_WAIT_FOR_ACK`, suppressing normal
802.11 acknowledgement/retry behavior and turning a transient loss into a
silent steering miss. The corrected path requests acknowledgement for unicast
action frames while retaining no-ACK behavior for multicast/broadcast frames.

OneWifi now treats raw action-frame commands as high priority, validates the
RBUS method instance and embedded payload length, and returns an error when
queue admission fails. The Agent preserves signed dispatch results and logs a
correlation tuple containing the station, source BSSID, target BSSID, source
VAP, and RBUS result. These changes do not redefine the standard 1905 ACK as
an over-the-air completion; they make the asynchronous boundaries reliable
and diagnosable.

Acceptance on the rev140 20-client lab after the lookup change included:

- four consecutive cold-cache moves of one hidden-SSID station;
- ten further cold-cache moves of one instrumented hidden-SSID station;
- one complete hidden `iot_ssid` matrix with 10 of 10 passes before the
  delivery hardening;
- a two-round hidden `iot_ssid` matrix with 20 of 20 passes after the HAL,
  OneWifi, and Agent delivery hardening;
- two additional back-and-forth hidden-SSID moves with a cold scan cache;
- a post-change eligible `private_ssid` matrix with 8 of 8 passes; and
- a final health audit with model counts `5/15/50/24`, 20 of 20 physical
  associations matching controller ownership, zero service restarts, and
  zero packet loss in the ten-packet reachability check from every client.

Each matrix pass required agreement between the physical association,
controller database, and WebUI topology, followed by exact RF restoration.
The separate OneWifi live-snapshot reactivation fix is required so a station
that moved successfully cannot remain absent from the controller model.

The three delivery patches built successfully in both the
`qemux86bpibroadband` and `qemux86bpiap` component builds before deployment.
A management-frame capture during the hidden-SSID moves showed:

- directed Probe Responses carrying the complete `iot_ssid`;
- WNM BTM Requests from the serving AP to the selected station; and
- WNM BTM Responses from the station to the serving AP.

The Agent and OneWifi logs correlated the same operations through Agent
dispatch, OneWifi high-priority queue admission, queue consumption, and HAL
acceptance. No queue rejection or local dispatch failure occurred in the
acceptance runs. The capture intentionally establishes management-frame
delivery, not the lower-level ACK itself; the HAL source and deployed binary
establish that unicast requests use the acknowledged nl80211 transmit path.

## Request-only mode

```sh
gen/steer.sh --request-only iot-18 extender-2
```

Request-only mode performs name and BSS resolution and sends the controller
command, but does not alter wmediumd and does not claim that movement occurred.
It is appropriate for studying the client's native BTM acceptance policy.

A successful command submission only proves that the request entered the
control path. The station can legitimately accept, reject, or ignore it.

## Pass criteria

Default deterministic mode passes only when all of these agree:

1. the target BSSID was discoverable by the station;
2. the controller steering transaction completed, unless the client moved
   during RF preparation;
3. the physical `iw` link uses the exact target BSSID;
4. the controller topology assigns the STA to that target BSS;
5. the previous RF state was restored exactly.

An EasyMesh ACK, successful command return, BTM transmission, or physical
association by itself is not an end-to-end pass.

## Failure interpretation

The stage reported by the script narrows the failing boundary:

- **RF-bias failure:** identity discovery, medium control, generation or
  readback problem; no steering request is sent.
- **Target absent from scan:** target BSS discovery, channel, or simulated
  frame-delivery problem.
- **Target RF-visible but ESS identity unresolved:** the hidden-BSS directed
  probe/response or scan-cache reporting path is incomplete.
- **Controller command timeout/failure:** controller command transport or
  serialized `libemcli` path problem; an ambiguous timeout is not retried.
- **Controller success but no BTM on air:** the 1905 request was acknowledged,
  but the Agent-to-OneWifi queue, HAL, nl80211, or medium delivery boundary
  failed. Inspect the BTM dispatch and action-frame queue records; command
  success alone is not air-delivery evidence.
- **BTM refusal with status 7:** the station found no suitable candidate. A
  strong wmediumd target does not override ESS, security, band or client-policy
  validation.
- **Physical move without topology convergence:** association succeeded but
  the HAL, Agent, controller model, or WebUI event path is stale.
- **Restore failure:** the test result is unsafe to reuse until the saved state
  is reconciled.

In particular, target `60 dB`, source `20 dB`, and others `-20 dB` make RF
preference clear, but they do not bypass standards-correct station behavior.
A passing private-SSID steer does not by itself prove hidden-SSID BTM candidate
handling.

## Commands

```sh
# Resolve without changing the lab
gen/steer.sh --dry-run sta-05 extender-1

# Deterministic commanded steer
gen/steer.sh sta-05 extender-1

# Target the colocated Agent
gen/steer.sh sta-05 agent-1

# Select a specific advertised band
gen/steer.sh --band 6 sta-05 extender-2

# Send the standards path without RF assistance
gen/steer.sh --request-only sta-05 extender-2

# Give every currently connected client one valid topology-derived target
gen/steer-soak.sh

# Issue an exact number of sequential topology-derived steers
gen/steer-soak.sh 50

# Submit three requested moves under one RF transaction
gen/steer-batch.sh \
  sta-03 extender-1 \
  sta-04 extender-2 \
  iot-15 agent-1

# Select five distinct clients and compatible targets automatically
gen/steer-batch.sh --count 5
```

`steer-soak.sh` refreshes the live source, SSID, band and compatible target
before every move, then calls this single-steer adapter. It supports the full
2.4/5/6 GHz client roster. It differs from `steering-matrix.sh`, which is a
fixed 5 GHz cohort acceptance/timing test, and from the carousel, which drives
RF roaming without sending BTM requests.

`steer-batch.sh` is the safe concurrent form. It resolves every move before
changing state, rejects duplicate clients, and creates one combined set of
frequency-qualified links. One atomic wmediumd generation gives each client a
`60 dB` target, `20 dB` source and `-20 dB` alternatives. Candidate scans run
concurrently; BTM commands are then submitted in a short serialized burst
because the RDK controller command transport is serialized. Physical links
and WebUI ownership are verified concurrently, and the original medium matrix
is restored once after the whole batch. Running several independent
`gen/steer.sh` commands with `&` is unsupported because their independent
snapshots and restores can overwrite each other.

## What this test proves

A full pass proves that a specifically addressed controller steer can traverse
the EasyMesh and BTM control path, produce the requested physical association,
reach the controller model and WebUI, and leave the simulated medium unchanged
afterward.

It does not prove that an autonomous optimizer chose the target, that the
station would accept the same request without RF preparation, or that the
selected SNR values model a realistic location.

For the deliberately disconnected, RF-driven visual demonstration, see
[wmediumd client carousel](client-carousel.md).
