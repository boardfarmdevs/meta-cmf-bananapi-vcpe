# External optimizer architecture

## Purpose and ownership

The steering optimizer is a completely external component. It runs on the lab
host or Vagrant VM, outside every BPI container and outside the EasyMesh,
OneWifi, WebUI and wmediumd processes.

The optimizer owns all optimization behavior:

- measurement interpretation and freshness rules;
- candidate construction, filtering, ranking and scoring;
- thresholds, margins, hysteresis, dwell and cooldown;
- per-client state and outstanding transactions;
- whether, when and where to steer; and
- decision, action and outcome records.

The BPI EasyMesh implementation supplies protocol facts and mechanisms only:

- topology, association, capability and measurement reports;
- standardized measurement queries and responses;
- Policy Configuration transport for reporting and exclusions;
- Client Steering Request transport, 1905 ACK and steering reports; and
- the OneWifi/HAL path that transmits BTM and reports reassociation.

It supplies no optimizer, target recommendation, candidate score, threshold
evaluation or steering trigger. Agent-local steering must be explicitly disabled
for controller-optimizer experiments so the external optimizer is the only
decision maker.

## Complete architecture

```mermaid
flowchart TB
    classDef external fill:#e8f1ff,stroke:#1e5aa8,stroke-width:2px,color:#102a43
    classDef stimulus fill:#fff3cd,stroke:#9a6700,stroke-width:2px,color:#4d3500
    classDef bpi fill:#eaf7ea,stroke:#287a28,stroke-width:2px,color:#153b15
    classDef kernel fill:#f2e9ff,stroke:#6f42c1,stroke-width:2px,color:#34205f
    classDef client fill:#ffe9ee,stroke:#a61b45,stroke-width:2px,color:#541027
    classDef contract fill:#ffffff,stroke:#4f5b66,stroke-width:1.5px,stroke-dasharray:5 3,color:#20262c
    classDef warning fill:#fff0f0,stroke:#b42318,stroke-width:2px,color:#7a1a12

    subgraph HOST["Linux 7 lab host or Vagrant VM"]
        direction LR

        subgraph RF["Independent RF stimulus plane"]
            direction TB
            SRC["Scenario source<br/>two-ap crossover"]:::stimulus
            COMP["wmdcfg compiler<br/>frozen physical-radio bindings"]:::stimulus
            RUN["wmdcfg runner<br/>timed atomic generations"]:::stimulus
            SOCK["wmediumd control socket<br/>APPLY / GET / readback / restore"]:::contract
            SRC --> COMP --> RUN --> SOCK
        end

        subgraph EXTOPT["External optimizer process — Python"]
            direction TB
            OBS["Observation adapters<br/>topology + real EasyMesh metrics"]:::external
            NORM["Normalized immutable snapshot<br/>STA, current BSS, candidates,<br/>RCPI, utilization, age"]:::external
            DEC["Pure decision engine<br/>filter + score + state transition"]:::external
            PCFG["Versioned optimizer policy<br/>thresholds, margin, dwell,<br/>hold, timeout, cooldown"]:::external
            STATE[("Per-STA state store<br/>stable / degraded / eligible /<br/>pending / verifying / cooldown")]:::external
            SAFE["Safety gate<br/>health, freshness, exclusions,<br/>one in-flight action"]:::external
            ACT["Action adapter<br/>steer(STA, target BSSID)"]:::external
            VERIFY["Outcome verifier<br/>link + controller model + API + traffic"]:::external
            JOURNAL[("Append-only experiment journal<br/>snapshots, reasons, actions, outcomes")]:::external

            OBS --> NORM --> DEC --> SAFE --> ACT
            PCFG --> DEC
            STATE <--> DEC
            ACT --> STATE
            ACT --> VERIFY --> STATE
            NORM --> JOURNAL
            DEC --> JOURNAL
            ACT --> JOURNAL
            VERIFY --> JOURNAL
        end

        ORACLE["Lab evaluator only<br/>wmediumd truth, client iw link,<br/>traffic and service health"]:::contract
        WMD["wmediumd.patched<br/>one process, all active hwsim radios"]:::stimulus
        SOCK --> WMD
        RUN --> JOURNAL
        WMD -.-> ORACLE
        ORACLE --> JOURNAL
    end

    subgraph KERNEL["Shared Linux 7 kernel"]
        direction LR
        HWSIM["patched mac80211_hwsim<br/>24 radios / 3 channel contexts"]:::kernel
        MAC["cfg80211 + mac80211<br/>nl80211 namespaces"]:::kernel
        HWSIM <--> MAC
    end

    WMD <-->|"generic netlink frames,<br/>frequency and TX status"| HWSIM

    subgraph CONTROLLER["bpibroadband LXD container"]
        direction TB
        HTTP["onewifi_em_cli WebUI/API :8888<br/>live topology and clients only"]:::bpi
        CMD["steer.sh + steer_drv<br/>validated command adapter"]:::bpi
        METRICBR["Raw observation boundary<br/>EasyMesh metric/query results"]:::contract
        CTRL["em_ctrl<br/>EasyMesh controller protocol engine"]:::bpi
        MODEL[("OneWifiMesh model<br/>topology, BSS and STA state")]:::bpi
        C1905["ieee1905_em_ctrl<br/>AL-SAP / IEEE 1905.1"]:::bpi
        CAGENT["colocated em_agent<br/>no optimizer"]:::bpi
        CONEWIFI["OneWifi + HAL<br/>2.4 / 5 / 6 GHz VAPs"]:::bpi

        HTTP <-->|"libemcli command channel"| CTRL
        CMD -->|"steer_sta command"| CTRL
        METRICBR <-->|"read-only metric queries/reports"| CTRL
        CTRL <--> MODEL
        CTRL <--> C1905
        CAGENT <--> C1905
        CAGENT <--> CONEWIFI
    end

    subgraph EXTENDERS["bpiap[-NNN] LXD containers — four accepted"]
        direction TB
        A1905["ieee1905_em_agent"]:::bpi
        AGENT["em_agent<br/>policy receiver and protocol endpoint<br/>no optimizer; local steering mode 0"]:::bpi
        ONEWIFI["OneWifi + HAL<br/>backhaul STA + fronthaul VAPs"]:::bpi
        A1905 <--> AGENT
        AGENT <--> ONEWIFI
    end

    subgraph STATIONS["wlan-client[-NNN] LXD containers — ten accepted"]
        direction TB
        SUPP["WNM-capable wpa_supplicant<br/>802.11v BTM response"]:::client
        DATA["wlan0 traffic and DHCP"]:::client
        SUPP --- DATA
    end

    MAC <-->|"namespaced hwsim wiphy"| CONEWIFI
    MAC <-->|"namespaced hwsim wiphy"| ONEWIFI
    MAC <-->|"namespaced hwsim wiphy"| SUPP

    C1905 <-->|"wireless backhaul<br/>1905 CMDUs and ACKs"| A1905
    ONEWIFI <-->|"802.11 association,<br/>measurements and BTM"| SUPP

    OBS -->|"GET live topology / clients"| HTTP
    OBS -->|"associated STA, AP and<br/>candidate-link measurements"| METRICBR
    ACT -->|"current lab hook:<br/>lxc exec bpibroadband -- steer.sh"| CMD
    CTRL -->|"Client Steering Request"| C1905
    A1905 -->|"RBus raw-frame action"| ONEWIFI
    SUPP -->|"reassociation and BTM response"| ONEWIFI
    A1905 -->|"association notification,<br/>metrics and steering report"| C1905
    MODEL -->|"association/model feedback"| HTTP
    HTTP --> VERIFY
    METRICBR --> VERIFY
    ORACLE -.-> VERIFY

    DEMO["Do not use for decisions:<br/>canned WebUI metrics, Optimize Layout,<br/>wmediumd plan or configured SNR"]:::warning
```

The absence of a decision edge from wmediumd or the BPI agents to the decision
engine is intentional. wmediumd knows the simulated truth, and the BPI agents
know local protocol state, but neither selects the target for this experiment.

## Interface contracts

| Interface | Producer | Consumer | Contract now |
| --- | --- | --- | --- |
| RF generation | `wmdcfg` | wmediumd | Atomic radio-pair SNR generations with verified restore |
| RF transport | wmediumd | hwsim | Frequency-isolated simulated frame delivery |
| live topology | controller/WebUI | external observer | `/api/v1/topology` with current devices, radios and BSSs |
| live association | controller/WebUI | external observer/verifier | Parent agent and STA MAC in `/api/v1/topology` |
| real metrics | EasyMesh reports/queries | external observer | Required adapter; current WebUI metric handlers are not valid |
| policy baseline | operator/external setup | controller and agents | Reporting/exclusion configuration; local agent steering set to mode 0 |
| steer action | external actuator | controller | `steer.sh STA TARGET_BSSID` at the current implementation stage |
| protocol action | controller | source agent | EasyMesh Client Steering Request in Mandate mode |
| WLAN action | source agent/OneWifi | client | 802.11v BTM Request from the source VAP |
| outcome | client/agent/controller | external verifier | link, BTM/report, model and API must converge |
| experiment truth | runner/client/health audit | recorder only | Scenario events, client link, traffic and restart counters |

### Observation boundary

Only the topology endpoint is accepted as live topology and association state.
The other WebUI endpoints below are not optimizer inputs at this stage:

- `/api/v1/clients` reads packaged `static/clients.json` demonstration data;
- `/api/v1/metrics/clients` returns canned demonstration clients and values;
- performance and interference endpoints also contain demonstration data.

The first implementation task is therefore a read-only observation adapter for
real EasyMesh Associated STA Link Metrics, AP Metrics and candidate-link
measurements. It should expose timestamped raw facts without scoring them. If a
small native bridge is required at the controller boundary, it remains an
interface adapter only: no optimizer state or algorithm may enter the image.

Direct MariaDB and `iw` reads are useful acceptance oracles. They must not
become the durable optimizer API because they bypass the EasyMesh observation
contract being evaluated.

### Action boundary

The current action hook is deliberately narrow:

```text
external actuator
  -> lxc exec bpibroadband -- /usr/bin/steer.sh STA TARGET_BSSID
  -> steer_drv / libemcli
  -> em_ctrl Client Steering Request
```

This path is already proven at scale. The actuator must resolve the current
source and validate the target immediately before execution. A later
authenticated steering API may replace `lxc exec`, but it must preserve the
same transaction and verification semantics.

## External optimizer components

The proposed host-side Python package is:

```text
gen/optimizer/
|-- pyproject.toml
|-- configs/
|   `-- threshold-policy.yaml
|-- optimizer/
|   |-- cli.py
|   |-- model.py
|   |-- observer.py
|   |-- policy.py
|   |-- state.py
|   |-- actuator.py
|   |-- verifier.py
|   `-- recorder.py
`-- tests/
```

Its execution modes are:

| Mode | Behavior |
| --- | --- |
| `observe` | Collect and record real snapshots; never recommend or steer |
| `recommend` | Run the complete state machine and record decisions; never act |
| `act` | Issue one validated action and verify the complete outcome |

The decision core should be a pure function over a snapshot, versioned policy
and prior client state. Network I/O belongs in adapters, not in scoring logic.
This makes recorded inputs replayable in unit tests.

## External policy model

The optimizer policy is its own versioned configuration, not an EasyMesh Policy
Configuration TLV and not a WebUI conservative/balanced/aggressive preset. The
following values illustrate the schema; they are not accepted tuning defaults.

```yaml
policy_version: 1
decision_interval_seconds: 1
current_rcpi_below: 100
minimum_target_gain_rcpi: 16
condition_hold_seconds: 5
minimum_dwell_seconds: 20
steer_timeout_seconds: 10
post_steer_cooldown_seconds: 30
maximum_in_flight_per_sta: 1
reject_stale_metrics_after_seconds: 3
```

Configured wmediumd SNR is never substituted for observed RCPI. The two are
different quantities and their relationship must be measured through the
actual Wi-Fi/EasyMesh reporting path.

EasyMesh policy configuration remains useful only to establish the experiment
environment:

- agent-local steering mode `0` so no BPI process makes a steering decision;
- empty local and BTM exclusion lists unless the experiment tests exclusions;
- reporting intervals and inclusion settings needed to obtain raw metrics; and
- no reliance on the misleading WebUI `Add Station Entry` label: per-radio
  settings are keyed by RUID, not client MAC.

## Decision and feedback sequence

```mermaid
sequenceDiagram
    autonumber
    participant R as wmdcfg runner
    participant W as wmediumd
    participant N as hwsim / Wi-Fi network
    participant E as BPI EasyMesh controller + agents
    participant O as External observer
    participant P as External policy engine
    participant A as External actuator
    participant V as External verifier
    participant J as Experiment journal

    Note over E,P: Agent-local steering is disabled and no BPI component selects a target
    R->>W: Apply next atomic SNR generation
    W->>N: Change simulated frame delivery conditions
    N->>E: Real association and link measurements
    E-->>O: Topology, AP metrics and STA link metrics
    O->>O: Normalize identities, timestamps and freshness
    O->>P: Immutable observation snapshot
    P->>P: Update hold/dwell/hysteresis state
    P-->>J: Snapshot, candidates, scores and state transition

    alt Not eligible or data stale
        P-->>J: No action with explicit reason
    else Exactly one target is eligible
        P->>A: Decision(STA, source, target, reason, policy hash)
        A->>E: steer.sh STA TARGET_BSSID
        E->>E: EasyMesh Steering Request and matching 1905 ACK
        E->>N: OneWifi transmits BTM from source VAP
        N-->>E: Reassociation and BTM response/report
        A->>V: Start bounded verification transaction
        E-->>V: Controller model and API association update
        N-->>V: Client-link and traffic test oracle
        V-->>P: Passed, rejected or timed out
        V-->>J: Per-plane evidence and convergence latency
        P->>P: Enter cooldown or failure backoff
    end

    R->>W: Restore captured medium baseline
    W-->>R: Readback confirms restoration
    R-->>J: Final scenario and restoration result
```

The feedback loop belongs to the external optimizer: it observes the resulting
association and closes its own transaction. It never asks wmediumd whether the
steer should have worked.

## Health and safety gates

Action mode is inhibited unless all of these are true:

- expected `5/15/50` model and 10/10 active clients are present;
- the STA has one current association and a fresh current-link measurement;
- the target BSSID exists, is not the source and is eligible for the STA;
- candidate measurements are fresh and exceed the configured margin;
- minimum dwell and condition-hold periods are satisfied;
- no steering transaction or cooldown exists for the STA;
- wmediumd is healthy, but its link values are not read by the decision engine;
- controller/agent/OneWifi services have not restarted; and
- the experiment recorder is writable.

Missing, contradictory or stale data results in `NO_ACTION`, never an inferred
value or optimistic steer.

## Implementation stages

1. **Real observation vertical slice.** Return real hwsim client identities and
   changing EasyMesh metrics; prove correlation with a crossover without
   exposing wmediumd truth to the optimizer.
2. **Observe mode.** Record normalized snapshots from both rev130 and rev150-VM.
3. **Recommend mode.** Replay snapshots through a deterministic state machine
   and require exactly one recommendation in the active crossover.
4. **Act mode.** Use the proven `steer.sh` adapter, bounded verification and
   cooldown.
5. **Scale and fault tests.** Ten clients, four extenders, stale metrics,
   rejected BTM, missing target, delayed model convergence and process loss.
6. **Optional API hardening.** Replace `lxc exec` with authenticated observation
   and steering endpoints without moving optimization logic into the BPI image.

## Acceptance criteria

The first optimizer is accepted only when the same policy and scenario pass on
rev130 and rev150-VM with:

- identical policy/scenario hashes and frozen radio bindings;
- real measurement changes preceding the decision;
- exactly one explained steer for the selected STA;
- no unintended agent-local steering;
- client link, BTM/report, controller database and API agreement;
- bounded traffic impact and no service restarts;
- cooldown preventing an immediate return steer;
- verified wmediumd restoration; and
- a complete append-only record sufficient to replay the decision offline.

The WebUI may later display optimizer state or submit external policy files, but
it is never the decision engine. `Optimize Layout`, canned metrics and generic
steering presets remain outside this architecture.
