# Room extender signals and adaptive RDK backhaul

## Scope and diagnosis

This is a rev140-only live overlay, not a rebuilt 0906 thin archive. rev120/prplMesh and rev150 runtime remain unchanged. The existing fixed container pool stays running.

Previously the world-switching session captured mesh-to-mesh RF at startup and protected it on every subsequent move/world load. Only client BTM steering ran automatically. Drawing extenders in different places did not select new parents. The controller reported actual backhaul but did not automatically optimize it in this room flow.

The centered default room actually favors a star: at 5 GHz each gateway-to-extender path is 24 dB; the nearest same-side extender path is 23 dB, horizontal pairs 19 dB and diagonals 12 dB. A nearby extender also has an upstream bottleneck and consumes another wireless hop. A chain is not automatically better. The network-topology diagram is logical, not a copy of floor coordinates; both views draw controller-reported parent edges.

## Live star audit and simulated peer overlay

The September 7 UTC rev140 audit reads all 60 directed, per-band mesh RF
overrides directly from the running wmediumd control socket. They agree with
both the room's applied-RF snapshot and the canonical geometry calculation.
The four kernel `wifi1.3` parent BSSIDs agree with controller topology and the
external planner. Adaptive mode is enabled, with no pending move or failure.
No RF write, BSSID change or BPI-stack modification is needed for this audit.

Using the **displayed** node names rather than the reversed binding-role order:

| Link | Distance | Wall loss | Applied 5 GHz SNR |
| --- | ---: | ---: | ---: |
| Agent-1 to each extender | 9.434 m | 5 dB | 24 dB |
| Extender-1 to Extender-3 | 10 m | 5 dB | 23 dB |
| Extender-2 to Extender-4 | 10 m | 5 dB | 23 dB |

The direct score is 24. Via either requested neighboring extender it is
`min(23, 24) - 3 = 20`. Even without the extra-hop penalty or hysteresis,
23 does not beat 24. Enumeration of all 125 valid gateway-rooted trees gives
the star as the unique maximum under the current score (summed score 96).
The requested two branches score 88. This is not an imposed star constraint
or missing parent-steering support.

Branch/chain formation needs a genuinely better relay path: move Agent-1
toward one end, place stronger near-gateway relays ahead of farther extenders,
or use a world whose walls attenuate direct paths more than relay paths.
Canonical-model regressions confirm that shifted Home B selects a branch and
the corridor positions `gateway=[1,1]`, `extender_1=[5,1]`,
`extender_2=[8,1]`, `extender_3=[12,1]`, `extender_4=[18,1]` converge to a chain.
These identifiers are binding roles, not display numbers. Earlier live tests
also verified corridor associations and traffic; the current room is left intact.

The viewer now draws each extender's strongest **simulated** peer as a thin
dashed floor ribbon, colored by that peer (red Agent-1, orange extender),
offset 0.14 m from the actual route when they coincide. Its width is 0.026 m
versus the actual route's 0.09 m; both use the lighter wall-occluded pass.
This uses the selected preview band and updates while dragging. It is not an
actual association, verified applied RF, or loop-free steering plan; strongest
peer choices can be reciprocal. The viewer and movable properties panel use
the platform's standard arrow cursor, even while dragging. Selected mesh nodes no longer draw a distracting elevated fan of
purple candidate lines.

A viewer-only bug is corrected: live mesh peers now follow actual mesh-node
presence rather than fronthaul availability. Disabling fronthaul cannot make
a still-running extender disappear from simulated backhaul comparisons.
Offline worlds continue to honor their own presence flags.

Evidence: `/home/rev/work/extender-simulated-links-0906` on rev140 and the
working host. Tests include `gen/tests/viewer-mesh-best-test.js` and canonical
star/branch/chain cases in `gen/demo/tests/test_backhaul.py`.

## Signal rendering

If an actual parent appears to alternate after a verified change, compare the
kernel BSSID with controller telemetry before adjusting steering hysteresis.
The [0906 backhaul reporting correction](backhaul-parent-reporting-0906.md)
fixes an IEEE1905 transport bug that erased live parent membership and made
shifted Home B appear to roam repeatedly despite a stable radio association.

Every extender now has the same ten-segment red/yellow/green/grey uplink meter as network topology. It uses the controller's actual-parent RSSI, expires after 20 seconds, and never replaces missing measurements with geometry. The gateway has no wireless parent meter. Disabling fronthaul leaves an extender's backhaul and meter active.

The adjacent `RF 24 dB` label is **verified applied wmediumd SNR**, matched to the actual reported parent, band and channel. It is not receiver-measured SNR. No assumed noise floor is subtracted from RSSI. Select the extender to see actual parent, RSSI, applied SNR and the separate geometric candidate preview. Changing the preview band does not retune backhaul.

## Explicit low-resource lab control

Opt in with `room-demo interactive --mode act --yes-act --adaptive-backhaul`. The option is rejected outside act mode and outside the known five-device RDK/OneWifi channel-36 inventory. Without it, fixed-pool sessions retain startup protection. Do not use this adapter for prplMesh.

1. Room moves and world loads atomically apply and read back mesh-peer RF as well as client RF. Fronthaul presence changes still leave mesh RF intact.
2. After at least 10 seconds of stable RF, the existing optimizer worker checks actual `iw` parent BSSIDs. Checks are at least 30 seconds apart; no extra process, VM or monitoring service is added.
3. At most 256 parent combinations are considered for four extenders. Only gateway-rooted, loop-free trees with bidirectional links of at least 5 dB are eligible. Path score is the weakest bidirectional SNR minus a heuristic 3 dB per extra hop; this is **not a throughput estimate**.
4. A proposed tree must not reduce any final path score and must improve the summed path score by at least 4 dB per changed parent. One eligible parent changes at a time, prioritizing the largest immediate fleet path-score gain without reducing any intermediate path's RF bottleneck. Hysteresis can intentionally retain a slightly non-optimal existing tree.
5. The RoomEngine serializes the action with movement/world changes/client steering and rejects stale RF epochs. The actual parent graph is checked again immediately before mutation.
6. If needed, activate the parent's lazy 5 GHz mesh AP with `Device.WiFi.AccessPoint.14.ForceApply`. Already active APs are not reloaded. Select the child's parent with `Device.WiFi.STA.2.Bssid` (the existing writable OneWifi RBUS path).
7. Allow up to 30 seconds to verify the real `wifi1.3` association and two consecutive gateway probes over `brlan0`. On failure, restore and verify the previous BSSID. Individual subprocesses have timeouts. The viewer can briefly wait behind this serialized transaction; lease time is extended by the internal action duration so a browser is not evicted while renewals wait. Controller topology may lag the kernel association.
8. Wait 60 seconds after failure. Three consecutive failures, a failed rollback, or 100 parent attempts pause backhaul control until service restart. Client BTM has its own separate budget. Unknown/disconnected backhaul pauses selection rather than guessing a parent.

This is **lab-assisted OneWifi backhaul control**, not native EasyMesh backhaul-steering CMDUs, not client BTM, and not a claim of controller-driven automatic backhaul optimization. Parent BSSID changes remain real associations after session shutdown; existing shutdown recovery restores RF/client state, not a saved parent graph. Starting the default room lets the bounded policy reconsider those parents. No container or agent restart is used for a parent change.

Pending backhaul changes take priority over starting a new full-fleet client measurement cycle. The optimizer explicitly displays “Settling mesh backhaul before measuring client APs”. This avoids repeatedly querying agents over a known weak old route while a better parent is pending. A query already in flight when the user moves a node can still fail or be discarded; live topology and measurements can briefly disappear during a real roam and must recover afterward.

## Operation and validation

On rev140, enable the option in a systemd drop-in for `easymesh-room-demo.service` inside `rdkeasymesh-20-0906`, preserving its existing ExecStart arguments. Restart only the room service after checkpointing the selected world, all positions/presence, playback and traffic probe. Never overwrite a user's active movement/recording.

Open `http://192.168.2.140:18891/viewer/?mode=interactive`. Whole lab shows **Lab backhaul** status and reason; Recent events shows started/verified/failed actions. `/api/demo/interactions` reports `backhaul_policy: adaptive-rdk` and verified `backhaul_links`. `/api/demo/current` retains controller parent edges and adds their `applied_rf` plus `network.mesh.backhaul_control` status. The UI does not draw planned edges as successful links.

Keep Agent-1 centered to check the stable star. For a multihop test, move Agent-1 toward one end of a corridor and arrange extenders progressively farther away, with strong neighboring paths. Stop movement and allow at least one full client-measurement cycle plus the settle interval for selection. Observe verified parent events, actual controller edges, extender gauges and client/gateway traffic. Restore the saved room afterward; do not force a chain where the default geometry favors direct links.

Local regressions:

```sh
PYTHONPATH=gen/optimizer:gen/demo:gen/wmediumd/configurator \
  python3 -m pytest -o addopts='' -q gen/optimizer/tests gen/demo/tests
node gen/tests/viewer-extender-signal-test.js
node gen/tests/viewer-backhaul-test.js
```

Runtime test evidence and deployment checkpoints live under `/home/rev/work/adaptive-backhaul-0906` on the working host and rev140. The 0906 thin release tarballs are intentionally unchanged.
