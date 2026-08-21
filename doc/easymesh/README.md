# EasyMesh evaluation lab

This directory is the authoritative documentation for the 0815-codex EasyMesh
lab. The lab runs the Banana Pi RDK-B EasyMesh userspace in LXD containers with
Linux 7.0 `mac80211_hwsim` radios and a patched multichannel wmediumd.

The purpose is repeatable onboarding and steering experimentation, including RF
gradients that are independent from the steering decision being evaluated.

## Read in this order

| Document | Question it answers |
| --- | --- |
| [architecture.md](architecture.md) | What runs where, how the control and data planes work, and how nodes onboard |
| [patch-set.md](patch-set.md) | Which 0815 patches are retained, why they exist, and what was removed from 0814 |
| [lab-setup.md](lab-setup.md) | How to build, deploy, scale, access and validate the direct and Vagrant-VM labs |
| [demo-scenarios.md](demo-scenarios.md) | Operator-led rev130 demonstrations: manual steer, live RCPI, client carousel, extender outage and full reconstruction |
| [packet-capture.md](packet-capture.md) | How to capture plaintext EasyMesh, agent/client traffic and safely handle the raw 802.11 boundary |
| [wmediumd.md](wmediumd.md) | What the medium can simulate, how radios and frames are resolved, and which static and live controls remain |
| [configurator.md](configurator.md) | How RF scenarios are described and applied dynamically through wmediumd |
| [metrics-reporting.md](metrics-reporting.md) | Why STA/AP metrics were inactive, how they are configured, and how to verify the live observation path |
| [memory-footprint.md](memory-footprint.md) | Measured whole-container and per-process memory during cold reconstruction and convergence |
| [wmediumd-extender-outage.md](wmediumd-extender-outage.md) | Repeatable RF-loss, client recovery, extender isolation and live-WebUI acceptance |
| [wmediumd-client-carousel.md](wmediumd-client-carousel.md) | Visual client disconnect/reconnect rotation across every AP |
| [steering.md](steering.md) | What steering works today, the EasyMesh policy boundary, and how policy experiments should run |
| [optimizer.md](optimizer.md) | How the completely external optimizer observes, decides, acts and verifies without BPI optimizer logic |
| [optimizer-scenarios.md](optimizer-scenarios.md) | How deterministic homes, mobility, walls, RF goldens and traffic profiles form the optimizer test matrix |
| [next-steps.md](next-steps.md) | Prioritized stability, integration, scale and novel-policy research plan |
| [lab-presentation.md](lab-presentation.md) | Presentation-ready lab introduction, current demos and policy roadmap |

These documents are the complete current documentation set. Historical
bring-up notes and superseded 6.8-era decisions remain in Git history rather
than beside current operating instructions.

## Current source and accepted scale

```text
source             codex/0815-clean
patch series       EasyMesh through 0059, IEEE1905 through 0005
image provenance   record filename, SHA-256 and source revision per deployment
kernel             Linux 7.0.0-28
topology           controller + colocated agent + four extenders
model              5 agents / 15 radios / 50 BSSs
clients            10 active WLAN clients
medium             patched multichannel wmediumd
```

The current deployment deliberately records each role independently. The
controller contains EasyMesh through `0059`, IEEE1905 through `0005`, the
serialized log4c category-factory fix, and the cross-user SNMP self-heal fix.
The extenders add OneWifi `0012`, which resolves an extender AL MAC shared by
its bridge and backhaul STA without delaying DML and backhaul publication.

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller | `X86EMLTRBPIBB_rdk-next_20260820210038.rootfs.lxc.tar.bz2` | `da74e07dfece8653bc76d9c821324b75cc72e783d85e681f7524554cc671dc6e` |
| extender | `X86EMLTRBPIAP_rdk-next_20260820202147.rootfs.lxc.tar.bz2` | `5468a70d0c5345866d2592062575bf8b197466f1970ca25837b9909a40d8ac29` |

The controller was built at `3c8a41f1fc868cd3ec823ea722430b152e20e4e7`;
the extender was built at `a50a008152c7c3860af73b58af4bb8b944c777e7`.
The different revisions are intentional because `0012` changes only the
extender's OneWifi discovery path. The controller also refreshes packaged
WebUI assets into persistent `/nvram/static` on every service start, so a
same-identity upgrade cannot continue serving an older UI. Never infer image
contents from a newer host checkout.

A fresh 2026-08-20 deployment of this exact pair on rev130 passed
`5/15/50/14`, ten-client topology and traffic, a 120-second stable window, and
zero monitored service restarts. Three two-second topology polls were
byte-identical after convergence. The controller served
`topology-layout-optimized-1`, and the live JavaScript regression verified
that optimization changes D3's render nodes without mutating the API model.

## Runtime access

From the `192.168.2.0/24` lab network:

```text
http://192.168.2.130:8888    rev130 WebUI
http://192.168.2.150:18889   rev150 Vagrant-VM WebUI
http://192.168.2.120:18889   rev120 Vagrant-VM WebUI
```

SSH into the VM through rev150:

```sh
ssh -tt rev@192.168.2.150 \
  "cd /home/rev/easymesh-vagrant-lab && vagrant ssh"
```

For the clean-install rev120 VM:

```sh
ssh -tt rev@192.168.2.120 \
  "cd /home/rev/easymesh-lab/0820 && vagrant ssh"
```

## Documentation rules

- 0815-codex is the working implementation; 0814 is comparison material only.
- Record source revision, image hashes and live container provenance for every
  result.
- Do not describe commanded steering as an autonomous steering policy.
- Do not add host-specific diaries here. Convert a finding into architecture,
  setup, patch rationale, configurator semantics or steering behavior.
- A successful API response, 1905 ACK or association alone is not an end-to-end
  pass; use the gates in [lab-setup.md](lab-setup.md).
