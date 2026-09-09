# Room coordination qualification, 0908

This records the five-part follow-up to the
[0907 streaming audit](room-streaming-coordination-0907.md): failure attribution,
cross-boundary tracing, bounded evidence and HTTP handling, explicit profiling
authority, and a new catalog qualification with fullscreen recordings.

Scope: the RDK candidate VM `rdkeasymesh-20-0907` on **rev140 only**. Room,
topology and medium ports are **48891, 48889 and 48890**, respectively. The
published 18889/18891 services, rev150 and prpl/rev120 runtimes are unchanged.
Native BPI controller and agent executables are not modified. This is not a
new thin release, and existing tar files do not contain these changes.

**Qualification is not all green.** All 14 scenarios completed, but only 12
had the exact final native roster and none met the strict final fresh-fleet
convergence condition. The fixes and tracing are useful profiler improvements,
not certification of instantaneous native optimization or a zero-overhead lab.

## What changed

### Immediate, truthful presentation

The topology already updated its ownership data promptly, but hid the actual
client icon, name and signal meter for 1,250 ms before a 250 ms reveal. A second
moving icon disguised that presentation delay. Patch 0171 removes the hidden
interval and duplicate moving icon; the current owner is visible immediately.
The pulse/trail highlight remains. The fixed-node force simulation no longer
runs continuously while idle; dragging updates the fixed coordinates directly.

The browser audit now checks **visibility**, opacity, nonzero bounds and
on-screen position as well as data ownership. It records response arrival,
DOM submission and the following animation frame. A changed DOM alone is not
evidence that a user could see the new client position. These are browser
submission measurements, not measurements of physical monitor scanout.

### Bounded asynchronous evidence

Interactive event storage uses a single asynchronous writer, a 16 MiB queue,
eight 64 MiB journal segments and a 4,096-event/16 MiB in-memory history.
The maximum journal payload retained per run is 512 MiB, plus small metadata.
The queue bound includes the record currently being written. Rotation preserves
sequence numbers and hash anchors in an atomically replaced
`journal-index.json`.

Overflow, a short write or disk failure makes qualification incomplete; the
error is sticky and the system does not silently present a complete recording.
Control execution does not wait for a slow journal. The history endpoint and
`/api/demo/storage` expose truncation and writer status. An expired SSE cursor
receives a reset event and the viewer resynchronizes from current state. Full
replay refuses a journal whose beginning has expired rather than replaying a
tail as a complete experiment. Shutdown flushes within a bounded deadline.

These bounds are **per run**, not a garbage collector for old run directories.
Archive/remove completed runs according to available disk space. Explicit user
recordings and movement-command histories are separate data structures; this
change is not a claim of bounded memory for arbitrarily many user commands.

### Slow peers cannot hold native ownership

Patch 0170 reads a request body before acquiring native C command/tree ownership
and buffers a bounded response before writing it to the peer. Request bodies
are limited to 1 MiB, responses to 8 MiB, and peer I/O to five seconds. Headers
are bounded too. WebSocket upgrades and the candidate/steering routes retain
their existing dedicated handling. Native C ownership remains serialized:
removing that lock without a safe native result-ownership interface would
introduce races, not improve profiling.

The room HTTP server separately limits connections to 64 and SSE streams to
16, leaving capacity for control/status requests. Slow I/O times out and
capacity exhaustion is explicit. Idle SSE waits do not hold the event-store
lock. Healthy native reads remain cached for only the existing 100 ms interval.

### World application and partial rosters

World loading previously disconnected each unavailable client sequentially.
It now disconnects in a bounded four-worker group, applies and verifies one
atomic RF generation, then reconnects the present clients in a bounded group.
Existing transaction rollback and recovery are retained. The world-commit
event reports disconnect, medium/readback, reconnect and total times.

Profiling no longer freezes all healthy clients merely because another
expected client is missing from the native roster. Each available client still
needs fresh measurements and valid target/mesh prerequisites. The expected
roster is never reduced to make a test pass; missing or unexpected MACs remain
visible, and the whole room cannot claim convergence while membership or
measurements are incomplete. Non-profiling policy retains the strict complete
roster gate.

## Select the policy authority deliberately

| Invocation | Client decisions | Candidate requests | Backhaul RF |
| --- | --- | --- | --- |
| `interactive --mode act --yes-act --profiling` | External room threshold policy requests unassisted native BTM | External native candidate queries | Startup mesh RF protected |
| `interactive --mode stimulus --profiling` | No external client steering | No external candidate collection | Startup mesh RF protected |
| `interactive --mode stimulus --profiling --model-backhaul` | No external client steering | No external candidate collection | AP-to-AP RF follows the room |

All modes retain serving-state observation and the selected traffic probe.
"Native observation" therefore does not mean zero observation traffic. It also
does not assert that a native autonomous optimizer exists: a station may roam
on its own, respond to the stack, or stay where it is. The viewer labels the
authority in normal and fullscreen views; the journal records `lab.profiling`.

`--model-backhaul` is rejected outside stimulus profiling. It deliberately
removes the startup AP-to-AP RF protection but does **not** introduce an external
backhaul parent selector. A physically weak link may disconnect an extender;
that is not repaired by silently restoring a star. The default client
profiling mode is still a fixed-backhaul experiment, not a test of autonomous
backhaul topology optimization.

For temporary mode changes, stop the room service, change its systemd
`ExecStart` override, run `systemctl daemon-reload`, then start it again. Do not
run two room conductors against the same medium. Stop restores owned RF and
client-presence state. Keep all 20 client containers and six native mesh nodes
running; rooms make unused client roles unavailable without resizing the VM.

## Capture a cross-boundary trace

Run inside the LXD VM as root, using a **new** output directory:

```sh
repo=/home/easymesh/git/meta-cmf-bananapi-vcpe
evidence=/home/easymesh/easymesh-evidence
systemd-run --unit=easymesh-coordination-trace \
  --property=KillMode=mixed --property=MemoryMax=768M \
  --setenv=PYTHONPATH="$repo/gen/demo" \
  /usr/bin/python3 -m room_demo.trace \
  --output "$evidence/my-trace" --duration 600 --raw-monitor
```

The tracer opens one persistent read-only `wpa_cli` control attachment per
running WLAN client. It records events and five-second status heartbeats; it
does not issue reconnect, roam or disconnection commands. It also captures
IEEE 1905 traffic in the controller's network namespace. Optional raw capture
uses `hwsim0`, excludes beacon/probe chatter and restores its prior link state.
Client text buffers, journal queues and packet-capture rings are bounded.
Packet-capture limits are eight 16 MB files per capture, with kernel-drop
counters collected at shutdown. A potentially wrapped capture is unqualified.

Stop the **main tracer process first** so it can close children and collect
their counters; do not kill its whole cgroup simultaneously:

```sh
systemctl kill --kill-whom=main --signal=SIGTERM easymesh-coordination-trace
systemctl status easymesh-coordination-trace
cat /home/easymesh/easymesh-evidence/my-trace/trace-summary.json
```

Require `complete: true`, all client streams, no packet-capture kernel drops,
complete capture histories and a complete journal. `KillMode=mixed` permits
normal service stop to give the main process cleanup time. An interrupted
capture with incomplete shutdown is retained for diagnosis, not counted as a
qualified experiment.

Copy both the completed room-run directory and trace directory to a machine
with `tshark` and the source checkout:

```sh
PYTHONPATH=gen/demo python3 -m room_demo.trace_report \
  --room /path/to/completed-room-run \
  --trace /path/to/my-trace \
  --output /path/to/trace-report.json
```

The decoder verifies every journal hash/sequence, then correlates external
request, native IEEE 1905 command, BTM request/response, client connection
event and native room readback. Matching is bounded by 40 seconds, the next
request for that station, a world change and capture end. Censored actions are
reported separately. `--allow-incomplete` is diagnostic only and never turns an
incomplete trace into qualified evidence.

### Important clock and packet limits

- Client events carry **collector receipt** timestamps, not supplicant source
  timestamps. Native captures and room events use the same VM wall clock.
- Browser-to-VM delay needs a clock-offset check. Browser receive-to-frame
  measurements use one monotonic browser clock and need no cross-host offset.
- Raw `hwsim0` capture is **transmitter-side evidence**, not proof that the
  receiving station/AP received a frame. Upstream Linux v7.0 invokes the
  monitor path before handing TX to the external medium. See the primary
  [mac80211_hwsim source](https://raw.githubusercontent.com/torvalds/linux/v7.0/drivers/net/wireless/virtual/mac80211_hwsim.c).
  The installed Ubuntu kernel is a downstream build, not that exact source tag.
- Protected management frames, notably on 6 GHz, cannot be decoded as clear
  BTM without the appropriate keys. A protected action is not a missing BTM.
- A client BTM rejection is not a renderer delay. Conversely, an accepted BTM
  followed by unanswered authentication cannot be blamed solely on the
  controller: AP, medium, kernel and client evidence must be separated.
- Do not enable `hwsim0` on older/unqualified daemons merely because this
  candidate passed. The [packet-capture warning](packet-capture.md) still
  applies to other runtime/kernel combinations.

## Measurement results and evidence

Evidence staging is `/home/rev/work/coordination-completion-0908` locally and
on rev140. The definitive catalog is `catalog-v15`; the first two interrupted
runs are explicitly preliminary. Qualification results, mode tests and video
metadata are recorded beside the raw journals rather than replacing failures
with a summary-only success claim.

The slow-peer test opens eight incomplete native HTTP requests while issuing
60 ordinary client reads. All reads return HTTP 200; 40 finish before the slow
bodies time out. Median read latency is **21.641 ms**, p95 **52.324 ms**, maximum
**64.375 ms**. All eight unfinished bodies time out. Separate race tests cover
a real TCP reader that stops consuming an 8 MiB response. A real WebSocket
connection receives three pongs over 18 seconds, beyond the new five-second
ordinary HTTP I/O deadline.

A reduced-limit retention soak writes 60,000 events/273,248,389 bytes in
9.675 seconds, retaining 4,053,950 bytes under a four-by-1-MiB test bound.
The queue drains completely and truncation is explicit. Its repeated padding
payload is not a realistic production heap benchmark; the live catalog RSS
measurements are the production-sized resource check.

Automated source validation: **374 Python tests pass, one skips**, plus
43 subtests; **22 JavaScript test programs pass**. Native HTTP/coordination
helper tests pass with Go's race detector over 20 repetitions. The skipped
Python test requires an explicitly supplied daemon test binary.

### Full catalog, V15

The final sweep runs from **17:43:28 to 18:22:15 UTC on 2026-09-08**, with
normal 1× playback, 45-second initial/final settling windows and 30-second
checkpoint waits. Default-world restoration follows the measurement window.
All 14 Play sequences finish. A timeout is a recorded result, not grounds for
discarding a room or silently forcing its clients onto the expected APs.

"Checked" means fresh complete AP comparisons for a client, not merely a
serving RSSI sample. Native counts below come from the independently fetched
topology, including stale extras. Zero known stronger candidates is **not**
optimality when candidate coverage is incomplete.

| Room | Expected / native final clients | Checked / evaluated | Final qualification finding |
| --- | --- | --- | --- |
| `home-a-asymmetric-link` | 11 / 11 | 10 / 11 | Pending client; incomplete comparisons |
| `home-a-band-walk-small` | 10 / 10 | 1 / 10 | Pending actions, missing current/candidate readings |
| `home-a-border-hover` | 12 / 12 | 2 / 12 | Incomplete comparisons; one fresh client owner ahead of native readback |
| `home-a-disappear-reappear` | 12 / 12 | 1 / 12 | Membership restored; insufficient fresh comparisons |
| `home-a-extender-loss-recovery` | 10 / 10 | 9 / 10 | Recovery complete; one steering-failure hold |
| `home-a-fast-transit` | 12 / 12 | 9 / 12 | Pending steer and incomplete comparisons |
| `home-a-flash-crowd` | 10 / 11 | 10 / 10 | Offline client remains in native roster; one pending steer |
| `home-a-one-client-handover` | 11 / 11 | 10 / 11 | One client still actionable/pending |
| `home-a-private-client-room-walk` | 20 / 20 | 19 / 20 | Membership correct; one pending client |
| `home-a-slow-walk-ten` | 20 / 20 | 5 / 20 | Incomplete comparisons and post-steer hold |
| `home-a-stationary` | 10 / 10 | 9 / 10 | One pending client |
| `home-b-slow-walk-ten` | 20 / 20 | 12 / 20 | Missing current/candidate readings; pending client |
| `large-room-extender-evacuation` | 12 / 14 | 0 / 12 | Two offline native extras and missing fresh readings |
| `large-room-perimeter-counter-roam` | 12 / 12 | 9 / 12 | Missing current reading/incomplete comparisons |

The catalog has **129 accepted dispatches**, **100 association-and-traffic
verifications**, 20 verification timeouts and nine verifications discarded at
world changes. Independent client events and native target ownership agree on
100 catalog actions. Clear BTM response evidence identifies 21 client
rejections. Six actions have protected payloads; this is a decoding limitation,
not six proven delivery failures. Censored windows and the remaining unmatched
requests are preserved individually in `v15-trace-report.json`.

Candidate collection completes 228 successful rounds; 589 rounds encounter
native busy responses, 41 time out and 16 are superseded by environment changes.
Two actual action batches proceed while another expected client is missing,
proving removal of the profiling-only global missing-client barrier without
pretending the whole roster is complete.

### Measured boundaries

Catalog-window figures are milliseconds. Populations differ by the available
matching evidence; medians from separate populations must not be summed as a
synthetic per-action trace. Negative clock-order matches are excluded from
nonnegative latency statistics.

| Boundary | Samples | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Playback RF application/readback | 618 | 24.725 | 107.401 | 756.275 |
| Whole world application | 14 | 169.599 | 834.875 | 834.875 |
| Candidate publication to decision consumption | 1,076 | 114.497 | 201.193 | 722.088 |
| Successful native candidate round service | 228 | 5,825.117 | 13,694.386 | 22,108.834 |
| External dispatch request to HTTP result | 129 | 70.391 | 126.331 | 213.250 |
| HTTP overhead beyond the local helper | 129 | 1.705 | 5.835 | 13.827 |
| External request to native steering CMDU | 126 | 1,215.603 | 7,793.277 | 23,730.903 |
| Clear BTM request to client connection receipt | 97 | 48.879 | 68.736 | 111.374 |
| Client connection receipt to native association CMDU | 98 | 1,894.886 | 3,711.194 | 15,876.764 |
| Association CMDU to room native-owner readback | 97 | 331.024 | 592.701 | 647.865 |
| Room event received to scene submission | 9,250 | 11.100 | 20.600 | 192.200 |
| Topology response received to checked DOM submission | 9,306 | 3.800 | 108.500 | 185.600 |

The approximately 331 ms association-CMDU-to-room interval includes native
model/API availability, CLI caching and observer collection; it is **not all
native controller time**. Likewise RF application, external-policy scheduling,
HTTP handling and browser work remain nonzero. Most of the measured handover
chain's seconds occur before command transmission and before native association
reporting; the client handover itself is commonly around 49 ms.

The browser remains fullscreen in both independent foreground windows:
**132,231 client-label checks, zero invisible labels, zero ownership mismatches
and no JavaScript errors**. The next-frame measurements are slower than DOM
submission: room median/p95 25.2/33.8 ms; topology 62.2/236.6 ms. The removed
1.25-second hidden-marker interval must not be confused with those real frame
costs. Room event-to-browser receipt is 4.419 ms median before clock correction;
guest-minus-browser-host midpoint offsets are +3.309 ms initially and +2.675 ms
at the end, bounded by best round trips below 0.93 ms.

The 52,661-event room journal validates completely across its segments. During
the catalog the room process RSS grows from 100.3 MiB to 152.5 MiB, with a
152.6 MiB maximum, rather than retaining every event indefinitely. The tracer
process stays around 19.2 MiB. These are process RSS figures, not the memory
sum of all LXC/tcpdump children or a proof of an indefinitely flat heap.

### Protocol and medium findings

The qualified trace lasts 2,416.9 seconds, including restoration, with 20 client
control streams, 22,538 CMDU packets, 1,542 raw management packets and **zero
kernel capture drops**. Both capture histories and journals are complete.
Full-trace totals include three restoration actions outside the catalog window.

Two useful concrete failure boundaries are:

1. At **17:47:00.453 UTC**, client `02:00:00:00:0e:00` receives a successful
   local native-command result, but no matching steering CMDU, clear/protected
   BTM or target connection is captured in 40 seconds. Client status remains
   on the requested source BSSID. This isolates an accepted-command-to-wire
   gap; it does not prove a renderer or wmediumd delivery failure.
2. At **18:16:43.770 UTC**, client `02:00:00:00:0d:00` accepts BTM toward
   `02:00:00:16:e8:29`. Three authentication requests toward that AP appear at
   43.815, 43.917 and 44.029, with no captured target authentication response.
   The client then authenticates/associates with `02:00:00:97:6a:c8` instead.
   This is a post-BTM authentication/delivery boundary, not UI latency. Without
   receiving-AP evidence it cannot be assigned exclusively to AP software,
   kernel delivery or the medium.

The medium instance and daemon PID remain unchanged. Interval counters show
910,242 frames, 7,625,584 injection attempts, 3,872 tracked-clone `EINVAL`
rejections, **zero new other netlink errors** and zero new no-receiver drops.
The observer's pre-existing gap flag remains set. Of 1,850 positively captured
rejection events, 1,795 align with a client reporting a non-connected state;
55 align with a connected client at the same or an unknown frequency. These
status samples can be up to ten seconds old and do not prove current scanning
context. The 197,794 ring overwrites and incomplete sampled rejection history
prevent a gap-free delivery claim; none are hidden or relabeled as repaired.

### Final reporting correction, V16

The full catalog exposed a remaining display bug: policy correctly filtered
unavailable clients out of steering candidates, but fleet reporting reused
that filtered roster and could overlook a native phantom/offline entry. The
final correction preserves the **unfiltered native MAC set** solely for fleet
qualification and labels unexpected/offline entries in the viewer. Candidate
selection, policy decisions and RF execution do not change.

The corrected roster predicate is replay-checked against **2,224 captured
snapshots from all 14 rooms**, with focused Python/JavaScript regressions and
live checks during the final recordings. This is a reporting replay, not a
second claim of replaying the RF experiment. The 38-minute V15 timing audit
predates this final reporting-only change; its independent exact-roster check
already rejected the two problematic rooms, so no catalog pass is downgraded
or invented by the correction.

The live V16 monitor checks 157 samples, including three with missing clients
and five with unexpected/offline native entries. Every such sample keeps
roster, measurement and convergence qualification false; no monitor errors
occur. These reporting checks do not block other available clients' actions.

### Native-observation mode checks

Both stimulus modes pass live tests with all 20 client trace attachments,
complete journals/captures, no external optimizer evaluations, **zero external
candidate collections and zero client steering actions**. Normal and fullscreen
labels agree and the browser reports no errors. Fixed startup backhaul retains
all 60 directed frequency-qualified AP-to-AP values throughout the handover
scenario. Modeled backhaul produces nine distinct AP-to-AP matrices during
moving-extender playback, without an external parent selector.

The RF comparison waits for the medium observer to publish the room's committed
daemon generation and complete AP identities. Comparing an old cached observer
snapshot immediately after service restart produced a preliminary test failure;
that attempt is retained and is not counted as qualification. Control-path
readback and the observer's independently published snapshot are not the same
timestamp. The definitive mode evidence is `fixed-v2` and `modeled-v2`.

### New fullscreen side-by-side recordings

Both views remain in their native fullscreen mode for every captured frame
pair, with the external-policy/unassisted/fixed-backhaul label visible. Videos
show complete normal-speed playback, checkpoint waits and the subsequent
settling period; no handover is accelerated or spliced into an earlier time.

| Recording, available locally and on rev140 | Duration | Result |
| --- | --- | --- |
| `/home/rev/Videos/easymesh-coordination-evacuation-0908.mp4` | about 1:54.5 | All eight selected cluster clients start on the moving extender; all eight finish away from it |
| `/home/rev/Videos/easymesh-coordination-perimeter-0908.mp4` | about 2:04.4 | Both walkers complete the full route, including the 14/28/42-second checkpoints |

The files are H.264, 2560×900, with two independent 1280×900 browser views.
476 and 555 concurrent screenshot pairs are timestamped and composed at their
actual wall-clock durations. Capture achieved about four pairs/second rather
than its eight-pair target; the 15 fps encoded output repeats frames as needed.
**Use protocol timestamps, not the video frame rate, for millisecond latency.**
Both complete videos decode successfully, and beginning/mid-scenario frames
are visually inspected. Metadata, hashes, fullscreen assertions and per-frame
timestamps are in `videos-report.json`, `video-inspection.json` and each
recording directory's `report.json`.

The bundled audit Chromium advertises no H.264 decoder, so browser playback
cannot be qualified in that build; this is recorded explicitly rather than
reported as a passing browser test. Both files pass full FFmpeg decoding.
Open the MP4s in an H.264-capable browser or media player.

SHA256:

```text
f0a3ab1af0b2c2c48280428b20ad8ed27445030913cce69044efa13a868d793b  easymesh-coordination-evacuation-0908.mp4
36143be80cd1d85eb13110ce2b79098a3bf0088f73950af6812f70b1c6538984  easymesh-coordination-perimeter-0908.mp4
```

### Interpretation

The lab must not promise instantaneous convergence or blame every remaining
second on the native optimizer. External policy, native command admission,
metric service, Wi-Fi client behavior, simulated RF, kernel delivery and
presentation are distinct stages. The new tracer makes several boundaries
measurable without replacing native results with simulated truth.

The wmediumd observer's history-gap flag is sticky from observer startup.
Ring overwrites alone are not proof of a newly missed event, and clearing the
flag by restarting an observer does not repair history. HTTP snapshot sampling
is not a lossless rejection-event recorder. Interval counter deltas and
positive rejection samples are retained; a netlink rejection with unknown
endpoints is not assigned to a particular failed client handover. A tracked
clone `EINVAL` indicates a rejected delivery attempt, not proof that it was
harmless. Other netlink errors include failures outside that tracked category,
not merely non-`EINVAL` errors.

## Source and operational handoff

The source includes reproducible recipe patches and regression tests; staged
runtime binaries are not silently written over checked-in release artifacts.
Before a new thin release, rebuild the CLI artifact through the normal recipe
or `gen/rebuild-em-cli-artifact.sh`, then package and qualify that release.

The candidate returns to the default 20-client world, paused at zero with no
operator lease, an explicit 100-action budget and VM `boot.autostart=false`.
Its runtime remains **unassisted external-policy client profiling**. Use the
explicit stimulus modes above when studying native/client behavior without
the room optimizer issuing candidate or steering requests.
