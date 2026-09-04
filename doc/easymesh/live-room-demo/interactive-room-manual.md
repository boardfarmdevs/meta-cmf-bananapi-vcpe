# Interactive EasyMesh room manual

## Purpose and present boundary

The interactive room connects the 3D home directly to the live RDK lab. A
client dragged in the browser is no longer a visual-only object: the room
server calculates distance and wall loss, writes all affected links through
the wmediumd control plane, verifies the atomic generation, and then waits for
the normal station, agent, controller, and optimizer paths to react.

The current safe boundary is deliberately narrow:

- every one of the 20 bound WLAN clients can be moved, hidden, or restored;
- gateway and extender positions remain fixed;
- one browser holds the control lease while any number of browsers observe;
- all mutations pass through one serialized `RoomEngine`, and retries with the
  same command ID cannot apply RF twice;
- client motion changes five AP links on three bands in both directions, or 30
  frequency-qualified values in one atomic generation;
- session start captures the full baseline and applies the 20-client room as
  one 600-link atomic generation before accepting browser control;
- `recommend` is the default optimizer authority;
- stopping the process restores the exact pre-session value and override bit
  for every touched wmediumd link.
- a checksummed recovery record is updated before every generation so an
  interrupted process can be restored without guessing.

The room position is simulated truth. Association, RCPI, candidate metrics,
optimizer decisions, BTM acceptance, topology, and traffic remain observed
truth. Moving an icon never directly moves it to a different AP. The room and
the unchanged EasyMesh Network Topology view consume the same live controller
graph: solid client links are current BSS ownership and solid dark-blue AP
links are current wireless-backhaul parentage. Modeled AP-to-AP reachability is
not presented as an actual live mesh edge.

Controller display ordinals can follow discovery order. Room coordinates are
bound to stable container/radio identities, then joined to controller nodes by
BSSID ownership. The room displays the controller's current `Agent-1` and
`Extender-N` names on those coordinates, so a star, branch, or chain conveys
the same actual parent/child topology in both views.

Predicted geometry SNR, applied/read-back wmediumd SNR, associated-link RCPI,
and candidate RCPI are separate values with separate directions, timestamps
and ages. A fresh controller value becomes the primary network observation;
it never replaces or relabels the room prediction.

## Start the interactive room

Run inside the RDK appliance VM:

```bash
cd /home/easymesh/git/meta-cmf-bananapi-vcpe
gen/tests/health-audit.sh
gen/demo/room-demo check
gen/demo/room-demo interactive \
  --mode recommend \
  --listen 0.0.0.0:8891
```

On the outer LXD host, expose VM port 8891 once. Substitute the VM name,
outer-host address, and VM address shown by `lxc list`:

```bash
lxc config device add rdkeasymesh-20-interactive room-demo-viewer proxy \
  nat=true \
  listen=tcp:192.168.2.140:18891 \
  connect=tcp:10.142.138.250:8891
```

Open:

```text
http://192.168.2.140:18891/viewer/?mode=interactive
```

The printed first URL is an observer URL. It can see every accepted position,
measurement and optimizer event but cannot mutate RF. The process also prints
an operator URL whose `#operator=...` fragment contains the run-scoped write
capability. That fragment is consumed locally by the browser and removed from
the address bar; it is never sent as an HTTP request target or referrer.

To construct an outer-host operator URL, read the capability inside the VM:

```bash
TOKEN=$(cat /run/easymesh-room-demo/operator.token)
printf 'http://192.168.2.140:18891/viewer/?mode=interactive#operator=%s\n' "$TOKEN"
```

Opening the observer URL and selecting **Interact** prompts for the same
capability. The purple badge changes to green **LIVE RF** when the writable API
is present; possession of the API URL alone does not grant write authority. A
static viewer remains labeled **PREVIEW ONLY**.

## Move a client directly

1. Select **Interact**. The browser acquires a 30-second renewable lease.
2. Drag a client across the floor.
3. Watch the spatial panel for coordinates, distance, walls, wall loss,
   predicted SNR, current AP, strongest AP, and measured RCPI.
4. Release the pointer to submit the one authoritative final position.
5. Watch the event list for `RF position applied`, then watch measured RCPI,
   optimizer state, and the cyan observed-association line.

Pointer motion is a smooth browser-local ghost preview at display rate and
does not write RF. The translucent purple ghost and purple predicted path move
with the pointer; the solid client and cyan observed-association line remain at
the last authoritative position. Pointer-up sends one revision-checked
position command. Only after successful apply/readback does the solid client
move and the ghost disappear. The server quantizes the point to the 5 cm room
grid, applies only changed RF keys in one generation, and reads them back
before advancing its room revision. If the position changes geometrically but
none of the integer SNR values changes, it records an RF no-op and does not
advance the medium generation.

Client bodies keep a stable cohort identity: blue is `private_ssid` and green
is hidden `iot_ssid`. Signal quality is shown independently by the ten-segment
red/amber/green vertical gauge spanning the client icon. The gauge uses fresh
controller RSSI when available and otherwise the modeled serving-link SNR. It
is placed on the side opposite the serving RF line so the two cues do not
obscure one another.

## Walk to a destination

1. Choose `0.6`, `1.4`, or `3.0 m/s` in **Destination speed**.
2. Right-click a client and choose **Move to destination…**.
3. Click the destination on the room floor.

The purple path and marker show the route. The server owns the movement after
the click, interpolates constant-speed positions, and applies bounded RF
generations independently of browser rendering. The browser follows accepted server events; throttling,
closing, or reloading that browser therefore cannot distort the route. Use
**Pause walk**, **Resume walk**, or **Cancel walk** at any point. Cancelling
freezes the client at its last applied position.

The walk does not issue a steering command. A later optimizer recommendation
or BTM request is a separate, visible closed-loop outcome. Releasing or losing
the control lease cancels the walk safely and also freezes the last accepted
position.

## Disappear and reappear

Right-click a client and select **Disappear**, or use the button in the
interactive card. The server retains the container and stable identity but
sets all 30 affected links to the world's minimum SNR (`-20 dB`) atomically.
This models complete RF isolation rather than a container failure.

The role can be repositioned while absent. Select **Reappear** to recompute
all links at that location and let normal scanning, association, telemetry,
and controller ownership recover.

## Reset and multi-browser behavior

The current transitional controls use **Reset role** for that client's
session-start position/presence and **Reset all** for every changed client.
They use ordinary revisioned RF transactions and never recreate radios,
containers or identities. The accepted interface will separate **Undo**,
**Clear overrides**, and **Stop and restore**, because those operations have
different meanings in hybrid mode.

Only one browser can enter Interact mode. A second browser receives a clear
lease-owner conflict and remains an observer. The lease renews while the
controller page is open. Closing it or losing connectivity releases or
expires the lease and freezes the last accepted room state; it does not
silently undo a presentation.

## Record and replay an improvised room walk

1. Select **Start recording** and give the session a short name.
2. Drag clients, run destination walks, or use disappear/reappear normally.
3. Select **Stop recording**.
4. Select **Download world**.

Recording stores only accepted server state, never unacknowledged browser
preview positions. The downloaded file is a compiled
`wmdcfg.world-plan.v1`: it contains all bound clients, their time-based paths,
presence intervals, and the calculated links for each 200 ms generation. It
can be opened directly in the static viewer or supplied to the configurator as
a deterministic scenario. The source `wmdcfg.mobility.v1` and compiled world
are also retained in the run evidence as `recorded-mobility.json` and
`recorded-world.json`.

Stopping the interactive process while recording safely finalizes the partial
recording before restoring the original RF matrix.

## Automatic closed-loop steering

The default command runs the external optimizer in recommendation mode. It
will explain which AP is better, but it will not change the association. To
make a committed room movement automatically drive normal EasyMesh steering,
start the room in explicitly authorized act mode:

```bash
gen/demo/room-demo interactive \
  --mode act \
  --yes-act \
  --max-actions 100 \
  --listen 0.0.0.0:8891
```

Interactive act mode is not constrained by the prerecorded scenario's
150--220 second action window. It continuously checks the complete live client
roster, including before any manual movement. The default circuit breaker is
100 automatic BTM requests per run and can be changed with `--max-actions`.

Every client remains within its existing SSID and band; private and hidden-IoT
candidate inventories never mix. For each client, the optimizer measures all
eligible same-network, same-band APs. A client becomes eligible when another
AP is strictly stronger (at least one RCPI unit in this interactive
reconciliation mode) for the configured five-second hold. If several clients
are eligible together, the optimizer moves the client with the largest RCPI
gain first. Only one BTM transaction runs at a time. The next complete fleet
measurement then determines the next action. Exact ties do not roam, avoiding
gratuitous ping-pong.

At initial startup and after every committed room movement, the room performs
this closed loop:

1. atomically apply and read back the new directional wmediumd links;
2. reset the optimizer hold state for the new environment epoch;
3. wait until movement stops and RF has been stable for at least two seconds;
4. require serving-link telemetry newer than the RF application (for the
   complete roster on startup, or the moved client after an edit);
5. collect same-SSID, same-band candidate measurements for all 20 clients
   without allowing the room to change during that transaction;
6. apply the gain and five-second hold policy to every client;
7. select at most one client, preferring the largest measured RCPI gain;
8. enter one RoomEngine-owned steering transaction. The already-selected
   target is temporarily made unambiguous to hwsim on the selected band, in
   both directions: target `60 dB` SNR, source `20 dB`, and other APs
   `-20 dB`;
9. discard stale non-serving scan-cache records, actively refresh the serving
   BSSID that wpa_supplicant must retain, and use a directed scan to resolve
   the nominated BSSID and SSID, including the hidden `iot_ssid`,
   then send a graceful mandated BTM through `gen/steer.sh --request-only`;
   if the client declines it, retry once with Disassociation Imminent while
   retaining the same measured target, and keep the serialized assist active
   until the physical target association succeeds or the bounded ten-second
   verification expires;
10. atomically restore and read back the exact authoritative room RF matrix,
    start a new measurement epoch, and reject telemetry sampled while the
    steering assist was active; and
11. verify the physical BSSID, controller ownership and traffic before
    checking the whole fleet again.

The temporary RF assist is an explicit hwsim actuation aid, not an optimizer
input and not an independent candidate measurement. The optimizer chooses the
target first, solely from the controller's current and candidate telemetry.
Only RoomEngine may then apply the temporary values; browser movement and
other medium mutations are serialized behind it. The request-only steering
helper cannot install a competing RF bias and cannot directly force a roam.
The client still changes AP through the controller, EasyMesh Client Steering
Request, 802.11v BTM, supplicant, authentication and association path.

This assist is necessary because multiple hwsim VAP scan entries can otherwise
present indistinguishable client-side signal values even when controller
candidate RCPI correctly identifies a unique best AP. Every assist is visible
as `rf.steering_assist.started` and `rf.steering_assist.completed` evidence.
The latter must report `room_matrix_restored=true`. The continuous path first
avoids the BTM Disassociation Imminent flag so a cooperative client can move
without being kicked off its serving BSS. If it declines, the same transaction
makes one disassociation-imminent retry; the verifier still requires the exact
nominated BSSID and does not count a landing on a different AP as success. A
later fleet cycle retries any unresolved client from its new live state.

Refreshing the serving BSSID is important in repeated demonstrations. The
associated BSS cannot be removed by `bss_flush`; without the directed refresh,
wpa_supplicant can retain the old high-signal Probe Response created when that
AP was a previous steering target. The refresh changes no association and
invents no identity. It replaces that stale cache signal with a new response
received under the current serialized medium generation before the BTM policy
compares source and target.
Full initial convergence may take several minutes because controller candidate
queries and steering transactions are serialized deliberately. After the
fleet converges, measurements continue indefinitely; a later room movement or
radio change starts a new environment epoch and reconciliation resumes. The
Optimizer card shows `AUTO BTM`, checked clients, clients with a stronger AP,
the current focus, and the action circuit breaker.

## Public no-connect sandbox

The same viewer is available without a lab connection:

<https://boardfarmdevs.github.io/meta-cmf-bananapi-vcpe/viewer/?mode=no-connect&world=home-a-private-client-room-walk>

This browser-only mode starts in Interact mode. Anyone can drag clients,
right-click to move them at a selected speed, disappear/reappear them, inspect
distance and wall crossings, and preview the calculated links. Its prominent
`NO CONNECT` badge means that it does not contact a controller, optimizer,
client or wmediumd and therefore cannot cause a real association change.

## Stop, restoration, and evidence

Press Ctrl-C in the room-demo terminal. SIGINT and SIGTERM both enter the
normal shutdown path. The server first withdraws command admission, drains
already accepted actor work, stops movement clocks, and restores and reads
back the exact captured wmediumd baseline before the postflight mesh audit.

An uncatchable `kill -9` cannot restore in the dead process. The recovery
journal remains at `/run/easymesh-room-demo/recovery.json`. Before starting a
new room session, run:

```bash
gen/demo/room-demo recover
```

Recovery refuses a different wmediumd instance, an unexplained generation or
a contaminated ownership record; those cases require engineering diagnosis.
Do not run `steer.sh`, another configurator scenario, or another room demo at
the same time because they would be competing RF writers.

Evidence is written under `/tmp/easymesh-room-demo-runs/<run-id>/`:

- `world.json`: immutable signed Golden World;
- `layout.json`: verified source geometry;
- `runtime-world.json`: viewer world with space and propagation fields;
- `live-events.jsonl`: leases, accepted interactions, RF generations,
  telemetry, optimizer, traffic, health, and restoration events;
- `health-preflight.json` and `health-postflight.json`;
- `interactive-summary.json`; and
- `recovery.json`, the final checksummed recovery state copied from `/run`;
- `recorded-mobility.json` and `recorded-world.json`, when a recording was
  made; and
- `evidence-index.json` with size and SHA-256 for every artifact.

The terminal must finish with `outcome=passed restored=true`. Treat any failed
restore as a stop condition for further RF tests.

## Direct API examples

The browser is the normal client. For diagnosis, acquire a lease:

```bash
curl -sS -X POST http://127.0.0.1:8891/api/demo/interactions/lease \
  -H "Authorization: Bearer $(cat /run/easymesh-room-demo/operator.token)" \
  -H 'Content-Type: application/json' \
  -d '{"owner":"terminal-demo","command_id":"terminal-lease-0001"}' | jq
```

Read `/api/demo/interactions` to obtain the current revision. A position write
then has this shape:

```json
{
  "token": "returned lease token",
  "expected_revision": 0,
  "client_sequence": 1,
  "command_id": "terminal-position-0001",
  "position": [12.5, 8.0],
  "final": true
}
```

Send it with `PUT /api/demo/roles/sta_mobile_01/position`, the bearer header
shown above, and `If-Match: "world-revision-0"`. Responses carry the new
world revision as an `ETag`. A retry must reuse the exact same `command_id` and
body; it receives the original response without advancing world or medium
state. Reusing that ID with different content returns a conflict. Presence uses
`PUT /api/demo/roles/sta_mobile_01/presence` and a boolean `present` member.
The response identifies the accepted revision, daemon generation, role state,
changed-link count, and calculated per-AP/per-band link budget. Tokens are
never included in the event stream.

A server-owned walk begins with `POST /api/demo/roles/{role}/move` and this
body (using the latest revision):

```json
{
  "token": "returned lease token",
  "expected_revision": 4,
  "client_sequence": 2,
  "command_id": "terminal-move-0001",
  "destination": [17.0, 12.0],
  "speed_mps": 1.4
}
```

The reply supplies a movement ID. Pause and resume it with `POST` to
`/api/demo/movements/{id}/pause` or `/resume`; cancel it with `DELETE
/api/demo/movements/{id}`. Each control body carries the token and current
`expected_revision`. `GET /api/demo/interactions` exposes active and completed
movement state without exposing lease credentials.

Recording uses `POST /api/demo/recording/start` with `token`,
`expected_revision`, and `name`; `POST /api/demo/recording/stop` uses the token
and revision. After stop, `GET /api/demo/recording/world` returns the compiled
world document without requiring the lease.
