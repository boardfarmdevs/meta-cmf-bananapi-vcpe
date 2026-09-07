# Apparent backhaul parent flapping: 0906 transport correction

## What was switching

The September 7 rev140 investigation concerns the shifted Home B world,
`home-b-slow-walk-ten`, in room run
`20260907T135904Z-private-client-room-walk-interactive`.
The room repeatedly drew Extender-1 on either Extender-2 or Agent-1. This was
inconsistent reporting, not repeated physical roaming by the optimizer.

Use binding roles and MAC addresses when comparing evidence: native API
discovery names are not necessarily the room's displayed extender numbers.

| Room label | Binding role | Container | Identifier |
| --- | --- | --- | --- |
| Extender-1 | `extender_4` | `bpiap-003` | AL `02:00:00:00:09:20`; STA `02:00:00:0a:91:73` |
| Extender-2 | `extender_3` | `bpiap-002` | AL `02:00:00:00:08:20`; backhaul AP `02:00:00:03:ae:99` |
| Agent-1 | `gateway` | `bpibroadband` | Backhaul AP `02:00:00:c8:2c:87` |

The manager started one parent change at 19:51:33 UTC and verified it at
19:51:41. Its attempt count remained one, with zero failures. Subsequently,
saved room events alternated the displayed parent between the new relay and
the old gateway. Old-parent reports had no usable uplink measurement.
At 19:57:22 the kernel association and manager parent were Extender-2 while
the room topology said Agent-1. Later polling sometimes saw only the correct
parent: a short successful observation did not disprove the historical fault.

## Root cause

The Rust IEEE1905 AL-SAP proxy replaces an HLE's Device Information TLV in
outgoing Topology Responses with the AL's local interface inventory. That
inventory did not carry the live Wi-Fi network membership supplied by the
EasyMesh agent, so replacement erased the connected backhaul BSSID and
associated media-specific data.

There was a second loss point: `MediaTypeSpecialInfo::serialize()` explicitly
discarded supplied bytes for newer Wi-Fi media types, including this lab's
`0x0109`. The native controller already understands the HLE's live-parent
information, but the transport prevented those bytes from reaching it.
Periodic reports could therefore expose the old parent again.

Passive captures on the gateway's IEEE1905 link established the difference:

| Extender-1 STA entry | Before | After |
| --- | --- | --- |
| Media type | `0x0109` | `0x0109` |
| Media-specific length | 0 | 10 |
| Network membership BSSID | Absent | `02:00:00:03:ae:99` |

The corrected HLE response carries
`02:00:00:03:ae:99:40:03:00:00`. This is wire evidence, not a viewer cache or
a simulated parent substituted for controller telemetry.

## Correction and scope

`recipes-ccsp/ieee1905/ieee1905-em/0007-sap-preserve-live-wifi-network-membership.patch`
changes only the IEEE1905 transport:

- Retain the AL database's device identity, local interface roster and media types.
- Preserve HLE media-specific bytes only when its AL MAC matches the local AL,
  exactly one reported interface matches the local MAC, both media types are
  Wi-Fi, and the supplied membership is exactly ten bytes.
- Ignore mismatched identities, ambiguous interfaces, missing or malformed
  membership, and interfaces not managed by the AL. Do not mutate the AL database.
- Serialize supplied Wi-Fi 6/7 media information rather than silently erasing it.
  Empty media information remains empty. No historical membership cache is added.

Neither the native EasyMesh agent/controller code nor the room's parent
selection, hysteresis or scoring changes. The correct branch in this world
remains Extender-1 → Extender-2 → Agent-1. The centered Home A world can still
correctly retain a star; see [adaptive backhaul](room-adaptive-backhaul-0906.md).

## Regression and build checks

Three new Rust tests accompany the patch: live membership preservation;
rejection of unbound/incomplete membership; and modern Wi-Fi codec round trips.
They also exercise replacement of an earlier parent with a newly reported one.

The upstream full library unit-test target currently has an unrelated Rust
`E0382` moved-value error in a `topology_manager.rs` test. It was not modified
as part of this fix. A focused runner uses the actual production injector and
codec, plus three existing injector tests, without building that broken unit
test module:

```sh
python3 gen/tests/ieee1905-backhaul-membership-test.py /path/to/patched/ieee1905
```

It requires Cargo and the locked dependencies already cached for `--offline`.
The runner creates an exclusive temporary integration test and removes it
afterward. For a before/after comparison, provide the candidate sources as
`--regression-source /path/to/patched/ieee1905` when testing a baseline checkout.
Use separate Cargo target directories, or clean the `ieee1905` package between
copied workspaces, to prevent cached artifacts with misleading source mtimes.

Recorded results: baseline **4 passed, 2 failed**; corrected transport
**6 passed, 0 failed**. The canonical rev140 Yocto
`bitbake -c install ieee1905-em` build also completed successfully.

## Deployment and verification

This is a rev140-only live overlay in VM `rdkeasymesh-20-0906`, applied to the
four extender transports. The existing native agent processes reconnect to
their replacement AL-SAP sockets. OneWifi is not restarted, and the warm
reconnect avoids cold-start interface teardown. Each extender retains its
kernel parent during that reconnect and passes two gateway probes. The
gateway/controller transport, room process and VM are not restarted.
Temporary service overrides used for the warm reconnect are removed afterward.

The deployed transport SHA-256 is
`0dcf86f8107675f41212a8602dacdc89db10fcbaca6ce80ca04f50fe43eb52ed`.
The previous binary is retained in each extender as
`/usr/bin/ieee1905.before-membership-0906`. Restoring it also requires reconnecting
the native agent; replacing an executing binary alone does not activate a rollback.

Validation compares all three sources repeatedly, not just the drawing:

```sh
ssh rev140 lxc exec rdkeasymesh-20-0906 -- \
  lxc exec bpiap-003 -- iw dev wifi1.3 link
curl -fsS http://192.168.2.140:18889/api/v1/topology
curl -fsS http://192.168.2.140:18891/api/demo/current
```

Expect kernel BSSID `02:00:00:03:ae:99`, the native edge into AL
`02:00:00:00:09:20` from AL `02:00:00:00:08:20`, and the room edge into
`extender_4` from `extender_3`. Observe across multiple periodic topology
refreshes, with no increased parent-action count. Also check fleet health and
client measurement recovery after the telemetry reconnect.

### Weak-link recovery during rollout

Extender-3 (`bpiap-001`, not the originally reported Extender-1) did not finish
its configuration refresh at its original 20 dB gateway link. Captures showed
the controller transmitting three WSC M2 fragments, but none arriving on the
extender's transport interface. Small gateway pings passed while four pings
with 1150-byte payloads all failed. The same failure persisted when briefly
testing the previous transport binary, so it was not a regression introduced
by the membership patch. Repeated native-agent restarts alone were ineffective.

The driver rejected a temporary transmit-rate restriction. Recovery instead
used the normal room control lease and position API: briefly place Extender-3
at `[7, 7]`, reconnect its corrected transport/agent, then restore its exact
original `[17, 3]` position in a `finally` cleanup. At the stronger link the
large pings passed and the native inventory recovered to all 50 BSS records.
Do not write directly to the medium socket during an owned interactive session;
that would invalidate the room's generation tracking.

All role positions/presence and the selected world were verified identical
afterward; playback remains paused and the maintenance lease is released.
The RF epoch advances because these are real, recorded room moves. The planner
temporarily moved Extender-4 onto the relocated Extender-3, then restored its
direct gateway parent after the original position was restored. Extender-1
remained on Extender-2 throughout. The final graph again has only the original
Extender-1 → Extender-2 branch, with all 20 clients and six topology nodes
healthy and the client optimizer reporting a complete, converged fleet.

This recovery does not claim to fix weak-link large-packet delivery or to prove
throughput optimality. No permanent RF boost, rate mask or artificial parent
is left behind. For future transport maintenance, update extenders one at a
time and verify complete inventory and large-packet delivery before proceeding
to the next node; a successful small ping is not a sufficient readiness gate.

The final restored-room check collected 71 three-way parent snapshots over
399 seconds (20:42:25–20:49:04 UTC), with no Extender-1 parent mismatch. A
separate read-only audit verifies all four kernel parents and all 60 directed
mesh RF overrides against the room. One candidate snapshot briefly became
incomplete around 20:48:15–20:48:37 and recovered automatically; this is not a
claim of uninterrupted measurement availability. Final inventory and client
convergence checks pass.

Evidence, regression logs, passive packet captures, deployment scripts and
timestamped polling are retained under
`/home/rev/work/backhaul-parent-stability-0906` on the working host and rev140.
The existing 0906 thin archives are not rebuilt by this overlay. rev120/prplMesh
and rev150 runtime are unchanged; only the RDK canonical source/build includes
this transport correction for future builds.
