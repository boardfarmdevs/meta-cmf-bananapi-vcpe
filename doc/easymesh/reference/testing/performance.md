# Performance and failure attribution

[Testing reference](README.md)

A deployment measurement is not automatically a native-stack benchmark.
Measure these intervals separately, retaining epochs, request/action IDs,
clock resolution and failures:

1. World intent → committed RF/readback.
2. Native candidate request → complete fresh measurement.
3. Eligible decision → native submission acceptance.
4. Request → physical association / controller ownership / verified traffic.
5. Published state → browser receipt → rendered observation.

Do not sum overlapping collection timings or treat an accepted BTM as completed
roaming. Prpl candidate timestamps have a whole-second freshness boundary;
RDK candidate requests can be refused/busy or time out. Keep those delays
visible instead of returning stale data. Use request-only/unassisted actuation
when profiling native behavior, not a deterministic RF-assisted demonstration.

## Tools and evidence

The repository's `gen/tests/room-feature-acceptance.js` records browser/API
samples and selected SSE; its report helper aggregates action/collection
timings. The [room test plan](room-acceptance.md) owns invocation and gates.
`gen/tests/room-feature-host-monitor.py` samples physical-host load separately.

During a separately controlled moving-room test, run the read-only
`tests/controller-render-latency.js --url TOPOLOGY_URL --seconds 90 --output NEW_DIR`
from the directory containing `tests/` (RDK: `gen/`). It uses the same Playwright
environment variables as room acceptance. It measures a decoded controller
response to the changed SVG-bound association identity across two animation frames,
including removals; it does not measure native commit time, polling wait or
paint timing or animation completion. Zero transitions are insufficient evidence. Timeouts,
superseded transitions and pending observations remain in the report.

For deeper attribution, `gen/demo/room-demo` and the `room_demo.trace`
module provide room evidence and passive client/1905 capture; inspect their
`--help` before starting. [Packet capture](../observability/packet-capture.md)
must remain observation, not reconnect/roam commands. Retain drop, truncation
and overflow counters; a wrapped/incomplete trace cannot prove event absence.

Prefer a separate observer machine or hardware-accelerated browser. If sharing
a lab host, bound only the owned test browser's CPU load and disclose it.
Record host CPU, available memory, pressure, temperature and throttle counters.
Do not change native CPU allocation, metrics intervals or RF policy halfway
through a comparison. A low average CPU does not exclude thermal throttling.

Infrastructure Grafana panels use coarse scraping and are not substitutes for
correlated native traces. Keep PSS/RSS, guest memory and container cgroup memory
separate; they answer different questions. Retain raw measurements beside the
run, not as JSON/log dumps in the active manuals.

## Acceptance

Report successful distributions **and** censored failures, incomplete
measurements, sample gaps, unsupported timestamp fields and restoration status.
Test medium/radio behavior independently before blaming renderer delays.
Do not extrapolate a bounded run into claims of zero external overhead,
real-world propagation fidelity or long-term stability.

## 0913 bounded qualification

The RDK run on 2026-09-14 tests source `5d954ad` with rebuilt controller and
extender images, eight VM CPUs, 16 GiB RAM and the fixed 100-client pool.
All 18 rooms pass the unchanged 60/45/90-second gates, native ownership audits
and topology checks. Native identities remain unchanged during the run;
host sampling is complete and there are no event gaps. All 144 submitted
actions verify with traffic: request-to-verification p50/p95/max is
1.768/4.232/6.285 seconds. Fourteen superseded collections correspond to changed
contexts; no candidate-unavailable collections or native response timeouts occur.
The 50-client room settles initially in 32.124 seconds and finally in 19.774
seconds, including the five-second stable requirement.

Separate provider diagnostics show why layered attribution matters:

- Two deliberate native 2.4 GHz scans each produce one response per private
  BSSID on all five APs, rather than three. The capture has zero drops. This
  measures transmitted response multiplicity, not successful delivery latency.
- Four two-client 2.4 GHz moves in a 50-client world settle in 24.931–27.061
  seconds, versus 26.001–43.841 previously. Removing pre-drag candidate reuse
  eliminates five unnecessary Agent-1 detours: eight verified roams instead of
  thirteen. These bounded before/after observations do not isolate native stack
  speed or establish a statistical performance guarantee.
- A separate uploaded world simultaneously enables forty clients and relocates
  two 2.4 GHz clients at its six-second mark. The 10-to-50-client burst settles
  in 24.997 seconds; both affected clients verify on their intended extender
  in about two seconds after submission. Only explicit band capabilities and
  normal room Play are used, with no BSSID pinning or native restarts.

Detailed evidence is retained on the observer under
`/home/rev/work/release-0913/evidence/rdk-management-routing/legacy-mlo/`:
`catalog/` contains the full suite and default restoration; `probe-check.*`
and `fifty-diagnostic/` contain the separate diagnostics; `burst-24/` records
the join-burst case. Earlier failures
remain in sibling directories. This catalog qualifies room behavior; artifact
acceptance is a separate check.

The exact `40a9064` thin tar subsequently passes fresh zero-to-105 provisioning,
the full 100-client native/traffic baseline and three imported-room checks:
50-client counter-roam, 5-to-6-GHz band upgrade and stationary ten-client room.
There are no failed verifications, native response timeouts or unavailable
collections in that run. Default-20 restoration also passes. After monitoring
installation, all twenty active clients pass traffic again and the final room
is healthy, converged, paused and unleased. The rebuilt HAL hashes match on all
five APs. Exact bytes and evidence are identified by
`/home/rev/releases/0913/rdk-0913-acceptance.json` and
`evidence/rdk-0913-final/`. The separate VirtualBox artifact has static checks
only; neither a VirtualBox guest boot nor a Windows boot is qualified.
