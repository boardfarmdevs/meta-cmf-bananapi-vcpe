# wmediumd Console: architecture, operation and design

## Goal

An operator should be able to open one page and immediately answer:

- Is the lab using wmediumd, and is it keeping up with the offered load?
- Which hwsim radios and VIFs are active, who owns them, and on which band,
  channel and frequency are they transmitting?
- Which directed radio paths have carried traffic recently?
- Which startup rule, live pair value or frequency override is effective on a
  path right now?
- What SNR, received signal, modeled PER, retry and delivery/drop behavior is
  being applied?
- How many management, control, data, unicast, multicast and broadcast frames
  has the medium seen?
- Which RF generation, scenario phase, steering action and EasyMesh topology
  change occurred at the same time?

This is an **experiment-observation plane**. It must not become another
scenario writer, steering optimizer or source of EasyMesh measurements.

## Implementation status

Phases 1 and 2 are implemented in the current `codex/0829-lxd-primary` series:

- patched wmediumd exposes bounded packet telemetry through a separate,
  host-only `-O` Unix socket;
- the static Go `wmediumd-console` process serves an embedded UI, immutable
  REST APIs, a WebSocket snapshot stream and Prometheus metrics;
- startup generates a bounded radio identity inventory, so the UI names
  `agent-1`, `extender-N`, `sta-NN` and `iot-NN` rather than showing only MAC
  addresses;
- controls are disabled by default. An explicit startup option enables only
  typed, atomic pair-SNR and exact-frequency operations plus one-step undo;
  and
- the existing `-R` endpoint remains the small, read-only HAL measurement
  interface and is not changed into a general telemetry endpoint.

The code is in `gen/wmediumd/observer/`; its focused operator and API manual is
`gen/wmediumd/observer/README.md`. Phases 3 and 4 below remain planned work.

### Current Phase 1/2 data flow

```mermaid
flowchart LR
    H[mac80211_hwsim] <-->|802.11 frames and TX status| W[wmediumd]
    C[Python configurator] -->|typed scenario updates| WC[-C writable control socket]
    WC --> W
    W -->|minimal pair/frequency readback| R[-R HAL metrics socket]
    R --> B[BPI hwsim HAL]
    W -->|paged bounded telemetry| O[-O host observer socket]
    I[generated identity inventory] --> G[wmediumd Console - Go]
    O --> G
    G --> UI[embedded live UI]
    G --> API[REST / WebSocket / Prometheus]
    UI -. explicit opt-in typed HTTP set/clear/undo .-> G
    G -. typed generation-checked socket operations .-> WC
```

The Console reports simulator truth. It does not infer or change EasyMesh
associations, run configurator scenarios, or make optimizer decisions.

## Important model boundary

wmediumd does not maintain Wi-Fi associations or EasyMesh topology. It starts
with a complete set of potential directed radio pairs and processes actual
802.11 transmissions. The UI must keep three concepts separate:

1. **Configured potential links**: every radio pair to which a default,
   startup link or live override can apply.
2. **Recently active medium paths**: radio/frequency paths on which wmediumd
   has actually seen frames during the selected time window.
3. **Observed WLAN/EasyMesh relationships**: current client association and
   backhaul parent obtained from the controller APIs.

An EasyMesh association may be drawn over a recently active medium path, but
the association must not be inferred from packet counts alone. Likewise, an
unused pair with a configured 50 dB SNR is not a connection carrying traffic.

## Runtime interfaces

The accepted launcher starts one patched daemon with three separately
permissioned sockets:

```text
/run/wmediumd-control.sock
    writable scenario endpoint; APPLY, readback and restore

/run/meta-cmf-wmediumd/metrics/control.sock
    multi-client read-only endpoint; mounted in a BPI as
    /wmediumd-metrics/control.sock

/run/meta-cmf-wmediumd/observer/telemetry.sock
    host-only, multi-client read-only endpoint; paged traffic telemetry,
    radio/frequency state, active links, VIF ownership and event ring
```

The `-R` read-only endpoint supplies daemon instance ID, control generation,
station count, pair/frequency SNR readback and capability flags. It deliberately
rejects both APPLY operations. The hwsim HAL uses it to answer simulated
Unassociated STA Link Metrics requests.

The `-O` endpoint adds the following bounded state without JSON encoding, file
I/O or blocking subscribers in wmediumd's frame loop:

- learned `VIF MAC -> radio + frequency` ownership;
- daemon and radio/frequency packet counters;
- sparse active directed link counters and applied SNR/PER state;
- modeled attempts, retries, ACK/no-ACK, injection and drop reasons;
- queue depth/delay, active-state eviction and netlink health; and
- a low-rate bounded event ring with gap detection.

Artifact provenance beyond hashes, EasyMesh association correlation and
long-term history are intentionally deferred to Phases 3 and 4.

Optional `wmediumd -p FILE` pcapng output contains scheduled frames and modeled
ACKs, but it is not enabled by the launcher. Continuously parsing a pcap or
debug log would be delayed, expensive and unable to recover every internal
decision. It remains an opt-in forensic artifact, not the live telemetry API.

## Selected service architecture

`wmediumd-console` is a separate, unprivileged Go process on the lab host/VM.
The Python configurator remains the stimulus compiler and runner.

| Choice | Benefit | Cost or risk |
| --- | --- | --- |
| Extend the Python configurator | reuses its control client, inventory and run artifacts; fastest proof of concept | mixes short-lived actuation with a long-lived observer; WebSocket/history work adds lifecycle complexity; less predictable CPU/memory under 50-100-client telemetry |
| Separate Go service | small deployable process; strong concurrency for polling, aggregation, history and many browser clients; embedded static UI; bounded memory; matches the existing Go WebUI operating model | requires a Go decoder for the binary protocol and a small identity adapter |
| Put the page in `onewifi_em_cli` | one familiar WebUI | incorrectly couples simulator truth to a BPI/controller component, increases its already important memory footprint and makes the view disappear when the controller is unhealthy |

The separation is useful scientifically as well as operationally:

```text
Python configurator  -> changes the experiment stimulus
external optimizer   -> makes policy decisions from EasyMesh observations
Go observer          -> displays evaluator truth and correlations
```

The Console is a self-contained, statically linked binary with embedded
HTML/CSS/JavaScript and a hardened systemd unit. The service connects only to
the `-O` socket by default and listens on `127.0.0.1:8890`. The accepted VM
configuration binds guest port 8890 and forwards it to host port 18890. A
writable socket is opened only when the operator explicitly enables typed
controls.

## Operate the current Console

Inside a VM, verify the default read-only service and open its UI:

```sh
systemctl status wmediumd-console.service
curl -fsS http://127.0.0.1:8890/api/v1/status | jq .
curl -fsS http://127.0.0.1:8890/api/v1/controls | jq .
```

The LXD VM host proxies the page to `http://HOST:18890/`; bind the proxy to a
trusted host/LAN address only when another workstation must view it. Normal
`/api/v1/controls` output says `enabled:false` and `mode:read-only`.

Typed controls are a diagnostic convenience, not the scenario runner. Enable
them only for a bounded session as described in
`gen/wmediumd/observer/README.md`. A request must carry the instance ID,
generation, same-origin header, JSON content type and per-process CSRF token.
Pair/frequency batches are atomic. Undo restores the exact captured prior value
or prior override absence, and is invalid after another generation or daemon
restart.

The launcher publishes a PID-qualified binary-hash manifest under `/run`, so
the hardened non-root service can verify the root-owned live executable
without `CAP_SYS_PTRACE`.

The accepted profile requires 25 resolved identities, 600 directed pairs,
healthy packet telemetry, immutable read-only HTTP behavior, and no change to
wmediumd state when the Console starts, stops, or fails. Exact binary hashes
belong in the deployment evidence described by
[current state](../current-state.md).

## Target closed-loop correlation architecture

The solid Phase 1/2 medium and service paths below are implemented. SQLite
history, annotation ingestion and EasyMesh/optimizer correlation are explicitly
labelled Phase 3/4 targets; they are not implied by the current Console.

```mermaid
flowchart TB
    classDef rf fill:#fff3cd,stroke:#8a6500,stroke-width:2px,color:#493600
    classDef daemon fill:#ffe8d6,stroke:#b54708,stroke-width:2px,color:#5c2600
    classDef observe fill:#e8f1ff,stroke:#175cd3,stroke-width:2px,color:#102a56
    classDef em fill:#e8f7ea,stroke:#27803b,stroke-width:2px,color:#173c20
    classDef store fill:#f4ebff,stroke:#7f56d9,stroke-width:2px,color:#3c246b
    classDef boundary fill:#fff,stroke:#667085,stroke-width:1.5px,stroke-dasharray:5 3,color:#344054
    classDef warn fill:#fff1f3,stroke:#c01048,stroke-width:2px,color:#650528

    subgraph HOST["Linux 7 lab host or VM"]
        direction TB

        subgraph STIMULUS["Stimulus plane — existing"]
            WMD[".wmd / world artifact"]:::rf
            CFG["Python wmdcfg<br/>compile, run, readback, restore"]:::rf
            WRITE["Writable socket -C<br/>/run/wmediumd-control.sock"]:::boundary
            WMD --> CFG --> WRITE
        end

        subgraph MEDIUM["Simulated medium — one process"]
            BOOT["Generated startup config<br/>radio IDs, model, defaults"]:::rf
            CORE["wmediumd frame loop<br/>SNR/PER, retries, EDCA,<br/>frequency eligibility, delivery"]:::daemon
            COUNTERS["Bounded telemetry state<br/>64-bit counters + sparse active links<br/>+ low-rate event ring"]:::daemon
            HALREAD["Existing read-only -R socket<br/>minimal SNR readback for HAL"]:::boundary
            OBSREAD["Host-only observer -O socket<br/>paged snapshots and deltas"]:::boundary

            BOOT --> CORE
            WRITE --> CORE
            CORE --> COUNTERS
            CORE --> HALREAD
            COUNTERS --> OBSREAD
        end

        subgraph SERVICE["wmediumd Console — separate Go process"]
            PROTO["Binary protocol client<br/>instance/generation/cursor checks"]:::observe
            ID["Identity resolver<br/>LXD + hwsim inventory + BSS map"]:::observe
            AGG["Aggregator<br/>rates, windows, outcome totals,<br/>health and bounded cardinality"]:::observe
            CORR["Timeline correlator<br/>scenario phases + optimizer/steer<br/>+ EasyMesh association changes"]:::observe
            API["Read-only REST + WebSocket<br/>and Prometheus summary"]:::observe
            UI["Embedded live UI<br/>graph, links, packets, timeline,<br/>artifact and health panels"]:::observe

            OBSREAD --> PROTO --> AGG
            ID --> AGG
            AGG --> CORR --> API --> UI
        end

        subgraph HISTORY["Observer-owned evidence"]
            MEM["Recent in-memory windows<br/>high-resolution live state"]:::store
            DB[("SQLite WAL<br/>1 s / 10 s aggregates,<br/>events and run metadata")]:::store
            EXPORT["Per-run JSON/CSV export<br/>hashes and completeness flags"]:::store
            AGG --> MEM
            CORR --> DB --> EXPORT
        end

        ANNO["Local annotation socket<br/>run, phase, generation claim,<br/>steer attempt and result"]:::boundary
        CFG --> ANNO
        OPT["External optimizer / steer.sh"]:::rf --> ANNO
        ANNO --> CORR

        PROC["Host process health<br/>CPU, RSS, fd/thread count,<br/>netlink socket drops"]:::boundary
        PROC --> AGG
    end

    subgraph KERNEL["Shared Linux kernel"]
        HWSIM["mac80211_hwsim<br/>TX frames, RX injection,<br/>TX status and frequency"]:::daemon
    end

    CORE <-->|"generic netlink"| HWSIM

    subgraph BPI["BPI containers and real EasyMesh behavior"]
        WIFI["OneWifi / hostap / supplicant"]:::em
        EMS["agents + controller"]:::em
        WEB["controller APIs<br/>topology, clients, BSSs"]:::em
        WIFI <--> EMS --> WEB
    end

    HWSIM <--> WIFI
    WEB -->|"poll every 2 s; receipt timestamped"| ID
    WEB -->|"association, signal and topology deltas"| CORR
    HALREAD -->|"read-only candidate SNR only"| WIFI

    UI -. "explicit opt-in: typed HTTP set, clear, undo" .-> API
    API -. "instance/generation-checked control client" .-> WRITE
    BLOCK["No shell/generic socket proxy,<br/>steer or optimizer decision"]:::warn
    API -.-> BLOCK
```

The existing `-R` endpoint should remain small and stable because it is part of
the hwsim HAL measurement boundary. Add a distinct host-only `-O` observer
socket rather than exposing detailed counters and VIF state inside every BPI
container.

## wmediumd telemetry additions

### Hot-path design

wmediumd is single threaded. A per-frame log write, JSON encoding or blocking
subscriber would directly reduce medium capacity. Instrumentation in C must be
limited to:

- fixed-width `uint64_t` counter increments;
- one frame classification performed when `HWSIM_CMD_FRAME` arrives;
- sparse radio-pair/frequency entry lookup with a bounded allocation policy;
- a bounded ring for **low-rate state events**, not every frame; and
- paged binary snapshots served when requested.

No WebSocket, database, HTTP, DNS, LXD or controller query belongs in
wmediumd. If the observer is absent or slow, frame processing must be unchanged.

### Counting levels

Do not create a full packet-type histogram for every VIF-to-VIF pair. Use these
bounded levels:

| Level | Key | Values |
| --- | --- | --- |
| daemon | daemon instance | frames, bytes, modeled attempts/retries, fan-out, all outcome reasons, allocation/protocol/netlink errors |
| radio-frequency | source radio + MHz | frames/bytes by 802.11 type and address class, EAPOL count, plus last subtype/access category |
| directed active link | source radio + destination radio + MHz | frames/bytes, attempts/retries, delivery outcomes, effective SNR origin, last activity |
| VIF ownership | VIF MAC | owner radio, last learned frequency and last-seen time |

At 105 radios, the full pair universe is 10,920 directed cells. Traffic state
should remain sparse: materialize a frequency-qualified statistics entry only
after a frame uses that path and age inactive entries out of the live cache.
The authoritative cumulative radio counters remain available even after an
inactive link is evicted.

### Frame classification

The default classifier reads only the 802.11 header:

- management, control or data;
- management/control subtype, or QoS/non-QoS data;
- access category: background, best effort, video or voice;
- unicast, multicast or broadcast destination;
- protected/unprotected flag;
- length, frequency and attempted rates.

For unprotected LLC/SNAP data, the current aggregate EtherType classifier
counts EAPOL only. It never retains payload bytes, IP addresses, hostnames or
application ports. Protected data is not decoded; guessing its contents would
be false.

### Outcome vocabulary

The UI must label internal decisions precisely. “Delivered” means injected by
wmediumd toward hwsim, not proven received by an application.

| Counter | Exact meaning |
| --- | --- |
| `frames_seen` | one `HWSIM_CMD_FRAME` accepted from a configured simulated sender |
| `tx_attempts` | attempts evaluated across the kernel-provided multi-rate retry series |
| `retries` | attempts after the first modeled attempt |
| `tx_acked` / `tx_no_ack` | wmediumd's modeled transmit-status result |
| `drops_no_receiver` | unicast destination had no learned owning radio/VIF |
| `drops_offchannel` | receiver ownership/frequency was not eligible for this transmission |
| `rx_injected` | clone submitted toward an eligible hwsim receiver |
| `drops_cca` | multicast receiver signal was below the carrier-sense threshold |
| `drops_per` | receiver-specific random PER decision rejected delivery |
| `drops_interference` | enabled interference model rejected/overlapped delivery |
| `multicast_frames` | original multicast/broadcast transmissions, counted once |
| `multicast_candidates` | receiver fan-out evaluations before eligibility filters |
| `netlink_clone_einval` | tracked clone received the known command-2 `EINVAL` |
| `netlink_other_errors` | any other tracked netlink/protocol failure |

The existing netlink sequence tracker stores only a sequence number. To
attribute asynchronous clone rejection, retain a bounded sequence record with
source radio, destination radio, frequency, frame class and enqueue time until
the kernel response arrives or the record expires.

### SNR, PER and path-loss presentation

The current lab uses the SNR model. For a selected link display:

```text
effective SNR
  -> base matrix or exact-frequency override
  -> optional fading and same-frequency interference adjustment
  -> effective signal = adjusted SNR - 91 dBm
  -> PER for this frame's rate and length
  -> random delivery decision and retry result
```

PER is not one permanent property of a link; it varies with rate, length,
fading and interference. The UI should show both:

- the configured/effective SNR input; and
- observed-window PER decisions, attempts and delivery ratio, with the last
  evaluated rate and frame length.

Do not label SNR as path loss. When the startup model is `path_loss`, expose its
coordinates, transmit power, calculated path loss and resulting SNR as such.
For the accepted SNR model, show `path_loss: not modeled`.

### Phase 3 rule and experiment provenance target

Phase 1/2 already publishes the matrix/frequency value, daemon generation,
startup-config hash and live-binary hash. Phase 3 should add the following
scenario attribution for every effective link value:

```text
source: startup default | startup explicit pair | live pair generation |
        live frequency override
value: 25 dB
frequency: 5180 MHz (5 GHz, channel 36)
last changed generation: 42
scenario claim: run abc..., phase crossover, plan SHA-256 ...
```

This requires small provenance fields next to wmediumd's matrix state:

- whether generation zero came from the default or an explicit startup link;
- last control generation changing each base pair;
- creation/last-change generation for each frequency override; and
- daemon instance, build ID and monotonic boot timestamp.

The Go service independently hashes the running binary, generated startup
configuration and optional PER file. The configurator announces the scenario,
plan hash, bindings, phase and claimed generation over a **local annotation
socket**. wmediumd remains authoritative for the actual effective value and
generation. If no annotation claims a generation, the UI displays
`unclaimed live change`; it must not guess a scenario.

## Observer protocol

Retain the existing fixed-width, network-byte-order `SOCK_SEQPACKET` framing.
The implemented capability-advertised operations on the new `-O` socket are:

```text
TELEMETRY_SUMMARY              opcode 9
DUMP_RADIO_FREQUENCIES         opcode 10
DUMP_ACTIVE_LINKS              opcode 11
DUMP_VIFS                     opcode 12
DUMP_EVENTS                    opcode 13
```

Every dump operation uses the same bounded page request/header contract. Pair
matrix and frequency-override readback retain
their existing opcodes 5 and 8.

Every response uses the existing 24-byte header, including opcode, status and
control generation. `HELLO` supplies daemon instance/capabilities/limits. Each
paged response then includes:

```text
snapshot telemetry sequence
oldest retained event sequence
total record count
next cursor (all-ones when complete)
more/gap flags
```

The existing 64 KiB maximum makes pagination mandatory for medium and stress
profiles. Requests specify a bounded page size and optional `changed_after`
telemetry sequence. Unknown opcodes remain protocol errors, so the current HAL
client continues to work unchanged on `-R`.

One response is coherent because the wmediumd event loop is not processing a
frame while it handles that request. A multipage walk may span new activity;
each page's watermark makes that visible. The Go client retries a current-state
walk when the control generation changes and marks event history incomplete
when the retained ring cannot cover the requested sequence.

The low-rate event ring contains only:

- VIF learned or changed;
- a directed link becoming active;
- a control generation being applied;
- a netlink rejection; and
- bounded active-link eviction.

Daemon identity and telemetry/event overrun counters are carried by every
snapshot rather than synthesized as ring entries.

Per-frame UI rates come from counter deltas, not a per-frame event firehose.

## Identity enrichment

wmediumd knows radio MACs and transmit-learned VIF ownership but not container,
SSID, BSSID, AP/client role or EasyMesh AL-MAC. The implemented identity path
keeps discovery outside the service:

1. `wmediumd-up.sh` runs a bounded generator after radio assignment.
2. The generator maps the same sysfs permanent-radio identity used by
   `gen-config.sh` to active LXD owners and writes one atomic JSON inventory.
3. The Console reads only that file and joins on exact radio MAC; it cannot
   access the LXD/Incus daemon and never invents an unresolved owner.
4. VIF ownership and last observed frequency come independently from wmediumd
   telemetry.

Polling controller topology/client/BSS APIs and correlating current
associations/backhaul parents is Phase 3 work.

Frequency remains medium truth. Derive the visual band/channel from MHz and
show both, for example `5180 MHz / 5 GHz / channel 36`. A controller API value
that disagrees is a visible `identity disagreement`, not silently overwritten.

## Current Phase 1/2 service APIs

The normal managed service is read only. It exposes these implemented routes:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/status` | service and daemon identity, generation, freshness, health and gaps |
| `GET /api/v1/snapshot` | coherent UI summary: identities, paths, counters, rates and events |
| `GET /api/v1/stations` | configured radio identities and enrichment |
| `GET /api/v1/identities` | generated label/role/owner/interface overlay |
| `GET /api/v1/radio-frequencies` | radio/frequency counters and activity |
| `GET /api/v1/vifs` | learned VIF ownership and last-seen state |
| `GET /api/v1/links?kind=all\|pair\|frequency` | configured pair matrix and exact-frequency overrides |
| `GET /api/v1/active-links` | bounded recently active directed paths |
| `GET /api/v1/telemetry` | daemon/radio/link/VIF counters and rates |
| `GET /api/v1/events?limit=N` | bounded wmediumd state/health event ring |
| `GET /api/v1/health` | factual queue, netlink, collection and gap state |
| `GET /api/v1/artifacts` | startup-config and running-binary hashes |
| `GET /api/v1/controls` | read-only/typed-control capability and undo state |
| `GET /metrics` | low-cardinality Prometheus summary without MAC labels by default |
| `WS /api/v1/stream` | initial snapshot followed by sequenced deltas |

When and only when the process starts with `--enable-control` and the dedicated
writable socket, four POST routes become available: atomic pair set, atomic
frequency set, frequency clear and one-step undo. Every operation is typed,
same-origin/CSRF checked, and must name the current daemon instance and
generation. There is no shell, arbitrary opcode or generic socket-proxy route.

### Phase 3 target correlation schema

The richer scenario/EasyMesh fields in the following example describe the
planned correlation overlay. Current Phase 1/2 active-link records contain the
authoritative medium fields but not `scenario_run_id`, optimizer actions or an
EasyMesh association join.

Example active-link record:

```json
{
  "source": {
    "radio_mac": "42:00:00:00:0e:00",
    "container": "wlan-client-003",
    "vif_mac": "02:00:00:00:0e:00"
  },
  "destination": {
    "radio_mac": "42:00:00:00:02:00",
    "container": "bpiap",
    "vif_mac": "02:11:22:33:44:55"
  },
  "frequency_mhz": 5180,
  "band": "5GHz",
  "channel": 36,
  "rule": {
    "effective_snr_db": 25,
    "origin": "frequency_override",
    "generation": 42,
    "scenario_run_id": "run-20260823-101500",
    "phase": "crossover"
  },
  "window": {
    "seconds": 5,
    "tx_frames": 214,
    "modeled_attempts": 248,
    "modeled_retries": 34,
    "delivery_injected": 205,
    "per_drop": 9,
    "last_per": 0.041,
    "last_signal_dbm": -66
  },
  "easymesh": {
    "relationship": "fronthaul_association",
    "observed_at": "2026-08-23T17:15:04.821Z"
  },
  "last_activity_monotonic_ns": 483221998201
}
```

Current WebSocket messages are bounded full `snapshot` updates or
`collector_error` events, each with service sequence and timestamp; the
snapshot carries the daemon instance and telemetry/event completeness state.
Phase 3 may add sequenced link/VIF/scenario/steering/association deltas, at
which point a browser must request a fresh snapshot after any gap or daemon
instance change.

The planned annotation interface is a separate Unix socket, not a browser POST
route.
It accepts additive metadata only:

```json
{
  "type": "generation_claim",
  "run_id": "run-20260823-101500",
  "plan_sha256": "...",
  "phase": "crossover",
  "daemon_instance_id": "...",
  "generation": 42,
  "recorded_at": "2026-08-23T17:15:00.000Z"
}
```

It cannot request an SNR change or a steer.

## Current Phase 1/2 UI

### Live overview

The header shows daemon readiness/health, generation, identity coverage,
frames/bytes and attempts per second, delivery/drop rates, queue depth and
event-ring state. Detail panels expose the exact counters, hashes and learned
ownership. A factual error or gap is visible; an unused potential link is not
reported as a failure.

### Medium graph

The graph draws one node per configured hwsim radio, enriched with its
label/role/owner. The default mode shows recently active directed paths with
band/channel, frame count, last SNR and drops. A configured-state mode shows
the selected source radio's potential pair edges instead of attempting to draw
the complete matrix. Clicking a node selects that source; table searches
filter MAC, owner, label or frequency.

### Link and packet tables

The active-link table keeps direction explicit and shows frequency,
frames/bytes, attempts/retries, ACK state, receiver injections, individual
drop reasons, last signal/SNR/PER and last activity. Separate radio-frequency
and VIF tables expose type/address-class totals and learned ownership. The
configured-pair table remains distinct so a 50 dB unused pair cannot look like
an active connection.

### Artifact and timeline panels

The artifact panel displays the startup configuration and live running-binary
paths/hashes plus the identity-inventory result. The current timeline is the
bounded wmediumd event ring (VIF learning/change, first link activity,
generation apply, netlink rejection and active-link eviction).

### Phase 3/4 correlation UI target

The later shared timeline should align, without claiming causality:

```text
scenario phase entered
-> wmediumd generation applied
-> SNR/rate/retry/delivery counters changed
-> EasyMesh RCPI/candidate report observed
-> optimizer recommendation or manual steer attempted
-> client link changed
-> controller topology/API converged
-> medium restored
```

Future correlation records must carry wall-clock receipt time plus host
monotonic time, boot ID and daemon instance. Controller API changes must be
labelled with **observer receipt time** unless their source supplies a
measurement timestamp. Scenario/world/plan hashes, phase, touched-link count,
restore result, EasyMesh state and optimizer actions remain Phase 3/4 work.

## Phase 4 storage and retention target

The page must remain useful if persistence is disabled. Keep the last several
minutes of one-second samples and events in bounded memory. Optional history is
owned by the Go process, never by wmediumd:

```text
/var/lib/wmediumd-observer/history.db       SQLite WAL
/var/lib/wmediumd-observer/exports/<run>/   explicit run exports
```

Suggested defaults:

- one-second link/radio aggregates for 24 hours;
- ten-second rollups for seven days;
- low-rate scenario/steering/association/health events for 30 days;
- no packet payloads;
- a fixed total disk quota with oldest-complete-window deletion; and
- explicit export before deleting a named experiment run.

Batch database writes on a storage goroutine. A slow disk may drop historical
samples and increment `history_dropped_samples`; it must not delay wmediumd or
the live collector. Each export records gaps, daemon restarts and partial
samples so incomplete evidence cannot look complete.

## Health and overload signals

Current Phase 1/2 health uses authoritative daemon and collector counters:

- incoming frames/s and bytes/s;
- current/peak queue depth and last/maximum queue delay;
- modeled attempts, retries, receiver injections and multicast fan-out work;
- tracked clone `EINVAL` versus other netlink errors;
- active-link eviction and event-ring overruns; and
- observer collection freshness and event-history gaps.

Phase 4 should add read-only process CPU/RSS/thread/fd sampling, kernel socket
drop counters, scheduler-loop lag and persistence backlog.

Phase 4 thresholds should be configurable and first established from the
20-client profile. CPU affinity can reduce scheduling jitter but is not extra capacity;
one saturated wmediumd thread, growing netlink drops or increasing queue age is
an overload condition even if the UI itself remains responsive.

## Security and privacy

- Bind HTTP to `127.0.0.1` by default and use the established SSH/reverse proxy
  pattern for remote access.
- Run as the unprivileged `wmediumd-console` user with no capabilities. The
  shared `lxd` group gates only the wmediumd sockets; the hardened unit hides
  all known LXD/Incus daemon sockets from the service namespace.
- Open `/run/wmediumd-control.sock` only after explicit `--enable-control`;
  otherwise every HTTP mutation returns 405 and the socket is never opened.
- Permit only typed pair/frequency set, frequency clear and one-step undo with
  daemon-instance/generation checks. Never implement an arbitrary command,
  opcode or socket proxy.
- Disable CORS and all browser write routes by default. If direct network
  exposure is later required, use a TLS/authenticating reverse proxy.
- Retain MAC identities only because they are required to understand this lab.
  Do not collect payloads, IP/port flows or SSID credentials.
- Make pcapng capture an explicit, duration/size-bounded operator action in the
  launcher, not a hidden observer side effect.

## Package layout

```text
gen/wmediumd/observer/
|-- cmd/wmediumd-observer/main.go
|-- internal/wmdproto/       binary socket client and golden fixtures
|-- internal/identity/       bounded generated identity overlay
|-- internal/state/          counter deltas, windows and health
|-- internal/artifacts/      startup config and live binary provenance
|-- internal/httpapi/        REST, WebSocket and Prometheus handlers
|-- web/                     embedded static UI
|-- packaging/               hardened systemd service and defaults
`-- wmediumd-console         static release binary
```

Keep protocol constants in one machine-readable schema from which C, Go and
Python golden fixtures are checked. A wire-compatibility test must decode the
same captured response in the Go observer and Python `ControlClient` tests.

## Phased implementation

### Phase 1: current-state viewer — implemented

- Build the Go process against the existing read-only socket.
- Show daemon identity/generation, radio inventory, base/frequency SNR rules,
  effective values, config/binary hashes and EasyMesh identity overlay.
- Add REST/WebSocket snapshot plumbing and the initial graph/table UI.
- Clearly mark packet, retry and delivery fields unavailable.

This phase is useful immediately and validates process/UI boundaries, but it
does not satisfy traffic observability.

### Phase 2: bounded wmediumd counters and host-only protocol — implemented

- Add frame classification, radio/frequency counters, sparse active-link
  counters, VIF dump, outcome taxonomy, queue health and attributed netlink
  rejection.
- Add `-O`, paged/delta operations and a low-rate event ring.
- Display packet mix, active paths, multicast fan-out and health in the UI.
- Measure overhead at idle and with declared traffic before enabling it by
  default.

### Phase 3: artifact and closed-loop correlation

- Add the local annotation socket and configurator run/phase/generation
  announcements.
- Add optimizer/`steer.sh` transaction annotations.
- Correlate controller association, signal, backhaul and topology deltas.
- Export one complete crossover and one extender-outage timeline.

The observer is still not an optimizer input. It is an evaluator and debugging
view, just as a packet capture is.

### Phase 4: history, scale and forensic handoff

- Add bounded SQLite retention and per-run JSON/CSV export.
- Add optional launcher-managed pcapng capture and links from a run to its
  capture, without parsing payloads into live state.
- Accept 20-, 50- and eventually 100-client profiles.
- Extend the already-packaged binary/unit/UI workflow with the optional
  history/export dependencies and acceptance artifacts.

## Test and acceptance criteria

### Correctness

1. A deterministic unicast test makes `frames_seen`, attempts, retries,
   ACK/no-ACK and injected-delivery counts agree with the wmediumd decision
   path and bounded pcap evidence.
2. A multicast test counts one source frame, the exact eligible receiver
   fan-out and separate off-channel, CCA, PER/interference and injected
   outcomes.
3. Management/control/data and key management subtypes are classified from
   golden 802.11 headers; protected data is never decoded further.
4. Pair and exact-frequency APPLY/readback/clear/restore changes show the exact
   effective value, origin and generation without a daemon restart.
5. A VIF channel change updates ownership/frequency once and does not assign
   one VIF to two radios.
6. Restarting wmediumd changes instance ID, resets cumulative counters and
   forces every browser to obtain a new snapshot.

### Safety

1. In default read-only mode the writable socket is unopened and every APPLY
   route is rejected; opt-in mode exposes only the four typed operations.
2. Starting, stopping or crashing the observer does not change the control
   generation, matrix, associations, daemon PID or scenario restore result.
3. A stalled browser and a full history queue cannot block the medium loop.
4. Browser APIs expose no shell execution, control-socket proxy or packet
   payload.

### Performance and scale

At each accepted profile, compare identical declared traffic with telemetry
disabled and enabled. Initial acceptance targets are:

- no new kernel netlink drops or missed scenario deadlines;
- no telemetry-ring gaps at the default one-second collection interval;
- no more than five percentage points of one CPU additional wmediumd cost;
- no more than 5% increase in p99 scenario deadline lateness;
- bounded wmediumd telemetry memory, with a design target below 4 MiB at 105
  radios;
- observer RSS below 50 MiB with one browser and bounded history queues; and
- live snapshot age below two seconds under the 20- and 50-client profiles.

Targets should be revised from recorded evidence rather than waived silently.

### End-to-end demonstrations

- **Two-AP crossover**: the graph shows the claimed phase/generation and
  changing directed SNR/retry/delivery behavior before the EasyMesh RCPI and
  association overlays change.
- **Client carousel**: active edges move among APs while physical radio-role
  bindings and scenario functions remain fixed.
- **Extender outage/recovery**: all affected RF paths become unusable, clients
  move, the controller later ages the extender, and the same identity returns
  after exact medium restoration.
- **Multiband activity**: simultaneous 2.4, 5 and 6 GHz traffic appears in
  independent frequency contexts with correct channel labels.
- **Overload gate**: deliberately increasing offered traffic makes queue lag,
  CPU and any netlink/telemetry loss visible and machine-readable.

## Decision summary

Build a separate Go observer, not another page inside the BPI `em_cli` and not
a long-running mode of the Python configurator. Deliver the present rule and
identity view first. Then add cheap, bounded counters and a host-only paged
telemetry socket to wmediumd. Keep per-frame payloads out of the system, keep
the normal service read only, constrain opt-in writes to typed atomic
pair/frequency controls, and treat scenario/EasyMesh/steering information as
time-correlated annotations around authoritative medium counters.
