# The RDK EasyMesh lab's documents

[Repository](../README.md) · [Site](https://vcpe.dev/meta-cmf-bananapi-vcpe/)

The [site](https://vcpe.dev/meta-cmf-bananapi-vcpe/) has the system explorer and the
room sandbox. What both optimizer labs share is documented once, with its component:
the RF medium, lab monitoring and the neighbor-rooms proposal in
[easymesh-medium](https://vcpe.dev/easymesh-medium/); the optimizer, the room service
and room access in [easymesh-optimizer](https://vcpe.dev/easymesh-optimizer/). This
lab's documents are below.

| Document | Kind | What it covers |
| --- | --- | --- |
| [Current state](project/current-state.md) | project | the last-tested VM, its qualification, addresses and limits |
| [Architecture](concepts/architecture.md) | concept | the processes, containers and radio model |
| [Optimizer](concepts/optimizer.md) | concept | the external optimizer in this lab |
| [Steering policy](concepts/steering-policy.md) | concept | steering and policy experiments: the operator's control contract |
| [Quickstart](guides/quickstart.md) | guide | validate and use an installed lab |
| [Build](guides/build.md) | guide | the Banana Pi images from a fresh checkout, then a VM |
| [Build a named VM](guides/build-vm.md) | guide | `gen/vm/lxd/build.sh`: build, check, update, the EMOSA option |
| [Operations](guides/operations.md) | guide | deploy, start, stop, recover and validate |
| [Room manual](guides/room-manual.md) | guide | the live room and the network topology |
| [Test suite](guides/test-suite.md) | guide | qualify a ready VM: static, browser, room and soak tests |
| [Experiments](guides/experiments.md) | guide | test changes and measure convergence |
| [Repo mirror](guides/repo-mirror.md) | guide | an optional local mirror for faster source checkouts |
| [DAC / LCM build](guides/dac-lcm-build.md) | guide | an image with the prpl Lifecycle Manager |
| [Test tiers](reference/test-tiers.md) | reference | what each test tier runs and when to use it |
| [Room catalog](reference/room-catalog.md) | reference | every room and what to watch in it |
| [Room acceptance](reference/room-acceptance.md) | reference | room correctness and convergence acceptance |
| [Room coordination](reference/room-coordination.md) | reference | the room service's authority, leases and recovery |
| [Remote access](reference/remote-access.md) | reference | the optional Tailscale gateway and exclusive sessions |
| [Bare metal](reference/bare-metal.md) | reference | direct radio-host operation |
| [Metrics](reference/metrics.md) | reference | STA and AP metrics reporting |
| [Packet capture](reference/packet-capture.md) | reference | capturing the lab's 1905 and Wi-Fi traffic |
| [Commanded steering](reference/commanded-steering.md) | reference | EasyMesh steering on command, end to end |
| [Patch set](reference/patch-set.md) | reference | the consolidated EasyMesh patch set and why each patch stays |
| [Single-wiphy radio model](reference/single-wiphy-radio-model.md) | reference | the MediaTek single-wiphy model on hwsim |
| [Performance](reference/performance.md) | reference | performance and failure attribution |
| [RF qualification](records/rf-qualification.md) | record | RF property qualification and its evidence |
| [Release information](records/release-notes.md) | record | what a VM is built from; shipped in each VM's bundle |
| [VirtualBox qualification](records/virtualbox-qualification.md) | record | the RDK lab in VirtualBox on a Linux host, 8 September 2026 |
| [Rooms: design and plan](proposals/rooms-convergence.md) | proposal | each lab in its own VM behind the gateway, the builder in the labs |
| [Optimizer workbench](proposals/optimizer-workbench.md) | proposal | uploadable optimizer policies developed against replayed journals |
| [A retail extender](proposals/retail-easymesh-extender.md) | proposal | a retail EasyMesh extender on the RDK lab's controller |

Keep each subject in its owning document; put evidence (JSON, logs, screenshots)
beside the release or test artifacts, not here. Run
`python3 gen/tests/test_documentation.py` before submitting documentation changes.
