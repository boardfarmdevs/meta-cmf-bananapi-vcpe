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
| [next-steps.md](next-steps.md) | Prioritized stability, integration, scale and novel-policy research plan |
| [lab-presentation.md](lab-presentation.md) | Presentation-ready lab introduction, current demos and policy roadmap |

These documents are the complete current documentation set. Historical
bring-up notes and superseded 6.8-era decisions remain in Git history rather
than beside current operating instructions.

## Current source and accepted scale

```text
source             codex/0815-clean
patch series       EasyMesh through 0056, IEEE1905 through 0005
image provenance   record filename, SHA-256 and source revision per deployment
kernel             Linux 7.0.0-28
topology           controller + colocated agent + four extenders
model              5 agents / 15 radios / 50 BSSs
clients            10 active WLAN clients
medium             patched multichannel wmediumd
```

The current fully rebuilt image pair contains the complete P0 source patch set
through EasyMesh `0055`, IEEE1905 `0005`, and the serialized log4c category
factory fix. It was built from source revision
`9a9bd454c5c466a21b8bc44b7e83d279597c4e99`:

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller | `X86EMLTRBPIBB_rdk-next_20260820022527.rootfs.lxc.tar.bz2` | `af446b9610a9d030c6a642903a65b770a3fe49295f813788f32398ab13eed090` |
| extender | `X86EMLTRBPIAP_rdk-next_20260820023708.rootfs.lxc.tar.bz2` | `fd731d207cf2bc5139d62bade5ee73f2f4ee9de33f452b7848c3844f6bce248e` |

Fresh deployments of this exact pair on rev130 and the rev150 VM reached the
complete `5/15/50/14` model and ten live clients, held zero monitored service
restarts, passed 10/10 traffic and a fresh 10/10 steering matrix. The rev130
demo rehearsal additionally passed client carousel, RF-only extender
expiry/return, live RCPI cycling, and a complete identity-preserving
reconstruction.

EasyMesh `0056` is newer than that image pair. Its targeted extender agent was
built from revision `7536d8c`, deployed to a clean rev120 VM, and passed two
consecutive identity-preserving cold reconstructions. The next full image
roll-up must include `0056`; image contents are never inferred from the newer
host checkout.

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
