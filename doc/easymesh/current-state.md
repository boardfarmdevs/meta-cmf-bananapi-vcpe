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
| Runtime image source checkpoint | `dee4dd4a773d8d4a5fe0e1312c6393b42c986d0c` |
| Kernel | Linux `7.0.0-28-generic` |
| Runtime | LXD containers on rev130; peer Vagrant VMs on rev120 and rev150 |
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
| Controller | `X86EMLTRBPIBB_rdk-next_20260824200448.rootfs.lxc.tar.bz2` | `27c5716f7248c2ecbf2110d841bc504e80e727a5b5c1c55729f133d71fcab8e2` |
| Extender | `X86EMLTRBPIAP_rdk-next_20260824200947.rootfs.lxc.tar.bz2` | `5203eea2d89785a0245e25f76a565655a4fabcdd585b5372158db66b5f9adf54` |

The controller contains the consolidated EasyMesh series through `0114`. The
extender contains the applicable Agent series through `0112`. IEEE 1905 is at
`0006`. The retained OneWifi, Wi-Fi HAL, libwebconfig, log4c, journald, and SNMP
fixes are described in [the patch reference](reference/patch-set.md).

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
| Autonomous production steering policy | Not implemented |
| Completed 12-hour 20-client churn soak | Not yet claimed |
| Validated 50/100-client runtime | Not yet claimed |

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

## Runtime access

| Runtime | EasyMesh WebUI | wmediumd Console |
| --- | --- | --- |
| rev130 | `http://192.168.2.130:8888` | `http://192.168.2.130:8890` |
| rev120 VM | `http://192.168.2.120:18889` | `http://192.168.2.120:18890` |
| rev150 VM | `http://192.168.2.150:18889` | `http://192.168.2.150:18890` |

rev130 is the primary development and demonstration runtime. rev120 and rev150
are portability and parity targets.

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
