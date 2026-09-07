# Live world switching with a fixed lab pool

The lightweight implementation keeps the accepted appliance intact: **20
client containers and five radio-bearing mesh containers stay running**. The
Network Topology shows six mesh nodes because the logical Controller is drawn
separately from its co-located Agent-1. World switching does not add a sixth
radio-bearing container.

The normal server command and appliance startup still use the default
20-client world. A selection is session state, not a new persistent appliance
profile. There is no Yocto build, image import, container creation/deletion,
SSID reconfiguration, hwsim reload, or wmediumd restart during a switch.

## Operator workflow

1. Open the interactive viewer on rev140, not the static GitHub Pages preview.
2. Stop an active recording first and download it if it is needed.
3. Select an installed world, or open a local `.world.json` file smaller than
   4 MiB. Loading immediately applies it to the lab; there is no separate Apply
   button, confirmation, or operator-token prompt. The
   control lease and revision checks still protect every change. Select/file/
   default controls stay disabled until the request finishes. The viewer changes
   rooms only on the server's accepted world event. Invalid uploads or denied
   control leave the current room and selection intact and display an error.
4. The server validates the world and its installed layout, retains the live
   role-to-container/radio bindings and cancels current walks. For each newly
   offline client it sends a real Wi-Fi disconnect before isolating its links,
   then applies and reads back the complete new RF matrix.
5. Follow the status below the controls. RF completion is not association
   completion: the Network Topology continues showing actual controller
   associations until the Wi-Fi clients and controller converge.
6. Click **Restore default 20** to return all clients to their default room
   positions and online presence, without restarting any container.

For example, `home-a-border-hover` contains 12 clients,
`home-a-stationary` contains 10, and `home-b-slow-walk-ten` contains 20 in a
different floor layout. The role names retain their existing SSID, band and
permanent radio identities; ordinals are not reassigned to fill missing slots.

## What “offline” means

An unused client remains a running LXD container. Its existing supplicant sends
a disconnect while the old RF path is still usable, so the AP and medium can
observe the association ending instead of retaining a stale owner. The server
immediately isolates that client's links in a bounded atomic generation and
keeps its supplicant disconnected for the offline interval. This prevents
background association retries from reintroducing stale controller entries.
When a world or Reappear makes it online, RF is restored first and then normal
supplicant connection attempts resume. No network configuration file changes.

All its serving links to all
five APs, on 2.4/5/6 GHz in both directions, are set to the simulator's minimum
SNR, -20 dB: 30 isolated RF values per unused client. This is the reversible
RF disappearance model also used by the client presence control, not a
container failure. The native topology is never filtered to fabricate success.

Roles omitted from the selected world cannot be re-enabled individually through
the interaction API. Restore the default or select a world containing them.
Included clients may still use Disappear/Reappear. Health expectations track
the requested online subset, and optimizer decisions exclude offline clients.
The steering policy uses that same authoritative online count, not the startup
20-client capacity. Observed counts are never rewritten to pass its health
guard: a missing client or mesh device still blocks steering until recovered.
Matching the client roster is not AP convergence. The optimizer must finish
fresh candidate measurements and verified steering until no stronger eligible
same-network, same-band AP remains; weak signals can remain when every eligible
AP is weak.

A missing post-transition signal sample blocks that client, not the rest of
the fleet. In the fixed-pool interactive lab only, the optimizer may recover a
missing controller RSSI using a real client-kernel measurement: one successful
ping through `wlan0`, then `iw dev wlan0 link`. The measured BSSID and band must
match the controller association; failed probes, mismatched owners and invalid
signals remain unknown. This is not a floor-plan prediction, SNR conversion or
an injected controller value. The generic observer has no fallback unless
explicitly configured. The optimizer displays and journals
`kernel_current_link_measurements` separately. Native topology keeps its own
controller RSSI, which can remain grey until telemetry recovers.
An offline traffic-probe role does not continue producing expected-failure
pings. The action circuit breaker remains per server run, not per world.

On rev140, the opt-in [adaptive RDK backhaul overlay](room-adaptive-backhaul-0906.md)
supersedes startup protection: world loads and AP moves apply mesh RF too, and
bounded lab-assisted OneWifi parent selection follows after settling. Other
sessions retain the following protected policy unless explicitly enabled.

All mesh roles must remain in the world. An extender's initial absence means
disabled fronthaul service, as with the existing presence control; its backhaul,
agent and container remain alive. **The startup mesh-peer RF matrix is protected**
across world changes and subsequent interactive AP moves in this fixed-pool
mode. Room geometry changes the client-serving RF, not the infrastructure
backhaul. This avoids a shifted floor plan disconnecting an extender and losing
one of the six topology nodes. Predicted geometric backhaul budgets must not be
confused with the protected applied backhaul values or controller measurements.
Parent selection is still observed EasyMesh behavior, not a nearest-neighbor
policy introduced by world switching.

## Supported boundary

- Use only roles already bound in the server's startup world, with unchanged
  role types and all five mesh roles retained. New names, capacity expansion,
  new APs, changed bands or arbitrary SSID/security assignments are rejected.
- Uploaded worlds must have a valid content checksum and reference an installed
  layout with its matching checksum. A checksum is integrity validation, not
  an authentication signature. The interactive API has no built-in user
  authentication; restrict access to trusted users at the network/gateway layer.
- The interactive room loads the world's **initial frame** paused. Play/Pause
  advances scripted positions and presence in the live lab; dragging pins only
  that role while others keep playing. See the
  [interactive manual](../live-room-demo/interactive-room-manual.md) for the
  bounded cadence, authorization and stable-RF optimizer behavior. Use offline playback to
  inspect the full scripted timeline.
- Layouts and the client pool are reused. This is not a general LXD provisioner
  or an arbitrary world-to-hardware compiler.
- The supported delivered startup remains the 20-client profile. Explicit
  custom startup manifests are an advanced operator feature, not changed by
  the viewer selection.

## Ownership, recovery and evidence

`GET /api/demo/worlds` lists compatible installed worlds.
`POST /api/demo/world/apply` accepts `world` as a catalog name, `default`, or a
world document, plus the ordinary lease token, command ID and expected
revision. It requires same-origin validation,
and `If-Match: "world-revision-N"`. Failed validation writes no RF; successful
retries with the same command ID cannot apply twice.

World changes use the existing serialized RoomEngine and checksummed recovery
journal. Per-client disconnect/isolation steps and the final whole-room
generation are serialized as one room command; the accepted world is published
only after verified completion. They cannot overlap a steering RF-assist transaction. A changed
environment invalidates pending optimizer observations and policy holds. A
failed readback attempts a verified rollback to the preceding room; loss of
medium ownership fails closed rather than overwriting another writer.

The original pre-session RF baseline remains unchanged across all selections.
Stopping the room normally restores that exact baseline, not the last selected
world. The existing `room-demo recover` command handles interrupted RF writes
against the original medium instance/generation. A browser disconnect does not
reset the room; it expires the control lease and cancels owned movement.

The recovery journal also records a client before its runtime supplicant pause.
Rejected operations restore the previous roster, and crash recovery resumes any
journaled clients after RF restoration. A failed resume remains recorded and blocks a new
session until recovery succeeds. Normal shutdown allows up to 60 seconds for
clients to reassociate before the final health check.

`room.world.committed` events retain the applied initial geometry, full pool
presence, revision, RF generation and requested online count. SSE updates every
connected viewer. Reconnecting fetches the current world; evidence replay starts
from the original world and applies recorded switches in order.

## Validation

Local regression coverage is in `gen/demo/tests/test_world_switch.py` and the
server/interaction suites. It covers 20 → 12 → 10 → 20 transitions, immutable
bindings, all-band isolation, rejected roles/layouts, operator/revision checks,
idempotent retries, recording protection, rollback and crash recovery.
`gen/demo/tests/test_client_wifi.py` covers the disconnect/resume journal and
recovery after an interrupted pause. `node gen/tests/viewer-world-loading-test.js`
checks immediate select/upload, startup and in-flight control guards, rejected
loads, default restoration, and read-only/offline boundaries. The opt-in
appliance test is:

```bash
python3 gen/tests/room-world-switch-smoke.py --yes-act --all-worlds \
  --output /tmp/world-switch-acceptance.json
```

It checks all compatible catalog rooms, exact controller MAC rosters, six
topology nodes, kernel disconnection for offline clients, and measured best-AP
convergence for every online client. The final condition must hold for at least
ten seconds in the current RF epoch. It records serving APs and RSSI, verifies
unchanged container/service/medium process identities, and restores the default
20-client room in cleanup. Allow several minutes per room; the default timeout
is 600 seconds per phase. Run only when no other operator owns the room.
The recorded association/RSSI list is an independently sampled passive network
snapshot and can lag a steering evaluation; the convergence gate uses the
current-epoch optimizer measurements and the native controller MAC roster.

### rev140 0905 acceptance

Run `20260905T235053Z-private-client-room-walk-interactive` passes all eleven
catalog rooms, plus default restoration and client Disappear/Reappear. Each
row below passed the exact roster, six-node health, offline-kernel and measured
convergence checks, including the ten-second stability gate. These times are
observed full convergence durations, not the time to submit or apply RF, and
are not latency guarantees.

| Installed room | Initially online | Converged after |
| --- | ---: | ---: |
| `home-a-asymmetric-link` | 11 | 231.18 s |
| `home-a-band-walk-small` | 10 | 290.95 s |
| `home-a-border-hover` | 12 | 224.14 s |
| `home-a-disappear-reappear` | 12 | 100.80 s |
| `home-a-extender-loss-recovery` | 10 | 82.90 s |
| `home-a-fast-transit` | 12 | 67.53 s |
| `home-a-flash-crowd` | 10 | 87.18 s |
| `home-a-private-client-room-walk` | 20 | 86.83 s |
| `home-a-slow-walk-ten` | 20 | 152.70 s |
| `home-a-stationary` | 10 | 76.89 s |
| `home-b-slow-walk-ten` | 20 | 208.04 s |

Returning from the shifted layout to default converged in 305.01 seconds;
Disappear/Reappear converged at 19/20 clients in 44.92/48.40 seconds. The test
verified unchanged container, native-service and wmediumd process identities.
The action counter ended at 37/100; it was not reset between worlds. Explicit
kernel measurements recovered missing controller samples in border-hover and
the reappearance check. This acceptance tests initial frames and interactive
presence changes, not automatic playback of every scripted future generation.
The machine-readable report is
`/root/room-convergence-0905-v2/all-rooms-acceptance.json` inside the appliance.

Read-only Chromium checks also pass exact visible client rosters in both views
for all eleven catalog rooms. Automatic-loading browser checks pass installed
selection (flash-crowd), local upload (stationary), observer SSE updates and
default restoration without an Apply button or confirmation. Invalid checksums
are rejected without a world revision change; a cancelled capability prompt
retains the preceding selection. Controls remain disabled while a request is
pending and before the initial catalog is ready. Browser errors: zero.

Live changes and acceptance are restricted to **rev140**. Rev150, GitHub Pages
and the accepted 0905 thin archives are not updated by this feature. See
[current state](../current-state.md) for the recorded live test outcome.
