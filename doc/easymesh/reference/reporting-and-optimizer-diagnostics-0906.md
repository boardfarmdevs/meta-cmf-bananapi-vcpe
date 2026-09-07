# Reporting and optimizer diagnostics: 0906 rev140 overlay

This work targets rev140 only. It does not repack the immutable 0906 thin
archives or modify the rev120/rev150 deployments.

## Confirmed reporting faults

- The decoder's installed `em_base.h` lacked runtime structure extensions.
  Its station/device layout differed from the agent's layout across callback
  boundaries. The `unified-wifi-mesh-header` append now aligns the public ABI.
- The OneWifi translator cleared `sizeof(pointer)` instead of the entire
  allocated station record, leaving unpopulated fields undefined.
- Agents subscribed to association notifications but did not periodically
  retrieve authoritative associated-client snapshots. Clients already present
  at agent startup, or missed notifications, could remain metrics-only rows
  with a zero association clock. After onboarding, the agent now retrieves a
  full snapshot every 30 seconds through the existing OneWifi bus getter.
  Existing full-snapshot reconciliation suppresses unchanged ownership events
  and retains the earliest valid clock. A real reconnect can reset it.
- Station assignment and metrics merging must preserve the association clock
  and ownership. Metrics are not a new association event.
- Fleet convergence previously counted selected queries rather than clients
  with fresh comparisons for every eligible same-band AP. Missing or expired samples now leave coverage
  incomplete instead of implying convergence.
- RF waiting/change events did not invalidate the old optimizer panel.
  They now clear old convergence and per-client decisions.
- Human-facing AP names could use a geometric role number instead of the
  controller's discovery-order label. Serving and candidate names now agree
  with the native topology; role/BSSID bindings remain unchanged.

The controller's pre-association sample rejection and the optimizer's
20-second dwell safeguard remain enabled. Freshness thresholds are not
extended. When a full snapshot supplies no elapsed association age, the agent
starts a conservative observed clock; it does not invent an earlier connect
time. On agent restart this clock may initially reset, then must advance.

## New visibility

`optimizer.progress` reports current-connection reads and actual candidate
query completion counts. `optimizer.evaluation.client_decisions` contains a
decision for each observed client, association age, metric timestamp/source,
candidate-query eligibility, target and remaining policy wait. The viewer
shows a selected station's reason plus an expandable fleet list.

The progress header explains measurement, waiting, blocked and converged
states. It includes the last evaluation's age and cycle duration. Remaining
waits are explicitly sampled values, not a browser-created timer that can
hide a frozen backend clock. Query failures remain visible with retry backoff.

Live bars use fresh controller measurements, or the existing verified client
Wi-Fi fallback, never synthetic model-green. Grey means unavailable or stale.

### Candidate timeouts and event ages

A subsequent longer rev140 run exposed another controller defect. Its journal
reported `Candidate metrics query timed out before transmit in state
em_state_ctrl_bsta_cap_pending`: a cancelled backhaul capability query left
the radio in its pending protocol state. Repeated HTTP queries then timed out
even though the clients, fronthauls and room server remained healthy. This is
a controller scheduling failure, not evidence that the browser's Internet
connection or every client signal has failed.

Patch `0160` releases that pending state on capability-query cancellation.
Delayed capability reports may still update inventory, but cannot overwrite
an unrelated candidate/configuration state. The state transition uses the
orchestrator's existing command lock. Candidate timestamps, completeness
checks and timeouts remain unchanged: the optimizer still pauses steering on
incomplete measurements and retries automatically. A displayed retry backoff
is the scheduled delay after a failure, not the duration of the query itself.

The old Recent events column used `world_time_ms`, which caps at the room's
240-second duration. Thus new events all displayed `240.0s` after four minutes;
this was not their age and did not mean the event stream had stopped. Live
entries now use `recorded_at` and the server-anchored monotonic browser clock
to display advancing ages. Hover reveals the exact recorded timestamp. Replay
keeps scenario timestamps, and missing timestamps stay explicitly unknown.

The follow-up overlay rebuilds and restarts only the rev140 native controller;
the viewer files hot-reload without restarting the room. Its evidence and
controller rollback binary are under `/home/rev/work/event-timeouts-0906`.
The controller does not link the station decoder, so no decoder replacement
or additional controller library-path configuration is required.

## Live deployment boundaries

The running legacy OneWifi process was built with the earlier decoder ABI.
For this overlay the rebuilt decoder is installed privately as
`/usr/lib/easymesh/libwifi_webconfig.so.0` inside each mesh container, selected
only for `em_agent.service` by
`/etc/systemd/system/em_agent.service.d/reporting-abi.conf`. The global decoder
and OneWifi daemon are left intact; this avoids mixing the old OneWifi binary
with a new callback layout. A full image build uses the aligned header for
all consumers and does not require the live-overlay isolation.

Agent binaries and their private decoder are a matched pair. Restart only the
agents for the native overlay. Updating the Python diagnostics requires a room
service restart; capture the current world, role positions/presence and probe
first, then restore and verify them through the normal room API. The underlying
VM, containers, OneWifi and wmediumd are not restarted.

## Verification

- `gen/tests/em-public-header-abi-test.py RUNTIME_HEADER DECODER_HEADER`
  compares the complete public header tokens, ignoring comments/formatting.
- `gen/tests/em-agent-snapshot-refresh-test.py em_agent.cpp` compiles the
  production periodic refresh against a small fake bus and checks cadence,
  onboarding gating and failed-read handling.
- `gen/tests/em-agent-metrics-association-test.py` checks metrics/clock merging.
- Python candidate, conductor and event tests cover real query progress,
  failure accounting, missing/stale convergence and per-client dwell reasons.
- `gen/tests/viewer-optimizer-status-test.js` covers progress, selected-client
  explanations, stale evaluations and RF invalidation.
- `gen/tests/em-controller-capability-recovery-test.py em_orch_ctrl.cpp em_capability.cpp`
  compiles production cancellation/report code and verifies recovery without
  changing another command's state. The original cancellation path fails it.
- `gen/tests/viewer-event-time-test.js` verifies advancing live ages beyond the
  playback endpoint, unknown timestamps and unchanged replay-time semantics.
- Live acceptance must verify all 20 native timestamps refresh, association
  ages advance except on actual reassociation, iot-14 is no longer dwell-blocked,
  and candidate measurements/steering converge after the environment settles.

Evidence and rollback copies are in `/home/rev/work/topology-metrics-0906` on
the operator host and rev140. Do not claim every possible reporting fault is
eliminated from this bounded audit; retain grey/error states and investigate
any newly observed failures rather than masking them.

## Initial acceptance on rev140

On 2026-09-07 UTC (2026-09-06 Pacific), both Yocto machine configurations
built successfully. All five agents load the matched private decoder. The
controller, CLI, OneWifi and wmediumd PIDs remain unchanged. All 25 containers
remain running and outer-VM autostart remains false.

The 18-sample, approximately three-minute native API check found all 20
clients, advancing association clocks and refreshed timestamps; the oldest
sample observed was 12.32 seconds. No association age was stuck at zero.
The optimizer reported 20/20 clients checked, 80 candidate measurements and
no stronger eligible same-band AP after convergence. iot-14 automatically
moved to controller-labelled Extender-1, from RCPI 76 (-72 dBm) to RCPI 116
(-52 dBm); the dwell safeguard was not bypassed.

Python validation passed 211 tests plus 19 subtests. Browser acceptance
verified real advancing query counts, iot-14's selected-client explanation,
the 20-row decision list, reconnect/reload and native topology rendering.
The browser tests make no lab writes. All 25 positions/presence flags and the
shared iot-14 probe selection were preserved across the room-service update.

Runtime pair SHA-256 (identical on all five mesh containers):

```text
91adf3fc267028589bbdb8d3a9c6f55ca93d1cdbe769dce2a1f624b524b81917  onewifi_em_agent
dece00d241b100e039300bde5843f811240f1c4f450d85421f8ab3bc4dcc40ce  libwifi_webconfig.so.0
```
