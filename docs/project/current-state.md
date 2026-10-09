# Current RDK lab

[Documents](../README.md)

Reviewed 7 October 2026. This is the last-tested deployment, not a live health
monitor. See [operations](../guides/operations.md).

## Identity

| Item | Current value |
| --- | --- |
| Branch | `main` |
| Development and build checkout | `rev140:/home/rev/git/easymesh-labs/meta-cmf-bananapi-vcpe` (the easymesh-labs workspace) |
| Last-tested VM | `rev140:rdk-1004` and `rev120:rdk-emosa-1005`, both in the target configuration (below) |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd from easymesh-medium (the `gen/medium` submodule); the optimizer from easymesh-optimizer (the `gen/optimizer` submodule) |
| Images | the controller and extender images the easymesh-labs `manifest.json` pins, with the commit each was built from |
| Fixed pool | 100 clients; the gateway, four Wi-Fi extenders and the wired extender `bpiap-004` (`extender_5`) |
| prplMesh peer | prplmesh-lab; no prplMesh lab runs now |

Controller and Agent-1 share the root container. Default selects ten private
and ten IoT clients; other rooms change presence, not permanent pool size.
Do not enable VM autostart as part of rebuilding or optional remote access.

## Qualification

Every running lab of this repository is in the target configuration: EMOSA wholly in the
gateway image (`EASYMESH_EMOSA=1 EASYMESH_EMOSA_IN=gateway`), with its fleet, one C agent per
pod in a network namespace of its own (so em_ctrl never takes a pod's AL MAC for its
co-located agent), the image's mosquitto as the pods' broker and `emosa-gtp` on the gateway's
onboarding VAP `wifi1.4`. No `emosa` or `em-gtp` container. A VM restart (`build.sh start`)
brings the lab back whole, the pods with it.

| VM | Host, ports | Images | Last qualification |
| --- | --- | --- | --- |
| `rdk-1004` | rev140, 29610 to 29615 | gateway `X86EMLTRBPIBB_rdk-next_20261008233022` (image 18: image 17, which added unified-wifi-mesh 0246 and EMOSA 9d930bc, with 0247 to 0250: the pods' backhaul BSSes backhaul candidates, learned station rows, a backhaul move's operating class on every band and its answer naming another station), extenders `X86EMLTRBPIAP_rdk-next_20261008164642` (the series through 0245) | built from scratch on 8 October (cd9fc41, with free page reporting; 108 minutes): the build's acceptance and the health audit; images 14 and 15 redeployed in place: the health audit each, then an 8-hour soak with the Pis on image 15 (passed: em_ctrl one process, 46.6 to 46.7 MB, no restart; the Pis' agents provisioning throughout). The Pis left rdk-1004 after it (8 October, 16:23 UTC). Image 16 and the extender image redeployed in place (16:53 to 17:40 UTC): the health audit (100 clients, no loss) and two rooms (the wired extender's loss and recovery, the private client's walk with the pods) passed. Image 17 redeployed in place, extenders unchanged (21:38 to 22:24 UTC): the health audit (100 clients, no loss) and the private client's walk with the pods passed. Image 18 the same way (8 October 23:38 to 9 October 00:24 UTC): the controller's backhaul candidates 20 with the pods' backhaul BSSes, the room passed, the health audit on its second run (the first, right after the bring-up, saw loss on clients of every access point). On image 11, 7 October, with the Pis on its controller: the catalog 27 of 27 and the four geometry rooms |
| `rdk-emosa-1005` | rev120, 22010 to 22015 | gateway `X86EMLTRBPIBB_rdk-next_20261008163353` (image 16), extenders `X86EMLTRBPIAP_rdk-next_20261008164642` (the series through 0245) | image 16 and the extender image redeployed in place on 8 October (17:54 to 18:58 UTC): the default room settled once the pods' OpenSync was restarted (each pod held steering rows its agent's journal had pruned, EMOSA finding 23, fixed since), then the health audit, after one client's lease clash was repaired. Image 12 on 7 October: the health audit, the wired extender's outage room; the whole suite before, on image 11 |

What the qualification rests on:

- **The controller's renewals.** unified-wifi-mesh 0233, 0234 and 0239: a radio the
  controller renews on its own waits neither at the Topology Query, the AP Capability Query
  nor the Channel Preference Query for its agent's radios that stayed configured. Without
  them such a radio was renewed again and again, refused candidate queries, and the room
  never settled. 0236 gives the controller the pods' backhaul stations, so a pod's move is
  verified.
- **The journals.** 0237 to 0242 send em_ctrl's and every em_agent's per-message work and
  whole documents to em's debug channel (`/nvram/emCtrlDbg`, `/nvram/emConfDbg`) and take
  the keys out of every line: through a catalog no line is dropped and no passphrase is on a
  journal.
- **EMOSA's stored reporting policy.** One of another radio identity is superseded by the
  controller's next policy, not refused (emosa-lab, in image 12): it had left a stale radio
  in the controller's model after a pod's radio changed.
- **Storage** (easymesh-resources lab-storage). Every lab is in its host's ZFS pool `labs`,
  its room evidence on a volume of its own (`<lab>-evidence`); the pods' journals are capped
  at 128 MiB and the VM's at 256 MiB; Boardfarm's recovery path keeps its images; the base
  image carries only the running kernel. rdk-1004, built from scratch with all of it, holds 2.9 GB on its host (5.7 in the guest); rdk-emosa-1005 6.4 GB.
- **Devices the room does not own.** Physical OpenSync pods on a lab's controller (opensync-rpi's
  Raspberry Pis, over Ethernet, on rdk-1004 until 8 October) are listed by AL MAC in the VM's
  `/etc/easymesh-lab/foreign-devices` and left out of the room's health, the optimizer's
  observer, the acceptance, the health audit and the bring-up's topology count. rdk-1004 keeps
  the Pis' two lines for their return.
- **The outage rooms** give every client 8 s to leave an AP: a 6 GHz client needs 3.7 to
  4.5 s (beacon loss, a scan of every 6 GHz channel, a 1 s association comeback because the
  AP still holds its earlier PMF association).

The evidence is in emosa-lab's rdk-lab record and this repository's
[RF qualification record](../records/rf-qualification.md).

Open, each with what shows it in the easymesh-labs
[open work](https://mesh.vcpe.dev/):

- The controller's memory grows while the mesh keeps re-forming; it is killed at
  the gateway's 1 GiB limit, which stays as it is. Idle and through the rooms it
  is flat.
- Under heavy contention for the host's CPU the extenders keep leaving and
  rejoining their backhaul.
- A controller that restarts on its own comes back with part of the model;
  `gen/lab-bringup.sh up` restores it.
- The gateway forgets its DHCP leases at every start (meta-cmf-filogic's utopia bbappend),
  while the clients keep their addresses and never ask again; dnsmasq can then give an
  address a client off the air still holds to a pod or an extender, and that client's
  traffic goes to the other device. Fixed in this repository's `utopia.bbappend`, from
  image 13 (rdk-1004 since 8 October); in a lab still on an older image, a client the
  health audit fails after a gateway start is repaired with a new lease (`udhcpc -i wlan0
  -n -q` in it).

Build and test one lab at a time on rev140: with a second lab running, the
build's traffic check loses packets. With a lab VM and its browser on one host,
rev140 runs at load 15 to 20 and rooms with short windows can miss them: run the
room browser from another host (`--host`, `--room-url`, `--topology-url`). On rev120 the
suite needs `EASYMESH_HOST_ADDRESS=192.168.2.120` and `EASYMESH_SSH_HOST=rev120`, where the
VM's proxies listen on the host's address. Do not relax deadlines, disable native admission
checks or invent unavailable metrics to make a run green; the RF qualification record holds
the attribution of past failures.

## Rebuild

A new VM from scratch: the [build guide](../guides/build.md)
(`gen/vm/lxd/build.sh build`), from a clean checkout; the medium and the optimizer
come from the `gen/medium` and `gen/optimizer` submodules at the commits this
repository pins, EMOSA from emosa-lab at the commit `gen/vm/lxd/emosa-lab.env`
pins. A change the lab runs from its checkout (the optimizer, the room service)
moves an accepted VM in place: `gen/vm/lxd/build.sh update`. New images into a
running lab: `gen/lab-redeploy.sh`, then, with the EMOSA option, `build.sh emosa` to set
EMOSA's forwarding and pods up again (the room service refuses to start while the pods
cannot reach EMOSA). Keep old VMs stopped until their replacements pass.

EMOSA in the controller image is opt-in and off by default: the recipe
`recipes-emosa/emosa` with `EMOSA_ADAPTER = "1"` (`BUILD_EMOSA=1 gen/build/build-images.sh
controller`) installs emosa-lab's C programs at the pinned commit (the package `emosa`,
520 KiB; without the setting the image's packages are the default's), logging through
RDK's logger into `/rdklogs/logs`, the fleet enabled and inert until `/etc/emosa-fleet.json`
exists, and the GRE termination point inert until `/etc/emosa-gtp.json` exists
(`EMOSA_GTP = "0"` leaves it out). The image keeps EMOSA's configuration and state on
`/nvram/emosa`, which an image upgrade keeps, and its agents' status in `/run/emosa`; the
fleet starts its agents at boot, and after a controller restart the pods return by
themselves within about two minutes (an agent onboards again after 120 s without a Topology
Query). In the gateway an agent takes about 5 MiB and 0.46 % of a core; the gateway held
506 MiB median of its 1 GiB through five rooms. The recipe's license is emosa-lab's:
Apache-2.0.

## Access

The last-tested VM's addresses, not a health promise:

| View | `rdk-1004` |
| --- | --- |
| Live room | <http://192.168.2.140:29612/> |
| Network topology | <http://192.168.2.140:29610/> |
| Console NG | <http://192.168.2.140:29611/> |

Each new VM name receives its own port block. See
lab monitoring (in [easymesh-medium](https://vcpe.dev/easymesh-medium/)) for LXD and Grafana. Remote
access is the host's gateway, [easymesh-remote](https://vcpe.dev/easymesh-remote/); a published
lab goes into its maintenance mode while it is worked on.

## Supported behavior and boundaries

- Loading applies a world immediately; Play, drag, presence, traffic probes,
  signal colors, fullscreen and room-following topology are supported.
- The external optimizer supplies client policy through native BTM; this is not
  a claim of native autonomous client optimization.
- Most rooms protect startup backhaul; three geometry rooms exercise native
  parent adaptation. Loss recovery and proactive steering are separate checks.
- Convergence requires native membership, ownership, fresh eligible measurements
  and traffic, not just a green badge or an accepted request.
- Host cooling and observer load remain separate from native steering latency.
- Neighbor-network rooms (in [easymesh-medium](https://vcpe.dev/easymesh-medium/)) remain proposed;
  [room acceptance](../reference/room-acceptance.md) defines the tests.
