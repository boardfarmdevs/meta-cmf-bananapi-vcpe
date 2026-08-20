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
| [lab-setup.md](lab-setup.md) | How to build, deploy, scale, access and validate the rev130 and rev150-VM labs |
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
patch series       EasyMesh through 0055, IEEE1905 through 0005
image provenance   record filename, SHA-256 and source revision per deployment
kernel             Linux 7.0.0-28
topology           controller + colocated agent + four extenders
model              5 agents / 15 radios / 50 BSSs
clients            10 active WLAN clients
medium             patched multichannel wmediumd
```

The last fully rebuilt pre-P0 image pair is retained as historical provenance:

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller | `X86EMLTRBPIBB_rdk-next_20260819032857.rootfs.lxc.tar.bz2` | `e5314430402513823c86c3a29823b4d2fbc9e826f381d0bb9c342364f52b8a9f` |
| extender | `X86EMLTRBPIAP_rdk-next_20260819032857.rootfs.lxc.tar.bz2` | `716ef80633e4b3097f2e77e885b828f195778d457d15090db7d00dc62ddc2449` |

That pair does not contain source patches `0047`-`0055`. Current P0 behavior
was proven with rebuilt targeted artifacts on rev130: complete extender
expiry/return, association-owner repair, three cold reconstructions, 10/10
traffic, zero monitored restarts and bounded memory. A full image roll-up and
dual-lab deployment must record its own new hashes before replacing the table.

## Runtime access

From the `192.168.2.0/24` lab network:

```text
http://192.168.2.130:8888    rev130 WebUI
http://192.168.2.150:18889   rev150 Vagrant-VM WebUI
```

SSH into the VM through rev150:

```sh
ssh -tt rev@192.168.2.150 \
  "cd /home/rev/easymesh-vagrant-lab && vagrant ssh"
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
