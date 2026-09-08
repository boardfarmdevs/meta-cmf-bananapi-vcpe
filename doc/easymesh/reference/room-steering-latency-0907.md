# Room steering latency: staged rev140 measurements

This document records the earlier, blocking-highlight iterations. See
[fast interactive steering](room-fast-steering-0907.md) for the subsequent
nonblocking-highlight, reduced-timer and multi-mover collection work.

## Scope and method

This work changes the room/optimizer host-side Python code, not the BPI
EasyMesh agents, controller binaries, or immutable 0907 thin archives.
Only rev140's isolated `rdkeasymesh-20-0907` candidate is deployed/tested:
native topology port 48889, interactive room port 48891. Published rev140
ports 18889/18891 and the other hosts' runtimes are untouched.

The benchmark loads `large-room-extender-evacuation`, waits for eight exact
stationary client identities to associate with Extender-4, then waits another
35 seconds so recently associated cluster clients clear the normal dwell and
cooldown gates. Play runs the same 20-second scenario: only that extender moves
from (8,8) to (36,32). No client placement, SSID, presence, or association is
scripted during the measured movement. The twelve-client native roster is
checked before and after. Timing starts at the server's playback-completed
event, not browser animation or polling receipt time. First/all-eight timings
come from successful association-and-traffic verification events.

Two repetitions are intended per stage. The default twenty-client room is
restored paused with no control lease between stages. Only the room service
is restarted to load each code version; BPI/native services are not restarted.
The existing three-second per-client topology highlight remains enabled and
is checked in every submitted action's command output.

Evidence and the benchmark scripts are stored under
`/home/rev/work/steering-latency-0907` on rev150 and copied to rev140.
Each overlay tarball freezes that iteration's deployed source. `deploy.py`
packages the current working tree; its phase label is not a historical-version
selector. Use the saved overlays/evidence when comparing historical stages.
These small-sample live-lab timings are not general Wi-Fi performance claims.
Successful cluster evacuation is not a full-fleet convergence qualification.
The hwsim steering transaction temporarily assists the nominated client's RF;
clients can reassociate during scan-cache refresh before a BTM is needed.

## Stage 1: bounded steering batches and independent backhaul settling

The interactive action batch grows from three to eight. Selection still ranks
weak links and gain, honors the action budget, and sends/verifies each action
serially. RF transactions must not overlap: each temporarily changes the
medium and verifies exact restoration before the next one. This allows an
affected group to use one observation rather than automatically repeating a
whole-fleet collection after every three clients. Original serving and target
metric timestamps are rechecked before every dispatch; expired evidence stops
the batch and requires another collection. World edits and failed requests or
verification also abort the remaining actions.

Backhaul now has its own epoch and settling clock. World changes, AP RF changes,
and actual parent-switch transactions invalidate it. Client-only movement and
temporary client steering assistance still invalidate the appropriate client
measurement state, but no longer restart ten seconds of backhaul settling.
A newly changed backhaul epoch is evaluated after settling without waiting for
an old periodic poll deadline. Failure/recovery backoffs remain enforced.

## Stage 2: collect useful fresh candidates first

For up to 120 seconds after an RF environment change, new collection rounds
prioritize the moved station, or clients actually associated with the moved
AP. This uses controller association identities, not geometric predictions of
the winning AP. If there are no eligible priority clients, or that window
expires, collection returns to all eligible clients. World loads without a
single changed role use the normal fleet collection immediately.

Clients whose policy is pending, cooling down, or in failure backoff do not
trigger candidate queries they cannot use. Their actual associations are still
observed, allowing pending success/failure and timer expiry to advance normally.
Every selected client still requires a complete fresh candidate response from
all of its eligible same-band APs. A holding client obtains another real
measurement; no RF sample cache or fabricated receipt timestamp is introduced.
The optimizer and query-progress payloads report selected, priority, and
deferred counts, and deferred clients do not count as fully measured fleet
convergence. Ordinary noninteractive experiment collection is unchanged.

The native CLI/HTTP command path remains serialized, and each agent's eight-STA
response-table limit remains enforced. This reduces redundant collection work
instead of adding competing native polling handlers or more background workers.

## Results

Seconds after the server reports the twenty-second playback complete:

| Stage | First client, runs 1 / 2 | All eight, runs 1 / 2 | Mean first / all eight |
| --- | --- | --- | --- |
| Baseline, batches of three | 34.273 / 93.515 | 171.558 / 217.654 | 63.894 / 194.606 |
| Stage 1, batches up to eight and separate settling | 88.631 / 53.599 | 196.382 / 129.035 | 71.115 / 162.709 |
| Stage 2 initial, sixty-second collection priority | 33.308 / 33.983 | 121.388 / 175.023 | 33.646 / 148.206 |
| Stage 2 final, 120-second collection priority | 28.437 / 40.006 | 84.618 / 102.103 | 34.222 / 93.361 |

Baseline had three and four transient passive network-observer timeouts,
respectively. All eight action verifications succeeded in each run; there
were no candidate-measurement-unavailable events in the measured intervals.
Collection/observation rounds ranged from 7.94 to 43.88 seconds. This variation
is part of the result, not discarded as an outlier. Keep the raw verification
timeline and any timeouts alongside summary numbers, and never describe
cached samples as new RF data.

Stage 1 reduces mean all-eight time by 16.4%, but does not improve mean first
handover. The first repetition alone showed no clear gain. Slow observations
used up much of the sixty-second freshness allowance: the guard stopped two
batches in run 1 and one in run 2 rather than dispatching stale decisions.
The actual groups were 2+4+2 and 5+3 despite a configured maximum of eight.
Passive network-observer timeouts numbered four and one in the measured
intervals. All sixteen cluster verifications succeeded. The second repetition's
unmeasured preparation also encountered temporary incomplete native telemetry
and unavailable candidate responses, which recovered before the initial-state
gate passed. The native controller and WebUI processes remained running; they
were not manually restarted. These limitations are retained in the evidence.

The initial collection iteration cuts the affected-client rounds from sixteen
queries to four. Mean first handover improves markedly, but both runs finish
only seven clients before the batch freshness guard forces another collection.
The sixty-second priority cap has expired by then, so the remaining client
waits behind an unrelated full-fleet collection. The second run additionally
encounters a candidate HTTP 504 and retry backoff. Its slower result is retained,
not excluded. Both still complete all eight verified handovers, averaging
148.206 seconds (23.8% below baseline, 8.9% below stage 1).

The final collection iteration extends the bounded priority window to 120
seconds to cover the preserved per-client highlight/scan/verification work.
No freshness deadline, gain/hold/dwell gate, or safety check is relaxed. The
normal full-fleet fallback still occurs immediately when no eligible client
remains in the affected group, even before the time cap.

### Final measured outcome

- Mean all-eight verification time falls from 194.606 to 93.361 seconds:
  **52.0% below baseline**, and **42.6% below stage 1**.
- Mean first verification falls from 63.894 to 34.222 seconds: **46.4% below
  baseline**. These times exclude the preceding twenty-second movement.
- Final targeted collection rounds use four actual candidate transactions.
  Measured totals are 12 and 24 transactions, versus baseline 44 and 76:
  **70% fewer transactions on average**. No candidate sample is cached.
- Unnecessary backhaul-wait events between the first requested action and last
  verification fall from eight per baseline run to zero in both stage-1 runs.
- The final iteration's first run has one passive network-observer timeout;
  the second has one safe batch interruption for expired evidence. Both finish
  as seven clients followed by one, with a targeted fresh final collection.
  Neither measured final run has a candidate-measurement-unavailable event or
  a failed association/traffic verification.

All 64 timed client verifications across the eight trials succeed. Exact
identities, SSIDs and bands are preserved; only the extender changes position.
All initial/final native checkpoints have twelve unique clients and six nodes.
The default twenty-client room is restored after every stage. The final code
passes 281 Python tests with one skipped test and 39 passing subtests.

The small sample size and variable native control-path load limit statistical
claims: these are observed demo improvements, not a roaming latency guarantee.
Full-fleet collection still has a native reliability limitation. In particular,
the final iteration's second *preparation*, before Play, encountered repeated
candidate HTTP 504s and retry backoff before recovering and passing the initial
state gate. This interval is saved as `preparation-outage-events.jsonl`, not
hidden as a discarded measured run. The changes do not fix every native
reporting failure or qualify the immutable thin archive for promotion.
