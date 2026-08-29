# Current lab state

Audience: anyone who needs to know what is implemented, validated, or still
open before using the lab.

Status: accepted `codex/0824-clean` baseline.

This is the single current-state record. Concept and operating documents should
link here instead of repeating versioned results.

## Accepted baseline

| Item | Accepted value |
| --- | --- |
| Source branch | `codex/0824-clean` |
| Runtime image source | `codex/0824-clean`; EasyMesh `0123`, OneWifi `0020`, Wi-Fi HAL `0030` |
| Kernel | Linux `7.0.0-28-generic` |
| Runtime | primary LXD lab on rev130; accepted Vagrant VM on rev120 |
| Medium | patched multichannel wmediumd |
| Mesh | controller, colocated Agent-1, and four extenders |
| Controller model | 5 devices / 15 radios / 50 BSS records / 24 associated STAs |
| Fronthaul clients | 20: 10 `private_ssid` and 10 `iot_ssid` |
| Backhaul clients | 4 extender bSTAs |
| wmediumd identities | 25 radios and 600 directed pairs |

The WebUI displays six mesh nodes because the controller is shown separately
from its colocated radio agent.

## Accepted images

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| Controller | `X86EMLTRBPIBB_rdk-next_20260828160826.rootfs.lxc.tar.bz2` | `9a4c432c857dbbf80a68c5b7835d7d0ba39327919dc53becc3c5a9eeb78d51cd` |
| Extender | `X86EMLTRBPIAP_rdk-next_20260828161337.rootfs.lxc.tar.bz2` | `8e8ffbfe4b2404dfc9ae19ab27b0eab6243d3bc55d443ceca0d269d36b3e5d18` |

Both images derive from the consolidated EasyMesh source series through
`0123`; their installed controller/Agent binaries remain role-specific.
IEEE 1905 is at `0006`. The retained OneWifi, Wi-Fi HAL, libwebconfig, log4c,
journald, and SNMP fixes are described in
[the patch reference](reference/patch-set.md).

## What works now

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
| Independent start/stop/restart of every provisioned node without medium regeneration, unrelated-node restart, identity repair, database correction, or manual recovery | Not yet accepted |
| Direct-host reboot remains stopped while packaged VM boot starts the lab | Not yet accepted as a unified installation policy |
| Autonomous production steering policy | Not implemented |
| Completed 12-hour 20-client churn soak | Not yet claimed |
| Validated 50/100-client runtime | 50-client bounded cold reconstruction passed in the isolated `0829` experiment; duration acceptance and the 100-client full lab are not claimed |

## Acceptance

The clean rev130 deployment completed without an operator nudge:

```text
model                    5 / 15 / 50 / 24
fronthaul                10 private + 10 IoT
current client metrics   20 / 20
fresh backhaul signals   4 / 4
gateway traffic          20 / 20 clients, 10 packets each, 0% loss
service restarts         0
named steering           sta-11 -> Extender-2 in 1.379 s, 0% loss
wmediumd Console         25 identities, 600 directed pairs, health ok
SNMP                     one systemd-owned subagent, no launcher leak
```

The Console also passed every REST resource, Prometheus export, live packet
telemetry, provenance reporting, and rejection of writes in read-only mode.

The clean rev120 VM deployment and subsequent real reboot reconstruction both
reached `5/15/50/24`, 20/20 matching physical/API client owners, 20/20 nonzero
RCPI values, four fresh backhaul signals, 20/20 working WLAN data paths, and
zero OneWifi/EasyMesh restarts. The rebooted lab then held the topology for 120
seconds before the accepted disk was packaged as
`easymesh-lab-0828-cf6b5e8.box`.

## Runtime access

| Runtime | EasyMesh WebUI | wmediumd Console |
| --- | --- | --- |
| rev130 | `http://192.168.2.130:8888` | `http://192.168.2.130:8890` |
| rev120 VM | `http://192.168.2.120:18889` | `http://192.168.2.120:18890` |
| rev150 older VM | `http://192.168.2.150:18888` | `http://192.168.2.150:18890` |

rev130 is the primary development and demonstration runtime. rev120 is the
accepted portability target. The running rev150 VM is an older compatibility
image and is not a current parity claim.

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
  `0829` kernel medium is a reduced-physics comparison backend, not a baseline
  replacement. Its implementation and bounded 50-client results are in the
  [kernel-medium reference](reference/hwsim-kernel-medium.md).
- The packaged VM currently performs a complete ordered runtime reconstruction
  after boot. That is a temporary recovery mechanism, not the accepted target
  for independent node lifecycle. A direct bare-metal host should not
  auto-start the lab; only an explicitly started EasyMesh VM should auto-start
  its internal lab.

## Evidence and reproducibility

Acceptance evidence is consolidated under the active lab root:

```text
/home/rev/easymesh-lab/0824-clean/evidence/0824-acceptance/
```

Evidence is intentionally outside the Git worktree and must record source
revision, image hashes, topology, scenario inputs, timestamps, service restart
counts, and result data.

For the exact operating gates, use [operations](guide/operations.md). The
[experiment catalog](experiments/README.md) identifies tests that are accepted
and tests whose completion is still required.
