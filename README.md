# meta-cmf-bananapi-vcpe: the RDK EasyMesh lab

<!-- labs block: the same in every repository of the EasyMesh labs, but for the Site line -->
**Site:** <https://vcpe.dev/meta-cmf-bananapi-vcpe/>
The [EasyMesh labs](https://mesh.vcpe.dev/) serve three
goals: EasyMesh optimizer development
([easymesh-optimizer](https://vcpe.dev/easymesh-optimizer/)) in a rich
virtual lab, on both stacks
([RDK EasyMesh](https://vcpe.dev/meta-cmf-bananapi-vcpe/),
[prplMesh](https://vcpe.dev/prplmesh-lab/)); unchanged OpenSync
pods as EasyMesh agents under a local controller, without the OpenSync cloud
([EMOSA](https://vcpe.dev/emosa-lab/), with the
[OpenSync lab](https://vcpe.dev/opensync-lab/)'s pods); and
EasyMesh on physical hardware
([Protocol lab](https://vcpe.dev/easymesh-lab/)). Two core
components carry them: the RF medium
([easymesh-medium](https://vcpe.dev/easymesh-medium/)) and EMOSA's
OVSDB ⇄ EasyMesh conversion. The rest is infrastructure, tools (the
[room builder](https://vcpe.dev/easymesh-room-builder/)) and learning
around them.
<!-- /labs block -->

A Yocto layer that retargets the **Banana Pi R4 (MediaTek Filogic / MT7988) RDK-B
broadband build** to **x86 userspace packaged as LXC containers**, and the lab that runs
them: an LXD VM with the controller, Wi-Fi extenders, a wired extender and 100 clients
on simulated radios, the RF medium, the optimizer and an interactive room.

The containers run the same RDK-B userspace the physical Banana Pi runs (utopia,
ccsp-*, RdkWanManager, OneWifi, rbus, …) with no kernel modules. Wi-Fi comes from
`mac80211_hwsim` radios moved into each container as physical NICs; the
`HWSIM_RADIO`-gated patches adapt what hwsim lacks (MLO, three concurrent channel
contexts, MAC ACLs), and the ungated ones fix defects that are real on hardware too.
Each patch header carries the trace it was root-caused from. The two machines are
the two EasyMesh roles: `qemux86bpibroadband` is the controller (with a colocated
agent), `qemux86bpiap` the extender; together they form a mesh over the simulated
radios: 1905 transport, AP autoconfiguration, WSC M1/M2, wireless backhaul and the
fronthaul the controller pushes.

## Components

| Part | What it is |
| --- | --- |
| [conf/machine/](conf/machine) | the two x86 container machines |
| [recipes-ccsp/unified-wifi-mesh/](recipes-ccsp/unified-wifi-mesh) | the EasyMesh controller and agent: fixes, the database bootstrap, `steer_drv`, the em_cli tooling, the topology page from the medium |
| [recipes-ccsp/hal/rdk-wifi-hal/](recipes-ccsp/hal/rdk-wifi-hal) | the Wi-Fi HAL: `HWSIM_RADIO`-gated adaptations and defect fixes |
| [recipes-ccsp/ccsp/](recipes-ccsp/ccsp) | OneWifi's radio and security defaults for hwsim; its EasyMesh translation and association snapshots |
| [recipes-ccsp/ieee1905/](recipes-ccsp/ieee1905), [recipes-ccsp/rdk-wifi-libhostap/](recipes-ccsp/rdk-wifi-libhostap) | 1905 service lifecycle and topology publication; hostapd and supplicant fixes |
| [recipes-core/images/](recipes-core/images) | the container image customisations |
| [gen/build/](gen/build) | the image build: the pinned upstream manifest, the source bootstrap and the BitBake run |
| [gen/vm/](gen/vm/README.md) | the lab VM: `gen/vm/lxd/build.sh` builds, checks and updates it, with or without EMOSA |
| [gen/](gen/README.md) | the host-side lab tooling: container deployment, clients, steering, redeploys |
| [gen/rooms/](gen/rooms/README.md) | the lab's live room: its launcher, manifests and bindings |
| [gen/tests/](gen/tests/README.md) | the suites: static, browser, room and soak |
| [gen/explorer/](gen/explorer/README.md) | the site: the system explorer and the room sandbox |
| `gen/medium`, `gen/optimizer` | easymesh-medium and easymesh-optimizer, pinned as submodules |

## Getting started

Build the images, then a VM from them, then qualify it. The clone's parent directory
is the workspace for the RDK sources, the builds and their evidence:

```sh
mkdir -p ~/yocto/easymesh-bpi && cd ~/yocto/easymesh-bpi
git clone --recurse-submodules https://github.com/boardfarmdevs/meta-cmf-bananapi-vcpe.git
cd meta-cmf-bananapi-vcpe
bash gen/build/bootstrap-sources.sh          # the pinned RDK sources
bash gen/build/build-images.sh both          # the controller and extender images
source gen/build/lab-config.sh demo-a        # the VM's name, pool and ports
EASYMESH_CONTROLLER_IMAGE=... EASYMESH_EXTENDER_IMAGE=... gen/vm/lxd/build.sh build
gen/tests/run-easymesh-suite.sh all --yes-act
```

The [build guide](docs/guides/build.md) has the host prerequisites and every step; the
[quickstart](docs/guides/quickstart.md) uses an installed lab.

## Documentation

The [site](https://vcpe.dev/meta-cmf-bananapi-vcpe/) has the system explorer and the
room sandbox. The documents are indexed in [docs/README.md](docs/README.md): the current
state, the architecture, the build, operations, the room manual, the tests and the
reference, records and proposals.
