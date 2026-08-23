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
| [client-scale.md](client-scale.md) | How private/IoT cohorts grow from the accepted 20-client profile toward 50 and 100 clients |
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
| [optimizer-manual.md](optimizer-manual.md) | How operators run the optimizer and how researchers add snapshots, live adapters, metrics, policies and scenarios |
| [optimizer-scenarios.md](optimizer-scenarios.md) | How deterministic homes, mobility, walls, RF goldens and traffic profiles form the optimizer test matrix |
| [next-steps.md](next-steps.md) | Prioritized stability, integration, scale and novel-policy research plan |
| [soak-acceptance.md](soak-acceptance.md) | Exact 12-hour topology, traffic, candidate-RCPI, restoration and memory gates |
| [lab-presentation.md](lab-presentation.md) | Presentation-ready lab introduction, current demos and policy roadmap |

These documents are the complete current documentation set. Historical
bring-up notes and superseded 6.8-era decisions remain in Git history rather
than beside current operating instructions.

## Current source and accepted scale

```text
source             codex/0815-clean
patch series       EasyMesh through 0104, IEEE1905 through 0006
image provenance   record filename, SHA-256 and source revision per deployment
kernel             Linux 7.0.0-28
topology           controller + colocated agent + four extenders
model              5 agents / 15 radios / 50 BSSs
clients            20 active WLAN clients (10 private + 10 IoT) on rev130
medium             patched multichannel wmediumd
```

The current deployment deliberately records each role independently. The
controller contains EasyMesh through `0104`, IEEE1905 through `0006`, OneWifi
through `0018`, libwebconfig through `0010`, Wi-Fi HAL through `0026`, the
serialized log4c category-factory fix, and the cross-user SNMP self-heal fix.
The extender artifact contains every AP-side change needed by the same lab;
the final controller-only metrics confirmation and database reconciliation do
not require a second AP rebuild.

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller | `X86EMLTRBPIBB_rdk-next_20260823165225.rootfs.lxc.tar.bz2` | `c4e2965b20ca9c1c5906bb1f31e368370708dbbab08f6e15efd6a10623018825` |
| extender | `X86EMLTRBPIAP_rdk-next_20260823141018.rootfs.lxc.tar.bz2` | `0d35c1e6df576b97cb6f8be9e25fec9914fce35b55852ceb19776c300a4b7bb8` |

The accepted platform source is recorded by commit `d353c65`; the matching
host-side scale and acceptance tooling is commit `5280bb4`. The controller
also refreshes packaged
WebUI assets into persistent `/nvram/static` on every service start, so a
same-identity upgrade cannot continue serving an older UI. Never infer image
contents from a newer host checkout.

A fresh 2026-08-23 deployment of this exact pair on rev130 passed the immediate
20-client gate at `5/15/50/24`: 10 private clients, 10 IoT clients, deliberate
2.4/5/6 GHz client associations, four wireless backhauls, 20/20 zero-loss
health traffic and zero automatic service restarts. Cold chain and branch
multi-hop trees both passed exact physical-link, forwarding, API-edge,
RSSI/RCPI and database checks. A controller-only restart then reconstructed
the branch at the same `5/15/50/24` invariant. The 20-client duration/RF-churn
gate remains distinct from this immediate result; see
[client-scale.md](client-scale.md) and [soak-acceptance.md](soak-acceptance.md).

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
