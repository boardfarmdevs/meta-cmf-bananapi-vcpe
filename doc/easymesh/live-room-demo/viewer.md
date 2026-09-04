# Live room viewer: stimulus-only compatibility procedure

## Purpose and scope

This is the retained stimulus-only procedure from the first viewer milestone.
For controller telemetry, optimizer decisions, bounded steering, evidence and
replay, use the [complete immersive-demo manual](manual.md).

The implemented path is:

```text
Golden World JSON
       |
       v
live hwsim inventory + fixed role bindings
       |
       v
wmdcfg compiler -> authoritative monotonic runner clock
       |                         |
       | atomic SNR generations | typed REST/SSE events
       v                         v
wmediumd control socket      live 3D viewer
       |
       v
hwsim radios -> RDK EasyMesh lab response
```

This milestone proves synchronized stimulus and presentation. It does **not**
run the optimizer, issue BTM requests, show the actual associated AP, or expose
browser controls that change RF. A line in the room is the strongest
**simulated** link for the selected band; it is not claimed to be the client's
current EasyMesh association. Use the EasyMesh WebUI independently for the
observed network topology.

## What is implemented

- live discovery and validation of the complete 25-radio RDK profile;
- the checked-in five-agent, 20-station `home-a-slow-walk-ten` Golden World;
- all-band, frequency-qualified fronthaul SNR changes;
- the existing `wmdcfg.Runner` as the only intentional RF writer;
- an authoritative monotonic scenario clock with 250 ms live ticks;
- typed, ordered events after each generation is applied and read back;
- read-only REST and Server-Sent Events (SSE) endpoints;
- a `?mode=live` viewer mode with play, speed, and scrub disabled;
- exact captured RF restoration on success, failure, or handled interruption;
- preflight and postflight validation of 5 devices, 15 radios, 50 BSS records,
  24 associations, and 20 active WLAN clients;
- a self-contained evidence directory for each run.

Do not run `steer.sh`, another scenario, or a wmediumd Console write operation
while this milestone is active. Those are separate RF writers and are outside
this acceptance test.

## Before the run

The instructions assume an installed RDK appliance VM with the small profile
already healthy. From the outer LXD host, identify its name and address:

```bash
lxc list
```

Set explicit convenience variables. Substitute values for your installation:

```bash
LAB_VM=rdkeasymesh-20-0904
LAB_HOST_IP=192.168.2.150
LAB_VM_IP=10.212.227.250
```

Expose the viewer on outer-host port 18891. This is a one-time VM device
configuration; skip it if the device already exists:

```bash
lxc config device add "$LAB_VM" room-demo-viewer proxy \
  nat=true \
  listen="tcp:${LAB_HOST_IP}:18891" \
  connect="tcp:${LAB_VM_IP}:8891"
```

The browser URL is then:

```text
http://LAB_HOST_IP:18891/viewer/?mode=live
```

For example, the validated rev150 URL is:

```text
http://192.168.2.150:18891/viewer/?mode=live
```

## Validate without changing RF

Open a shell in the appliance VM:

```bash
lxc exec "$LAB_VM" -- bash
cd /home/easymesh/git/meta-cmf-bananapi-vcpe
```

Run the preflight compiler check:

```bash
gen/demo/room-demo check
```

The command discovers the current LXD/hwsim inventory, verifies the world and
bindings, compiles all 30 timed generations, and queries the wmediumd control
socket. It does not apply a generation. A ready 20-client lab reports:

```text
status:            ready
roles:             25
duration_ms:       60000
plan_generations:  30
wmediumd stations: 25
```

Do not start the live run if this check fails. Correct the lab health or radio
inventory first.

## Run the visible milestone

In the VM shell, run:

```bash
gen/demo/room-demo run --listen 0.0.0.0:8891 --linger-seconds 30
```

Open or reload the browser URL as soon as the command prints the viewer
address. During the run, verify:

1. the badge progresses through `LIVE · READY` and `LIVE · RUNNING`;
2. room time advances from the runner rather than from browser Play;
3. mobile stations move and leave trails;
4. strongest simulated links and their colors change with the world;
5. camera orbit, pan, zoom, band, trail, and label controls still work;
6. Play, speed, scrub, world selection, and local-file input are disabled;
7. the final badge becomes `LIVE · PASSED` after RF restoration and postflight.

The default scenario runs for 60 seconds. The server then remains available
for the requested linger interval and exits. A successful terminal run ends
with the evidence directory path and exit status zero.

Pressing Ctrl-C during execution requests a handled stop. The runner enters its
restoration path before returning a failure. Do not kill the process with
`SIGKILL`, because no userspace program can execute a cleanup handler after
that signal.

## Inspect the live API

These endpoints are intentionally read-only:

```bash
curl -s http://127.0.0.1:8891/healthz
curl -s http://127.0.0.1:8891/api/demo/current | python3 -m json.tool
curl -s http://127.0.0.1:8891/api/demo/world | python3 -m json.tool
curl -N http://127.0.0.1:8891/api/demo/events
```

`/api/demo/current` is the refresh/reconnect snapshot. `/api/demo/events` is an
ordered SSE stream. A client can resume after event 40 with either an SSE
`Last-Event-ID: 40` header or:

```bash
curl -N 'http://127.0.0.1:8891/api/demo/events?after=40'
```

Every event has this common envelope:

```json
{
  "schema": "easymesh.room-demo.event.v1",
  "run_id": "20260904T035700Z-home-five-agent--slow-walk-ten",
  "sequence": 41,
  "recorded_at": "2026-09-04T03:57:08.849636+00:00",
  "world_time_ms": 8386,
  "kind": "scenario.clock",
  "payload": {}
}
```

The stream includes preflight, start, clock, mark, applied generation,
restoration, postflight, and completion events. HTTP `POST` is rejected with
status 405; the browser is not an RF control surface.

## Verify the result and evidence

The command prints a directory under:

```text
/tmp/easymesh-room-demo-runs/RUN_ID/
```

Inspect its summary:

```bash
RUN_DIR=$(find /tmp/easymesh-room-demo-runs -mindepth 1 -maxdepth 1 \
  -type d -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
cat "$RUN_DIR/summary.json"
tail -3 "$RUN_DIR/live-events.jsonl"
```

A pass requires all of the following:

```text
outcome:  passed
restored: true
error:    null
```

The final events must show `rf.restore.completed` with `verified: true`, a
successful `runner.postflight`, and `scenario.completed` with `outcome:
passed`.

The evidence directory contains:

| File | Contents |
| --- | --- |
| `world.json` | exact Golden World used by the viewer |
| `world.wmd` | all-band scenario-language projection |
| `bindings.json` | role-to-container map |
| `inventory.json` | frozen live radio inventory |
| `event-plan.json` | bound atomic execution plan and input hashes |
| `medium-events.jsonl` | applied generations, readback observations, restore |
| `health-events.jsonl` | complete preflight and postflight state |
| `live-events.jsonl` | exact typed events sent to the viewer |
| `summary.json` | outcome, elapsed time, backend, and restoration result |

The files are diagnostic evidence for this milestone; they are not yet the
final hash-bound replay bundle proposed for the complete optimizer demo.

## Use a different Golden World

Any compatible checked-in world with the same 5-agent/20-station role set can
be selected explicitly:

```bash
gen/demo/room-demo check \
  --world gen/wmediumd/configurator/worlds/golden/home-a-border-hover.world.json

gen/demo/room-demo run \
  --world gen/wmediumd/configurator/worlds/golden/home-a-border-hover.world.json \
  --listen 0.0.0.0:8891
```

`check` is required first. A world whose roles cannot be covered by the chosen
binding file fails before RF is changed.

## Remove the outer-host proxy

The proxy is harmless while no server listens inside the VM. To remove it:

```bash
lxc config device remove "$LAB_VM" room-demo-viewer
```

## Validated result

The first live acceptance was performed on the RDK 20-client LXD appliance on
rev150. The run compiled 25 roles into 30 frequency-qualified generations and
completed in 60.310 seconds. Preflight and postflight both reported:

```text
20/20 active clients
6/6 complete topology nodes
5 devices / 15 radios / 50 BSS / 24 associations
```

The run passed, exact RF restoration readback was true, the REST state and SSE
clock were reachable through `192.168.2.150:18891`, and no EasyMesh process or
container restart was used.
