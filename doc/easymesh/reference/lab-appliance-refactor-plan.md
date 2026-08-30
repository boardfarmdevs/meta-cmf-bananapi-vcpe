# EasyMesh lab appliance refactor plan

## Purpose

The lab must present a small appliance interface to an operator while retaining
the detailed engineering tools needed by developers. Normal operation should
not require knowledge of LXD ordering, hwsim PHY cleanup, wmediumd inventory,
NVRAM ownership, EasyMesh database structure, or recovery scripts.

This plan complements the live-lab resilience design. The resilience design
defines the intended/configured/active/EasyMesh state model and stable radio
inventory. This plan defines how operators, Python lifecycle code, systemd,
and the repository should use that model.

The end state is:

> One manifest, one CLI, systemd-owned services, one state model, and no
> operator-visible repair scripts.

## Current conclusion

The accepted lab is an engineering toolkit, not yet an appliance.

The present VM boot service is a shell state machine that stops wmediumd and
every managed container, cleans returned VIFs, starts the controller,
extenders, and clients in order, reapplies metrics policy, and performs a
120-second health hold. It preserves persistent containers and NVRAM, but it
still reconstructs the complete runtime after every VM boot.

That behavior is acceptable as a temporary VM recovery mechanism, but it is
not the target lifecycle model. It also must not be enabled automatically on a
direct bare-metal lab host.

The following capability remains **not accepted**:

> Independent start, stop, and restart of every provisioned node without
> medium regeneration, unrelated-node restart, identity repair, database
> correction, or a manual recovery command.

## Operator contract

Normal operation exposes only:

```text
easymesh-labctl start [NODE|all]
easymesh-labctl stop [NODE|all]
easymesh-labctl restart [NODE|all]
easymesh-labctl status [NODE|all] [--json]
easymesh-labctl doctor [NODE|all] [--json]
```

Provisioning is explicitly separate:

```text
easymesh-labctl deploy [--manifest FILE]
easymesh-labctl add NODE
easymesh-labctl remove NODE
easymesh-labctl reset --destructive --confirm
```

Expert-only diagnostics may expose `inventory`, `reconcile`, and transaction
inspection, but normal lifecycle commands invoke any required reconciliation
internally.

Operators must not directly use these during normal operation:

```text
bpi.sh
wlan-client.sh
wlan-client-pool.sh
wmediumd-up.sh
gen-util.sh
hwsim_reclaim_dirty_phys
lxc start / stop / delete
direct SQL topology repair
```

`status` and `doctor` are read-only. A repair-capable expert command must name
the exact affected node and operation; it must never become a generic shell or
arbitrary wmediumd control proxy.

## Boot policy

The two supported deployment modes intentionally differ:

| Environment | Boot behavior |
| --- | --- |
| Direct bare-metal lab host | Do not start or reconstruct the lab automatically. The operator explicitly runs `easymesh-labctl start all`. |
| Packaged EasyMesh VM | `lxc start INSTANCE` is the explicit appliance start, so the lab starts automatically inside that VM. |

A physical host must not create or import an LXD VM automatically. A guest reboot in
an already selected VM may restore the enabled lab, but it must converge the
existing desired state rather than stop every healthy node and rebuild the
whole runtime.

Installation may place all unit files on either platform. Only the packaged VM
profile enables `easymesh-lab.target` by default. Direct-host installation
leaves it disabled.

## Target architecture

```mermaid
flowchart TB
    OP[Operator] --> CLI[easymesh-labctl]
    MAN[/etc/easymesh-lab/lab.yaml] --> ENG[Python state engine]
    CLI --> ENG

    ENG --> STATE[Unified desired and observed state]
    ENG --> SD[systemd D-Bus]
    ENG --> LXD[LXD API]
    ENG --> INV[Versioned radio inventory]
    ENG --> HEALTH[Role-specific readiness gates]

    SD --> HWSIM[easymesh-hwsim.service]
    SD --> WMD[easymesh-wmediumd.service]
    SD --> CTRL[easymesh-node@bpibroadband.service]
    SD --> EXT[easymesh-extenders.target]
    SD --> CLIENTS[easymesh-clients.target]
    SD --> CONSOLE[wmediumd-console.service]

    INV --> HWSIM
    INV --> WMD
    LXD --> CTRL
    LXD --> EXT
    LXD --> CLIENTS

    WMD --> OBS[wmediumd telemetry]
    CTRL --> EM[EasyMesh controller model]
    EXT --> EM
    CLIENTS --> EM
    OBS --> STATE
    EM --> STATE
    HEALTH --> STATE

    EVENTS[LXD and systemd events] --> QUEUE[Bounded node-scoped reconciler]
    QUEUE --> ENG
```

The Python program owns lifecycle decisions. systemd owns long-running
processes and privileged execution. The CLI is not another daemon supervisor.

## One declarative manifest

The manifest is the sole desired-state input. Runtime discovery validates the
manifest; it never silently replaces it.

Example:

```yaml
schema: 1

lab:
  name: easymesh-small
  profile: small
  wan_bridge: br-wan101
  hwsim_radios: 32
  hwsim_channels: 3
  autostart: false        # direct-host default; VM profile overrides to true

medium:
  implementation: wmediumd
  default_snr_db: 40
  control_socket: /run/meta-cmf-wmediumd/control.sock
  telemetry_socket: /run/meta-cmf-wmediumd/telemetry.sock

nodes:
  - name: bpibroadband
    role: controller-agent
    enabled: true
    image: controller
    phy: virt-wlan0
    radio_identity: 02:00:00:00:00:00

  - name: bpiap
    role: extender
    ordinal: 1
    enabled: true
    image: extender
    phy: virt-wlan1
    radio_identity: 02:00:00:00:01:00

clients:
  - cohort: private
    count: 10
    first_ordinal: 0
    first_phy: 5
    ssid: private_ssid

  - cohort: iot
    count: 10
    first_ordinal: 10
    first_phy: 15
    ssid: iot_ssid
```

The production schema also records image digest, stable container identity,
NVRAM identity location, permanent hwsim radio identity, expected base
interface MAC, role, ordinal, and readiness policy.

The compiled inventory is stored atomically at:

```text
/var/lib/easymesh-lab/inventory.json
```

It contains a schema version, monotonically increasing generation, normalized
content hash, and provenance. Runtime activity is recorded separately under
`/run/easymesh-lab/`; stopping a node does not change the inventory generation.

The generation changes only when a node is added, removed, enabled, disabled,
or reassigned to a different stable PHY identity.

## Stable identity rules

Every provisioned node records and validates:

- permanent hwsim radio MAC or radio identifier;
- expected `virt-wlanN` parent;
- role and ordinal;
- expected base interface MAC;
- container name;
- NVRAM identity owner and path; and
- EasyMesh AL-MAC/RUID identity where applicable.

`phyN`, `wlanN`, and module enumeration order are observations, not identities.
After a reboot, stable `virt-wlanN` names are rebuilt from permanent radio
identity.

Learned VAPs and BSSIDs remain subordinate to the provisioned base radio. They
may appear and disappear without redefining inventory ownership.

## Unified state model

Every node exposes the same independent dimensions:

| Field | Meaning |
| --- | --- |
| `intended` | Present and enabled in the manifest |
| `configured` | Present in the accepted inventory and wmediumd roster |
| `active` | Container and assigned radio are operational |
| `easymesh` | `current`, `stale`, or `absent` in the controller model |
| `traffic` | `pass`, `fail`, or `not-applicable` |
| `healthy` | All gates required for this role currently pass |
| `reason` | Precise first failing gate and supporting observations |

Human output:

```text
NODE             ROLE              CONTAINER  PHY          MEDIUM   EASYMESH  TRAFFIC  HEALTH
bpibroadband     controller-agent  running    virt-wlan0   active   current   pass     healthy
bpiap            extender          running    virt-wlan1   active   current   pass     healthy
bpiap-001        extender          stopped    virt-wlan2   dormant  stale     n/a      stopped
wlan-client-007  private-client    running    virt-wlan12  active   current   pass     healthy
```

Detailed and JSON output includes inventory generation/hash, permanent radio
identity, current VIFs, container state, last frame time, service state,
backhaul/association, last onboarding time, controller owner, metrics age,
last lifecycle operation, and its transaction ID.

Tests and UIs consume the same JSON contract. They do not rediscover their own
versions of container, PHY, medium, and controller state.

## Provisioning versus runtime lifecycle

Provisioning performs operations that change durable state:

1. validate the manifest;
2. import pinned images;
3. create containers and persistent NVRAM;
4. assign stable container and radio identities;
5. create the complete hwsim assignment;
6. publish a new inventory generation;
7. create systemd instances and policy; and
8. retain an auditable deployment record.

Routine start, stop, and restart must never:

- import or rebuild an image;
- recreate a container;
- regenerate NVRAM;
- allocate a different PHY;
- increment the inventory generation;
- rebuild unrelated containers;
- directly edit the controller database; or
- restart wmediumd for an already provisioned radio.

Destructive identity recreation is available only through an explicitly named
and confirmed provisioning command.

## Python implementation

The main state machine moves into one Python package:

```text
gen/
  easymesh-labctl
  easymesh_lab/
    __init__.py
    cli.py
    manifest.py
    inventory.py
    state.py
    transactions.py
    systemd.py
    lxd.py
    hwsim.py
    medium.py
    nodes.py
    easymesh.py
    health.py
    recovery.py
    output.py
  systemd/
  manifests/
  install/
  expert/
  tests/
  legacy/
```

Module boundaries:

- `manifest.py`: schema parsing, defaults, normalization, semantic validation;
- `inventory.py`: stable identity resolution, generation/hash, atomic publish;
- `state.py`: desired/observed comparison and public status schema;
- `transactions.py`: locks, operation journal, step outcomes, rollback markers;
- `systemd.py`: D-Bus unit requests and result observation;
- `lxd.py`: direct LXD API ownership, devices, lifecycle, and events;
- `hwsim.py`: permanent identity mapping and strictly node-scoped VIF cleanup;
- `medium.py`: complete roster validation and typed wmediumd operations;
- `nodes.py`: idempotent start/stop/restart workflows;
- `easymesh.py`: controller APIs and model observations, never SQL repair;
- `health.py`: role-specific readiness gates;
- `recovery.py`: bounded node-scoped retry and reconciliation policy; and
- `output.py`: consistent table, JSON, diagnostics, and exit codes.

The first CLI version may call legacy scripts behind explicit adapters, but
each adapter receives a removal milestone. The final implementation directly
owns LXD operations, manifest validation, hwsim assignment, medium
configuration, readiness, locks, and state reporting.

## systemd ownership

Target units:

```text
easymesh-hwsim.service
easymesh-inventory.service
easymesh-wmediumd.service
easymesh-node@.service
easymesh-controller.target
easymesh-extenders.target
easymesh-clients.target
easymesh-observability.target
easymesh-lab.target
easymesh-reconciler.service        optional bounded event consumer
```

Dependency order:

```text
Boardfarm WAN/DHCP
  -> hwsim pool and stable naming
  -> inventory validation
  -> wmediumd complete roster
  -> controller readiness
  -> enabled extenders
  -> enabled clients
  -> WebUI and Console
  -> health gate
```

Systemd runs privileged actions. A lab-operator policy allows the unprivileged
CLI to start the narrowly scoped lab units through D-Bus. The CLI waits for and
evaluates readiness; it does not manage PID files or supervise daemons itself.

## Transaction semantics

All radio and medium mutations use one host-wide lock. Each transaction records
an operation ID, starting inventory generation, affected node, completed
steps, observations, timeout, and rollback or recovery result.

### `start NODE`

1. Return success immediately if the complete node readiness gate already
   passes.
2. Validate intended state, stable identity, and unchanged inventory
   generation.
3. Confirm the assigned PHY exists and is unowned.
4. Reclaim only stale dynamic VIFs belonging to that PHY.
5. Attach the same PHY and start the existing container.
6. Wait for role-specific services and wireless readiness.
7. Verify controller ownership, metrics, and traffic when applicable.
8. Return a precise result without changing unrelated nodes.

### `stop NODE`

1. Return success if the node is already cleanly stopped.
2. For an administrative AP stop, request graceful deauthentication and allow
   topology notifications to leave the node.
3. Stop the existing container without deleting it.
4. Verify that the assigned PHY returned to the host.
5. Clean only known dynamic VIFs owned by that PHY.
6. Keep the radio configured but dormant in wmediumd.
7. Record inactive/stale/absent state without changing inventory generation.

### `restart NODE`

`restart` is the composed stop/start transaction. It preserves NVRAM, AL-MAC,
RUIDs, client MACs, PHY assignment, image, and inventory generation. Repeating
it cannot produce extra VIFs, processes, database rows, or identities.

### `start all` and `stop all`

`start all` evaluates the dependency graph internally. The operator does not
perform ordered startup. Independent nodes at the same level may start with
bounded concurrency after their dependency gate passes. `stop all` uses the
reverse dependency order.

## wmediumd lifecycle

For the fixed provisioned topology, wmediumd starts once with the complete
roster. A stopped radio remains configured and dormant. Restarting its
container resumes frames from the same permanent identity without medium
regeneration.

Live station add/remove is a later topology-mutation feature. It must not block
restart-safe lifecycle. When added, it uses an atomic generation transaction
with validation, compare-and-swap, commit/abort, and rollback to the last
accepted roster.

Scenario pair/frequency updates remain separate from inventory identity. An RF
scenario cannot add, remove, or reassign a provisioned radio.

## Automatic reconciliation

Reconciliation is internal during ordinary lifecycle. LXD and systemd events
enqueue a node-scoped check; they never trigger a whole-lab restart.

Bounded recovery order:

1. diagnose the intended/configured/active/EasyMesh mismatch;
2. retry the failed local operation;
3. reconcile only the affected node;
4. restart only that node when necessary; and
5. stop and report before entering a loop or recreating identity.

Administrative shutdown and abrupt RF disappearance are different fault
models. Graceful stop sends deauthentication where possible. Abrupt loss must
eventually produce a real hwsim station-side link-loss indication or a bounded
affected-client workaround. It must not toggle every WLAN client.

Controller topology convergence remains protocol-driven. Direct SQL edits are
not recovery. Stable identities, normal liveness aging, duplicate uniqueness
checks, topology notification/query behavior, and live model adapters are the
authority.

## Repository migration

The public layout becomes:

```text
gen/
  easymesh-labctl             only normal operator entry point
  easymesh_lab/               state engine
  systemd/                    managed units and policy
  manifests/                  versioned examples and schema
  install/                    one-time host/kernel/tool installation
  expert/                     destructive and low-level diagnostics
  tests/                      acceptance and experiment scripts
  legacy/                     temporary migration-only scripts
```

Migration classification:

| Current entry point | Destination |
| --- | --- |
| `bpi.sh` | Provisioning behavior moves into `easymesh_lab`; destructive remnants temporarily under `expert/` |
| `wlan-client.sh`, `wlan-client-pool.sh` | Cohort provisioning and node lifecycle move into manifest/state engine |
| `wmediumd-up.sh` | Service configuration and typed medium adapter |
| `gen-util.sh`, broad PHY cleanup | Narrow hwsim library; broad cleanup removed from normal lifecycle |
| `steer.sh` | Expert/test action adapter; not lifecycle management |
| health, steering, churn, outage scripts | `tests/`; consume the unified status JSON |

Legacy scripts are not retained indefinitely behind the CLI. Every phase
removes duplicated discovery and lifecycle logic rather than merely hiding it.

## Phased implementation

### Phase 0: formalize the appliance contract

Deliverables:

- add the not-accepted independent-lifecycle capability to current state;
- freeze the CLI, manifest, status JSON, transaction, and boot-mode contracts;
- capture the current restart counters, VIFs, identities, inventory hash,
  controller rows, and manual steps as baseline evidence;
- classify every existing script as migrate, expert, test, install, or delete.

Gate: documentation, schemas, fixtures, and read-only probes change no runtime
behavior.

### Phase 1: manifest and read-only state engine

Deliverables:

- Python package skeleton and schema validation;
- migrate the accepted topology into one manifest;
- compile deterministic full inventory from explicit LXD metadata and
  permanent hwsim identity, including stopped nodes;
- implement `status --json` and `doctor --json` using adapters for LXD,
  systemd, wmediumd, controller APIs, and traffic observations;
- make existing tests consume the new state API.

Gate: unchanged topology produces the same manifest/inventory hash; stopped
nodes remain intended/configured; invalid or duplicate identities fail clearly.

### Phase 2: fixed-roster node lifecycle

Deliverables:

- host-wide transaction lock and operation journal;
- direct Python ownership of LXD start/stop, hwsim assignment, and node-scoped
  cleanup;
- wmediumd complete provisioned roster with dormant stopped radios;
- role-specific start/stop/restart gates;
- systemd node template and targets.

Implement and accept in this order: one WLAN client, all clients, one
extender, all extenders, controller, then `all`.

Gate: every provisioned node independently cycles without a wmediumd restart,
unrelated container restart, inventory-generation change, identity change,
duplicate record, or manual command.

### Phase 3: boot-mode convergence

Deliverables:

- direct-host installation leaves `easymesh-lab.target` disabled;
- packaged VM enables it and `lxc start INSTANCE` starts the appliance;
- replace VM stop-all/restart-all boot logic with desired-state convergence;
- implement reverse-order shutdown and preserve the last enabled-node set;
- update the operating guide so ordered manual startup is engineering fallback
  only.

Gate: physical-host reboot leaves a direct lab stopped; VM boot reaches the
accepted topology automatically; guest reboot does not restart a healthy node
unnecessarily.

### Phase 4: bounded automatic reconciliation

Deliverables:

- LXD/systemd event consumer and node-scoped queue;
- bounded retry and precise reason reporting;
- graceful AP withdrawal and affected-client-only abrupt-loss recovery;
- protocol-driven controller aging/return and duplicate checks;
- unified Console/status visibility for drift and last operation.

Gate: injected local failures self-heal where safe, never cause whole-lab
restart, and stop with a diagnostic before looping or recreating identity.

### Phase 5: provisioning and topology mutation

Deliverables:

- direct manifest-driven deploy/add/remove/enable/disable/reassign operations;
- atomic inventory generation transaction;
- typed atomic wmediumd roster mutation or bounded atomic daemon replacement;
- explicit destructive identity reset with confirmation;
- remove lifecycle calls into legacy scripts.

Gate: add and remove one client and one extender while unrelated traffic
continues; readers never observe a partial roster; failed mutation preserves
the prior working generation.

### Phase 6: appliance release and legacy removal

Deliverables:

- normal documentation contains only the small CLI workflow;
- engineering fallback procedures move under `expert/`;
- obsolete wrappers and duplicate discovery logic are deleted;
- packaged VM and direct host use the same state engine with different
  autostart policy;
- release evidence covers small, medium, and accepted stress profiles.

Gate: a new Wi-Fi expert can unpack/start the VM, inspect one status model,
cycle any node, run tests, and recover supported failures without using a raw
LXD, hwsim, wmediumd, SQL, or repair command.

## Release acceptance matrix

For every provisioned controller, extender, private client, and IoT client:

- start it from an otherwise running lab;
- stop it from an otherwise running lab;
- restart it from an otherwise running lab;
- repeat each lifecycle operation enough times to detect VIF, process, memory,
  and controller-record leaks.

Also test:

- controller restart while extenders and clients remain running;
- wmediumd restart without restarting containers;
- arbitrary provisioned nodes stopped at lab start;
- starting any missing node later without reconstruction;
- physical direct-host reboot with lab remaining stopped;
- VM boot and guest reboot with automatic convergence;
- randomized bounded node start/stop/restart sequences; and
- abrupt extender loss, normal aging, and same-identity return.

For every ordinary node restart require:

```text
wmediumd restart count                  unchanged
unaffected container restart counts    unchanged
inventory generation and hash          unchanged
node PHY and MAC identities             unchanged
duplicate topology records              zero
unrelated-client traffic disruption     zero or within an explicit bound
affected node recovery                  automatic and bounded
manual commands after requested action  zero
```

Scale profiles also record CPU, PSS/RSS, frame and drop counters, queue health,
VIF count, process count, topology ownership, and transaction duration.

## Bounded review commits

Implementation should remain reviewable in narrow commits:

1. appliance contracts, schemas, and fixtures;
2. Python package skeleton and manifest validation;
3. deterministic inventory compiler;
4. unified read-only status and doctor;
5. transaction journal and locking;
6. client lifecycle;
7. extender lifecycle;
8. controller and all-node lifecycle;
9. systemd units, operator policy, and boot-mode split;
10. event-driven reconciliation and abrupt-loss handling;
11. provisioning and atomic topology mutation;
12. acceptance campaigns, documentation simplification, and legacy removal.

Each commit must include focused unit/fixture tests and the smallest relevant
live acceptance result. A passing broad test does not substitute for proving
the lifecycle invariant changed by that commit.

## Definition of done

The refactor is complete only when:

- one declarative manifest is the sole desired-state authority;
- `easymesh-labctl` is the only documented normal entry point;
- Python directly owns lifecycle and reconciliation decisions;
- systemd owns privileged long-running services;
- the fixed provisioned roster survives independent node lifecycle without
  medium regeneration;
- the direct host and packaged VM obey their distinct boot policies;
- status explains every desired/configured/active/EasyMesh mismatch;
- tests consume the same state API as operators;
- no normal workflow performs broad VIF cleanup, SQL correction, identity
  recreation, or ordered manual startup; and
- the full acceptance matrix passes with retained evidence.
