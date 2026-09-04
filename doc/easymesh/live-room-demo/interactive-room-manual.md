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
- client motion changes five AP links on three bands in both directions, or 30
  frequency-qualified values in one atomic generation;
- session start captures the full baseline and applies the 20-client room as
  one 600-link atomic generation before accepting browser control;
- `recommend` is the default optimizer authority;
- stopping the process restores the exact pre-session value and override bit
  for every touched wmediumd link.

The room position is simulated truth. Association, RCPI, candidate metrics,
optimizer decisions, BTM acceptance, topology, and traffic remain observed
truth. Moving an icon never directly moves it to a different AP.

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

The purple badge changes to green **LIVE RF** only when the writable API is
present. A static viewer remains labeled **PREVIEW ONLY**.

## Move a client directly

1. Select **Interact**. The browser acquires a 30-second renewable lease.
2. Drag a client across the floor.
3. Watch the spatial panel for coordinates, distance, walls, wall loss,
   predicted SNR, current AP, strongest AP, and measured RCPI.
4. Release the pointer to force delivery of the exact final position.
5. Watch the event list for `RF position applied`, then watch measured RCPI,
   optimizer state, and the cyan observed-association line.

Pointer motion is smooth and local at display rate. Requests are coalesced to
at most five writes per second, serialized, and revision checked. Every
accepted update is read back before the server advances its room revision.

## Walk to a destination

1. Choose `0.6`, `1.4`, or `3.0 m/s` in **Destination speed**.
2. Right-click a client and choose **Move to destination…**.
3. Click the destination on the room floor.

The purple path and marker show the route. The server owns the movement after
the click, interpolates constant-speed positions, and applies at most five RF
generations per second. The browser follows accepted server events; throttling,
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

**Reset role** restores that client's session-start position and presence.
**Reset all** restores every changed client through ordinary revisioned RF
transactions. Neither command recreates radios, containers, identities, or
the lab.

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
normal shutdown path. The server stops accepting controls, workers stop, and
the exact captured wmediumd baseline is restored and read back before the
postflight mesh audit.

Do not use `kill -9`; no userspace program can restore state after SIGKILL.
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
- `recorded-mobility.json` and `recorded-world.json`, when a recording was
  made; and
- `evidence-index.json` with size and SHA-256 for every artifact.

The terminal must finish with `outcome=passed restored=true`. Treat any failed
restore as a stop condition for further RF tests.

## Direct API examples

The browser is the normal client. For diagnosis, acquire a lease:

```bash
curl -sS -X POST http://127.0.0.1:8891/api/demo/interactions/lease \
  -H 'Content-Type: application/json' \
  -d '{"owner":"terminal-demo"}' | jq
```

Read `/api/demo/interactions` to obtain the current revision. A position write
then has this shape:

```json
{
  "token": "returned lease token",
  "expected_revision": 0,
  "client_sequence": 1,
  "position": [12.5, 8.0],
  "final": true
}
```

Send it with `PUT /api/demo/roles/sta_mobile_01/position`. Presence uses
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
