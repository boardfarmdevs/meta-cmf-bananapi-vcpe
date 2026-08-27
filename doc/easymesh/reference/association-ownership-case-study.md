# Case study: steering succeeded, but topology reverted

## Executive summary

A manual steer of `sta-10` to `extender-3` completed over the air, but the
EasyMesh topology continued to show the client on `extender-1`. The steering
command, BTM exchange, and client reassociation were not the failure. The
investigation found three HAL lifecycle/provider defects plus one controller
snapshot-reconciliation defect.

After a silent BTM roam, mac80211_hwsim could retain an authorized station
object at the old AP. A later, unrelated station-flag update on that retained
object caused the HAL to emit another associated-device callback because it
tested the station's resulting `AUTHORIZED` state rather than whether this
operation had just authorized it. OneWifi and EasyMesh correctly treated that
callback as an authoritative association edge, so the obsolete AP could reclaim
the client in the controller model.

The first fix is in the HAL, not in a host-side synchronization service. An
associated-device callback is now emitted only after a successful transition
into `WPA_STA_AUTHORIZED`. Telemetry reads and unrelated WMM, MFP, or other flag
maintenance can no longer manufacture associations.

A larger 20-client topology exposed the second path: periodic nl80211
diagnostics still exported the retained old-AP row as a live associated
device. OneWifi correctly turned every returned row into a full Associated
Clients snapshot, and a missed association event left the controller choosing
between contradictory snapshots. The hwsim-only diagnostic provider now
filters a row after 120 seconds of kernel inactivity. The conservative window
avoids hiding a legitimately idle current station. The existing OneWifi
poller then marks it inactive and the next standard EasyMesh snapshot removes
the obsolete claim.

The agent did remove that obsolete row from its own consolidated model, but a
fourth defect remained: the controller treated every Associated Clients TLV as
an additive update. It kept ownership rows omitted by a later full snapshot,
so a withdrawn old-owner claim could remain in the database indefinitely and
block current ownership evidence. The controller now reconciles each received,
validated Associated Clients TLV as the reporting device's authoritative
snapshot and deletes absent rows through its normal database path.

The final failure was on the destination side. During staged VAP provisioning,
EasyMesh applies the operational BSS configuration by stopping and starting the
hwsim AP. The VAP continued to beacon, but its first management-frame receive
registration could remain tied to the pre-reconfiguration state. A monitor on
the same target wiphy received the client's authentication request while
OneWifi did not. Restarting OneWifi recreated the sockets and immediately made
the target usable. The HAL now refreshes its management-frame and EAPOL receive
registrations at the AP restart boundary on hwsim targets. The optional
spurious-frame subscription is deliberately retained: it remains live across
the restart and mac80211_hwsim rejects a replacement subscription with
`EBUSY`.

## User-visible failure

The test command was:

```sh
cd gen
./steer.sh sta-10 extender-3
```

The command resolved the friendly names to a station MAC and target BSSID and
the target client changed BSS. Nevertheless, the WebUI either remained on the
old extender or briefly showed the target before returning to the old one.
Waiting or refreshing the page did not correct the model.

This distinction matters:

- a successful steering response proves that the request was accepted;
- `iw dev wlan0 link` in the station container identifies the actual serving
  BSSID;
- an AP station-table entry proves only that the AP retains state for that
  station; and
- the controller API and WebUI show the controller's current ownership model.

The over-the-air state and the control-plane model had diverged.

## Relevant event path

```text
steer.sh / EasyMesh controller
            |
            | Client Steering Request / BTM request
            v
station reassociates to target AP
            |
            | nl80211 station authorization
            v
RDK Wi-Fi HAL associated-device callback
            |
            v
OneWifi associated-client delta
            |
            v
EasyMesh Agent Client Association Event
            |
            v
controller database -> em_cli API -> topology WebUI
```

The HAL callback is therefore not a harmless refresh. It asserts, “this station
has just become associated here.” Everything downstream is designed to consume
it as an authoritative edge.

## Investigation

### Establishing ground truth

The client container's `iw dev wlan0 link` output showed the target BSSID after
the steer. At the same time, the controller API still selected the old
extender. Inspection of AP station tables showed that both the old and new AP
could contain an entry for the same MAC.

That duplicate is possible in this simulated environment after a silent BTM
roam. It does not mean that the station is simultaneously associated to both
APs. Only the client link and current authorization transition can establish
the association edge.

### Eliminated explanations

- **Name resolution:** `sta-10` and `extender-3` resolved to the intended MAC
  and target BSSID.
- **Steering transport:** the request reached the client and its physical link
  moved.
- **WebUI-only caching:** the controller API itself contained the obsolete
  owner, so repainting the browser could not fix it.
- **Controller duplicate-row selection:** existing controller protections
  reject ambiguous snapshots and maintain one current owner, but cannot tell
  that an explicitly published association event is false.
- **Need for a host synchronizer:** a prototype could compare every client link
  with every AP table and repair state, but it would conceal the producer bug,
  add another state owner, and differ from physical deployments.

### Source-level root cause

In `wifi_drv_sta_set_flags()`, the HAL previously used:

```c
if (total_flags & WPA_STA_AUTHORIZED)
    nl80211_read_sta_data(interface, addr);
```

`total_flags` describes the state after the operation. It remains authorized
while hostapd changes unrelated station flags. `nl80211_read_sta_data()` reads
the entry and ultimately notifies associated-device listeners, so any later
flag maintenance could replay the association callback.

This becomes visible with hwsim because an obsolete station object may remain
at the source AP. The defect is nevertheless generic: the HAL used persistent
state as if it represented a state transition and emitted an edge-triggered
event from it.

### Destination AP accepted beacons but not authentication

Packet capture on the client and target proved that a BTM-directed station sent
Open System Authentication to the requested BSSID. A target-side monitor
interface received those frames at approximately -31 dBm, yet embedded
hostapd sent no authentication response. `strace` of OneWifi's nl80211 receive
thread showed its management descriptors in the wait set but no readable
descriptor and no `NL80211_CMD_FRAME` delivery during the same interval.

Restarting only OneWifi on that extender restored authentication, reassociation,
the four-message WPA2 handshake, station authorization, and the association
notification. This eliminated wmediumd, BTM construction, target BSSID
selection, and target RF strength as causes. The remaining boundary was the
HAL's receive registration across `STOP_AP`/`START_AP` in
`restart_interface()`.

## Fix

### Edge-triggered association notification

Patch
`recipes-ccsp/hal/rdk-wifi-hal/0027-notify-association-only-on-authorization-edge.patch`
changes the contract as follows:

1. Detect authorization from `flags_or & WPA_STA_AUTHORIZED`, the bits enabled
   by this operation, rather than `total_flags`.
2. Send `NL80211_CMD_SET_STATION` first;
3. emit the associated-device callback only if that command succeeds and this
   operation started authorization; and
4. perform the existing Banana Pi backhaul WDS setup on the same successful
   authorization edge.

No polling daemon, hwsim repair process, WebUI exception, or controller timeout
was added.

### Live associated-device snapshot

Patch
`recipes-ccsp/hal/rdk-wifi-hal/0028-hwsim-filter-inactive-associated-station-rows.patch`
corrects `wifi_getApAssociatedDeviceDiagnosticResult3()` on `HWSIM_RADIO`.
While constructing the station list, it reads the standard
`NL80211_STA_INFO_INACTIVE_TIME` field already present in the dump and omits a
row after 120 seconds without a received frame.

This boundary is intentionally hwsim-only. Physical firmware and drivers keep
their native association-liveness policy. The HAL does not delete the retained
kernel object, and no host synchronizer writes association state; it simply
stops presenting historical hwsim state through an API whose contract is a
list of currently associated devices.

### AP receive-registration lifecycle

Patch
`recipes-ccsp/hal/rdk-wifi-hal/0029-hwsim-refresh-frame-registrations-after-ap-restart.patch`
refreshes the VAP's management-frame and EAPOL receive paths after a successful
hwsim AP restart. This repair is colocated with the lifecycle operation that
invalidates the old context. It leaves the independent spurious-frame
subscription intact and is guarded by `HWSIM_RADIO`; physical drivers retain
their native restart behavior.

### Authoritative EasyMesh snapshot reconciliation

Patch
`recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh/0119-agent-reconcile-authoritative-station-snapshots.patch`
removes exact STA/BSSID/RUID rows omitted by a full OneWifi station snapshot,
scoped to the reporting radio. Patch
`0122-controller-reconcile-authoritative-client-snapshots.patch` completes the
same contract in the controller: after validating the complete Associated
Clients TLV, it removes rows absent from that reporting device's model and
queues the normal database deletion. A missing optional TLV is not treated as
an empty snapshot.

## Why the fix belongs in the HAL

The HAL is the first layer that can distinguish a requested authorization
transition from a later read of an authorized station object. Downstream
components should not infer physical truth by comparing timestamps from
contradictory authoritative events. Fixing the event at its source provides the
same semantics to OneWifi, the EasyMesh Agent, the controller, APIs, and any
future optimizer.

This preserves the responsibilities of each layer:

| Layer | Responsibility |
| --- | --- |
| mac80211/nl80211 | expose station objects and apply flag changes |
| Wi-Fi HAL | preserve live AP receive registrations and translate a successful authorization transition into one association event |
| OneWifi/Agent | publish that association delta to EasyMesh |
| Controller | reconcile full snapshots and maintain one current client owner from valid events |
| WebUI/optimizer | consume the controller model without repairing it |

## Validation

The complete `0027` through `0029` HAL repair and the `0119` authoritative
EasyMesh snapshot reconciliation were compiled into matching controller and
extender images:

```text
source baseline     de49068a80b6ee2c3d6290afc1f9530084050a07 + uncommitted series
controller image    X86EMLTRBPIBB_rdk-next_20260827024949.rootfs.lxc.tar.bz2
controller SHA-256  30668e3e44450d467f62363f2bbce1759472fd2c25755c35b627e89375236081
extender image      X86EMLTRBPIAP_rdk-next_20260827025725.rootfs.lxc.tar.bz2
extender SHA-256    c624b04304de4b33c7d7505009daa611189e838aa706c3c065a450536400c240
deployed HAL hash   0593def6b25228e6c8f054ad0ef589928533e2f5049ed0929cc8b23b08db8e0a
```

All five deployed BPI containers reported that same HAL library hash.

| Gate | Result |
| --- | --- |
| controller `rdk-wifi-hal -c patch -f` | PASS |
| controller `rdk-wifi-hal -c compile -f` | PASS |
| extender `rdk-wifi-hal -c compile -f` | PASS |
| complete controller image | PASS |
| complete extender image | PASS |
| clean rev130 container/radio startup | PASS: five BPI containers active without a service restart |
| complete clean-start controller inventory | PASS: 5 devices, 15 radios, 50 BSS records and no factory MLO SSID |
| client population | PASS: 20/20 clients, including one 2.4 GHz and one 6 GHz association |
| controller association inventory | PASS: 24 current stations (20 clients plus four backhaul STAs) |
| physical-link/API ownership agreement | PASS: 20/20 clients after cold start and after steering |
| `sta-10` to `extender-3` | PASS: physical and API BSSID `02:00:00:fb:f7:03`; no OneWifi restart |
| backhaul topology and metrics | PASS: four wireless edges, all fresh at the validation gate |
| delayed stale-owner regression check | PASS: 45-second per-steer gates plus final 90 seconds |

The live test must compare three views after every steer:

```text
requested target BSSID
        == client iw link BSSID
        == controller API serving BSSID
```

The focused regression automates that comparison and the delayed hold:

```sh
./gen/tests/association-ownership-regression.sh \
  --rounds 2 sta-09 wlan-client extender-2 extender-3 extender-1
```

It must also wait after convergence so a retained old-AP entry has time to
receive ordinary flag maintenance. A test passes only if the three values stay
equal; an immediate match followed by reversion is a failure.

The rev130 campaign used `sta-09` and rotated it across Extenders 1, 2, and 3.
The first move converged in one second and its return to the previously visited
AP converged in two seconds. Both were observed for 45 seconds. Six additional
rotations converged in one or two seconds and remained consistent for 20
seconds each. The final owner then remained stable for another 90 seconds.

After the rotations, all three AP kernel station tables still described the
station as authorized, authenticated, and associated. The test therefore
exercised multiple retained-old-entry conditions rather than relying on ideal
disassociation cleanup. Only the client-side link identified the physical
owner, and the controller remained aligned with it; no topology reversion
occurred.

### Clean-deployment regression and correction

An intermediate clean image exposed a separate lifecycle interaction. The
management-frame refresh succeeded, but attempting to replace the optional
spurious-frame subscription returned `EBUSY`. Treating that diagnostic failure
as fatal stopped staged VAP provisioning after the first 5 GHz VAP. The
affected extender still joined, but advertised a factory MLO SSID on an enabled
BSS; the controller consequently rejected its full Operational BSS TLV and
stopped at 12 radios and 40 BSS records.

The final `0029` scope leaves the live spurious-frame subscription alone and
refreshes only the paths required for authentication and EAPOL. A clean
redeploy then converged without nudges or service restarts to five devices, 15
radios and 50 BSS records. Twenty clients joined, the controller reported 24
associated station rows including four backhaul STAs, and every client-side
serving BSSID matched the API. This supersedes the intermediate 12/15-radio
observation; it is retained here only to explain why the narrower lifecycle
boundary is required.

## Scope and residual risk

The fixes do not force hwsim to delete an old AP station object. They prevent
that object from producing a false association edge and bound how long it can
remain in a live diagnostic snapshot. Normal disassociation cleanup remains
desirable, but a separate synchronization daemon is not required for EasyMesh
ownership convergence.

The patch should be proposed to the HAL maintainers because its event semantics
are generic, while the reproduction is especially deterministic in the
container/hwsim lab. Regression coverage should retain both normal association
and reassociation tests, including returning to a previously visited AP.

## Lessons for optimizer experiments

An optimizer can be evaluated only when its observation and actuation loops
agree on current ownership. This case shows why a steering ACK or a topology
animation is insufficient evidence. Every optimizer test should retain:

- the requested action and target;
- the client-side serving BSSID;
- the controller's serving BSSID and observation time;
- a bounded convergence time; and
- a delayed consistency window that detects stale-event replay.

The laboratory remains intentionally closed-loop, but the loop must be repaired
at component boundaries rather than by an external process that silently
reconciles contradictory state.
