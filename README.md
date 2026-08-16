# meta-cmf-bananapi-vcpe

Retargets the **Banana Pi R4 (MediaTek Filogic / MT7988) RDK-B broadband build**
to **x86 userspace packaged as an LXC container** for running inside LXD on a host
machine. The output is a `*.lxc.tar.bz2` rootfs that runs the same RDK-B userspace
stack the physical Banana Pi runs (utopia, ccsp-*, RdkWanManager, ccsp-dhcp-mgr,
hal-generic, rbus, sysevent, syscfg, telemetry, …) on x86 with no kernel modules.

Wi-Fi is provided by `mac80211_hwsim` radios moved into the container as
`nictype: physical` NICs instead of real hardware. That is what the
`HWSIM_RADIO`-gated patches exist for — hwsim implements no MLO, exposes a single
channel context, and advertises no MAC ACL capability, none of which the Banana Pi
defaults expect. Patches that are not gated fix defects that are real on hardware
too but only get exercised here; each patch header carries the trace it was
root-caused from.

The two machines are the two EasyMesh roles: `qemux86bpibroadband` is the
controller (`EasyMesh with_alsap`, plus a colocated agent) and `qemux86bpiap` is
the agent/extender (`em_extender`). Run one of each and they form a mesh over the
simulated radios — 1905 transport, AP-Autoconfiguration, WSC M1/M2, wireless
backhaul, and the fronthaul VAPs the controller pushes to the extender.

## documentation

| | |
|---|---|
| [doc/easymesh](doc/easymesh) | the EasyMesh lab — start here |
| [doc/easymesh/architecture.md](doc/easymesh/architecture.md) | how EasyMesh, the containers, hwsim and the client fit together |
| [doc/easymesh/deploy-and-test.md](doc/easymesh/deploy-and-test.md) | deploy the two containers, bring up the mesh, validate end to end |
| [doc/easymesh/steering.md](doc/easymesh/steering.md) | directed 802.11v client steering (`steer_drv` / `steer.sh`) |
| [doc/easymesh/wmediumd-multichan.md](doc/easymesh/wmediumd-multichan.md) | the optional multichannel wmediumd RF model |
| [doc/easymesh/patches.md](doc/easymesh/patches.md) | every patch, by recipe and why (hwsim- / container- / defect-driven) |
| [doc/build](doc/build) · [doc/repo-mirror](doc/repo-mirror) · [doc/dac-lcm](doc/dac-lcm) | building the images; local repo mirror; prpl LCM build |

## layout

| | |
|---|---|
| `conf/machine/` | the two x86 container machines, `qemux86bpibroadband` and `qemux86bpiap` |
| `recipes-ccsp/hal/rdk-wifi-hal` | Wi-Fi HAL patches — `HWSIM_RADIO`-gated adaptations plus ungated defect fixes |
| `recipes-ccsp/ccsp/ccsp-one-wifi` | OneWifi radio/security defaults for hwsim |
| `recipes-ccsp/ccsp/ccsp-one-wifi-libwebconfig` | the EasyMesh translator — report clients from the full associate-status list |
| `recipes-ccsp/unified-wifi-mesh` | EasyMesh controller/agent fixes, DB bootstrap, and the `steer_drv`/`steer.sh` + em-cli tooling |
| `recipes-ccsp/ieee1905` | 1905 service startup ordering |
| `recipes-ccsp/rdk-wifi-libhostap` | hostapd/supplicant fixes |
| `recipes-core/images` | image customisations for the container |

Every patch header carries the trace it was root-caused from — minidump stacks,
netlink captures, or log excerpts — so start there rather than from the diff. See
[doc/easymesh/patches.md](doc/easymesh/patches.md) for the full catalog.
