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
truth. Moving an icon never directly moves it to a different AP.

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
does not write RF. Pointer-up sends one revision-checked position command. The
server quantizes it to the 5 cm room grid, applies only changed RF keys in one
generation, and reads them back before advancing its room revision. If the
position changes geometrically but none of the integer SNR values changes, it
records an RF no-op and does not advance the medium generation.

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

## Optional steering authority

The default command runs the external optimizer in recommendation mode. To
permit its existing single bounded BTM action, restart the room with both
confirmations:

```bash
gen/demo/room-demo interactive \
  --mode act \
  --yes-act \
  --listen 0.0.0.0:8891
```

The current manifest still limits the action to its declared time window and
hero client. Other clients may be moved to explore RF and telemetry, but they
do not acquire steering authority from the room server.

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
