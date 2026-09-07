# Topology fit, wall-visible backhaul and room acceptance

This live overlay targets rev140 only. No native service restart or Yocto build
is needed for its JavaScript/HTML assets. The 0906 thin archives are unchanged.

## Rendering

- Fresh branch graphs no longer pin the native API's cramped coordinates.
  Stars and shallow Agent-1-rooted branches start with a compact centered mesh
  arrangement; true full chains retain their folded hierarchy. This chooses
  drawing positions only: actual parent edges are never rewritten into a star.
- Render and Optimize Layout separate overlapping node groups before fitting.
  The bounded deterministic pass accounts for the complete SSID bubble extent,
  holds Agent-1 fixed, and leaves already separated groups exactly where they
  are. Cached node/client arrangements survive parent changes; optimization
  repairs spacing rather than replacing a user's top/bottom or left/right
  arrangement. Labels are placed again after an optimization correction.
- The native HTML uses a new script cache key so a normal page reload obtains
  the spacing correction. Deployment changes only static assets on rev140;
  the room, RF, containers and native services are not restarted or changed.

- Client and mesh-node names use 22 px text; private/IoT SSID titles use 26 px,
  and other SSID titles use 22 px, before the uniform viewport fit. Client band
  and channel are hover-only, not a second line below each client. Backhaul
  band/channel labels and all API radio details remain unchanged.
- Client names choose nearby clear positions around their icons, avoiding
  other names, icons, signal meters and SSID titles. Placement reruns after
  redraw and completed drags without moving clients or mesh nodes. Slightly
  roomier SSID bubbles and left-offset client link origins reserve space for
  the enlarged quoted SSID titles. Arbitrary manual crowding can still exceed
  the available space; no name is hidden to make a crowded layout appear clear.
- Network topology displays `mesh_backhaul` as `"backhaul"` in dark red. This is
  only a display alias; the real SSID and topology API data are unchanged.
- Fit uses the largest uniform scale that contains the complete SVG bounds,
  including SSID bubbles, clients and text, with a six-pixel limiting margin.
  The old 40-pixel padding and 1.5× enlargement cap are removed. Unequal graph
  and viewport aspect ratios can leave extra space on the other axis; nodes,
  circles and text are not distorted just to fill that space.
- Fit runs on graph render, viewport resize, Optimize Layout, and completed
  node/client drags. Node and client positions remain cached and unchanged by
  fitting. A resize during an active pointer gesture waits until it ends;
  ordinary pan/zoom remains available between automatic fits.
- The room's backhaul stays on the floor. A depth/stencil pass draws only the
  wall-occluded portions 30% lighter. Unobstructed segments keep their red/orange
  upstream-AP color. No x-ray segment appears when walls are hidden, and opaque
  objects in front of the wall are not painted over. Fronthaul-disabled mesh
  nodes retain their actual backhaul lines.

## Spacing acceptance

The September 7 spacing correction is patch
`0163-cli-space-branch-topologies-without-reordering-nodes.patch`. It fixes a
missed render-path case: non-star graphs used the API's tight native positions,
then fixed every node in place, so the configured collision force could not
separate the enlarged groups. Optimize Layout previously only changed zoom.

All six WebUI Node suites pass, including initial branch layout, overlap
repair, an unchanged Agent-1 anchor, preserved extender quadrants, repeated
optimization without drift and unmodified native topology data. Read-only
Chromium checks on the deployed assets cover branch, star, full-chain and
20-clients-on-one-AP views at 1700×1050, 1100×850 and 1900×1100: twelve cases,
with no cross-AP SSID-circle overlaps, name/name overlaps or name/icon/meter
overlaps. All twenty names remain visible, the limiting margin remains six
pixels, and a manually swapped extender arrangement survives a parent change.
These browser fixtures do not load new worlds or change real associations.

The live room's roles, selected world, run ID, RF generation/epoch, playback and
lease are unchanged, as are native/room service PIDs. Final live health is
20 clients and six complete topology nodes. Evidence and screenshots are under
`/home/rev/work/topology-spacing-0906` on the working host and rev140.

## All-room acceptance

Run inside the rev140 LXD VM, starting from the healthy, paused default room
with no active browser lease or recording:

```sh
python3 gen/tests/room-world-switch-smoke.py --yes-act --all-worlds \
  --timeout 600 --output /tmp/all-rooms-report.json
```

This is an explicit live RF test. It applies the initial frame of every room
in `/api/demo/worlds` (currently 11); it does not play each room's whole timeline.
It then tests the default room and client disappearance/reappearance. Each
room must retain the exact requested client MAC roster in the unfiltered native
topology, all six displayed mesh nodes, healthy lab state and a settled actual
backhaul graph. Omitted clients must also be disconnected in their kernel.

“Optimal AP” means no stronger eligible measured AP on the client's existing
SSID/band, not a claim of globally optimal throughput or cross-band migration.
Acceptance requires a complete fresh optimizer evaluation for the current RF
epoch, all online clients checked, no higher same-band candidate RCPI, and
agreement between decision-source BSSIDs and current reported associations.
The conditions must remain true for at least ten seconds. Stale convergence
from a previous room, a matching count with the wrong clients, or an unsettled
parent graph cannot pass.

The test records detailed per-client decisions, AP BSSIDs, signal readings,
counts, timings and action usage. Container/service/medium process identities
must remain unchanged. Finally it restores the default room and any original
mesh/client positions, verifies convergence again, and releases its lease.
Results and browser/deployment evidence are stored in
`/home/rev/work/topology-room-render-0906` on the working host and rev140.

## rev140 results, September 6 PDT / September 7 UTC

All 11 installed rooms passed the complete measured convergence gate:

| Room | Online clients | Convergence seconds |
| --- | ---: | ---: |
| home-a-asymmetric-link | 11 | 48.49 |
| home-a-band-walk-small | 10 | 220.84 |
| home-a-border-hover | 12 | 220.80 |
| home-a-disappear-reappear | 12 | 120.11 |
| home-a-extender-loss-recovery | 10 | 76.26 |
| home-a-fast-transit | 12 | 61.42 |
| home-a-flash-crowd | 10 | 86.14 |
| home-a-private-client-room-walk | 20 | 74.06 |
| home-a-slow-walk-ten | 20 | 140.89 |
| home-a-stationary | 10 | 69.22 |
| home-b-slow-walk-ten | 20 | 449.19 |

Home A settled to a star. The shifted Home B settled to a multihop graph:
Extender-1 uses Extender-2 as its parent; the other extenders use Agent-1.
Home B's longer delay included missing association-age telemetry for `iot-10`
(`sta_mobile_02`), which temporarily blocked its minimum-dwell/candidate check.
The native report recovered without a service restart or manual reassociation;
acceptance waited for all 20 clients to be measured rather than treating the
incomplete 19-client candidate snapshot as converged.

That acceptance established a real branch, not long-term stability of every
periodic parent report. A later user-observed apparent parent oscillation was
traced to the IEEE1905 transport dropping live Wi-Fi membership; the kernel
association remained on Extender-2. See the
[backhaul reporting correction](backhaul-parent-reporting-0906.md) for the fix
and the longer, kernel/controller/room comparison.

The subsequent default-room transition passed in 318.78 seconds. Client
disappearance (19 online) passed in 52.65 seconds and reappearance (20 online)
in 74.71 seconds. Final default restoration passed in 47.96 seconds, with the
original positions and traffic-probe selection preserved and the control lease
released. All container, OneWifi, native agent/controller/CLI and medium process
identities remained unchanged; the room run ID also remained unchanged.

Chromium validation passes at three viewport sizes, preserving node positions
and checking the dark-red labels. An actual WebGL pixel comparison confirms
the wall-only light pass: 66 changed pixels behind the test wall, zero with
walls hidden, and zero behind an opaque non-wall object. The live room also
renders matching floor/occluded geometry for all four measured backhaul links.
Python optimizer/demo regressions pass (224 tests and 19 subtests), as do the
viewer, signal-meter and native-topology Node regressions.
