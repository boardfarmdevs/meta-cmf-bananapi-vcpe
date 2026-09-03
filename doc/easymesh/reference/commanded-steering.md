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

The live `/api/v1/bsses` channel is preferred. If it is unavailable or reports
zero, the fixed lab fallbacks are:

| Band value | Band | Channel | Frequency |
| ---: | --- | ---: | ---: |
| `0` | 2.4 GHz | 6 | 2437 MHz |
| `1` | 5 GHz | 36 | 5180 MHz |
| `3` | 6 GHz | 5 | 5975 MHz |

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
7. Ask the supplicant to scan the target frequency and require the target
   BSSID to appear in its scan results.
8. If RF preparation already caused reassociation, skip the unnecessary BTM
   request. Otherwise run `/usr/bin/steer.sh STA_MAC TARGET_BSSID` inside
   `bpibroadband`.
9. The controller sends the EasyMesh Client Steering Request, and the serving
   Agent sends the station-facing BTM Request.
10. Wait up to ten seconds for `iw dev wlan0 link` to show the exact target
    BSSID.
11. Wait for the controller and WebUI topology to show the same ownership.
12. Restore the exact pre-test RF matrix.

Controller command execution is bounded and is not blindly retried after an
ambiguous timeout because the controller may already have transmitted the
request.

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
- **Target absent from scan:** target BSS discovery, channel, hidden-SSID probe
  handling, or simulated frame-delivery problem.
- **Controller command timeout/failure:** controller command transport or
  serialized `libemcli` path problem; an ambiguous timeout is not retried.
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
```

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
