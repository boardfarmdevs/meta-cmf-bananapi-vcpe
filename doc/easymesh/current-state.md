# Current lab state

Audience: anyone who needs to know what is implemented, validated, or still
open before using the lab.

Current canonical branch: **`codex/0908-clean`**. The new canonical workspace is
`rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0908-clean/meta-cmf-bananapi-vcpe`.
The [0908 clean rebuild](reference/release-0908.md) starts from synchronized,
pinned sources with fresh role build directories and workspace-local caches.
It is in progress; this paragraph does not claim a published or accepted tar.
The running rev140 lab remains 0907 until the new tar has been imported and
passed the small-profile smoke checks. No full room soak is required for 0908.

The sections below retain historical 0905/0906 acceptance records; their
canonical-directory and old-VM retention statements apply to those deliveries.

The original **0905 delivery is accepted for the 20-client profile** on
rev140 and rev150 as of 2026-09-05 19:05 UTC. `codex/0905-clean` is canonical.
Both complete role images were rebuilt, and the final thin tar was freshly
imported on each host from zero nested instances. Rev140 passes the complete
interactive API/browser and exact-restoration tests. Both deployed VMs pass
post-cutover convergence and full health audits with zero native service
restarts and zero packet loss for all 20 clients. The old VMs are retained,
stopped and excluded from autostart. Earlier rejected candidates and the fixes
they exposed are documented below; they are not the delivered archive.
The later rev140-only signal UI and fixed-pool world-switching overlays are
recorded separately below. They leave rev150's running lab and the accepted
0905 archive unchanged, and are now included in the separate 0906 package.

As of 2026-09-06, all outer LXD VMs on rev120, rev140 and rev150 have
`boot.autostart=false`, including the running prplMesh/RDK labs. This changes
host-reboot behavior only; no running VM is stopped. New RDK builds/imports
also disable autostart. The historical 0905 cutover below enabled it at the
time and is superseded by this operator preference. The
[0906 runtime refresh](reference/release-0906.md) is packaged separately;
it does not replace either current live lab.

The first full-roster builder reboot failed: early client-capability queries
incorrectly marked two extender radios configured before their WSC exchange,
leaving 34 rather than 50 BSS records. Patch `0154` preserves the radio state
while replying. Its compiled-handler regression reproduces the failure before
the patch and passes after it. Both corrected role images also build
successfully and pass the repeated reboot gates. The failed candidate and
its original hashes are retained in release evidence.

The canonical build workspace is
`rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean`. Both role images are
rebuilt in new build directories using the reviewed upstream source lock.
The original delivery artifact is `rdkeasymesh-0905-thin.tar`; its imported
20-client instances are named `rdkeasymesh-20-0905` on rev140 and rev150.

This is the single current-state record. Concept and operating documents should
link here instead of repeating versioned results.

## 0906 runtime refresh

| Item | Packaged value |
| --- | --- |
| Outer archive | `rdkeasymesh-0906-thin.tar` |
| Bytes | `2859612160` |
| SHA-256 | `32fa408e1180ecf27bcaae79bce64404bc5c2ea80bead9b49f2c4fd721fc5d3d` |
| Source base commit | `c69e766056b709c76933f62cbb1e2b1d8e7b9e47` plus the explicit uncommitted snapshot |
| Source snapshot SHA-256 | `ad2852ee033bb9c084a95791bcd370888782e97f7b9459294f60c7402031e4b3` |
| Source inventory | 785 files, verified before export and after fresh import |
| Inner VM archive | `rdkeasymesh-0906-c69e766-ad2852ee033b-thin-lxd.tar.zst` |
| Export completed | 2026-09-06 20:52:41 UTC |
| Fresh verification VM | rev140 `rdkeasymesh-20-0906-verify`, spare ports `48889`/`48890`/`48891` |
| First-boot provisioning | 21:02:06–21:18:43 UTC; zero to 25 nested instances |
| Default VM autostart | `false`; import starts provisioning once, later host boots do not start the VM |

The identical, checksum-verified archive and adjacent `.sha256` are at:

- rev140: `/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean/release-artifacts/rdkeasymesh-0906-thin.tar`
- rev150: `/home/rev/releases/0906/rdkeasymesh-0906-thin.tar`

This includes automatic world loading, fixed-pool RF/presence updates,
convergence fixes, Play/Pause with dragging, the shared signal palette and
updated viewer documentation. It is **not another Yocto rebuild**: 8,428
controller archive members retain identical contents and semantic metadata;
only its three WebUI assets are replaced/added. The extender has no WebUI and
its entire archive remains byte-identical. Native binaries, kernel, hwsim and
wmediumd retain their accepted 0905 identities. The refreshed controller
archive hash is `ec234f1078fb17f25b2c05f46af949b17a8d2a29d0cca510d22d0879da67011f`.

The fresh profile-20 import passes full health and zero-loss traffic audits.
Run `20260906T211917Z-private-client-room-walk-interactive` passes measured
convergence and exact native client appearance for border-hover (12),
stationary (10), home-b slow-walk (20), flash-crowd (10), default (20), and
client disappear/reappear (19/20), without restarting containers or native
services. Real Chromium checks pass shared rendered colours, automatic room
selection, static/live Play+drag, pause/resume and observer safety. An
eight-second scripted world verifies actual kernel disconnect/reconnect,
9/10-client presence, playback completion and unchanged process identities.
The source regression suites pass 286 Python tests (one unchanged optional
skip, 17 subtests), eight Node suites and the VM helper/import tests.

Evidence is under `release-evidence/release-0906/` in the canonical rev140
workspace. The immutable manifest retains `status: candidate`; test results
are recorded beside the tar rather than changing the tested artifact. Only
profile 20 receives fresh runtime qualification. No normal-port lab cutover,
rev150 runtime update, Git commit or push is performed. The source snapshot
inside the tar is immutable; later acceptance-document edits in the checkout
are deliberately not part of that snapshot. See the
[0906 refresh reference](reference/release-0906.md) for import and provenance.

## Release contract

| Item | Required value |
| --- | --- |
| Source branch | `codex/0905-clean` |
| Image source commit | `9f5d64019aad4679c04b7e563ad00c6f0a47e23f` |
| Runtime image source | EasyMesh through `0155`; complete retained OneWifi, Wi-Fi HAL and IEEE 1905 series |
| Kernel | Linux `7.0.0-30-generic` |
| Runtime | bare metal for performance/debug; LXD VM for portable appliance use |
| Medium | patched multichannel wmediumd |
| Mesh | controller, colocated Agent-1, and four extenders |
| Controller model | 5 devices / 15 radios / 50 BSS records / 24 associated STAs |
| Fronthaul clients | 20: 10 `private_ssid` and 10 `iot_ssid` |
| Backhaul clients | 4 extender bSTAs |
| wmediumd identities | 25 radios and 600 directed pairs |

The WebUI displays six mesh nodes because the controller is shown separately
from its colocated radio agent.

## Fresh image artifacts

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| Controller | `X86EMLTRBPIBB_rdk-next_20260905143930.rootfs.lxc.tar.bz2` | `39af925bc4b46f4505baf98f754a4b527ea3de5e5ee6f6d85cd99fc983285896` |
| Extender | `X86EMLTRBPIAP_rdk-next_20260905144620.rootfs.lxc.tar.bz2` | `b56b853db3d2362dd6f3854bfbaf86c93570ec7c8110134bbd0fb55e8208a17c` |

Both images derive from the same clean source commit; their installed
controller/Agent binaries remain role-specific. The initial cold build used
`c5ae1d0e1371b7fbdd11c55124c39f8d97850b55`. The controller ran 5792 tasks
successfully from an empty 0905 sstate directory, with zero external mirror
hits. Its build ran 06:17:49–09:30:26 UTC. The extender ran 4988 tasks
successfully, 09:31:25–09:41:41 UTC, reusing only outputs freshly built for
0905. Neither role reused an older release's rootfs or compiled sstate.

After the reboot defect was reproduced and fixed, both complete image targets
were rebuilt at `73586e6` using only those fresh 0905 outputs. The corrected
controller completed 5792 tasks (26 rerun), 11:07:41–11:13:56 UTC; the corrected
extender completed 4988 tasks (24 rerun), 11:13:56–11:17:04 UTC. Those images
passed the builder reboot gates but are superseded by the orchestration fix.
Both full targets were rebuilt again at `9f5d640`: controller 5792 tasks
(26 rerun), 14:38:56–14:45:40 UTC; extender 4988 tasks (24 rerun),
14:45:44–14:49:13 UTC. The compiled concurrency regression passes against
both actual patched source trees. The table lists these latest archives. Release
provisioning recreates all nested nodes from the complete corrected archives;
the diagnostic agent-only replacement is not a release input.

The accepted image's controller WebUI assets match the tested patched source exactly:
`script.js` SHA-256
`75d420edbd7c63b028327e6850a4626b2df8057503438ead556e3a4861f6e11c`;
`index.html` SHA-256
`4222b5188bf8d6e63f2446f489977bc714c7de299d020df4308cf41080843481`.
IEEE 1905 is at `0006`. The retained OneWifi, Wi-Fi HAL, libwebconfig, log4c,
journald, and SNMP fixes are described in
[the patch reference](reference/patch-set.md).

The appliance pins Boardfarm lab staging to
`ddb5a2b9e1707562595afc7e4000a3b8efa3cd81` on `codex/0905-clean`.
This is the previous `eeb4803` lab configuration plus one required build fix:
the WAN AFTR compilation stage now uses Debian Bookworm, matching its final
runtime image. The former Bullseye stage failed on missing security packages
after Debian 11 LTS ended on 2026-08-31. AFTR compiles successfully on Bookworm.
The failed first appliance attempt is retained as evidence, not reused as the
release builder. This dependency change does not alter either Yocto image.

## Delivered 0905 appliance

| Item | Accepted delivery |
| --- | --- |
| Outer archive | `rdkeasymesh-0905-thin.tar` |
| Archive bytes | `2784440320` |
| Archive SHA-256 | `a035a56c19f437dadaa9ebd36077cad07c05cdaf152680b61acddde75d313770` |
| Packaged runtime source | `fd320b70d2a0cd04e010d2ab09e083f3df0d812b` |
| Inner VM archive | `rdkeasymesh-0905-fd320b7-thin-lxd.tar.zst` |
| Accepted profile | 20 clients: 10 private and 10 IoT, plus five mesh containers |
| rev140 first boot | 18:27:12–18:44:44 UTC; zero to 25 nested instances, full audit pass |
| rev150 first boot | 18:19:46–18:36:53 UTC; zero to 25 nested instances, full audit pass |
| rev140 cutover | 19:01:31 UTC; final verification 19:04:52 UTC |
| rev150 cutover | 19:01:03 UTC; final verification 19:04:54 UTC |

The identical checksum-verified tar is stored on rev140 at
`/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean/release-artifacts/rdkeasymesh-0905-thin.tar`
and on rev150 at `/home/rev/releases/0905/rdkeasymesh-0905-thin.tar`, each with
an adjacent `.sha256` file. Pre-package documentation was committed in the
packaged source before export and deployment. The immutable manifest's
original `status: candidate` is not rewritten after testing; acceptance is
recorded here and in the host-side evidence, without changing the tested tar.
Profile selectors for 50/100 clients remain available but are not accepted
runtime/soak results.

At the 0905 cutover, both hosts ran `rdkeasymesh-20-0905` with autostart
enabled. Autostart has since been disabled as recorded above; these remain
the normal-port deployment identities:

| Host | EasyMesh WebUI | wmediumd Console | Interactive room |
| --- | --- | --- | --- |
| rev140 | `http://192.168.2.140:18889/` | `http://192.168.2.140:18890/` | `http://192.168.2.140:18891/viewer/?mode=interactive` |
| rev150 | `http://192.168.2.150:18889/` | `http://192.168.2.150:18890/` | `http://192.168.2.150:18891/viewer/?mode=interactive` |

The final checks require a continuously converged, fully measured 20-client
fleet for at least a minute, with a newer optimizer evaluation, before the
full ownership/service/traffic audit. Both hosts pass. The rev140 manual and
three-viewport topology browser checks also pass on these final public ports.

Rollback VMs `rdkeasymesh-20-interactive` on rev140 and
`rdkeasymesh-20-0904` on rev150 are stopped with autostart disabled. The old
rev140 room's RF state was restored before shutdown. Their original LXD
configurations are preserved as `release-evidence/final/rollback-old-config.yaml`
under each host's release workspace. Do not start an old VM alongside the new
one on the same public ports; perform deliberate room restoration and VM/port
handoff if rollback is needed. Rejected archives and builder snapshots remain
separate from this accepted delivery.

## rev140-only fixed-pool world switching

The interactive viewer immediately applies an installed world selection or
local world upload to the lab. There is no separate Apply button or confirmation;
lease, revision and server validation remain mandatory. The rev140 room overlay
removes the operator capability check; restrict network access to trusted users.
rev150, rev120 and the immutable 0906 thin tars retain their prior behavior.
Failed loads retain the current room. Compatible worlds use the existing
20 client containers and five mesh containers (six displayed topology nodes).
Unused clients are gracefully disconnected, held offline by their existing
supplicant, and isolated on all serving RF links. The native topology remains
actual controller state rather than a presentation filter. The original
startup backhaul matrix is protected so a shifted room does not drop an
extender from the infrastructure mesh.

**Restore default 20** restores the default room and client presence. The last
selection is not persisted as a boot profile. Neither container provisioning
nor a new Yocto build is involved. RF updates, client pauses, rollback and crash
recovery use the existing single-writer engine and recovery journal. Only the
room service is restarted to install this Python/viewer overlay; native mesh
services, containers and wmediumd do not restart during world transitions.

The initial world-switching acceptance run was
`20260905T215947Z-private-client-room-walk-interactive`. Its live tests cover
`home-a-border-hover` (12 online), `home-a-stationary` (10),
`home-b-slow-walk-ten` (20, different floor layout), and `home-a-flash-crowd`
(20 roles, 10 initially online), then restore the default 20. Separate client
Disappear/Reappear checks require exact 19/20-client controller MAC rosters.
The checks also verify kernel disconnection for unused clients and unchanged
container, native service and medium process identities. Counts must remain
correct for at least ten seconds, not just match once. That acceptance run's
client rosters converge in 19–32 seconds per transition, including the stability
gate; it did not require best-AP convergence. Early RF-only tests
exposed stale associations; those failed candidates were restored and replaced,
not accepted. Controller convergence is asynchronous and some transitions can
take around two minutes including aging and the sustained-health gate.

Real-browser acceptance on that service passes selection-without-writes,
explicit 12-client apply, observer SSE and reload, local JSON upload of the
10-client room, malformed-upload rejection without a revision change, default
restoration and no browser errors. Local validation
passes 267 Python tests with one unchanged optional skip, all four native WebUI
Node suites, the signal helper and room interaction suites, and JavaScript
syntax checks. The working source and documentation are synchronized to the
canonical rev140 checkout; this overlay is not included in the immutable thin
tar, rev150, or GitHub Pages.

Initial acceptance evidence is under the rev140 appliance's `/root/world-switch-0905-v8/`;
earlier candidate evidence is retained separately in the versioned directories.
Source-overlay bundles and final reports are retained in the host
release-evidence directory. The source/runtime changes are intentionally
uncommitted pending an explicit commit request. See
[live world switching](reference/live-world-switching.md) for the operator
workflow, protected-backhaul boundary and recovery behavior.

### Online-roster steering correction

A subsequent 10-client room exposed a separate steering guard that still
expected the startup count of 20. Candidate measurements correctly found
stronger APs, but every decision was rejected with `client_count_mismatch`.
The room conductor now derives the policy's expected count from the accepted,
epoch-checked room state on every evaluation, including Disappear/Reappear and
default restoration. Actual controller counts and the five-device health guard
remain unchanged; this is not a bypass for missing or stale associations.

The online-roster correction was accepted on
`20260905T235053Z-private-client-room-walk-interactive`. The viewer distinguishes
**Client roster ready** from optimizer AP convergence. Local regression passes
275 Python tests, one unchanged optional skip and thirteen parameterized subtests,
plus the native WebUI, room-interaction and signal-meter Node suites. The
all-catalog smoke test now requires exact client appearance/disappearance and
fresh measured best-AP convergence in the current RF epoch, not counts alone.
An initial full sweep then found a returning IoT client with a real Wi-Fi
association and working traffic but permanently missing controller RSSI.
Re-enabling reporting and a diagnostic client reconnect did not recover that
sample; the initial sweep is retained as failed, not accepted. Missing
post-transition metrics now hold only the affected client, rather than freezing
all other steering. The interactive lab also has an explicit kernel-RSSI
fallback, requiring a successful `wlan0` traffic probe and an exact match to the
controller BSSID and band before the sample can be used. It does not substitute
room predictions or overwrite native controller metrics. The UI and optimizer
evidence identify this measurement source separately; unreadable or mismatched
links still prevent a claim of complete fleet convergence.

The completed sweep passes **all eleven catalog rooms**, default restoration,
and 19/20-client Disappear/Reappear: fourteen measured-convergence checks in
total. Catalog transitions take 67.53–290.95 seconds including the stability
gate; returning from the shifted layout to default takes 305.01 seconds.
Container, native-service and wmediumd process identities remain unchanged,
and the per-run action count ends at 37/100. See the
[per-room results](reference/live-world-switching.md#rev140-0905-acceptance).

Read-only Chromium acceptance also verifies exact client appearance in both
the native topology and live room for all eleven catalog rooms, with no
browser errors or writes. The updated automatic-loading UI passes real-browser
selection of flash-crowd, local upload of stationary, observer synchronization,
default restoration, and invalid-checksum rejection without a revision change.
Cancelling the capability prompt retains the prior room and selector value;
no extra confirmation appears. All three world controls remain disabled during
requests and until the authoritative startup catalog is ready. The additional
`viewer-world-loading-test.js` regression suite passes. This final UI/manual
update is installed on rev140 without restarting the room service; refresh an
already-open browser tab to use it.

After acceptance, the user's `home-a-band-walk-small` room and original role
positions are restored, healthy and converged at ten clients. STA-05 retains
position `[1.2, 13.15]` and is associated with native **Extender-2**, BSSID
`02:00:00:51:26:61`; both native topology and the client's kernel confirm the
association, with a measured signal of -44 dBm. The final reports, screenshots,
regression output and uncommitted source overlay are archived on rev140 under
`/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean/release-evidence/room-convergence-0905-final/`.

Evidence for the updated sweep is retained under
`/root/room-convergence-0905-v2/` in the rev140 appliance. The earlier
`/root/room-convergence-0905/` directory also preserves the user's selected room
and positions for restoration after testing. Rev150 and the accepted thin
archives remain untouched.

### Unified playback and dragging

The current rev140 room service is
`20260906T013214Z-private-client-room-walk-interactive`. Camera/Interact pointer
buttons are removed. Drag devices to move them, empty space to orbit, Shift-drag
anywhere to pan, and scroll to zoom. Clicks and navigation do not acquire a
lease or write RF. A real drag remains a local preview until one authorized,
revision-checked position command is accepted on release.

Play/Pause now also works in the live interactive room, with one bounded
server-owned worker advancing scripted positions and presence through the
existing verified RF path. Dragging, a manual walk or presence control pins
only that role; other scripts continue. Pause/resume preserves pins and world
loading clears them. Live seeking/speed changes remain disabled; the player
samples geometry at up to one update per second, retains presence transitions,
and slows rather than bursting under load. The optimizer waits during playback
and resumes stable-room convergence after Pause/end. Lease loss, page departure,
world switching and shutdown pause playback. Static playback supports dragging;
live observer and evidence-replay views remain read-only.

Acceptance passes static and live Play+drag in Chromium, one final drag write,
continued motion of another client, read-only click/pan, Pause/resume, observer
positions/clock synchronization, and pause on controller departure. A separate
eight-second script verifies a real kernel Wi-Fi disconnect and reconnect at
9/10 clients and script completion. Complete timelines for all eleven installed
rooms also pass pre-play validation without RF writes. Container, native-service and medium process
identities are unchanged. Local regression: 286 passed, one unchanged optional
skip, seventeen subtests, plus the gesture/world-loading, signal/interaction and
four native WebUI Node suites. Final evidence and source are retained under
`/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean/release-evidence/room-play-drag-0905/`.
Only rev140 is updated; Pages, rev150 and the accepted thin tar stay unchanged.
The original ten-client band-walk room and user positions are restored with
playback paused and the fleet converged; STA-05 is back on Extender-2 at -44 dBm.

## rev140-only signal UI overlay

On 2026-09-05 at 20:35:43 UTC, rev140 received a static-only update to the
Network Topology and room viewer. Both now share `signal-meter.js`: ten
segments fill bottom to top with three red, four yellow and three green;
unlit upper segments are grey. Exact values remain available. Missing or
stale measurements show all grey, and the live room ages its gauges even
when the event stream stops. The simulator's modeled SNR uses its explicit
−91 dBm noise floor to map to the same RSSI scale, not a physical-radio
assumption. The ordinary traffic-probe client now uses its `sta-…` label
instead of the legacy special alias.

The static overlay does not restart the room, CLI, OneWifi, or EasyMesh
services and does not change RF or backhaul parentage. The existing room run
remains healthy with all 20 clients converged. Real-browser checks pass for
the four extender meters, 20 room gauges, ordinary probe label, three topology
viewport widths and zero API writes. Local validation passes 252 Python tests
with the unchanged optional skip, all four WebUI Node suites, the shared
signal-meter regression, and patch applicability against the accepted source.

| rev140 served asset | SHA-256 |
| --- | --- |
| Topology `script.js` | `6aa65d8004d2afff5ca4e9b2bcc1f97a2426e6ecf8867cfefa5281c1cafa05de` |
| Topology `index.html` | `d09eb3551d2b87ba7e2cf32bbd2dfedf304a8473aa7f0c9f48ebef6b578fd3a9` |
| Shared `signal-meter.js`, both views | `cfb6f115dcc6cd98c56e5d3eaed2f34e5dabe876d60ec2bca8bce12be1bfa7ef` |
| Room `index.html` | `915b393c41a5e1382592e5d8a52b10a92e6819373206009105c65e7d164bcbfe` |
| Room `manual.html` | `cdc9652d5f2909f08e816166e90294cb456a3f6b767ba085e4068b71639aab0e` |

Rollback copies of the previous packaged/NVRAM WebUI and room assets are in
`/root/signal-ui-0905/backup` inside the rev140 appliance. Its room checkout
therefore has an intentional static-file overlay on the packaged revision,
not a newly built appliance release. Patch `0156` and the shared-asset recipe
wiring preserve the change for future builds. No new Yocto images or thin
tars are produced by this update. Rev150 retains the original clean source
and WebUI hashes; GitHub Pages is also unchanged.

## Carried-forward capabilities

These functionality milestones predate the new image build. The separate
0905 acceptance record below determines which fresh-delivery gates have run;
this table is not evidence that every historical campaign was repeated.

| Capability | State |
| --- | --- |
| Repeatable controller and four-extender onboarding | Accepted |
| One hwsim wiphy representing tri-band service per BPI | Accepted |
| 2.4, 5, and 6 GHz client association | Accepted |
| Ten private plus ten IoT clients | Accepted |
| Client and extender identity in the WebUI | Accepted |
| Live client RCPI and approximate dBm | Accepted when metrics policy is active |
| Fresh/stale/unknown extender backhaul signal | Accepted |
| Friendly-name manual steering | Accepted |
| Live topology refresh and steering animation | Accepted |
| Client carousel and extender RF-outage tests | Accepted |
| Chain and branch multihop backhaul construction | Accepted |
| wmediumd dynamic pair/frequency control | Accepted |
| wmediumd Console Phase 1/2 visibility | Accepted |
| External optimizer unit and replay framework | Accepted |
| Live optimizer observation with 20 current links and 80 same-band candidate links | Accepted |
| Dynamic optimizer recommendation and bounded acting loop | Accepted |
| Independent start/stop/restart of every provisioned node without medium regeneration, unrelated-node restart, identity repair, database correction, or manual recovery | Not yet accepted |
| Direct-host reboot remains stopped while appliance-VM boot starts the lab | Accepted installation policy |
| Autonomous production steering policy | Not implemented |
| Completed 12-hour 20-client churn soak | Not yet claimed |
| Validated 50/100-client runtime | Campaign automation exists; duration acceptance is not claimed until its recorded runs complete |

## 0905 acceptance

Completed before appliance packaging:

- both complete role-image builds and installed WebUI asset checks;
- two complete corrected-image builder VM reboots: both restore 5/15/50,
  20 clients, 24 associated STAs, 20 live metrics and zero service restarts;
  full audits verify NVRAM bindings, kernel/DB/API association ownership,
  fresh uplink measurements and 0% packet loss for every client;
- the compiled capability-query handler regression, failing before `0154`
  and passing against both corrected Yocto source trees;
- 236 Python tests, four WebUI suites against the fresh patched source,
  room interaction JavaScript, helper-artifact and VM shell regressions;
- real-browser candidate checks for quoted cohort labels, uplink bars,
  manual layout preservation, and fitting three viewport sizes;
- GitHub Pages manual search, keyboard controls, print, mobile layout, and
  absence of live API writes in NO CONNECT mode; and
- isolated real-daemon checks for concurrent control clients, rejection of
  stale generations, atomic updates, frequency isolation and exact restoration.

The first `ac18169` archive passed builder browser/proxy gates and fresh
20-client imports on both hosts, each going from zero to 25 nested instances.
Both full audits passed with zero packet loss. Rev140 also passed all four
native away/return steering moves, the topology browser tests, embedded manual
checks, and the browser-only timeout-card regression.

Its interactive test converged all 20 clients, then exposed a missing gateway
track while recording a move of the colocated Agent-1. The session failed
closed and verified exact RF restoration. Recording now captures and exports
every movable role, including the gateway, rather than only roles permitted
to disappear. Gateway presence remains protected. A regression reproduces the
original failure and verifies the corrected movement, exported geometry, and
exact restoration. This Python runtime fix does not change either Yocto image.
The initial archive is superseded, not an accepted delivery.

The corrected `017abf7` runtime archive (SHA-256
`119342a7dd686c82828e1330aaaa5d3b6502e880aed39a16c164653e26e43bbb`)
passed fresh 20-client imports on both hosts. Rev140 passed native steering,
interactive API/browser/recording checks and exact RF restoration. However,
the post-room full health audit found `em_ctrl NRestarts=1`, so this archive is
also superseded, not accepted. Its retained Breakpad dump reports SIGABRT
during orchestration: a radio-thread candidate response can delete the active
command and its statistics while the manager timeout is still using them.

Patch `0155` serializes command queue/stat operations, candidate response/ACK
handling and controller radio-timer command access. It retains synchronous
completion before the next candidate request is admitted. The compiled
real-method concurrency regression fails on the previous source and passes
with locking, including nested completion and immediate follow-up submission.
Neither assertions nor service-restart counters are suppressed. Both complete
role images have been rebuilt successfully, as recorded in the artifact table.

The replacement-image builder `rdkeasymesh-20-0905-orch-builder` passes fresh
25-container provisioning and two complete VM reboot/full-health gates,
finishing at 15:25:10 UTC. Native steering and topology browser checks pass.
However, room run `20260905T152622Z-private-client-room-walk-interactive` fails
its initial 900-second convergence gate. Client `wlan-client-009` retains
`freq_list=5955` and `scan_freq=5955`, while its strongest target AP now uses
6135 MHz. The target is visible to a directed scan but excluded from the
client's allowed association frequencies. This client-generation constraint
is corrected in the client generator by selecting the enabled PHY channels
within the requested band, rather than the initially active AP channels.
Pool resume recreates legacy band-pinned clients using a configuration marker.
The three-band regression fails before the fix and passes afterward, with
disabled-channel exclusion, numeric ordering and deduplication; migration
tests cover legacy and current clients. Inspection of the first candidate's
persisted list also found hwsim's 5925 MHz 5 GHz edge incorrectly included as
6 GHz. The `supported-phy-v2` correction excludes it while retaining the
special 5935 MHz 6 GHz channel when supported; pool resume migrates the first
candidate too. Increasing the test timeout is not acceptance. Room shutdown
restores the exact saved RF state, and the controller restart counter remains
zero. Evidence is retained under `release-evidence/orch-fix/`.

Final band-scope runtime `23fb9c744494f19a5db568f3cd307a1ad93a1163` passes
standard pool migration and two further whole-VM reboot/full-health checks,
finishing at 17:54:47 UTC. Native away/return steering passes 4/4 and the real
topology browser fits three viewport sizes. Room run
`20260905T175555Z-private-client-room-walk-interactive` passes initial and final
20-client convergence, authenticated single-writer controls, idempotence and
stale-revision rejection, client/extender/gateway movement, presence outages,
walking controls, recording export and observed steering with traffic
verification. It completes with 22 optimizer actions, not a relaxed timeout.
Real-browser dragging, preview isolation, reset, camera mode, lease release
and embedded manual checks also pass. Room shutdown restores the exact RF
snapshot; the post-room audit reports zero native service restarts and 0%
packet loss for every client. Evidence is in `release-evidence/band-scope-v2/`.
Local validation passes 251 Python tests with the unchanged optional skip,
plus all seven portable-VM shell suites.

The final `fd320b7` thin archive passes fresh imports and full audits on both
hosts. Rev140 room run `20260905T184600Z-private-client-room-walk-interactive`
passes the complete API controls and observed steering with 20 actions,
real-browser dragging/preview/reset/lease checks, exact RF restoration at
18:59:33 UTC and the full post-room audit with zero service restarts. Rev150
also reaches settled 20-client room convergence and passes a full audit while
the room is running. Both cutovers and subsequent live checks pass as recorded
in the delivery table. Final evidence lives in `release-evidence/final/` on
each host. The archive's `release.json` identifies its exact runtime source
commit; documentation-only acceptance commits can follow without modifying
the tested images or tar.

One optional pre-existing daemon integration test is not a pass:
`gen/wmediumd/configurator/tests/test_actuator.py:69` expects a second control
connection to be rejected. The unchanged `0013` daemon patch deliberately
permits concurrent generation-protected clients. Explicitly enabling that old
test fails this assertion; the separate real-daemon protocol check above passes.
The normal Python run skips this optional integration test. This unrelated
test expectation was not changed for 0905.

## Runtime access

| Runtime | EasyMesh WebUI | wmediumd Console | Interactive room |
| --- | --- | --- | --- |
| bare metal | `http://HOST:8888` | `http://HOST:8890` | `http://HOST:8891/viewer/?mode=interactive` |
| LXD VM | `http://HOST:18889` | `http://HOST:18890` | `http://HOST:18891/viewer/?mode=interactive` |

Host addresses are site configuration. They are selected during LXD VM build
or import and are never baked into the portable artifact.

## Optional container monitoring

[Nested LXD UI and monitoring](reference/lxd-ui-and-monitoring.md) documents
an opt-in loopback-only setup with metrics-only TLS authentication, Prometheus,
Grafana provisioning and a bundled container dashboard. It observes the 25
nested LXD containers, not the outer VM or EasyMesh radio metrics.

On 2026-09-05, a temporary installation on the rev140 orchestration builder
passes Prometheus configuration validation, authenticated scraping, the exact
25-container roster comparison, Grafana data-source health and live queries
for every dashboard panel. The nested LXD UI serves over verified TLS;
anonymous metrics and administrative instance access using the metrics-only
certificate both return HTTP 403. Browser identity enrollment and the
operator's SSH setup remain installation steps, not claimed browser tests.
The memory panel uses the observed LXD 6.9 `MemTotal - MemFree` semantics,
including cache; this cgroup-v2 exporter does not emit the documented RSS
family.

Repeated setup preserves credentials, conflicting listeners are refused, and
disable preserves operator-modified settings while restoring owned settings.
Re-enable and repeated disable also pass. The temporary services, volumes,
images, trust entry and credentials are removed before release packaging;
the final full health audit passes with all service restart counters zero
and zero packet loss for all 20 clients. Local Python validation passes
244 tests with one unchanged optional skip, including eight new monitoring
checks. Evidence is in `release-evidence/observability/`. The optional stack
remains disabled in the delivered VMs; its tests do not substitute for the
separate interactive-room release qualification.

## Important boundaries

- EasyMesh supplies telemetry, policy configuration primitives, and steering
  commands. It does not supply the research optimizer used by this project.
- The external optimizer currently has a tested observation/replay framework
  and a deliberately simple threshold baseline. Acting experiments require an
  explicit operator opt-in and complete candidate measurements.
- wmediumd controls RF delivery. It does not decide which AP a client should
  use; the station and EasyMesh mechanisms react to the medium.
- The WebUI policy page configures reporting and standardized policy fields. It
  does not prove that an autonomous optimizing policy is running.
- Immediate reconstruction and functional acceptance do not replace the
  separately defined long-duration soak.
- Userspace wmediumd remains the accepted and default medium. The optional
  kernel medium is a reduced-physics comparison backend, not a baseline
  replacement. Its implementation and bounded 50-client results are in the
  [kernel-medium reference](reference/hwsim-kernel-medium.md).
- The appliance VM performs a complete ordered runtime reconstruction
  after boot. That is a temporary recovery mechanism, not the accepted target
  for independent node lifecycle. A direct bare-metal host should not
  auto-start the lab; only an explicitly started EasyMesh VM should auto-start
  its internal lab.
- Appliance NVRAM lives in `/var/lib/easymesh-lab/nvram`, not below the Git
  checkout. The health gate verifies all five BPI bind sources so source
  synchronization cannot invalidate persistent mesh identities.

## Evidence and reproducibility

Acceptance evidence is stored outside the source tree inside the appliance:

```text
/home/easymesh/easymesh-evidence/
```

The 0905 host-side build and release evidence is under
`rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean/release-evidence/`.
The sibling `release-artifacts/` directory holds the thin tar and checksum.

Evidence is intentionally outside the Git worktree and must record source
revision, image hashes, topology, scenario inputs, timestamps, service restart
counts, and result data.

For the exact operating gates, use [operations](guide/operations.md). The
[experiment catalog](experiments/README.md) identifies tests that are accepted
and tests whose completion is still required.
