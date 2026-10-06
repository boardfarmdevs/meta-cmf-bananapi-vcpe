# Current RDK lab

[Documents](../README.md)

Reviewed 6 October 2026. This is the last-tested deployment, not a live health
monitor. See [operations](../guides/operations.md).

## Identity

| Item | Current value |
| --- | --- |
| Branch | `main` |
| Development and build checkout | `rev140:/home/rev/git/easymesh-labs/meta-cmf-bananapi-vcpe` (the easymesh-labs workspace) |
| Last-tested VM | `rev140:rdk-1004` (with the EMOSA option, EMOSA in the gateway); `rev120:rdk-emosa-1002` (the same, updated in place) |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd from easymesh-medium (the `gen/medium` submodule); the optimizer from easymesh-optimizer (the `gen/optimizer` submodule) |
| Images | the controller and extender images the easymesh-labs `manifest.json` pins, with the commit each was built from |
| Fixed pool | 100 clients; the gateway, four Wi-Fi extenders and the wired extender `bpiap-004` (`extender_5`) |
| prplMesh peer | prplmesh-lab; last-tested VM `rev140:prpl-1002` |

Controller and Agent-1 share the root container. Default selects ten private
and ten IoT clients; other rooms change presence, not permanent pool size.
Do not enable VM autostart as part of rebuilding or optional remote access.

## Qualification

On 6 October `rdk-1004` took everything of EMOSA's into its gateway, the containers
`emosa` and `em-gtp` deleted: EMOSA's ports on the gateway's LAN through its forwarder
(1b6a68b), the pods' broker the image's mosquitto (165fdb5), and their GRE termination point
the image's `emosa-gtp` on the gateway's own onboarding VAP, `wifi1.4` (c5abb1d: OneWifi's
libwebconfig 0014 keeps lnf_radius VAPs out of EasyMesh, the pre-start makes the VAP map's
extra interfaces, `emosa-podbh` gives the VAP its SSID at each OneWifi start, and utopia
0001 has dnsmasq bind per interface). With the controller image
`X86EMLTRBPIBB_rdk-next_20261006083201`, redeployed in place, the pods came back through the
gateway on their own and the room catalog (27 rooms) and the four geometry rooms passed
twice, 62 of 62 (emosa-lab 04189dc, its rdk-lab record).

`rdk-1004` replaced `rdk-1002b` on rev140 on 5 October: built from scratch at d70f1c3 with the EMOSA option and `EASYMESH_EMOSA_IN=gateway` (the controller image built that day with EMOSA, emosa-lab 68515a2), 92 minutes, the lab's acceptance included. It is the target configuration. Fixed the same day (emosa-lab's rdk-lab record): `traffic-quieter-ap`'s screenshot timeouts were the browser harness rendering in software (36ce8d5); a VM restart now brings the lab back whole (7ee964a); and RDK's native backhaul steering never measured a candidate, so `backhaul-parent-handover` failed, because em_ctrl took an EMOSA agent, whose AL MAC was on one of the gateway's interfaces, for its co-located agent: the agents now live in a network namespace of their own (ceebf4c, emosa-lab 0a4bbcb). With that gateway image, redeployed in place, it passed the room catalog (27 rooms) three times and the four geometry rooms after each of two. unified-wifi-mesh 0236 (ca7bc1e) then gave the controller the pods' backhaul stations, so a pod's move is verified and leaves no uncertain mark: two more rounds passed the geometry rooms both times and 26 of 27 catalog rooms each, `home-a-wired-extender-loss-recovery` failing once at its 5 s outage boundary (2 of 8 runs) and once at the browser harness under another build's load. A pod whose remembered backhaul BSS is gone after a restart now falls back to the configured one instead of staying on GRE (emosa-lab 83f4ce4, finding 18; emosa-lab's rdk-lab record).

`rdk-1002b` was built from scratch on rev140 on 2 October, from this repository as
it is after its cleanup (the build scripts under `gen/build`, the documents under
`docs/`), with a controller image `gen/build/build-images.sh` built that day. It
passed the build's acceptance and, with the browser on rev150, readiness, five
rooms (`home-a-one-client-handover`, `band-upgrade-24-5`, `received-same-band-roam`,
`large-room-perimeter-counter-roam`, `traffic-quieter-ap`), `backhaul-wired-parent`
and `fifty-client-counter-roam`. `rdk-emosa-1002` (rev120, the EMOSA option) was
built the same day and passed readiness, the five rooms with the pods and
`backhaul-wired-parent`. On 3 October it took emosa-lab's adapter in C
(`EASYMESH_EMOSA_AGENT=c`: the fleet, the GTP and the agents, with no Python) and passed
readiness, the five rooms with the pods, `backhaul-wired-parent` and
`fifty-client-counter-roam` again. With emosa-lab after its plan 8.4 (the adapter's
features at its production bar) the full rooms section ran on it the same day with
the adapter in C: 26 of the catalog's 27 rooms on rev120 and the 27th
(`home-a-wired-extender-loss-recovery`, a client move between two native extenders
1 s past its check) in 4 of 4 runs after, the four geometry rooms, the RF stages and
the switch through every world. The suite needs `EASYMESH_HOST_ADDRESS=192.168.2.120`
and `EASYMESH_SSH_HOST=rev120` on rev120, where the VM's proxies listen on the host's
address.

The controller image carries unified-wifi-mesh 0233 and 0234: a radio the
controller renews on its own waits neither at the Topology Query nor at the AP
Capability Query for its agent's radios that stayed configured. Without 0234 such
a radio was renewed again every 88 seconds and reported on no client of its band;
with the EMOSA option the room then never settled.

Open, each with what shows it in the easymesh-labs
[open work](https://mesh.vcpe.dev/):

- The controller's memory grows while the mesh keeps re-forming; it is killed at
  the gateway's 1 GiB limit, which stays as it is. Idle and through the rooms it
  is flat.
- Under heavy contention for the host's CPU the extenders keep leaving and
  rejoining their backhaul.
- A controller that restarts on its own comes back with part of the model;
  `gen/lab-bringup.sh up` restores it.

Build and test one lab at a time on rev140: with a second lab running, the
build's traffic check loses packets. With a lab VM and its browser on one host,
rev140 runs at load 15 to 20 and rooms with short windows can miss them: run the
room browser from another host (`--host`, `--room-url`, `--topology-url`). Do not
relax deadlines, disable native admission checks or invent unavailable metrics to
make a run green; the [RF qualification record](../records/rf-qualification.md)
holds the evidence and the attribution of past failures.

## Rebuild

A new VM from scratch: the [build guide](../guides/build.md)
(`gen/vm/lxd/build.sh build`), from a clean checkout; the medium and the optimizer
come from the `gen/medium` and `gen/optimizer` submodules at the commits this
repository pins, EMOSA from emosa-lab at the commit `gen/vm/lxd/emosa-lab.env`
pins. A change the lab runs from its checkout (the optimizer, the room service)
moves an accepted VM in place: `gen/vm/lxd/build.sh update`. New images into a
running lab: `gen/lab-redeploy.sh`. Keep old VMs stopped until their
replacements pass.

EMOSA in the controller image itself is opt-in and off by default (the recipe
`recipes-emosa/emosa`, `EMOSA_ADAPTER = "1"`; `BUILD_EMOSA=1 gen/build/build-images.sh
controller`): emosa-lab's C programs at the same pinned commit, logging through RDK's
logger into `/rdklogs/logs`, the fleet enabled and inert until `/etc/emosa-fleet.json`
exists, and (plan 5.2, decided 4 October) the GRE termination point, inert until
`/etc/emosa-gtp.json` exists (`EMOSA_GTP = "0"` leaves it out). Built on 3 October on rev140 (`X86EMLTRBPIBB_rdk-next_20261004013832`): it
differs from the default image only by the package `emosa` (520 KiB); without the
setting the image's packages are the default's. The lab's EMOSA option keeps the
adapter in its own container; emosa-lab's `gateway.sh` moves it into the gateway's
container with that package and back. There, on 3 October (rdk-emosa-1002), RDK's
controller onboarded both pods' agents, and over 30 minutes with five rooms the gateway
held 506 MiB median and 592 MiB peak of its 1 GiB (487 and 498 MiB with EMOSA in its own
container), an agent about 5 MiB and 2.8 % of a core (emosa-lab's rdk-lab record).
With the journal bounded and kept parsed (emosa-lab f4011e8, the image's package built
again with it) the same run gave 0.46 % of a core per agent and five rooms of five. Since
emosa-lab 2a2d009 an agent writes its reporting policy only when the controller sends one,
no longer twice per periodic report (some 140 MB a day per pod at the controller's 5 s
interval). The recipe's license is emosa-lab's: Apache-2.0. The image keeps EMOSA's
configuration and state on `/nvram/emosa`, which an image upgrade keeps, and its agents'
status in `/run/emosa`. `EASYMESH_EMOSA_IN=gateway` (with the EMOSA option) runs EMOSA
in the gateway from that package, the image checked for it before the build. Since
4 October `rdk-emosa-1002` runs the image built at emosa-lab ee34885
(`X86EMLTRBPIBB_rdk-next_20261004213513`, deployed with `gen/lab-redeploy.sh`) with EMOSA in
the gateway, set up by the build's own step with that option (`build.sh emosa`). After the
upgrade EMOSA's fleet started its agents at boot; after a controller restart (also the one
`gen/lab-bringup.sh` does) the pods return by themselves within about two minutes (their
agents onboard again after 120 s without a Topology Query); readiness and the five
quick-requalification rooms passed (one rerun after a browser screenshot timeout). A
redeploy ends with the room service refusing to start while the pods cannot reach EMOSA:
emosa-lab's `gateway.sh on` (or `lab.sh up c gateway`) puts the forwarding back
(emosa-lab's rdk-lab record).

## Access

The last-tested VM's addresses, not a health promise:

| View | `rdk-1004` |
| --- | --- |
| Live room | <http://192.168.2.140:29612/> |
| Network topology | <http://192.168.2.140:29610/> |
| Console NG | <http://192.168.2.140:29611/> |

Each new VM name receives its own port block. See
lab monitoring (in [easymesh-medium](https://vcpe.dev/easymesh-medium/)) for LXD and Grafana. The optional
[Tailscale gateway](../reference/remote-access.md) is implemented and locally
tested, **not installed or published**; leave it disabled for a VM's first
qualification.

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
