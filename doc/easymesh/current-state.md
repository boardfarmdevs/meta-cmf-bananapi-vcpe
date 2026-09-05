# Current lab state

Audience: anyone who needs to know what is implemented, validated, or still
open before using the lab.

Status: `codex/0905-clean` is canonical. Both fresh 0905 Yocto image builds
passed on 2026-09-05 UTC; appliance and imported-runtime qualification are
pending. A successful image build is not a claim of live acceptance.

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
| Image source commit | `c5ae1d0e1371b7fbdd11c55124c39f8d97850b55` |
| Runtime image source | EasyMesh through `0153`; complete retained OneWifi, Wi-Fi HAL and IEEE 1905 series |
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
| Controller | `X86EMLTRBPIBB_rdk-next_20260905061756.rootfs.lxc.tar.bz2` | `90b4ff84810c6c50355ba0789bfcec9a2fd22e89ce42fe87c2e608c6404965f3` |
| Extender | `X86EMLTRBPIAP_rdk-next_20260905093132.rootfs.lxc.tar.bz2` | `3c1f6ea19ea978e0d475249110b4bc86b8bed7f5a6d47df15d6cecf22a8ba55e` |

Both images derive from the same clean source commit; their installed
controller/Agent binaries remain role-specific. The controller ran 5792 tasks
successfully from an empty 0905 sstate directory, with zero external mirror
hits. Its build ran 06:17:49–09:30:26 UTC. The extender ran 4988 tasks
successfully, 09:31:25–09:41:41 UTC, reusing only outputs freshly built for
0905. Neither role reused an older release's rootfs or compiled sstate.

The installed controller WebUI assets match the tested patched source exactly:
`script.js` SHA-256
`75d420edbd7c63b028327e6850a4626b2df8057503438ead556e3a4861f6e11c`;
`index.html` SHA-256
`4222b5188bf8d6e63f2446f489977bc714c7de299d020df4308cf41080843481`.
IEEE 1905 is at `0006`. The retained OneWifi, Wi-Fi HAL, libwebconfig, log4c,
journald, and SNMP fixes are described in
[the patch reference](reference/patch-set.md).

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
- 235 Python tests, four WebUI suites against the fresh patched source,
  room interaction JavaScript, helper-artifact and VM shell regressions;
- real-browser candidate checks for quoted cohort labels, uplink bars,
  manual layout preservation, and fitting three viewport sizes;
- GitHub Pages manual search, keyboard controls, print, mobile layout, and
  absence of live API writes in NO CONNECT mode; and
- isolated real-daemon checks for concurrent control clients, rejection of
  stale generations, atomic updates, frequency isolation and exact restoration.

Fresh builder, rev140/rev150 import, live traffic/steering, interactive-room
movement and restoration gates remain pending. Their results must be recorded
before calling the delivered appliance accepted. The archive's `release.json`
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
