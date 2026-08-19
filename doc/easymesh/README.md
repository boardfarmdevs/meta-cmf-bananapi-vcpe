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
| [wmediumd-extender-outage.md](wmediumd-extender-outage.md) | Repeatable RF-loss, client recovery, extender isolation and live-WebUI acceptance |
| [wmediumd-client-carousel.md](wmediumd-client-carousel.md) | Visual client disconnect/reconnect rotation across every AP |
| [steering.md](steering.md) | What steering works today, the EasyMesh policy boundary, and how policy experiments should run |
| [optimizer.md](optimizer.md) | How the completely external optimizer observes, decides, acts and verifies without BPI optimizer logic |
| [next-steps.md](next-steps.md) | Prioritized stability, integration, scale and novel-policy research plan |
| [lab-presentation.md](lab-presentation.md) | Presentation-ready lab introduction, current demos and policy roadmap |

These documents are the complete current documentation set. Historical
bring-up notes and superseded 6.8-era decisions remain in Git history rather
than beside current operating instructions.

## Current accepted baseline

```text
source             codex/0815-clean
image runtime code c2e8ce7
host tooling       current codex/0815-clean head
kernel             Linux 7.0.0-28
topology           controller + colocated agent + four extenders
model              5 agents / 15 radios / 50 BSSs
clients            10 active WLAN clients
medium             patched multichannel wmediumd
```

Accepted images:

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller | `easymesh-controller-rootfs-0818.tar.bz2` | `0425fda2a96434fd9c59150e037141c8569208f2bc25fc1e27ce4f7dceef9cd3` |
| extender | `easymesh-extender-rootfs-0818.tar.bz2` | `a4491eec0116d2bc0b2f6f0b438c43e77ec0ca95214d36ac7f80d039e818e6cd` |

rev130 and the rev150 VM are on the same source, kernel, accepted images and
`5/15/50` topology with 10/10 active clients and zero service restarts. Both
have passed 10/10 commanded steering and a dynamic two-AP crossover with
verified medium restoration; the VM also passed an earlier 30/30 matrix.

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
