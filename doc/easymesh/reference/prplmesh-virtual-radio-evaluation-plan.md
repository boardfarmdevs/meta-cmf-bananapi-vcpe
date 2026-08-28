# prplMesh virtual-radio evaluation plan

## Purpose

Establish a small prplMesh controller-and-agent lab that uses the same Linux
7.0 `mac80211_hwsim` radios, multichannel wmediumd medium, WLAN clients, and RF
scenarios as the RDK-B lab. The result will provide an implementation-level
comparison of onboarding, telemetry, steering, recovery, and optimizer
integration without changing the accepted RDK-B runtime.

This is an implementation plan only. It does not authorize a prplMesh build or
deployment yet.

## Target architecture

```text
                         optimizer / test drivers
                          | topology and metrics
                          | steering requests
                          v
  +-------------------------------+       +----------------------+
  | prpl-controller               |       | configurator         |
  | controller + colocated agent  |       | RF scenario engine   |
  +---------------+---------------+       +----------+-----------+
                  | IEEE 1905.1 / EasyMesh            |
          +-------+----------------------+             | control
          |                              |             v
  +-------+---------+            +-------+---------+  +----------------+
  | prpl-agent-001  |            | prpl-agent-002  |  | wmediumd       |
  | hwsim PHY       |            | hwsim PHY       |  | frame medium   |
  +-------+---------+            +-------+---------+  +-------+--------+
          | fronthaul/backhaul            |                    |
          +-------------------------------+--------------------+
                                          |
                              +-----------+-----------+
                              | hwsim WLAN clients    |
                              | private and IoT sets  |
                              +-----------------------+
```

Each prplMesh node receives an exclusive, permanently identified hwsim PHY.
No PHY may be shared with an active OneWifi/RDK-B node. The first evaluation
uses a separate roster and separate LXD containers so both implementations can
be compared without cross-contamination.

## Constraints

- Preserve the RDK-B lab as the working baseline.
- Use native Ubuntu builds in LXD first; do not introduce prplOS or Yocto into
  the initial comparison.
- Pin the source revision and all build dependencies.
- Reuse the medium, clients, scenarios, observer protocol, and result format
  wherever their contracts are implementation-neutral.
- Keep prplMesh's controller algorithms disabled or fixed when evaluating an
  external optimizer, so there is only one steering decision maker.
- Do not treat 6 GHz or wireless multihop as entry requirements. Establish a
  stable 2.4/5 GHz baseline first.
- Stop the spike if it begins to require broad prplMesh core rework. Record the
  missing capability instead of recreating another large downstream stack.

## Implementation phases

### 0. Freeze the comparison contract

1. Select and record a prplMesh release or exact commit from the upstream
   repository.
2. Record its supported Multi-AP profile, Linux distribution, compiler,
   hostapd, wpa_supplicant, and hwsim requirements.
3. Decide which controller functions are enabled for the baseline: topology,
   metrics, channel selection, client steering, optimal path, and load
   balancing.
4. Define the first topology: one controller with colocated agent, two remote
   agents, and five clients.
5. Freeze common acceptance measurements and result schemas before building.

Output: a one-page revision and capability manifest.

### 1. Prove an unmodified native build

1. Create an Ubuntu builder container independent of the runtime containers.
2. Clone the pinned prplMesh source and install only documented dependencies.
3. Build controller, agent, platform adapters, CLI/API components, and upstream
   tests without downstream patches.
4. Run unit and component tests and archive the logs, binary manifest, and
   dependency versions.
5. Package the install tree so runtime containers contain no compiler or source
   checkout.

Gate: an unmodified, reproducible native build and passing upstream test set.

### 2. Create minimal LXD runtime images

1. Create one controller image and one agent image from a small Ubuntu base.
2. Install the packaged binaries, configuration, hostapd/wpa_supplicant, and
   systemd units.
3. Grant only the network namespace, raw-socket, and netlink access required by
   the processes.
4. Connect the 1905/EasyMesh data plane to a dedicated lab bridge.
5. Persist AL-MAC, radio identities, and node configuration across restarts.

Gate: every daemon has explicit ownership, logs, readiness, and restart policy;
no interactive startup steps are required.

### 3. Integrate stable virtual radios

1. Extend the declarative radio inventory with a disjoint prplMesh roster.
2. Assign PHYs by permanent hwsim identity, never by transient `phyN` order.
3. Move the assigned PHY into each container before starting its agent.
4. Validate interface creation, AP operation, station operation, channel
   changes, and frame registration without wmediumd.
5. Start wmediumd once with the complete provisioned roster and verify that
   stopped radios remain configured but dormant.

Gate: repeated node stop/start preserves PHY, MAC, AL-MAC, and medium inventory,
and never restarts unrelated nodes.

### 4. Establish basic EasyMesh operation

1. Start the controller and colocated agent.
2. Onboard two remote agents over 5 GHz backhaul.
3. Expose private and IoT fronthaul BSSs on 2.4 and 5 GHz.
4. Associate five existing client containers.
5. Verify topology, BSS, STA ownership, channel, RCPI, and traffic from both the
   controller API and over-the-air captures.
6. Stop and restart each agent and verify controller aging and re-onboarding.

Gate: cold start and per-node recovery complete within defined time bounds with
no manual nudges.

### 5. Add implementation-neutral adapters

1. Define a topology/metrics adapter using the supported prplMesh northbound
   interface, preferring NBAPI and using BML only where necessary.
2. Define a steering actuator that maps the lab's stable node/client names to
   prplMesh steering requests.
3. Map output into the optimizer's existing snapshot and action-result schemas.
4. Keep the adapter outside prplMesh unless an upstream-supported plugin point
   exists.
5. Add capability discovery so unsupported measurements are explicit rather
   than represented as zero or `N/A` without cause.

Gate: the same optimizer test can read either RDK-B or prplMesh telemetry and
request a steer through a selected backend.

### 6. Reuse the RF scenario suite

Run, in order:

1. static good-link baseline;
2. deterministic manual steer;
3. slow crossover between two APs;
4. threshold-hover and anti-ping-pong case;
5. client disappearance and return;
6. agent RF outage and return;
7. mixed private/IoT traffic;
8. controller and agent restart recovery.

For every run, preserve the source revision, manifest, initial topology,
wmediumd scenario, packet capture, decisions, requested actions, actual
associations, controller model, and timing.

Gate: the scenario result is reproducible and an observed association change is
confirmed independently of the controller's command response.

### 7. Add advanced radio cases

Only after the earlier gates pass:

1. add 6 GHz AP and client operation;
2. establish tri-band onboarding;
3. test wireless multihop backhaul;
4. expose candidate-link measurements;
5. test backhaul topology and channel optimization separately from client
   steering.

These are capability evaluations, not reasons to weaken the stable baseline.

## Acceptance criteria

The first useful prplMesh lab must demonstrate all of the following:

- one-command cold start with one controller, two agents, and five clients;
- complete, current topology and per-client link metrics;
- successful manual steering confirmed by the station link and controller
  ownership;
- repeatable wmediumd attenuation and mobility scenarios;
- bounded recovery after an agent, client, controller, or medium restart;
- no identity drift, duplicate topology records, orphaned radios, or unrelated
  node restarts;
- stable process count and bounded memory/CPU use during the acceptance run;
- no unexplained downstream core patch; and
- archived evidence sufficient to reproduce every claimed result.

## Comparison and decision gate

Compare prplMesh and RDK-B using the same topology and scenarios:

| Area | Measurement |
| --- | --- |
| Bring-up | cold-start time, manual interventions, onboarding completeness |
| Recovery | node/medium restart time and topology convergence |
| Telemetry | metric availability, freshness, candidate-link coverage |
| Steering | API semantics, actual success rate, failure visibility |
| Optimizer fit | adapter size, decision ownership, action/result contract |
| RF support | multichannel, 6 GHz, multihop, dynamic VAP behavior |
| Stability | crashes, leaks, duplicate state, long-run drift |
| Maintenance | downstream patches and implementation-specific workarounds |

Proceed beyond the evaluation only if prplMesh provides a materially smaller
and clearer integration boundary, or exposes capabilities the RDK-B stack
cannot provide without disproportionate rework.

## Upstream starting points

- [prplMesh repository](https://gitlab.com/prpl-foundation/prplmesh/prplMesh)
- [Native agent and hwsim guidance](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/tree/stable/v1.7/agent)
- [Container build tooling](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/master/tools/docker/README.md)
- [Controller configuration](https://gitlab.com/prpl-foundation/prplmesh/prplMesh/-/blob/master/documentation/prplMesh-configuration.md)

Before implementation begins, revalidate these links and instructions against
the pinned source revision; upstream branches and supported environments can
change.
