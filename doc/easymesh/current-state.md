# Current lab state

Audience: anyone who needs to know what is implemented, validated, or still
open before using the lab.

Status: `codex/0905-clean` is canonical. Both fresh 0905 Yocto image builds
passed on 2026-09-05 UTC. Corrected images also passed two complete builder
VM reboots and full health audits. Initial thin imports passed on both hosts,
but rev140 room acceptance found a gateway-recording defect. Its corrected
runtime was repackaged and freshly imported on both hosts. Interactive API,
browser and exact-restoration checks then passed, but the final rev140 audit
rejected the candidate because the controller had restarted once. Patch
`0155` addresses the command-completion race exposed by that run. Complete
image rebuilds, replacement thin packaging and fresh qualification are pending;
the old live labs have not been cut over.

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
The portable artifact is `rdkeasymesh-0905-thin.tar`; final imported
20-client instances are named `rdkeasymesh-20-0905` on rev140 and rev150.

This is the single current-state record. Concept and operating documents should
link here instead of repeating versioned results.

## Release contract

| Item | Required value |
| --- | --- |
| Source branch | `codex/0905-clean` |
| Image source commit | `73586e6bb572d88bd53c4bc92a9d508bd89f7a79` |
| Runtime image source | EasyMesh through `0154`; complete retained OneWifi, Wi-Fi HAL and IEEE 1905 series |
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
| Controller | `X86EMLTRBPIBB_rdk-next_20260905110813.rootfs.lxc.tar.bz2` | `745168ffbcc0724d37a5a5e21306749d648527ebbfc503445c1d2b551024ffa3` |
| Extender | `X86EMLTRBPIAP_rdk-next_20260905111432.rootfs.lxc.tar.bz2` | `f13ff68babb03f4250fa41427efd320b1d34bf97dd264102dae7d3f0816111bf` |

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
extender completed 4988 tasks (24 rerun), 11:13:56–11:17:04 UTC. The table lists
these corrected archives, not the superseded first candidates. Release
provisioning recreates all nested nodes from the complete corrected archives;
the diagnostic agent-only replacement is not a release input.

The installed controller WebUI assets match the tested patched source exactly:
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
Neither assertions nor service-restart counters are suppressed. The two
complete role images must be rebuilt before another thin archive is created.

Replacement image builds, packaging and fresh imports on both hosts remain
pending. Their results must be recorded before calling the
delivered appliance accepted. The archive's `release.json`
identifies its exact runtime source commit; documentation-only commits can
follow the image-source commit without changing either image.

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
