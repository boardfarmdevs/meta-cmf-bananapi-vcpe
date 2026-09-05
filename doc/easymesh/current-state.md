# Current lab state

Audience: anyone who needs to know what is implemented, validated, or still
open before using the lab.

Status: `codex/0905-clean` is canonical; the fresh 0905 build and portable
release are undergoing qualification. The prior accepted baseline below is
historical and must not be cited as acceptance of the new 0905 artifacts.

The canonical build workspace is
`rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean`. Both role images are
rebuilt in new build directories using the reviewed upstream source lock.
The planned portable artifact is `rdkeasymesh-0905-thin.tar`; final imported
20-client instances are named `rdkeasymesh-20-0905` on rev140 and rev150.

This is the single current-state record. Concept and operating documents should
link here instead of repeating versioned results.

## Previous accepted baseline

| Item | Accepted value |
| --- | --- |
| Source branch | `codex/0831-clean` |
| Runtime image source | EasyMesh through `0127`, OneWifi through `0022`, Wi-Fi HAL through `0030` |
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

## Accepted images

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| Controller | `X86EMLTRBPIBB_rdk-next_20260830064504.rootfs.lxc.tar.bz2` | `69cb6f064b779438264fdefbd54f4ef74367d917ffdf78a96685b40974c0719f` |
| Extender | `X86EMLTRBPIAP_rdk-next_20260830064504.rootfs.lxc.tar.bz2` | `32d54805de07a5dd4d45412cd5664c49a9d028da755ec14dda8342cb60767d76` |

Both images derive from the same source series through `0127`; their installed
controller/Agent binaries remain role-specific. The latest reconciliation fix
applies an Agent's complete Associated Clients snapshot to all of its
radio-scoped controller models, including the valid zero-client withdrawal.
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
| Live optimizer observation with 20 current links and 80 same-band candidate links | Accepted |
| Dynamic optimizer recommendation and bounded acting loop | Accepted |
| Independent start/stop/restart of every provisioned node without medium regeneration, unrelated-node restart, identity repair, database correction, or manual recovery | Not yet accepted |
| Direct-host reboot remains stopped while appliance-VM boot starts the lab | Accepted installation policy |
| Autonomous production steering policy | Not implemented |
| Completed 12-hour 20-client churn soak | Not yet claimed |
| Validated 50/100-client runtime | Campaign automation exists; duration acceptance is not claimed until its recorded runs complete |

## Acceptance

The clean LXD-VM deployment completed without an operator nudge:

```text
model                    5 / 15 / 50 / 24
fronthaul                10 private + 10 IoT
current client metrics   20 / 20
fresh backhaul signals   4 / 4
gateway traffic          20 / 20 clients, 10 packets each, 0% loss
service restarts         0
NVRAM bind sources       5 / 5 persistent and non-empty
optimizer observation    20 current links / 80 same-band candidate links
optimizer closed loop    recommendation and acting crossover passed
wmediumd Console         25 identities, 600 directed pairs, health ok
SNMP                     one systemd-owned subagent, no launcher leak
```

The Console also passed every REST resource, Prometheus export, live packet
telemetry, provenance reporting, and rejection of writes in read-only mode.

The LXD VM deployment and guest reboot reconstruction reached
`5/15/50/24`, 20/20 matching physical/API client owners, 20/20 nonzero RCPI
values, four fresh backhaul signals, 20/20 working WLAN data paths, and zero
OneWifi/EasyMesh restarts. The post-roam ownership regression remained correct
for two 150-second stability windows, and the live optimizer subsequently
completed three no-retry candidate-collection cycles.

## Runtime access

| Runtime | EasyMesh WebUI | wmediumd Console |
| --- | --- | --- |
| bare metal | `http://HOST:8888` | `http://HOST:8890` |
| LXD VM | `http://HOST:18889` | `http://HOST:18890` |

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

Evidence is intentionally outside the Git worktree and must record source
revision, image hashes, topology, scenario inputs, timestamps, service restart
counts, and result data.

For the exact operating gates, use [operations](guide/operations.md). The
[experiment catalog](experiments/README.md) identifies tests that are accepted
and tests whose completion is still required.
