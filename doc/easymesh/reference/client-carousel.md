# wmediumd client carousel

This reference describes exactly how
`gen/tests/wmediumd-client-carousel.py` rotates client groups through the mesh
APs. The carousel is an RF-driven roaming and topology-visualization scenario;
it is not a controller-commanded EasyMesh steering test.

## Purpose and boundary

Run the carousel while observing the Network Topology page:

```sh
python3 gen/tests/wmediumd-client-carousel.py \
  --ssid private_ssid --rounds 2
```

The script creates an obvious repeating sequence:

```text
client group on AP-A
        |
        | BLACKOUT: every AP link becomes unusable; wlan0 goes down
        v
visible disconnection
        |
        | ARRIVAL: AP-B becomes strong; wlan0 comes up
        v
normal association to AP-B
        |
        v
controller and WebUI ownership converge
```

It is designed to demonstrate that wmediumd can control the RF world and that
physical associations, controller ownership, and topology animations follow
that world. The script does not send an EasyMesh Client Steering Request or an
IEEE 802.11v BTM Request.

## Components and interfaces

```text
wmediumd-client-carousel.py
   |---- live radio/BSS inventory
   |---- /api/v1/topology
   |---- nested LXD client commands: iw, ip link and wpa_cli
   |
   | atomic base radio-pair SNR generations
   v
wmediumd control socket (/run/wmediumd-control.sock)
   |
   v
normal station disconnect, scan and association
   |
   v
OneWifi/HAL -> Agent -> controller model -> Network Topology WebUI
```

The carousel currently requires these userspace wmediumd control capabilities:

- `radio_pair_snr`;
- `atomic_generations`;
- `readback`;
- `dump_links`.

Unlike `gen/steer.sh`, it currently applies base radio-pair SNR rather than
frequency-qualified overrides.
`ControlClient.apply()` sends the custom `OP_APPLY` operation (`3`) over the
Unix `SOCK_SEQPACKET` control socket. Every directional pair for one step is
committed under one new generation, so observers cannot see a half-applied
blackout or arrival matrix.

## Inventory and grouping

At preflight the script:

1. discovers the live mesh and station radios;
2. reads the topology API and refuses an empty response;
3. retains mesh radios that expose the selected `private_ssid` or `iot_ssid`;
4. maps every BSSID to its topology node and owning container;
5. selects only client radios provisioned for that SSID;
6. records every client's physical BSSID and controller-visible owner;
7. requires the physical and controller views to agree before starting.

The controller container's radio is not automatically a placement target. The
colocated Agent participates only if its discovered radio advertises the
selected fronthaul SSID.

Clients are sorted by container name and divided as evenly as possible into no
more groups than there are APs. Each group is assigned a starting AP. With five
APs and ten selected clients, this normally creates five two-client groups.

## SNR model

The carousel has two SNR levels by default:

| State | SNR | Approximate signal with `-91 dBm` noise | Meaning |
| --- | ---: | ---: | --- |
| Strong destination | `+45 dB` | `-46 dBm` | Clearly usable arrival AP. |
| Outage | `-20 dB` | `-111 dBm` | Deliberately unusable path. |

The values can be changed with `--strong-snr` and `--outage-snr`. Both must be
inside the configurator's `[-20, 60] dB` range and the strong value must exceed
the outage value.

The carousel does **not** use the steering script's `target=60`, `source=20`,
`others=-20 dB` pattern. There is no retained source level during a carousel
move:

```text
formation/arrival:
    selected target AP = +45 dB
    every other AP     = -20 dB

blackout:
    every AP           = -20 dB
```

Both directions between each selected client radio and every participating
mesh radio are updated in the same atomic generation:

```text
client -> AP
AP     -> client
```

Because these are base radio-pair updates, the SNR applies to that pair rather
than only one frequency. The client remains constrained by its provisioned
supplicant band/frequency configuration, and candidate scans are performed on
the frequency appropriate for that client and target BSS.

These levels are test actuators rather than a realistic propagation model. Use
the configurator's world scenarios when gradual motion, walls, fading or
time-varying gradients are the subject of the experiment.

## Initial formation

Before rotating, the script forms a recognizable initial distribution. It
processes one small client group at a time:

1. make that group's assigned AP strong;
2. make the group's links to every other AP unusable;
3. prime the target candidate scan;
4. wait for physical association and controller ownership to agree;
5. continue with the next group.

Groups are phased instead of releasing the entire cohort simultaneously. This
keeps a visual demonstration readable and avoids turning formation into a
separate association-burst stress test.

The complete formation is held for five seconds by default.

## One carousel movement

For every group in every round, the following transaction is used.

### 1. Select the next AP

The APs form a logical ring. A group at position `N` moves to position `N+1`,
wrapping from the last AP back to the first.

### 2. Blackout

The script atomically changes that group's links to **all** participating APs
to the outage SNR, then executes:

```sh
ip link set wlan0 down
```

Taking the interface down is intentional. Merely assigning `-20 dB` can leave
a station attempting candidates or retaining stale link state long enough to
make the visible disconnection nondeterministic.

The script waits until every client in the group reports no physical BSSID,
then holds that visibly disconnected state for four seconds by default.

### 3. Arrival

The next AP is changed to the strong SNR and all other APs remain at the outage
SNR. The script then brings each client interface back:

```sh
ip link set wlan0 up
```

It primes candidate scans for the client's provisioned band and waits for the
normal supplicant association process.

### 4. Verify convergence

Arrival passes only when every client in the group has:

- a physical BSSID belonging to the intended AP;
- a topology owner that maps to the same AP;
- the same BSSID in the physical and topology views.

The arrived state is held for four seconds by default before the next group is
moved.

No controller steering command is sent at any point. The client associates
with the destination because it reconnects into an RF world where that AP is
the only viable choice.

## Timing defaults

| Option | Default | Purpose |
| --- | ---: | --- |
| `--rounds` | `2` | Complete rotations; `0` continues until Ctrl-C. |
| `--formation-hold` | `5 s` | Show the initial distribution. |
| `--blackout-hold` | `4 s` | Keep the disconnection visible. |
| `--arrival-hold` | `4 s` | Show the new attachment before moving another group. |
| `--disconnect-timeout` | `30 s` | Bound physical disconnection. |
| `--connect-timeout` | `60 s` | Bound formation and arrival convergence. |
| `--return-timeout` | `90 s` | Bound return to original placement. |
| `--restore-settle` | `6 s` | Require restored placement to remain stable. |

The hold times are presentation controls; the timeouts are acceptance bounds.

## Exact medium and placement restoration

Before the first change, the carousel snapshots every affected directional
radio pair from wmediumd and records each client's original AP.

Cleanup first tries to return clients to their original APs in phased groups.
If an ordinary return fails, the repair path handles clients in groups of no
more than two, moves them through an alternate AP when necessary, and then
tries the original AP again. This bounds reassociation bursts and avoids
repairing unrelated clients.

After placement recovery, the script atomically restores the exact saved
wmediumd pair values and reads them back. Cleanup also runs after Ctrl-C and
test failure. The summary distinguishes medium restoration from client
placement restoration; neither is inferred merely from process exit.

## Result artifacts

Each run creates a timestamped directory under
`/tmp/wmediumd-client-carousel` unless `--output-root` is supplied. It contains:

- discovered inventory;
- topology before and after;
- compiled group/AP scenario;
- timestamped JSONL events and observations;
- a final summary;
- focused failure evidence and service logs when convergence fails.

The final summary records outcome, interruption, completed rounds, exact
medium restoration and placement restoration separately.

## Commands

```sh
# Two private-client rotations
python3 gen/tests/wmediumd-client-carousel.py \
  --ssid private_ssid --rounds 2

# Two IoT-client rotations
python3 gen/tests/wmediumd-client-carousel.py \
  --ssid iot_ssid --rounds 2

# Run continuously until Ctrl-C
python3 gen/tests/wmediumd-client-carousel.py \
  --ssid private_ssid --rounds 0

# Slow presentation with an especially strong arrival AP
python3 gen/tests/wmediumd-client-carousel.py \
  --ssid private_ssid --rounds 1 \
  --strong-snr 60 --blackout-hold 8 --arrival-hold 8
```

## What this test proves

A full pass proves that the selected clients can be disconnected and
reassociated according to atomic wmediumd RF changes, that physical links and
controller ownership converge on every requested placement, and that the
starting medium and client placement can be restored.

It does not prove:

- delivery or acceptance of an EasyMesh steering request;
- IEEE 802.11v BTM behavior;
- an autonomous optimizer or controller policy decision;
- that a client would voluntarily roam while its source link remained usable;
- realistic mobility at the intentionally discrete `45/-20 dB` boundary.

This distinction is particularly important for hidden SSIDs. A forced
disconnect followed by normal reconnection exercises a different supplicant
path from recognizing a hidden target in a BTM candidate scan. A passing IoT
carousel therefore does not prove hidden-SSID BTM steering.

For the real controller-commanded path, see
[Commanded EasyMesh steering](commanded-steering.md).
