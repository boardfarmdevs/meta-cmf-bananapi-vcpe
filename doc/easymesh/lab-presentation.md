---
marp: true
theme: default
paginate: true
title: EasyMesh steering policy research lab
description: Container, hwsim and wmediumd platform for repeatable steering research
---

# EasyMesh steering policy research lab

## A repeatable virtual WLAN for developing and comparing new policies

RDK-B EasyMesh · LXD · Linux 7 hwsim · multichannel wmediumd · Vagrant

---

# Why this lab exists

- Physical Wi-Fi labs are valuable but slow and expensive to replicate.
- Steering algorithms need controlled RF trajectories and repeatable faults.
- A successful steering command is not proof of a useful policy.
- We want many APs and clients, deterministic experiments, complete evidence
  and quick reset to a known baseline.

**Primary goal:** derive steering mechanisms that improve client experience
and explain why they outperform simple baselines.

---

# The lab in one picture

```text
Ubuntu host
`-- VirtualBox VM, managed by Vagrant
    |-- Boardfarm Docker lab: br-wan105 + DHCP + WAN
    |-- LXD: bpibroadband controller/agent
    |-- LXD: four tri-band extender agents
    |-- LXD: ten real supplicant WLAN clients
    |-- Linux 7 mac80211_hwsim radio pool
    |-- patched multichannel wmediumd + control socket
    `-- em_cli WebUI/API :8888
```

Current accepted model: **5 agents · 15 radios · 50 BSSs · 10 clients**

---

# What is real, and what is simulated?

| Real implementation path | Simulated laboratory element |
| --- | --- |
| RDK-B OneWifi and EasyMesh processes | RF propagation and interference |
| IEEE 1905 EasyMesh messages | hwsim radio hardware |
| 802.11 association and 802.11v BTM | client/AP placement and motion |
| controller model and WebUI/API | WAN provider and lab endpoints |
| client traffic and DHCP | reproducible faults and gradients |

The same control and association software runs as on the BPI design. The
medium and radio hardware are virtual.

---

# Boardfarm has one narrow role

```text
Boardfarm
  -> creates br-wan105
  -> supplies DHCP to bpibroadband erouter0
  -> supplies IPv4/IPv6 WAN and Internet connectivity

Boardfarm does not
  -> implement Wi-Fi or EasyMesh
  -> simulate RF
  -> select an AP
  -> optimize or steer a client
```

This keeps WAN infrastructure reproducible without mixing it with policy logic.

---

# What can be demonstrated today?

1. Cold boot or reboot to a complete tri-band topology without manual nudges.
2. Watch all agents, radios, BSSs and clients in the live WebUI.
3. Inspect associated-client RCPI updating every two seconds.
4. Command a client steer through the real EasyMesh/BTM path.
5. Move ten clients visibly around five agents using live wmediumd control.
6. Isolate an extender over RF; watch clients move and the backhaul recover.
7. Stop/restart an AP and verify service, WLAN and controller recovery.
8. Capture IEEE 1905/EasyMesh traffic for offline Wireshark analysis.

---

# Current evidence

- Complete cold deployment: Boardfarm **60/60** checks.
- Topology/API: six rendered nodes and ten unique live clients.
- Service stability: zero OneWifi, agent, controller or CLI restarts.
- Traffic baseline: all ten clients reach the WLAN gateway.
- Commanded return steering: **4/4** passed.
- Scaled commanded steering: **30/30** passed across ten clients/five agents.
- Live RCPI experiment: reported values tracked the applied RF phases.
- Extender RF outage: client movement, backhaul loss, restoration and rejoin passed.
- IEEE 1905 capture: live decapsulated traffic verified on controller `brlan0`.

These are transport and lab-capability results—not yet an autonomous optimizer.

---

# wmediumd is an independent RF actuator

```text
scenario source
  -> compile named roles into physical radio pairs
  -> timed atomic SNR generations
  -> /run/wmediumd-control.sock
  -> frame delivery through hwsim
  -> real measurements, loss, scans and associations
```

- Directed or symmetric links; 2.4, 5 and 6 GHz isolated correctly.
- Live `APPLY`, readback, matrix dump and exact baseline restoration.
- No daemon restart during a scenario.
- RF phases remain bound to physical APs after a client roams.

Configured SNR is evaluator truth. It is never policy input.

---

# Commanded steering path works today

```text
steer.sh STA TARGET_BSSID
  -> em_ctrl Client Steering Request
  -> IEEE 1905 source agent + ACK
  -> OneWifi raw-frame provider
  -> 802.11v BTM Request
  -> client reassociation
  -> association report and controller model
  -> WebUI/API parent update
```

A pass requires the actual link, controller database, API parent and traffic to
agree. An HTTP success or 1905 ACK alone is insufficient.

---

# What is missing: the optimizer

The BPI implementation provides measurements, policy transport and steering
mechanisms. It does **not** provide the decision engine we need.

```text
observations -> external Python optimizer -> steer action
      ^                  |                      |
      +---------- outcome verifier <-----------+
```

The optimizer must own candidate filtering, scoring, thresholds, hysteresis,
dwell, cooldown, failure backoff and per-client transaction state.

---

# Correct integration boundary

| Adapter | Initial interface | Destination |
| --- | --- | --- |
| topology/association | `/api/v1/topology`, `/api/v1/clients` | normalized snapshot |
| current link quality | live EasyMesh RCPI reports | normalized snapshot |
| target quality/load | standard EasyMesh metrics/queries | normalized snapshot |
| action | `steer.sh STA BSSID` | controller transaction |
| verification | link + model + API + traffic | outcome record |

First answer the open question: which candidate-link measurements are already
implemented and which require a read-only controller adapter?

---

# First policy: intentionally simple

```text
STABLE -> DEGRADED -> ELIGIBLE -> STEER_PENDING
   ^                                  |
   +---- COOLDOWN <- VERIFYING <-------+
```

Inputs:

- current-link trigger;
- minimum candidate improvement;
- condition hold and minimum dwell;
- one outstanding action per station;
- steer timeout and cooldown; and
- measurement freshness.

Run it in replay, then recommend-only, then act mode.

---

# Scale is a research feature

```yaml
controller_agents: 1
extenders: 8
clients: 40
bands: [2.4GHz, 5GHz, 6GHz]
seed: 1701
```

A topology manifest can generate deterministic containers, MACs, hwsim radios
and wmediumd links. We then measure the capacity curve:

- onboarding and reporting latency;
- CPU and memory per node/client;
- event loss during bursts;
- wmediumd matrix/control cost; and
- maximum stable profile per host size.

Containers make expansion cheap; acceptance gates make it credible.

---

# Scenario library

| Scenario | Policy behavior under test |
| --- | --- |
| AP crossover / slow walk | threshold, dwell, hysteresis |
| fast transit | benefit horizon vs roam cost |
| asymmetric path | uplink/downlink awareness |
| strong congested AP | signal/load trade-off |
| client flash crowd | coordinated redistribution |
| extender outage/recovery | resilience and re-entry |
| stale metrics | uncertainty and safe no-action |
| BTM rejection | capability filters and backoff |

Every active run has a no-steering control and repeats across deterministic
seeds.

---

# Candidate novel mechanisms

- Uncertainty-aware scoring for stale or contradictory measurements.
- Roam-cost-aware decisions based on predicted benefit over time.
- RCPI-trend and mobility prediction without chasing short fades.
- Cohort-aware scheduling to prevent a client stampede to one AP.
- Resilience-aware scoring using extender and backhaul health.
- Adaptive hysteresis by mobility class and recent outcomes.
- Safe contextual learning in replay/recommend mode before live action.

Novelty is not a new formula alone. It is a repeatable improvement over frozen
baselines on held-out scenarios.

---

# How policies will be scored

**Client benefit**

- availability, goodput, latency and packet loss;
- time below service/RCPI floor;
- recovery time and fairness.

**Control cost**

- steering count, rejection and failure rate;
- ping-pongs and disruption per roam;
- convergence time and EasyMesh control load.

Report distributions and confidence intervals across runs—not a single good
screenshot.

---

# Stability work directly supports policy research

Highest-priority open items:

1. association/model consistency under simultaneous client events;
2. rare raw-frame provider delivery miss after successful 1905 ACK;
3. missing controller liveness/aging for isolated extenders;
4. recurring wmediumd command-2 `EINVAL` diagnostic;
5. long-run controller/CLI memory and CPU envelopes; and
6. reproducible scale limits for the VM profiles.

Bad observations produce bad policy conclusions. These are experimental
validity tasks, not peripheral cleanup.

---

# Roadmap

```text
accepted appliance
  -> trustworthy observations
  -> replayable policy harness
  -> baseline shadow policy
  -> closed-loop baseline
  -> scalable scenario benchmark
  -> novel policy comparison
  -> hardened observation/action API
```

Near-term target: one crossover, one explained recommendation, one verified
steer, one cooldown—without reading wmediumd truth in the optimizer.

---

# Suggested live demo

1. `sudo easymesh-labctl check`
2. Open Network Topology and Connected Clients.
3. Run the RCPI monitor and watch reported signal change.
4. Run one carousel round and watch groups disconnect/reconnect.
5. Execute a manual `steer.sh` and verify all observation planes.
6. Run extender RF outage/recovery.
7. Show the wmediumd event log and exact restoration result.
8. Show an IEEE 1905 packet capture in Wireshark.
9. End on the external optimizer boundary and research roadmap.

The demo proves we now have the instrument needed to develop the policy.
