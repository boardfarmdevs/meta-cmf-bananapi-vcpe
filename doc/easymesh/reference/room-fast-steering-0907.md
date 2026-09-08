# Fast interactive room steering: rev140

Follow-up: [observation and rendering latency audit](room-observation-latency-0907.md)
finds additional external delays after native association verification and
documents the nonblocking observation/rendering overlay. The measurements and
videos in this document describe the preceding steering iteration.

This follow-up removes avoidable lab scheduling delays from the previous
[staged measurements](room-steering-latency-0907.md). It changes the external
Python room optimizer and host steering adapter, not the BPI EasyMesh binaries.
Deployment and live testing are limited to rev140's isolated
`rdkeasymesh-20-0907` candidate: topology 48889 and room 48891. Published
18889/18891, prpl runtimes, other hosts' labs and immutable thin tars are
unchanged. Only the room service restarts when loading the overlay.

## Changes

- Interactive steering still publishes native topology highlights, but sets
  the host adapter's preview wait to zero. Highlighting no longer gates RF or
  BTM work. Ordinary standalone steering keeps its existing preview default.
- Interactive policy has no pre-action condition hold or minimum association
  dwell. A measured 2 dB target advantage replaces the former 0.5 dB margin to
  avoid reacting to tiny fluctuations. Post-success cooldown is five seconds;
  failure backoff starts at five seconds and caps at thirty. Noninteractive
  experiment policy remains unchanged.
- Playing a scenario is no longer itself a reason to suspend the optimizer.
  A native candidate collection must still span an unchanged RF generation.
  Guards before and after each query abandon superseded work; the final
  snapshot and each RF transaction retain their generation/revision checks.
  A changed-world race defers the batch rather than killing the optimizer.
- Normal polling and candidate-outage backoff wake within approximately
  100 ms of a committed RF epoch change. An already-issued native request is
  not cancelled ambiguously; its bounded response must return first.
- All recently moved roles receive candidate priority, including both
  opposite-direction walkers. The previous last-role-only selection could
  leave the other walker waiting behind unrelated collection work. Priority
  is bounded to 120 seconds and is reset on world load. Temporary steering
  assistance does not masquerade as another user-moved role.
- Backhaul evaluation uses two seconds of stable backhaul RF instead of ten.
  Waiting for that evaluation no longer blocks client measurement. Successful
  reparenting is rechecked without a thirty-second post-success poll delay.
  Actual switching remains serialized, with loop/gain checks, exact rollback,
  and conservative failure/recovery backoff.
- Candidate requests have one attempt per interactive round, followed by
  bounded 1/2/4/8-second outage backoff, rather than two attempts followed by
  5/10/20/30 seconds. Superseded RF samples are not reported as native outages.
  After an unavailable transaction, queued queries whose results cannot form a
  complete snapshot are skipped. Already-issued requests retain their bounds.
- A serving metric collected before the latest relevant RF change is refreshed
  before candidate collection, even if it is only a few seconds old. Previously
  it could pass the generic age check, trigger an entire candidate round, and
  then be rejected by the post-movement freshness gate. The existing real
  client traffic/`iw link` fallback supplies the replacement; no timestamps
  are fabricated. Both simultaneously moved clients share this protection.
- Scan-cache refresh coalesces per-BSSID preparation into a same-frequency,
  same-SSID scan followed by directed target discovery. Fresh target identity
  remains mandatory. Graceful BTM acceptance is polled immediately instead of
  sleeping four seconds unconditionally before checking the outcome.
- Per-client outcome verification reads actual native topology once per poll,
  rejects duplicate/missing ownership, and still probes client traffic. It
  no longer fetches unrelated device, BSS and metric inventories for each
  verification. Polling exits immediately on success, at 200 ms granularity.
  Native ownership may lag physical association: its interactive verification
  deadline is forty seconds rather than ten. This extends only the failure
  bound; it does not add a sleep when the target is already visible.
  Cooldown/failure backoff starts at the actual outcome rather than waiting for
  another candidate round to notice it. The verified subject's pending status
  is cleared immediately without claiming whole-fleet convergence.

## Safety and remaining latency

This is not a promise of zero latency outside EasyMesh. RF mutations and
restoration are serial because they share the simulated medium. Association,
scan completion, traffic and native telemetry have real processing time and
bounded retries. A short scan-completion allowance remains. The five-second
post-success anti-flap cooldown and recovery backoffs remain intentional.
No fake measurements, refreshed cache timestamps, forced association API or
parallel native command workers are introduced.

Continuous movement can still invalidate a collection before it completes.
The optimizer now tries valid generations rather than waiting for the Play
flag to clear, but does not act on an obsolete generation merely to make a
demo appear faster. The perimeter world's explicit corner checkpoints remain
part of its scenario; they are resumed after both real handovers are verified.
Native candidate HTTP 504s and passive-observer timeouts are not fixed by this
host-side work. Whole-fleet convergence and archive promotion require separate
qualification.

## Measurement and video method

Evidence is in `/home/rev/work/steering-fastpath-0907` on rev150 and copied to
the same directory on rev140. `benchmark.py` checks actual native BSSID
ownership, twelve unique clients and six nodes at every checkpoint, preserving
client MACs, SSIDs and bands. It restores the default twenty-client room paused
at zero without a lease. `summarize.py` measures from server playback-stop
events to successful association-and-traffic verification events, not from
browser animation. Negative times would mean a verified handover happened
before the checkpoint rather than being clamped to zero.

The evacuation baseline is the preceding final-collection iteration, with two
trials averaging 93.361 seconds for all eight clients after movement completes.
The current-code perimeter baseline is freshly replayed before deployment:
74.316, 174.557, 87.750 and 65.841 seconds for both walkers at successive
corners, averaging 100.616 seconds. All eight baseline verifications succeed.
The baseline's variable native observations and timeouts remain in the journal.

New recordings cover the moving-extender evacuation and both walkers' complete
opposite-direction perimeter laps. They show live room and native topology,
real browser fullscreen transitions and actual associations, without intentional
speed-up. Browser media time is not a precision benchmark. The recording gate
checks the requested clients and fresh serving measurements, not completion of
an unrelated whole-fleet candidate round after the handovers have succeeded.

## Validation and intermediate failures

The final Python validation passes 302 tests and 39 subtests, with one existing
skip. Viewer JavaScript tests, shell syntax and whitespace checks also pass.
Coverage includes observer callback wiring, RF supersession, both moved-client
priorities, serving-measurement boundaries, immediate association polling,
nonblocking highlight configuration and verification-result policy state.

The first fast overlay evacuates all eight clients in 62.689 and 73.973 seconds
(mean 68.331, versus 93.361 seconds immediately before this work). Its perimeter
trial reaches all requested physical associations, but one native ownership
update exceeds the old ten-second verification deadline. That trial is retained
as a failed verification, not averaged as a complete passing lap. The final
overlay uses the forty-second failure deadline described above.

The second deployment exposed a callback-scope error in the passive network
observer. The room service's automatic restart loop was stopped; shutdown
restored the medium. The callback belongs only to the optimizer observer and
was moved there, with regression tests for both constructor paths. The final
`fastpath-v3` overlay starts successfully and is the version used for final
validation. Failed startup logs and intermediate overlays remain in the evidence
directory; they are not counted as completed timing trials. No native BPI
service was restarted to recover this Python wiring error.

The first perimeter recording also fails its strict post-capture inventory
check: native topology has twelve clients, but the initial passive room
inventory temporarily contains eleven. Its preparation gate originally checked
the complete native roster and both movers, not every projected client. The
capture gate now requires matching complete unique rosters in both sources.
The rejected recording and report are preserved under
`videos/perimeter-initial-roster-lag` and
`recorded-perimeter-initial-roster-lag`; they are not the delivered perimeter
MP4. Re-recording does not change the earlier final benchmark results or
silently treat the incomplete inventory as a passing snapshot.

## Final timing results

The final `fastpath-v3` runtime completes all 24 timed association-and-traffic
verifications without a failed verification. Both evacuation repetitions and
all four perimeter checkpoints retain twelve unique native clients, six nodes,
the same client MACs/SSIDs/bands and unchanged non-moving positions. The default
twenty-client room is restored after each benchmark.

| Scenario / endpoint | Immediate baseline | Final overlay | Reduction |
| --- | ---: | ---: | ---: |
| Evacuation: all eight verified, mean of two trials | 93.361 s | 40.934 s | 56.2% |
| Evacuation: first verification, mean of two trials | 34.222 s | 11.140 s | 67.4% |
| Perimeter: both walkers verified, mean of four corners | 100.616 s | 14.657 s | 85.4% |

Final evacuation completion times are 38.857 and 43.010 seconds. Final perimeter
completion times are 11.845, 18.306, 17.780 and 10.698 seconds at room times 14,
28, 42 and 60 seconds respectively. These are small, observed samples, not a
latency guarantee. The timed baseline is the immediately preceding iteration,
not the much slower original implementation.

The first evacuation and first perimeter segment still contain native candidate
HTTP 504s and passive-observer timeouts; later segments in these runs have none.
No trial or outage is discarded. Superseded RF generations are retried safely.
All 24 submitted actions publish nonblocking highlights, and none logs the old
three-second preview wait.

The benchmark and recording harness also require at least six seconds of stable
roster/presence before declaring a checkpoint ready. That test-only acceptance
window is not an optimizer delay and is not included in verification timing.
Passive room inventory/metrics can arrive after the narrower native association
verification, so the displayed completion banner can appear later than the
timed event. The videos intentionally retain that observation lag rather than
cutting it out or synthesizing a faster display.

## Delivered videos

The following files are available at the same paths on rev150 and rev140:

| MP4 | Duration |
| --- | ---: |
| `/home/rev/Videos/easymesh-fast-evacuation-0907.mp4` | 1:40.12 |
| `/home/rev/Videos/easymesh-fast-perimeter-0907.mp4` | 3:20.88 |

Both are 3200×1200 H.264/YUV420p with fast-start metadata, without an audio
track. Full strict decoding passes, and extracted MP4 frames are visually
inspected. Each recording includes six actual browser fullscreen transitions
between room, topology and side-by-side views, with no browser script errors.
The perimeter recording includes the complete lap and all four roaming pauses.

The delivered evacuation's eight handovers verify in 37.377 seconds after the
extender stops. The delivered perimeter's pairs verify in 13.224, 16.300, 16.315
and 11.504 seconds after successive stops (mean 14.336 seconds). These additional
browser-loaded trials are reported separately from the controlled timing table.
All sixteen video handovers pass, bringing the final benchmark plus delivered
video total to forty verified handovers. Both views' initial and settled
inventories contain all twelve scenario clients; default twenty-client presence
is restored afterward.

The room service alone is restarted after testing to clear the temporary action
budget. The final state is the default twenty-client/six-node lab, paused at
zero with no lease. Controller, native CLI and medium process identities remain
unchanged across that restart, and the published room remains untouched. SHA-256
hashes, full-decode results, timing events and final runtime checks are retained
in the evidence directory. Older videos and immutable thin tars are preserved.
