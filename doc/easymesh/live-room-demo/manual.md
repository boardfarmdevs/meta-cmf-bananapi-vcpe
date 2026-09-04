# Immersive EasyMesh room demonstration manual

## 1. Purpose

This manual operates the complete RDK EasyMesh room demonstration. The demo
turns a deterministic model of a home into live RF conditions, observes the
real EasyMesh response, runs the external reference optimizer, optionally sends
one real steering request, and presents the result in one browser view.

This document covers the precooked timed presentation. For live drag,
destination, disappearance, lease, API, and restoration operation, use the
[interactive room manual](interactive-room-manual.md).

The default profile keeps the accepted lab fully loaded:

- one controller and colocated agent;
- four wireless extenders;
- five tri-band mesh devices and 15 radios;
- ten clients on `private_ssid`;
- ten clients on hidden `iot_ssid`;
- 20 WLAN clients and four wireless-backhaul stations;
- 50 controller BSS records and 24 associated-station records.

One ordinary private 5 GHz client, `wlan-client-007`, is the **hero client**.
It is presented as `Private-Laptop` and bound to world role
`sta_mobile_01`. The other 19 clients remain real, associated, monitored, and
visible, but do not receive an optimizer action in this profile.

The demonstration makes one bounded claim: as Private-Laptop moves through the
modeled home, controller measurements can cause the external reference policy
to recommend or request one same-band steer while traffic and the complete
mesh remain healthy. The run restores the exact pre-run wmediumd RF values.

### Accepted reference run

The implementation was accepted on rev140 on 2026-09-03 PDT using the
20-client LXD appliance `rdkeasymesh-20-hidden-debug`:

| Check | Recommend mode | Act mode |
| --- | ---: | ---: |
| Timed execution | 240.17 s | 240.72 s |
| Optimizer evaluations | 45 | 47 |
| Steering action attempts/successes | 0 / 0 | 1 / 1 |
| Association plus traffic verifications | 0 | 1 in 2.61 s |
| Ordered live events | 1,247 | 1,261 |
| Worker warnings/errors | 0 / 0 | 0 / 0 |
| Exact RF restore | pass | pass |

The act run moved the hero from the BSSID represented by stable room role
Extender-3 to Agent-1 after measured RCPI changed from 80 to 114. The request
used the standards-only `--request-only` path. A post-run audit retained the
`5/15/50/24` controller model, all 20 clients, zero packet loss, and zero
OneWifi/EasyMesh service restarts. Each run produced an 11-file SHA-256 index,
and the recommendation evidence was also loaded and rendered through offline
replay.

## 2. What is real and what is simulated

```text
Golden World (position, walls, deterministic SNR)
                 |
                 v
       wmdcfg timed runner                 sole RF writer
                 |
                 v
    wmediumd control socket -> mac80211_hwsim radios
                                  |
                                  v
        real OneWifi + Unified WiFi Mesh + wpa_supplicant
                                  |
                 +----------------+----------------+
                 |                                 |
                 v                                 v
       controller telemetry               EasyMesh steer API
                 |                                 ^
                 v                                 |
       external optimizer -------------------------+
                 |
                 v
     one event stream -> live viewer -> evidence/replay
```

The room coordinates, wall loss, and applied SNR are simulated. Association,
RCPI reporting, EasyMesh messages, the 802.11v BTM exchange, client behavior,
controller convergence, and IP traffic are produced by the running stack.

The optimizer never reads the Golden World as decision input. The world is
evaluator and presentation truth. Policy decisions use controller-facing
observations only.

In this hwsim profile, associated RCPI comes through the normal controller
model. Candidate RCPI is requested through the EasyMesh Unassociated STA Link
Metrics path, but the hwsim HAL obtains the measurement from wmediumd's
separate read-only metrics socket. The response is explicitly labeled
`simulated: true` and `provider: hwsim-wmediumd-read-only`; the optimizer must
opt in to it through the lab manifest. This preserves the protocol and API
path while making clear that it is not a physical off-channel scan.

## 3. Safety and ownership rules

During a room run:

- `wmdcfg.Runner` is the only process allowed to write wmediumd RF values;
- the optimizer calls `gen/steer.sh --request-only`, so it cannot install its
  usual temporary RF bias;
- the browser and every HTTP endpoint are read-only;
- candidate collection is restricted to the hero client;
- `iot_ssid` remains hidden and observe-only;
- act mode permits at most one request;
- action is allowed only during the manifest's bounded action window;
- the runner restores captured RF state in its `finally` path;
- no EasyMesh, OneWifi, container, or wmediumd restart is a successful-demo
  recovery action.

Do not concurrently run `steer.sh` without `--request-only`, `steer-soak.sh`,
`steer-batch.sh`, another configurator scenario, or a wmediumd Console write.
Those are competing RF writers.

## 4. Files that define the default presentation

| File | Responsibility |
| --- | --- |
| `gen/demo/manifests/private-client-room-walk.json` | mode-independent demo contract, gates, narrative and intervals |
| `gen/demo/bindings/private-client-room-walk.json` | deterministic world role to LXD container binding |
| `gen/wmediumd/configurator/worlds/layouts/home-five-agent.json` | home, AP locations, walls and propagation model |
| `gen/wmediumd/configurator/worlds/mobility/private-client-room-walk.json` | four-minute hero path and stationary peers |
| `gen/wmediumd/configurator/worlds/golden/home-a-private-client-room-walk.world.json` | checked-in, hash-verified compiled world |
| `gen/optimizer/configs/threshold-policy.yaml` | external reference policy thresholds and timers |
| `gen/demo/room-demo` | operator command |

The default world lasts 240 seconds and applies one all-band RF generation
every five seconds. Its narrative is:

| Time | Presentation phase |
| ---: | --- |
| 0–30 s | stable near Extender-1 |
| 30–90 s | walking away from the serving AP |
| 90–140 s | approaching the cell boundary |
| 140–150 s | entering the target room |
| 150–220 s | the only permitted optimizer action window |
| 220–240 s | verification/cooldown; no new action |
| end | exact RF restoration and postflight health audit |

## 5. Prepare the lab and browser path

Run the command **inside the RDK appliance VM**, not on the outer host and not
inside `bpibroadband`.

On the outer LXD host, identify the VM and its management address:

```bash
lxc list
```

Set values appropriate to that host:

```bash
LAB_VM=rdkeasymesh-20-0904
LAB_HOST_IP=192.168.2.140
LAB_VM_IP=10.142.138.250
```

Expose VM port 8891 on any unused outer-host port. This example uses 18891:

```bash
lxc config device add "$LAB_VM" room-demo-viewer proxy \
  nat=true \
  listen="tcp:${LAB_HOST_IP}:18891" \
  connect="tcp:${LAB_VM_IP}:8891"
```

If the device already exists, inspect it instead of adding it again:

```bash
lxc config device show "$LAB_VM" | sed -n '/room-demo-viewer:/,/^[^ ]/p'
```

Open a shell in the VM and enter the repository:

```bash
lxc exec "$LAB_VM" -- bash
cd /home/easymesh/git/meta-cmf-bananapi-vcpe
```

Verify the usual WebUI and wmediumd Console independently before the demo:

```bash
curl -fsS http://127.0.0.1:8888/api/v1/topology >/dev/null
curl -fsS http://127.0.0.1:8890/api/v1/status >/dev/null
gen/tests/health-audit.sh
```

Do not proceed if the audit reports missing agents, clients, BSS records,
backhaul associations, or traffic.

## 6. Compile and endpoint preflight

Run:

```bash
gen/demo/room-demo check
```

This is read-only. It verifies the manifest paths, Golden World hash, live
hwsim inventory, fixed role bindings, compiled event plan, and wmediumd control
capabilities. A ready profile reports 25 roles, 25 wmediumd stations, a
240000 ms duration, 48 scheduled world samples (39 effective RF-update
generations in the default path), and the hero radio identity.

`check` does not validate the hero's current SSID, band, RCPI, or traffic.
Those live gates run immediately before a presentation begins. A run stops
before changing RF if any of them fail.

## 7. Choose an operating mode

### 7.1 Stimulus mode

```bash
gen/demo/room-demo run \
  --mode stimulus \
  --listen 0.0.0.0:8891 \
  --linger-seconds 120
```

Stimulus mode applies and displays the world, live associations, RCPI, traffic,
and health. It does not instantiate the optimizer and cannot steer. Use it to
explain the RF model or validate presentation plumbing.

### 7.2 Recommend mode

```bash
gen/demo/room-demo run \
  --mode recommend \
  --listen 0.0.0.0:8891 \
  --linger-seconds 120
```

Recommend is the safe default. It collects live controller candidate metrics,
runs the threshold policy, and displays the same decision that act mode would
use. A `steer` result is retained as `recommended`; no request is sent.

### 7.3 Act mode

```bash
gen/demo/room-demo run \
  --mode act \
  --yes-act \
  --listen 0.0.0.0:8891 \
  --linger-seconds 120
```

Both `--mode act` and `--yes-act` are required. The conductor will submit at
most one request, and only if the policy produces a steer during 150–220
seconds. The command fails its acceptance result unless exactly one action is
accepted and verified.

Open the browser as soon as the terminal prints the viewer address:

```text
http://LAB_HOST_IP:18891/viewer/?mode=live
```

The process retains the terminal result and viewer for `--linger-seconds`
after the timed run. A second room-demo process is rejected by the host-wide
lock.

## 8. Read the presentation

### 8.1 Room objects

- red tower: gateway/colocated agent;
- blue tower: extender;
- blue client stem: `private_ssid`;
- green client stem: hidden `iot_ssid`;
- gold ring: selected hero client;
- purple/gray client head: mobile/static world role, colored by simulated link
  strength where applicable;
- translucent walls: fixed 5 dB obstructions used by the pseudo-world model;
- purple floor trail: path already traveled.

### 8.2 Three different link truths

- dashed red/amber/green: **scenario-best** AP for the selected display band;
- solid cyan: **actual controller-observed association**;
- dashed gold: optimizer's current measured target.

The lines are intentionally independent. A dashed green scenario-best line is
not proof that the client has associated there. During a useful crossover the
cyan line can remain on the old AP while the gold line identifies a better
candidate. It moves only after the real client and controller converge.

The room's `Extender-1` through `Extender-4` names are stable manifest/container
roles. RDK's controller may assign its displayed `Extender-N` ordinal in a
different discovery order. The conductor resolves both serving and candidate
links by their live BSSID ownership, so geometry and lines use the stable room
role. When the controller label differs, the Hero card shows it in
parentheses rather than silently treating the ordinal as an identity.

### 8.3 Left-side cards

`Scenario` states the current audience narrative marker.

`Whole lab` reports mesh-device, client, private/IoT cohort, controller-model,
and health counts. A healthy full model is `5/15/50/24`.

`Hero client` reports the real serving device and BSSID, band, SSID, associated
RCPI/RSSI, and the latest data-plane ping result.

`External optimizer` reports mode, state, decision reason, current metric,
best target, target metric, hold time, action-window state, and measured
candidates. After a request it separately retains the last-action verification
badge while continuing to show current policy state. `Action used` confirms
that the manifest's one-action budget is exhausted. Important reasons include:

- `current_link_acceptable`;
- `fresh_candidate_metric_missing`;
- `candidate_gain_too_small`;
- `condition_hold_not_met`;
- `threshold_margin_hold_satisfied`;
- `recommendation_unchanged`;
- `target_association_observed`;
- `post_steer_cooldown`.

`Recent events` provides a short audience-readable ribbon for movement phases,
policy changes, action, verification, health, and RF restoration.

### 8.4 Controls

In live mode, world selection, file input, play, speed, and scrub are disabled
because the runner owns time. Camera orbit, shift-pan, wheel zoom, band display,
labels, trails, scenario links, and backhaul controls remain available.

Changing the display band changes only visualization of Golden World SNR. It
does not change client or AP configuration.

The **Interactive room** card is **LIVE RF** when the writable room service is
running and **PREVIEW ONLY** when viewing a static world. In live mode, a drag
previews locally until pointer-up; pointer-up applies one atomic wmediumd
transaction. Association still changes only through station/EasyMesh behavior.

To place a client directly:

1. select **Interact**;
2. point at a client head and drag it across the room floor;
3. read the floating spatial panel while dragging; and
4. use **Reset role** or **Reset all** to return to scenario truth.

The panel follows the selected client but remains within the viewport. It
shows room coordinates, distance moved, current and strongest APs, distance,
walls crossed, wall loss, predicted SNR, current measured RCPI when available,
metric age, and the three strongest predicted candidates. Walls crossed by
the associated or strongest path are highlighted amber. The purple line is
the preview's strongest path; cyan remains the controller-observed association.

For visible movement at a defined speed:

1. choose `0.6`, `1.4`, or `3.0 m/s` in **Destination speed**;
2. right-click the client and select **Move to destination…**;
3. click the destination on the floor; and
4. observe the dashed route, destination ring, remaining distance, estimated
   time, wall crossings, and changing candidate ranking.

The **Move to…** button performs the same operation for the selected client.
Press Escape to cancel destination selection or an in-progress preview move.

Right-click and choose **Disappear**, or use the card button, to make a role
RF-absent by applying the minimum SNR on all affected links. **Reappear**
recomputes its links at the retained position and allows normal recovery.
Switch back to
**Camera** to orbit or shift-pan without moving a client.

Predicted geometry, applied/read-back SNR and measured controller RCPI remain
separate. A browser preview is never evidence that RF or association changed;
the committed event and subsequent network observation are the evidence.

### 8.5 Companion Network Topology signal meter

The RDK Network Topology view places a ten-segment vertical signal meter beside
every STA and IoT icon. The meter spans the full icon height and is intentionally
separate from the client label:

- more illuminated segments mean a stronger current associated-link RSSI;
- the active color follows the existing quality scale: green for strong, blue
  for good, amber for fair, and red for weak;
- gray segments are the unused part of the scale;
- zero illuminated segments means that fresh signal telemetry is unavailable;
- the exact RSSI and RCPI remain in the client hover details.

The meter is put on the horizontal side of the client opposite the serving AP.
If the squiggly RF line approaches from the left, the meter appears on the
right; if the line approaches from the right, the meter appears on the left.
Dragging a client recalculates the side immediately. This prevents the RF line
from being drawn through the meter and avoids implying that the meter is a
second link.

The ten displayed levels cover RSSI in approximately 5 dB increments from
below -85 dBm through -45 dBm and above. The two-second metrics poll changes
only the meter's fill and color; it does not rebuild, resize, or reposition the
topology.

## 9. Understand one optimizer cycle

Every policy cycle performs these steps:

1. Read `/topology`, `/clients`, `/devices`, and `/bsses`.
2. Confirm that the hero is still an eligible private client.
3. If its associated RCPI is weak enough, send bounded EasyMesh Unassociated
   STA Link Metrics queries for same-band candidate radios.
4. Reject missing, stale, malformed, mismatched, or simulated-without-opt-in
   results.
5. Apply health, freshness, dwell, threshold, target-gain, hold, action-window,
   maximum-action, cooldown, and backoff gates.
6. In recommend mode, expose the target without changing the network.
7. In act mode, call `gen/steer.sh --request-only STA_MAC TARGET_BSSID`.
8. Verify the target association through a fresh controller observation.
9. Verify hero traffic to `10.0.0.1`.
10. Publish the observation, decision, action, and verification to the same
    ordered event stream used by the viewer and evidence.

Candidate collection can take tens of seconds because the current RDK HTTP and
libemcli command path is serialized. That delay is visible; it is why the
presentation uses four minutes rather than the 60-second preview world.

## 10. Inspect the read-only API

From the VM while a run or replay server is active:

```bash
curl -s http://127.0.0.1:8891/healthz | python3 -m json.tool
curl -s http://127.0.0.1:8891/api/demo/current | python3 -m json.tool
curl -s http://127.0.0.1:8891/api/demo/world | python3 -m json.tool
curl -s http://127.0.0.1:8891/api/demo/events.json | python3 -m json.tool
curl -N http://127.0.0.1:8891/api/demo/events
```

The SSE stream can resume after event 100:

```bash
curl -N 'http://127.0.0.1:8891/api/demo/events?after=100'
```

The common event envelope includes `run_id`, global `sequence`, wall-clock
`recorded_at`, monotonic `run_elapsed_ms`, `scenario_time_ms`, compatibility
`world_time_ms`, `producer`, `kind`, `payload`, and event-chain hashes.
Runner-local sequence numbers are retained as `payload.producer_sequence`.
Scripted/replay servers reject writes. The interactive service exposes only
its bounded control routes, protected by a run-scoped operator capability,
renewable lease, idempotent command ID and `ETag`/`If-Match` world revision.
All accepted mutations are serialized by one `RoomEngine`.

## 11. Evidence and offline replay

Every attempt receives a unique directory under:

```text
/tmp/easymesh-room-demo-runs/RUN_ID/
```

Find the latest result:

```bash
RUN_DIR=$(find /tmp/easymesh-room-demo-runs -mindepth 1 -maxdepth 1 \
  -type d -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
cat "$RUN_DIR/demo-summary.json" | python3 -m json.tool
cat "$RUN_DIR/evidence-index.json" | python3 -m json.tool
```

The bundle includes immutable world, manifest, binding and inventory inputs;
the compiled event plan; applied/read-back medium generations; pre/post health;
the complete multi-producer event stream; runner and demo summaries; and a
SHA-256/size index.

Replay does not contact wmediumd, LXD, the controller, or any client:

```bash
gen/demo/room-demo replay "$RUN_DIR" --listen 0.0.0.0:8891
```

Open:

```text
http://LAB_HOST_IP:18891/viewer/?mode=replay
```

Replay restores play, pause, 0.5/1/2/4x speed, and scrub. Scrubbing backwards
reconstructs viewer state from the ordered recorded events. Press Ctrl-C in the
replay terminal to stop its read-only server.

## 12. Completion and restoration checks

A successful recommend run requires:

- runner outcome `passed`;
- exact RF readback restoration `true`;
- no worker errors;
- healthy postflight model and 20 clients;
- no action attempt.

A successful act run additionally requires:

- exactly one action attempt;
- controller command accepted;
- exactly one successful association-and-traffic verification.

Check the final event sequence:

```bash
tail -8 "$RUN_DIR/live-events.jsonl" | python3 -m json.tool --json-lines
```

The end should include RF restoration, runner postflight,
`scenario.completed`, and `run.completed`.

Ctrl-C requests the runner's handled interruption and restoration path. Never
use `kill -9` as a test procedure: `SIGKILL` cannot run userspace cleanup.

## 13. Failure handling

If the preflight fails, no RF generation has been applied. Correct the named
identity, SSID, band, metric, traffic, topology, or wmediumd condition.

If a worker fails during the run, the scenario still proceeds to its bounded
restoration path and retains evidence. The combined result is failed even when
the medium runner itself completed.

If an action is not produced in act mode, inspect:

```bash
jq -c 'select(.kind=="optimizer.evaluation") |
  [.world_time_ms,.payload.decision.reason,.payload.decision.current_rcpi,
   .payload.decision.target_rcpi,.payload.action_window_open]' \
  "$RUN_DIR/live-events.jsonl"
```

Common explanations are an acceptable serving link, stale or missing metrics,
insufficient target gain, incomplete hold time, or an action outside the
window. Do not lower gates during a presentation without creating a reviewed,
versioned manifest/policy pair.

If the request is accepted but verification fails, preserve the bundle and
inspect the client BTM logs, target scan result, controller ownership, and
traffic. The conductor does not force a roam and does not restart services to
turn a rejection into a pass.

After any failed restoration, stop further RF tests and use the wmediumd
Console/readback and accepted lab recovery guide. Do not start another room run
on an unknown RF baseline.

## 14. Customization contract

Use `--manifest`, `--world`, or `--bindings` only for reviewed experiments:

```bash
gen/demo/room-demo check --manifest gen/demo/manifests/private-client-room-walk.json
```

A compatible replacement must retain the world schema/hash, all 25 role
bindings, expected lab counts, one explicit hero, a flat optimizer policy,
bounded intervals, and exact restore support. A different hero must actually
match the manifest's SSID and band at preflight.

Do not use Golden World expected targets as optimizer inputs. Do not relabel a
hidden IoT client as private merely to bypass candidate-resolution behavior.

## 15. Stop and remove presentation access

The server exits after the linger period. To stop a replay, press Ctrl-C. The
proxy is inert when nothing listens on VM port 8891. Remove it when no longer
needed:

```bash
lxc config device remove "$LAB_VM" room-demo-viewer
```

The room-demo does not stop the EasyMesh lab. Leave the lab running for other
tests or use the normal appliance lifecycle procedure separately.
