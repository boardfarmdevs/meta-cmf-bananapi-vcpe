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
| [wmediumd-observability.md](wmediumd-observability.md) | How the Go wmediumd Console exposes live medium paths, rules, packet outcomes and bounded typed controls |
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
patch series       EasyMesh through 0113, IEEE1905 through 0006
image provenance   record filename, SHA-256 and source revision per deployment
kernel             Linux 7.0.0-28
topology           controller + colocated agent + four extenders
model              5 agents / 15 radios / 50 BSSs
clients            accepted 20-client profile (10 private + 10 IoT)
medium             patched multichannel wmediumd
```

The current deployment deliberately records each role independently. The
controller artifact contains EasyMesh through `0113`, including end-to-end
backhaul-signal freshness and the current WebUI/API helper. The extender
artifact contains the complete Agent recovery series through `0112`.
IEEE1905 remains at `0006`; the previously accepted OneWifi, libwebconfig,
Wi-Fi HAL, log4c and SNMP fixes remain in both roles as applicable.

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| controller | `X86EMLTRBPIBB_rdk-next_20260824075700.rootfs.lxc.tar.bz2` | `894fa478298afa8de7f8198df6e158e9f9d2dae525d867d982f9ecaf8047122d` |
| extender | `X86EMLTRBPIAP_rdk-next_20260824045243.rootfs.lxc.tar.bz2` | `676aa29dc9a3133b63dd48d09aca3457ac4c398fc77c4f54e7c4e113acaf61bd` |

The current Phase 1/2 runtime checkout is `8d1c49a`; the controller helper and
image input are captured by `fb3bf7e`. The controller also refreshes packaged
WebUI assets into persistent `/nvram/static` on every service start, so a
same-identity upgrade cannot continue serving an older UI. Never infer image
contents from a newer host checkout.

On 2026-08-23/24 the preceding `a9689eb` package baseline was independently
recreated from fresh containers in the rev120 and rev150 Vagrant VMs. Both the
initial deployment and persistent stop/start reconstruction passed
`5/15/50/24`, 10 private plus 10 IoT clients, all 20 non-zero RCPI reports,
four live backhaul metric edges, 20/20 zero-loss health traffic and zero
automatic EasyMesh/OneWifi restarts. Client associations included 2.4, 5 and
6 GHz. Current Phase 1/2 acceptance adds structured signal-freshness and
wmediumd Console gates on both rev120 and rev150. Independent destructive fresh
deployments and managed reconstructions passed at `5/15/50/24`, with four
`fresh` structured extender signals, 25/25 Console identities, 600 directed
pairs, packet telemetry, 20/20 traffic and zero monitored restarts. Evidence is
retained at `/home/vagrant/easymesh-evidence/20260824T085518Z` on rev120 and
`/home/vagrant/easymesh-evidence/20260824T081445Z` on rev150. The 20-client
duration/RF-churn gate remains
distinct from these immediate results; see
[client-scale.md](client-scale.md) and [soak-acceptance.md](soak-acceptance.md).

The previously accepted ready-to-run Vagrant/VirtualBox package is
`easymesh-lab-0824-a9689eb.box` (`16,560,643,152` bytes), SHA-256
`7d546151bde3d9c2174c7e26046f616894c557e27c843dac4a88050ad4f8fdb1`.
That immutable package is the `a9689eb` baseline and predates the wmediumd
Console and EasyMesh `0113`; regenerate a box from the current VM before
claiming those additions in a distributable appliance.
Use `gen/vm/consumer/Vagrantfile` and the import/start procedure in
`gen/vm/packaged/README.md`.

## Runtime access

From the `192.168.2.0/24` lab network:

```text
http://192.168.2.130:8888    rev130 WebUI
http://192.168.2.150:18889   rev150 Vagrant-VM WebUI
http://192.168.2.120:18889   rev120 Vagrant-VM WebUI
http://192.168.2.150:18890   rev150 Vagrant-VM wmediumd Console
http://192.168.2.120:18890   rev120 Vagrant-VM wmediumd Console
```

SSH into the VM through rev150:

```sh
ssh -tt rev@192.168.2.150 \
  "cd /home/rev/easymesh-lab/0821 && vagrant ssh"
```

For the clean-install rev120 VM:

```sh
ssh -tt rev@192.168.2.120 \
  "cd /home/rev/easymesh-lab/0821 && vagrant ssh"
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
