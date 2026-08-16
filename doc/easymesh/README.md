# EasyMesh on LXD + mac80211_hwsim

This layer retargets the Banana Pi R4 RDK-B broadband build to x86, packaged as
an LXC rootfs, so the same RDK-B EasyMesh userspace stack runs inside LXD on a
host machine with **simulated** Wi-Fi (`mac80211_hwsim`) instead of real radios.
Two containers — a `qemux86bpibroadband` controller (with a colocated agent) and
a `qemux86bpiap` extender — form a mesh over the simulated radios: 1905
transport, AP-Autoconfiguration, WSC M1/M2, wireless backhaul, and the fronthaul
VAPs the controller pushes to the extender. An Alpine `wlan-client` associates as
a real station.

Start here, then follow the section that matches what you're doing.

## Documents

**Foundations — how it works and how to run it**

| | |
|---|---|
| [architecture.md](architecture.md) | how EasyMesh, the containers, hwsim, wmediumd and the client fit together; process/API boundaries; control vs data plane; current state and limits |
| [platforms.md](platforms.md) | the deployment-requirements matrix — dual-band (6.8 / rev150) vs tri-band (7.0 / rev120): kernels, the hwsim pool, and why the two need different images (one build flag) |
| [deploy-and-test.md](deploy-and-test.md) | deploy the two containers on the runtime host, bring up the mesh, add clients, validate end-to-end, troubleshoot, teardown |

**6 GHz**

| | |
|---|---|
| [6ghz.md](6ghz.md) | the whole 6 GHz story on Linux 7.0: the 6.8-vs-7.0 kernel setup, the issues found and fixed (single-phy tri-band bring-up, WPA3/SAE + PMF in the WSC M2, the backhaul WDS-before-auth race, OneWifi-restart replay), the SAE-H2E + PMF acceptance, and the standalone hwsim 6 GHz VLP-AP verification (appendix) |

**RF simulation**

| | |
|---|---|
| [wmediumd-multichan.md](wmediumd-multichan.md) | the multichannel wmediumd model (optional RF gradient) — design, patch series, acceptance ladder; runnable tooling lives in this layer's gen/ |

**Steering & policy testing**

| | |
|---|---|
| [steering/steering.md](steering/steering.md) | directed 802.11v client steering — the flow, the `steer_drv`/`steer.sh` tooling, the acceptance test, the gotchas |
| [steering/steering-policy.md](steering/steering-policy.md) | the steering **policy** approach — the closed loop, the EasyMesh agent policy, the controller optimization strategy, the decision state machine, and the required run record |
| [steering/wmediumd-configurator.md](steering/wmediumd-configurator.md) | design for an RF-scenario **configurator** used to exercise steering policies — the scenario language, its semantics, and the compiled event plan on top of wmediumd |

**Reference**

| | |
|---|---|
| [0815-patch-stack.md](0815-patch-stack.md) | clean 0815-codex history, patch classes, deliberate removals, ordered core series and acceptance gates |
| [patches.md](patches.md) | every patch in this layer, by recipe, why it exists (hwsim- / container- / defect-driven), and upstreaming notes |
| [TODO.md](TODO.md) | open work from the latest external review — identity atomicity, 6 GHz capability-gating, Gate B, and more, by priority |
| [../build](../build) | building the two images on the build host |

## Orientation

- **Build host** `rev140` (Ubuntu 20.04) builds the two LXC images. The **runtime
  host** runs the LXD/hwsim lab: `rev150` (kernel 6.8) for the 2.4 + 5 GHz baseline,
  or `rev120` (kernel 7.0) for 6 GHz — see [6ghz.md](6ghz.md) for the 6.8-vs-7.0
  split. Deploy tooling (`bpi.sh`, `wlan-client.sh`) lives in this layer under
  `gen/`.
- Hard invariant: each BPI container gets **exactly one** hwsim phy
  (`FEATURE_SINGLE_PHY`) — see [architecture.md](architecture.md).
- Every patch header carries the trace it was root-caused from (minidump stacks,
  netlink captures, log excerpts) — start there, not from the diff.
