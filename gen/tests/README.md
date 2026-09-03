# EasyMesh lab tests

This directory contains live acceptance tests, long-running campaigns, build
artifact checks and isolated unit tests. Run commands from the repository root
unless a section says otherwise.

`hwsim-monitor-ack.sh` is a live Linux 7 multichannel regression. It briefly
enables the normally-down `hwsim0` radiotap monitor, generates acknowledged
client traffic, and rejects a kernel Oops, wmediumd death, or nl80211 deadlock.
Run it only on a healthy lab whose monitor interface is down.

## Basic lab concepts

### Devices and containers

The accepted small lab has five EasyMesh devices and twenty WLAN clients:

| Lab object | LXD container | EasyMesh role |
|---|---|---|
| Gateway | `bpibroadband` | Controller and colocated `Agent-1` |
| Extenders | `bpiap`, `bpiap-001`, `bpiap-002`, `bpiap-003` | EasyMesh agents |
| Private clients | `wlan-client` through `wlan-client-009` | `private_ssid` stations |
| IoT clients | `wlan-client-010` through `wlan-client-019` | `iot_ssid` stations |

The WebUI names extenders from their persistent EasyMesh AL identities. A
container suffix therefore does not necessarily equal its displayed
`Extender-N` number.

### Radio and interface names

`wifi1.1` is a Linux wireless interface inside each BPI container. It is not
an EasyMesh-standard name. It is the stable interface naming convention of the
current tri-band OneWifi/HWSIM image:

| Interface | Band | Mode and purpose |
|---|---:|---|
| `wifi0` | 2.4 GHz | `private_ssid` fronthaul AP |
| `wifi0.1` | 2.4 GHz | mesh-backhaul AP when enabled |
| `wifi0.2` | 2.4 GHz | `iot_ssid` fronthaul AP |
| `wifi1` | 5 GHz | `private_ssid` fronthaul AP |
| `wifi1.1` | 5 GHz | `mesh_backhaul` AP; the parent side of current backhaul links |
| `wifi1.2` | 5 GHz | `iot_ssid` fronthaul AP |
| `wifi1.3` | 5 GHz | managed mesh STA; the child side of an extender backhaul link |
| `wifi2` | 6 GHz | `private_ssid` fronthaul AP |
| `wifi2.1` | 6 GHz | mesh-backhaul AP |
| `wifi2.2` | 6 GHz | `iot_ssid` fronthaul AP |
| `wlan0` | selected client band | managed station inside a WLAN-client container |

The current deterministic multi-hop tests select the 5 GHz pair `wifi1.1` and
`wifi1.3`. When a child associates, mac80211 may create an interface such as
`wifi1.1.sta1` on the parent. This is a dynamic four-address AP/VLAN station
interface. Its numeric suffix is not stable; discover it with `iw dev`.

The host-side hwsim interfaces are named `virt-wlanN`. LXD passes one of those
radios into a container, where OneWifi creates the `wifi*` interfaces above.

Useful inspection commands are:

```sh
lxc exec bpiap-003 -- iw dev
lxc exec bpiap-003 -- iw dev wifi1.3 link
lxc exec bpiap-003 -- iw dev wifi1.1 info
```

### Identities and measurements

- A BSSID identifies one AP BSS, such as the 5 GHz `private_ssid` or
  `mesh_backhaul` BSS on one agent.
- A STA MAC identifies the station side of a WLAN client or extender
  backhaul.
- An AL MAC identifies an EasyMesh/IEEE 1905 device. The controller model and
  topology API use AL identities for mesh nodes.
- RSSI is expressed in dBm. EasyMesh RCPI uses half-dB units:
  `RCPI = 2 * (RSSI + 110)`, clamped to `0..220`; `255` means unavailable.
- `iw` proves the current kernel association. The controller database and
  `/api/v1/topology` prove that the EasyMesh model has converged to it. Tests
  deliberately check both because one can be current while the other is stale.

### wmediumd and real associations

wmediumd controls the simulated RF relationship between hwsim radios. Tests
use its control socket to change SNR atomically without restarting the daemon.
A wmediumd change influences association decisions, but it does not directly
edit the EasyMesh topology.

The multi-hop test uses a different mechanism: it writes a selected parent
BSSID to the child's OneWifi data model. OneWifi then makes a real nl80211
association. The resulting relationship is published by the agents through
IEEE 1905 and learned by the controller.

Tests that modify wmediumd record the initial matrix and restore the exact
values in a `finally`/exit path. Client placement may nevertheless change as a
result of roaming and can take additional time to converge.

### Observer-facing status

Demo and live-scenario entry points explain each action before performing it:

- bright cyan `==>` messages identify a change or command being issued;
- bright yellow `...` messages state what convergence is being awaited and
  its bound;
- bright green `OK:` messages identify an achieved gate;
- blue section and note messages give the scenario context.

Status messages use stderr so CSV, JSON and command-substitution stdout remain
machine-readable. Colors are enabled only on an interactive terminal. Set
`EASYMESH_COLOR=always` to force them through a nested console or
`EASYMESH_COLOR=never`/`NO_COLOR=1` for plain text.

## Before running live tests

Confirm that the lab and API are healthy:

```sh
lxc list
curl -fsS http://127.0.0.1:8888/api/v1/topology | jq '.nodes | length'
./gen/tests/health-audit.sh
```

Live tests expect `lxc`, `curl`, `jq`, Python 3 and access to the wmediumd
control socket where applicable. Unit tests additionally use `pytest` or a
modern Node.js runtime. `p0-cold-reconstruction.sh` is the exception that
explicitly uses `sudo` because it invokes the system-level VM runtime and
Docker/Boardfarm reconstruction.

## Test selection

| Test | Type | Changes the running lab? |
|---|---|---:|
| `health-audit.sh` | Live health gate | No |
| `verify-hwsim-profile-uniqueness.sh` | Live configuration gate | No |
| `multihop-backhaul-test.sh` | Live backhaul acceptance | Yes |
| `multihop-backhaul.sh` | Backhaul profile implementation and diagnostics | Yes |
| `gen/steer.sh` (manual) | One live commanded steer | Yes |
| `steering-matrix.sh` | Live commanded steering | Yes |
| `association-ownership-regression.sh` | Delayed serving-BSS consistency | Yes |
| `ap-recovery.sh` | Live forced AP failure/recovery | Yes, disruptive |
| `candidate-rcpi-test.py` | Live candidate telemetry | Temporary wmediumd override |
| `optimizer-live-smoke.py` | Live optimizer observation/evaluation | No steering |
| `optimizer-dynamic.sh` | Closed-loop scenario/telemetry/policy acceptance | Temporary RF changes; optional one steer |
| `wmediumd-client-carousel.py` | Live RF/roaming demonstration | Temporary RF changes |
| `wmediumd-extender-outage.py` | Live RF outage/recovery | Temporary RF changes |
| `p0-churn-soak.py` | Repeated live RF acceptance | Temporary RF changes |
| `scale-soak-campaign.sh` | Sequential 20/50/100-client qualification | Reprovisions the hwsim pool and client roster |
| `p0-cold-reconstruction.sh` | Repeated full reconstruction | Yes, highly disruptive |
| `bpibroadband-memory-profile.py` | Live measurement | No |
| `onewifi-memory-slope.py` | Live bounded-growth gate | No |
| `wmediumd-performance.py` | Live CPU/traffic benchmark | Generates bounded WLAN traffic |
| `deployment-model-evidence.sh` | Runtime/guest comparison evidence | Health audit only |
| `deployment-host-evidence.sh` | Physical-host/hypervisor comparison evidence | No |
| `steer-by-name-test.sh` | Isolated shell unit test | No |
| `test_client_pool.py` | Isolated pytest unit test | No |
| `test_soak_harness.py` | Isolated pytest unit test | No |
| `verify-snmp-subagent-selfheal.sh` | Built-rootfs check | No live lab required |
| `verify-webui-static-sync.sh` | Built-rootfs check | No live lab required |
| `webui-extender-signal-test.js` | Isolated WebUI unit test | No |
| `webui-mesh-device-signal-test.js` | Isolated WebUI unit test | No |
| `webui-metrics-reporting-test.js` | Isolated WebUI unit test | No |
| `webui-topology-layout-test.js` | Isolated WebUI unit test | No |

## Live health and configuration tests

### `onewifi-memory-slope.py`

Measure the post-warmup PSS slope of `OneWifi` on the controller and every
running extender without changing lab state:

```sh
./gen/tests/onewifi-memory-slope.py \
  --duration 900 --warmup 120 --interval 30 \
  --output /tmp/onewifi-memory-slope.json
```

The default gate permits at most 2 MiB/hour per process after warmup and fails
on a missing sample or process restart. A release campaign should use a full
hour; the 15-minute form is a focused regression for the five-second AP-metrics
allocation leak. Run its isolated arithmetic check with
`./gen/tests/onewifi-memory-slope.py --self-test`.

### `wmediumd-performance.py`

Measure idle overhead or drive all selected WLAN clients concurrently:

```sh
./gen/tests/wmediumd-performance.py --mode idle --duration 30
./gen/tests/wmediumd-performance.py \
  --mode ping --duration 20 --ping-interval 0.02 --client-limit 20 \
  --output /tmp/wmediumd-performance.json
```

The JSON report combines process CPU/RSS, affinity, context switches, netlink
drops, packet and queue telemetry, and per-client ping results. CPU is a
percentage of one logical CPU. The accepted measurements and overload boundary
are documented in `doc/easymesh/reference/wmediumd-performance.md`.

### `optimizer-dynamic.sh`

Run the complete five-node closed loop in recommendation-only mode, then in
explicitly acting mode:

```sh
./gen/tests/optimizer-dynamic.sh recommend wlan-client-007 bpiap-001
./gen/tests/optimizer-dynamic.sh act wlan-client-007 bpiap-001
```

The wrapper discovers the client's current owner, SSID and band, freezes the
five mesh radio identities, and makes only the requested target improve while
the other candidates remain weak. The RDK optimizer sees controller APIs and
standard associated/unassociated STA metrics only; it receives neither the
scenario plan nor the expected target.

Recommendation mode requires the exact target BSSID in the optimizer journal.
Act mode additionally requires a successful `steer.sh` action and association
verification. Both modes require exact frequency-qualified wmediumd restore.
The requested target must differ from the client's current serving node.

RDK carries all three logical bands on one hwsim PHY. Inventory therefore
records one permanent radio identity with three frequency contexts, and an
unqualified client/AP scenario follows the client's live band. This keeps
actual frame signal and the HAL's frequency-qualified candidate measurement on
the same medium key.

### `health-audit.sh`

Run:

```sh
./gen/tests/health-audit.sh
```

The audit reads the topology and controller database, counts live clients,
checks that OneWifi/EasyMesh services have not restarted, pings `10.0.0.1`
from every provisioned WLAN client in parallel, summarizes an existing
steering matrix CSV, and prints host memory. It fails on any service restart
or client packet loss above the configured limit.

Useful overrides are `HEALTH_PING_COUNT`, `HEALTH_PING_INTERVAL`,
`HEALTH_PING_MAX_LOSS`, `RESULTS_FILE` and `EASYMESH_REPO`. The default packet
loss limit is zero.

### `verify-hwsim-profile-uniqueness.sh`

Run:

```sh
./gen/tests/verify-hwsim-profile-uniqueness.sh
```

This reads all LXD instances and their attached profiles, finds devices whose
host parent is `virt-wlanN`, and proves that no hwsim radio is assigned to more
than one instance. It includes stopped instances because duplicate ownership
usually fails during a later start. It does not modify LXD.

## Backhaul and recovery tests

### `multihop-backhaul-test.sh`

Run one explicit profile:

```sh
./gen/tests/multihop-backhaul-test.sh star
./gen/tests/multihop-backhaul-test.sh branch
./gen/tests/multihop-backhaul-test.sh chain
```

The profiles are:

```text
star:    Agent-1 -> {bpiap-003, bpiap-002, bpiap-001, bpiap}

branch:  Agent-1 -> bpiap-003 -+-> bpiap-002 -> bpiap
                               +-> bpiap-001

chain:   Agent-1 -> bpiap-003 -> bpiap-002 -> bpiap-001 -> bpiap
```

The wrapper runs `multihop-backhaul.sh test PROFILE`, so it both applies the
profile and performs its complete acceptance check. The profile remains active
afterward. Timestamped logs are stored below `tmp/test-results/multihop/`.

Set `MULTIHOP_MIN_CLIENTS=20` to require the complete small client pool.

### `multihop-backhaul.sh`

This is the implementation and diagnostic interface used by the wrapper. For
each child/parent pair it discovers the parent's current `wifi1.1` BSSID. For
an extender parent it first asserts
`Device.WiFi.AccessPoint.14.ForceApply`, because the backhaul AP can be created
lazily. It then writes the compact BSSID to
`Device.WiFi.STA.2.Bssid` on the child. This causes OneWifi to associate the
child's `wifi1.3` with the selected parent.

The acceptance phase proves the child link, the parent's dynamic station,
gateway forwarding, the controller/API edge, parent-side RSSI/RCPI, all WLAN
client associations and traffic, and exact controller database counts. The
link, parent, model and onboarding timeouts have corresponding
`MULTIHOP_*_TIMEOUT` overrides described by its `--help` output.

Related lower-level operations are:

```sh
./gen/tests/multihop-backhaul.sh apply chain
./gen/tests/multihop-backhaul.sh verify chain
./gen/tests/multihop-backhaul.sh cold-test chain
./gen/tests/multihop-backhaul.sh status
./gen/tests/multihop-backhaul.sh restore
```

`cold-test` stops the extenders, masks EasyMesh protocol services on every
non-anchor node, establishes each requested physical parent in dependency
order, and only then starts that node's agents. `restore` returns all four
extenders to direct Agent-1 backhaul.

### `ap-recovery.sh`

Run with an extender container and one of its private BSSIDs, for example:

```sh
target=$(lxc exec bpiap-003 -- iw dev wifi1 info | awk '/addr/{print $2; exit}')
./gen/tests/ap-recovery.sh bpiap-003 "$target"
```

This is intentionally disruptive. It identifies private-cohort clients on the
target BSSID and force-stops the AP container. Because hwsim does not generate
the expected beacon-loss indication when LXD removes a wiphy, the test records
that stale-link boundary and toggles each affected client's `wlan0` down/up to
inject the missing link-loss condition. It then verifies reassociation away
from the failed BSSID, traffic, controller database agreement, AP restart,
service/backhaul readiness, all private and IoT BSSs, controller visibility,
and an unchanged wmediumd PID.

An exit trap restarts the AP if the test fails while it is stopped. Client
placement is not restored to its original AP. This test currently targets the
ten private-client containers.

## Steering and optimizer tests

### Manual steering with `gen/steer.sh`

`gen/steer.sh` is the host-side operator adapter for one directed EasyMesh
steer. It accepts the stable client and mesh-device names shown by the WebUI,
resolves them against the live topology, prepares a deterministic candidate in
the simulated medium, and sends an exact STA MAC and target BSSID to the
controller container.

Always resolve the command before executing it:

```sh
gen/steer.sh --dry-run sta-0e extender-2
gen/steer.sh sta-0e extender-2
```

Without overrides, the target BSS uses the client's current SSID and band. A
specific band can be requested when the target advertises that combination:

```sh
gen/steer.sh --band 2.4 sta-0e extender-2
gen/steer.sh --band 5 sta-0e extender-2
gen/steer.sh --band 6 sta-0e extender-2
```

Use `agent-1` to target the colocated agent in `bpibroadband`; `controller` is
not a wireless target and has no fronthaul BSS:

```sh
gen/steer.sh --dry-run sta-0e agent-1
gen/steer.sh sta-0e agent-1
```

The STA argument may also be a full MAC address, and the target may be an exact
BSSID. `--ssid private_ssid|iot_ssid` overrides SSID selection, but it should
only be used when the station is provisioned for that SSID.

The default adapter performs these bounded steps:

1. Read `/api/v1/topology` and require exactly one current placement for the
   requested STA.
2. Resolve exactly one target fronthaul BSS for the requested device, SSID and
   band, refusing an ambiguous, missing or already-current target.
3. Map the WebUI identity to its real client container, save the exact current
   wmediumd values, make the target preferable, and prime the target BSS in the
   deliberately small hwsim supplicant scan cache.
4. Execute `/usr/bin/steer.sh STA_MAC TARGET_BSSID` in `bpibroadband`. The
   controller sends the EasyMesh Client Steering Request and the serving agent
   issues the client-facing BTM request.
5. Require both the physical client link and controller/WebUI topology to show
   the requested target, then restore the exact prior wmediumd values.

The temporary RF preparation is a lab actuator, not an EasyMesh policy
primitive. It makes a manual demo repeatable without pretending that a BTM
request can force a real client. To test the station's unassisted BTM policy,
use request-only mode:

```sh
gen/steer.sh --request-only iot-19 extender-2
```

Request-only success proves submission, not movement: the client may reject or
ignore BTM. The command output reports that distinction. For a manual
cross-check, inspect the physical client link and controller topology:

```sh
lxc exec WLAN_CLIENT_CONTAINER -- iw dev wlan0 link

sta=02:00:00:00:0e:00
curl -fsS http://127.0.0.1:8888/api/v1/topology |
  jq --arg sta "$sta" '
    .nodes[]
    | select(any(.STAList[]?; ((.staMAC // "") | ascii_downcase) == $sta))
    | {name, id}'
```

The BSSID shown by `iw` must be the resolved target, and the topology should
eventually place the STA under the same agent. The Network Topology page shows
the move with its steering pulse/trail. Use `steering-matrix.sh` when a
repeatable pass/fail result and convergence timing are required; use the
optimizer smoke test to evaluate policy inputs without issuing a steer.

### `steering-matrix.sh`

Run one or more rounds for one SSID cohort:

```sh
./gen/tests/steering-matrix.sh 1 --ssid private_ssid
./gen/tests/steering-matrix.sh 1 --ssid iot_ssid
```

The script discovers the five 5 GHz target BSSs and the clients in the
selected cohort that are allowed to scan 5 GHz. It reports and skips the
small-profile clients deliberately pinned to 2.4 or 6 GHz; their supplicant
`freq_list` makes a 5 GHz BTM target invalid. For every eligible client the
script chooses a different target, snapshots the client's exact 5 GHz
wmediumd links, keeps the serving AP viable while making the requested target
unambiguously strongest, and invokes `/usr/bin/steer.sh` in `bpibroadband`.
This prevents standards-permitted BTM refusal under an all-equal RF matrix
from making the lab acceptance nondeterministic. A continuous ping runs during
the transaction. Success requires agreement from the command result, the
client's `iw` link, the controller `STAList` row and the topology API. The
exact prior RF values and override flags are restored after every transaction.
Link, database and API convergence times plus packet loss are recorded.

The default artifacts are `tmp/test-results/steering-scale.csv`, the adjacent
`.events.log`, and `.commands.log`. The exit trap restores the all-strong
wmediumd matrix. It does not move clients back to their original APs.

### `association-ownership-regression.sh`

Use this focused regression after changing HAL association events, OneWifi
client deltas, or controller ownership handling:

```sh
./gen/tests/association-ownership-regression.sh \
  --rounds 2 sta-09 wlan-client extender-2 extender-3 extender-1
```

Each target is resolved through `gen/steer.sh`. A pass requires the client
`iw` link and `/api/v1/clients` to converge on the target BSSID and remain equal
for the post-convergence stability window. This catches a delayed stale-AP
event or retained inactive hwsim station row that an immediate steering check
would miss. The default 45-second convergence deadline includes the bounded
HAL diagnostic filter, OneWifi station poll and EasyMesh snapshot repair.
`--convergence`,
`--stability`, and `--results` adjust the gates and artifact path.

### `candidate-rcpi-test.py`

Run:

```sh
python3 gen/tests/candidate-rcpi-test.py \
  --client wlan-client --target bpiap-003 --snr 25
```

The test selects the client's radio and a candidate agent radio, snapshots the
frequency-specific wmediumd matrix, applies one exact SNR override, and sends
an unassociated-STA query to the controller API. It verifies the returned
agent, STA, operating class, channel, simulated-provider marker and expected
RCPI. The expected HWSIM value is derived from the configured SNR for this
provider. A `finally` block restores the original value and override flag and
compares the entire frequency matrix before and after.

Use `--socket`, `--api`, `--opclass`, `--channel` and `--frequency` only when
testing a non-default control socket or band/channel.

### `optimizer-live-smoke.py`

Run:

```sh
python3 gen/tests/optimizer-live-smoke.py --cycles 3
```

This is a read-only optimizer integration test. Each cycle observes the live
controller APIs, obtains candidate-link RCPI through the configured candidate
provider only for clients whose policy gates can consume it, verifies the
policy's expected device/client counts, requires fresh current-link and
selected same-band candidate metrics, and evaluates the threshold policy. An
acceptable current link needs no active candidate transaction; weak links and
band-upgrade policies still fail closed if their complete candidate set cannot
be collected within the freshness bound. It prints the decisions and reasons
but does not deploy steering actions. `--policy`, `--maximum-age-seconds`,
`--interval` and `--base-url` select the policy and observation constraints.

The default 60-second freshness gate covers the measured collection interval
of the 20-client lab. Candidate batches and Agents are queried sequentially by
default because the native WebUI command path serializes `libemcli` access.
Launching concurrent HTTP handlers only makes them contend on that same path
and has caused client-side timeouts in live deployments. A server-side 504 may
also be a correct fail-closed result when controller association ownership is
stale and a required candidate response is incomplete. Tighten the freshness
gate or raise Agent concurrency only after the complete observation interval
has been measured through a command adapter that actually supports concurrent
transactions.

Run this with the VM's supported Python environment; the optimizer package
uses modern Python type syntax.

## wmediumd scenario tests

### `wmediumd-client-carousel.py`

Run while watching the Network Topology page:

```sh
python3 gen/tests/wmediumd-client-carousel.py --ssid private_ssid --rounds 2
python3 gen/tests/wmediumd-client-carousel.py --ssid iot_ssid --rounds 2
```

The script inventories all mesh AP radios and the selected client cohort,
splits the clients into groups, and uses atomic wmediumd generations to rotate
each group around the five APs. Each move has a blackout phase followed by a
strong-link arrival phase so disconnect/reconnect and steering animations are
visually distinguishable. It checks both the physical BSSID and topology owner
throughout the sequence.

`--rounds 0` runs until Ctrl-C. Timing, strong/outage SNR, socket, topology URL
and output root are configurable; use `--help` for all values. Cleanup restores
the exact RF matrix and attempts to restore the starting client placement,
requiring it to remain stable for `--restore-settle` seconds. A timestamped
directory containing events, observations, logs and a summary is written below
the selected output root.

### `wmediumd-extender-outage.py`

Run:

```sh
python3 gen/tests/wmediumd-extender-outage.py --extender bpiap-003
```

If the target has no client, the test first creates a temporary RF preference
to place one there and then restores that preparation matrix. It attenuates the
client/extender pairs and requires affected clients to move to another AP with
physical/API agreement. Unless `--skip-full-outage` is used, it then attenuates
every pair to the extender, requires loss of `wifi1.3`, and expects controller
liveness aging to remove the extender node.

The exact baseline matrix is restored in all paths. The test then requires the
extender backhaul and controller node to recover, all client ownership to stay
consistent for the stability window, all client traffic to pass, and the
controller service PIDs/restart counts to remain unchanged. Artifacts include
before/after topology, client-consistency snapshots, events and `summary.json`.
`--allow-stale-node` and `--allow-preflight-disagreement` are diagnostic
exceptions, not normal acceptance settings.

## Stability, reconstruction and memory tests

### Deployment-model evidence

Use the paired collectors when comparing bare metal and LXD VM.
Run the runtime collector inside the operating-system boundary that owns hwsim
and the host collector on the physical machine:

```sh
./gen/tests/deployment-model-evidence.sh bare-metal /path/to/evidence 30
./gen/tests/deployment-host-evidence.sh bare-metal /path/to/evidence 30
```

For a VM, the first command runs in the guest and the second runs on the outer
host. In a nested-LXD VM, run the first command with `sudo`; snap-LXD cannot be
invoked by the unprivileged guest user when that user session itself was
created through the outer host's `lxc exec`. The collector handles the source
checkout ownership difference without changing persistent Git configuration.
The runtime collector executes the normal health audit after capturing
topology, model, service, process, LXD, API-latency, wmediumd, memory, storage,
and module evidence. The host collector separates QEMU resource use from guest
measurements. Use the same sample length and idle/traffic phase on
every target. The complete comparison method and result table are in
[`deployment-models.md`](../../doc/easymesh/reference/deployment-models.md).

### `p0-churn-soak.py`

Use a short shakedown before a duration-bound campaign:

```sh
python3 gen/tests/p0-churn-soak.py --max-workloads 2 --duration 900
python3 gen/tests/p0-churn-soak.py --duration 43200
```

The soak alternates client-carousel and extender-outage workloads by default.
After every workload it samples process memory and checks exact topology/model
counts, SSID cohorts, physical/API association agreement, client traffic,
service PIDs and restart counts, journal size, candidate RCPI, wmediumd instance
identity, matrix restoration and netlink-drop counters. It also rejects new
OOM evidence and coredumps.

The 12-hour, duration-bound form is eligible for the PSS-growth acceptance
calculation; short or workload-count-limited runs are shakedowns. Default
limits cover `em_ctrl`, `em_cli`, wmediumd RSS, PSS growth and journal size.
Each campaign writes baselines, per-workload logs, JSONL events, memory samples
and `summary.json` below `/tmp/easymesh-p0-soak` unless overridden.

### `scale-soak-campaign.sh`

Run this as root inside the appliance VM or dedicated bare-metal lab host:

```sh
EASYMESH_SOAK_PROFILE_SECONDS=43200 \
  gen/tests/scale-soak-campaign.sh small medium stress
```

The campaign qualifies 20, 50 and 100 clients sequentially. At each boundary
it stops every managed node, changes the idle hwsim pool to 32, 64 or 128
radios, reconstructs the already provisioned roster, adds only missing client
identities, then performs a clean whole-profile stop/start and health audit.
It never changes a BPI `/nvram` identity. Each profile then runs the normal RF
churn soak with an exact expected-client count.

The default is twelve hours per profile. Results survive reboots below
`/home/easymesh/easymesh-evidence/scale-soak`. To launch it as a managed
background campaign:

```sh
sudo systemd-run --unit=easymesh-scale-soak --collect \
  --property=Type=exec \
  /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/tests/scale-soak-campaign.sh
sudo journalctl -fu easymesh-scale-soak.service
```

The first failed provisioning, health or soak gate stops the sequence and
retains the failing profile's logs. A profile is not accepted merely because
its containers started; its `summary.json` must report `outcome: passed`.

### `p0-cold-reconstruction.sh`

Run a bounded number of complete reconstructions:

```sh
./gen/tests/p0-cold-reconstruction.sh 3
```

This invokes the same guest runtime used by the distributable VM. Each run
stops and reconstructs WLAN participants, reclaims transient hwsim VAPs, and
brings up the controller, extenders, clients and wmediumd in dependency order
while retaining persistent `/nvram` identities. Boardfarm/Docker supplies the
WAN bridge, DHCP and NAT services. The script uses `sudo` for the system-level
runtime and stops at the first failed reconstruction.

Campaign metadata, the accepted runtime evidence and one log per run are stored
under `tmp/test-results/p0-cold-reconstruction/` by default. Override lab user,
group, home or result root only for a differently installed VM.

### `bpibroadband-memory-profile.py`

Run during a stable period or start it before a bring-up to capture phases:

```sh
python3 gen/tests/bpibroadband-memory-profile.py \
  --duration 900 --interval 5 --storage-interval 120
```

This is read-only. It samples every process in `bpibroadband` from
`smaps_rollup`, records PSS/RSS/swap/thread counts, captures host cgroup memory,
controller model and topology counts, and periodically records database/NVRAM
storage. Samples are classified as controller stopped, controller only,
partial extenders, partial clients or steady complete. The current phase
classifier uses the original ten-client baseline, while process and cgroup
measurements cover the complete container regardless of client count.

`samples.jsonl` retains raw samples and `summary.json` reports per-process and
per-phase minima, medians and maxima in a timestamped directory under
`/tmp/bpibroadband-memory` by default.

## Isolated and build-artifact tests

### `steer-by-name-test.sh`

Run:

```sh
./gen/tests/steer-by-name-test.sh
```

This creates a temporary topology fixture plus fake `curl` and `lxc` commands
and exercises `gen/steer.sh --dry-run`. It verifies resolution of labels such
as `sta-03`, `agent-1` and `extender-2`, band selection, already-associated
handling, ambiguous targets, invalid labels and MAC-address compatibility. It
does not contact the live lab.

### `test_client_pool.py`

Run:

```sh
python3 -m pytest -q gen/tests/test_client_pool.py
```

This verifies the `small`, `medium` and `stress` plans produced by
`gen/wlan-client-pool.sh`: cohort counts, required hwsim pool sizes, stable
container/MAC labels, SSID/security intent, and deterministic band assignments.
It plans containers but does not create them.

### `test_soak_harness.py`

Run:

```sh
python3 -m pytest -q gen/tests/test_soak_harness.py
```

This imports `p0-churn-soak.py` with mocked service state and verifies harness
invariants, including tolerating transient cgroup children while rejecting a
changed main PID, restart count or invalid process membership. It does not run
a soak or contact LXD.

### `verify-snmp-subagent-selfheal.sh`

Run against an extracted or staged BPI root filesystem:

```sh
./gen/tests/verify-snmp-subagent-selfheal.sh /path/to/rootfs
```

The test syntax-checks the installed task-health monitor and SNMP launcher,
requires cross-user `pidof snmp_subagent` detection, rejects the old UID-scoped
`ps` lookup, and verifies that an empty PID result is guarded. It validates a
build artifact rather than a running container.

### `verify-webui-static-sync.sh`

Run against an extracted or staged BPI root filesystem:

```sh
./gen/tests/verify-webui-static-sync.sh /path/to/rootfs
```

This checks the installed `em_cli` systemd drop-in. It requires packaged WebUI
assets to replace the persistent `/nvram/static` copy at startup and rejects a
no-clobber copy that would leave an old browser bundle active after deployment.

## WebUI unit tests

The four JavaScript tests load `rdkb-cli/static/script.js` directly with mocked
browser/API objects. Supply the patched source file from the
`unified-wifi-mesh` work tree:

```sh
script=/path/to/unified-wifi-mesh/src/rdkb-cli/static/script.js
node gen/tests/webui-extender-signal-test.js "$script"
node gen/tests/webui-mesh-device-signal-test.js "$script"
node gen/tests/webui-metrics-reporting-test.js "$script"
node gen/tests/webui-topology-layout-test.js "$script"
```

### `webui-extender-signal-test.js`

Verifies topology-edge fresh, stale and unknown signal handling; RCPI `0`;
legacy and future timestamps; band/channel/signal labels; Ethernet exclusion;
and metric-only in-place refresh without a D3 relayout. A true parent/child
structural change must still rebuild the graph.

### `webui-mesh-device-signal-test.js`

Verifies the Mesh Devices list representation of fresh, stale, unknown and
Ethernet backhaul signal, and verifies that the two-second Devices refresh
updates cards and badges without overlapping an in-flight request.

### `webui-metrics-reporting-test.js`

Mocks the metrics APIs and verifies that **Enable All Metrics** sends the
activation request, reloads policy state, refreshes clients, restores the
button state and presents a successful notification.

### `webui-topology-layout-test.js`

Verifies BSS band labels, SSID/client geometry, edge placement, draggable
clients, steering pulse/trail state, signal bars, channel display, exact
backhaul parent rendering, responsive resize, the deterministic landscape
optimizer, position caching, and the rule that a metric-only two-second poll
must not rebuild or move the graph. The API model must remain immutable through
all rendering operations.

## Result interpretation

A command exit status of zero is the acceptance signal. Do not infer success
only from an accepted steering command or from a visually plausible WebUI.
Live tests cross-check the kernel association, controller data, API model and
traffic because those layers converge independently.

Preserve a failed test's timestamped artifact directory before redeploying.
For RF tests, first confirm the recorded `medium_restored` result. For a stopped
AP test, confirm the cleanup restart. Then use `health-audit.sh` and the
topology WebUI to establish the post-test baseline.
