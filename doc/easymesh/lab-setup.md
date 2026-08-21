# Lab setup and operation

> The reproducible VirtualBox/Vagrant appliance, including Docker and the full
> Boardfarm installation, is maintained under `gen/vm/`. Its README is the
> canonical VM lifecycle and navigation guide. `gen/vm/thin/` documents the
> recommended Ubuntu 24.04 + Linux 7 image and one-time online installer;
> `gen/vm/precooked/` retains the complete offline appliance.

## Supported labs

| System | Role |
| --- | --- |
| rev140 | Yocto build host; does not run the lab |
| rev130 | direct Linux 7.0/LXD runtime |
| rev150 Vagrant VM | portable Linux 7.0/LXD runtime; accepted peer result |
| rev120 Vagrant VM | clean-install/portability acceptance runtime |

0815-codex is authoritative on all four systems. The three runtime labs are
peers: results are comparable only when source revision, image hashes, kernel,
topology, clients, wmediumd and test parameters match.

## Image provenance

Every deployment must record the exact image filenames and hashes. The current
fully rebuilt pair is:

```text
controller source         3c8a41f1fc868cd3ec823ea722430b152e20e4e7
extender source           a50a008152c7c3860af73b58af4bb8b944c777e7
image EasyMesh content    through EasyMesh 0059 and IEEE1905 0005
host tooling              codex/0815-clean at 3c8a41f or later
kernel                    7.0.0-28-generic
controller image          X86EMLTRBPIBB_rdk-next_20260820210038.rootfs.lxc.tar.bz2
extender image            X86EMLTRBPIAP_rdk-next_20260820202147.rootfs.lxc.tar.bz2
```

These hashes identify this pair; do not apply them to a newer rebuild:

```sh
sha256sum X86EMLTRBPI*.rootfs.lxc.tar.bz2
```

```text
da74e07dfece8653bc76d9c821324b75cc72e783d85e681f7524554cc671dc6e  controller
5468a70d0c5345866d2592062575bf8b197466f1970ca25837b9909a40d8ac29  extender
```

For any current pair, verify and retain its hashes before use:

```sh
sha256sum X86EMLTRBPI*.rootfs.lxc.tar.bz2
```

Artifacts are built on rev140 under
`/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0815-codex`. Build instructions are in
[../build/README.md](../build/README.md).

## Runtime prerequisites

- Linux 7.0.0-28 with the patched hwsim module;
- LXD 6.7 or 6.9 with a storage pool and management bridge;
- a 24-radio hwsim pool loaded with `channels=3 regtest=5`;
- patched `wmediumd.patched` from this repository;
- the prebuilt WNM-capable WLAN-client image; and
- Boardfarm `br-wan105` with DHCP/Internet for controller `erouter0`.

Each BPI container gets exactly one hwsim wiphy. Never deploy three physical
wiphys to represent the three bands.

Check the host before deployment:

```sh
uname -r
lxc version
ip link show br-wan105
cat /sys/module/mac80211_hwsim/parameters/radios
cat /sys/module/mac80211_hwsim/parameters/channels
cat /sys/module/mac80211_hwsim/parameters/regtest
iw phy | head
```

Do not unload hwsim while any lab container owns a radio.

## Source layout

The runtime checkout is `meta-cmf-bananapi-vcpe-0815-codex`. Host-side entry
points are:

```text
gen/bpi.sh                         deploy controller/extender containers
gen/wlan-client.sh                 deploy WNM client stations
gen/hwsim/                         build/load patched hwsim
gen/wmediumd/wmediumd-up.sh        generate/start/stop the medium
gen/wmediumd/configurator/         compile and run RF scenarios
gen/steer.sh                       host-side steering convenience wrapper
gen/tests/steering-matrix.sh       portable ten-client steering acceptance
gen/tests/health-audit.sh          topology, restart and traffic audit
gen/tests/p0-cold-reconstruction.sh repeatable managed cold-reconstruction gate
gen/tests/bpibroadband-memory-profile.py whole-container PSS/RSS/storage profile
gen/tests/p0-churn-soak.py          deferred long-duration P0 gate; not routine
```

The packaged rev150 VM normally installs its runtime source at
`/home/vagrant/git/meta-cmf-bananapi-vcpe`; an engineering VM may use an
explicit suffixed checkout. Enter it with:

```sh
ssh -tt rev@192.168.2.150 \
  "cd /home/rev/easymesh-vagrant-lab && vagrant ssh"
```

## Deployment order

Always deploy and pass the gate for one node before adding the next:

```text
controller              1 device / 3 radios / 10 BSSs
first extender          2 / 6 / 20
second extender         3 / 9 / 30
five clients            API active=5 total=5
third extender          4 / 12 / 40
fourth extender         5 / 15 / 50
ten clients             API active=10 total=10
```

The controller topology additionally displays a controller model node, so five
agents appear as six UI topology nodes.

### Deploy components directly

From `gen/` on a prepared runtime:

```sh
# controller; -F creates one coherent new AL-MAC/RUID identity set
./bpi.sh -F -b br-wan105 /path/to/controller.rootfs.lxc.tar.bz2

# four wireless-only extenders
./bpi.sh -F /path/to/extender.rootfs.lxc.tar.bz2
./bpi.sh -F -i 1 /path/to/extender.rootfs.lxc.tar.bz2
./bpi.sh -F -i 2 /path/to/extender.rootfs.lxc.tar.bz2
./bpi.sh -F -i 3 /path/to/extender.rootfs.lxc.tar.bz2

# start the medium after mesh radios exist
SNR=40 ./wmediumd/wmediumd-up.sh up

# ten clients; create sequentially so every client export gate completes
./wlan-client.sh up private_ssid test-fronthaul
for i in 1 2 3 4 5 6 7 8 9; do
  ./wlan-client.sh -i "$i" up private_ssid test-fronthaul
done
```

Adding an extender or client changes wmediumd's fixed radio registration
matrix. The deployment helpers refresh the daemon as required; client creation
then waits for association, DHCP and controller model export before returning.

`-F` destroys the named node's old `/nvram` identity and is correct for a clean
baseline. Omit it only when restarting the same logical device with its complete
identity preserved. The NVRAM root ownership guard prevents one checkout from
silently deleting another checkout's identities.

### rev150 Vagrant harness

The appliance is managed from `/home/rev/easymesh-vagrant-lab`:

```sh
cd /home/rev/easymesh-vagrant-lab
vagrant up
vagrant status
```

The provisioned appliance declares the full four-extender/ten-client scale step
and installs an enabled `easymesh-lab.service`. On every boot that service stops
any LXD-restored instances, removes stale OneWifi VAPs from the hwsim wiphys
returned to the host, then starts controller, extenders and clients in gated
order before rebuilding wmediumd. The VAP cleanup is required for in-place
service restarts; without it nl80211 reaches its interface-combination limit and
reports `ENFILE`. A PASS requires `5/15/50/14`, API
`10/10`, zero OneWifi/EasyMesh restarts, ten-client gateway traffic and a
120-second stable hold. Evidence is stored by boot ID under
`~/.local/state/easymesh-vagrant/reboot-acceptance/`.

Its gated `40-deploy-easymesh.sh` and `55-scale-topology.sh` accept:

```text
EASYMESH_REPO
EXPECTED_REPO_HEAD
EXPECTED_WMEDIUMD_SHA256
BPI_NVRAM_ROOT
CONTROLLER_IMAGE
EXTENDER_IMAGE
```

Pin all paths, the expected revision and the patched-wmediumd SHA-256 when
testing an alternate checkout. Do not remove provenance checks to make a
deployment proceed.

### rev130 recovery after a host reboot

LXD node and client profiles deliberately use `boot.autostart=false`; Docker's
Boardfarm WAN/DHCP containers also use `restart: "no"`. A host reboot therefore
does not reconstruct the lab merely by starting LXD. Preserve the existing BPI
containers and `/nvram` identities, but recreate the host medium and clients in
this order.

From the rev130 host:

```sh
cd /home/rev/git/meta-cmf-bananapi-vcpe-0815-codex/gen

# Boardfarm CPE-5 supplies DHCP, IPv4/IPv6 and Internet on br-wan105.
docker start wan-cpe5 dhcp-cpe5

# Load the already-installed patched module. Kernel headers are needed to build
# it, not to recover with the installed updates/mac80211_hwsim.ko.
sudo modprobe mac80211_hwsim radios=24 channels=3 regtest=5

# Recreate host bridges and rename wlanN pool devices to stable virt-wlanN.
bash -c 'source ./gen-util.sh'

# Preserve the controller identity and persistent database.
lxc start bpibroadband
```

Wait for controller OneWifi to be active. Its persistent database may still
contain the pre-reboot five-device inventory, so `1/3/10` is not a valid
identity-preserving recovery gate.

For each extender, in order `bpiap`, `bpiap-001`, `bpiap-002`, `bpiap-003`:

```sh
lxc start EXTENDER

# Wait for this to report active before regenerating the active-radio matrix.
lxc exec EXTENDER -- systemctl is-active onewifi

SNR=40 ./wmediumd/wmediumd-up.sh up

# Both must pass before adding the next extender.
lxc exec EXTENDER -- systemctl is-active em_agent
lxc exec EXTENDER -- iw dev wifi1.3 link
```

Never run two `wmediumd-up.sh` instances concurrently; the second registration
can fail with `EBUSY` and leave no daemon running. If an extender is stopped
during recovery, first remove the VAPs which its returned hwsim phy still owns,
then rebuild the medium without it:

```sh
bash -c 'source ./gen-util.sh; hwsim_reclaim_dirty_phys'
SNR=40 ./wmediumd/wmediumd-up.sh up
```

After all extenders reach `5/15/50`, recreate clients sequentially. The helper
refreshes wmediumd before starting each supplicant, then gates association,
DHCP and controller export:

```sh
./wlan-client.sh up private_ssid test-fronthaul
for i in 1 2 3 4 5 6 7 8 9; do
    ./wlan-client.sh -i "$i" up private_ssid test-fronthaul
done
```

Finish with the normal acceptance gate:

```sh
./tests/health-audit.sh
```

The expected operational result remains `5/15/50/14`, API `10/10`, ten working
WLAN data paths and a running wmediumd. Nonzero restart counters mean the
recovery is usable but is not a clean onboarding acceptance result; inspect the
corresponding boot journal rather than clearing the counters.

## Health gates

### Model

```sh
lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e '
select concat(
  (select count(*) from DeviceList),"/",
  (select count(*) from RadioList),"/",
  (select count(*) from BSSList));'
```

Expected scaled result: `5/15/50`.

### Services

```sh
for c in bpibroadband bpiap bpiap-001 bpiap-002 bpiap-003; do
  lxc exec "$c" -- systemctl is-active onewifi em_agent
done
lxc exec bpibroadband -- systemctl is-active em_ctrl em_cli
```

All must be active and `NRestarts` must remain zero. A manual restart invalidates
a clean-onboarding result.

### Clients and traffic

```sh
curl -fsS http://127.0.0.1:8888/api/v1/topology \
  | jq '[.nodes[].STAList[]?.staMAC] | unique | length'
lxc exec wlan-client -- iw dev wlan0 link
lxc exec wlan-client -- ip -4 -o addr show wlan0
lxc exec wlan-client -- ping -I wlan0 -c 3 10.0.0.1
```

Expected live topology result is ten. `/api/v1/devices` and
`/api/v1/clients` are also derived from the current controller tree: the device
list contains the controller, colocated agent and four extenders, while each
client record contains its observed STA MAC, parent agent and BSSID. The client
adapter joins detailed associated-STA metrics by MAC and exposes live RCPI,
derived dBm, rates and traffic counters when reported. Unsupported fields such
as a client IP address display as `N/A`; none are synthesized from packaged
demonstration JSON. Bind traffic to `wlan0`; client `eth0` is not the WLAN data
path.

### Backhaul

```sh
lxc exec bpiap -- iw dev wifi1.3 link
lxc exec bpiap -- bridge link show master brlan0
lxc exec bpibroadband -- sh -c 'ls /sys/class/net/brlan0/brif | grep sta'
```

The extender backhaul STA must be connected and the authorized WDS interfaces
must forward on both bridges.

### Medium

```sh
gen/wmediumd/wmediumd-up.sh status
cat /run/meta-cmf-wmediumd/wmediumd.pid
```

Every launch runs the ten internal multichannel/Linux-7 tests. Do not accept a
daemon that logs registration failure, unknown senders or cross-frequency
delivery.

## AP loss and recovery

Run the bounded recovery test with the container and its 5 GHz private BSSID:

```sh
gen/tests/ap-recovery.sh bpiap-003 02:00:00:69:29:b6
```

The test distinguishes an AP process/container failure from station-side link
failure detection. This distinction matters in hwsim: stopping an LXD container
returns its wiphy and OneWifi-created VAP interfaces to the host, but
mac80211_hwsim does not synthesize the beacon-loss indication that physical STA
firmware would normally deliver. `iw link` can therefore remain stale while
traffic to the stopped AP fails. The test records that raw behavior, toggles
only the affected client WLAN interfaces to inject the missing link-loss event,
and then verifies reassociation, traffic, controller database convergence, AP
restart, backhaul, complete tri-band configuration, and that the returned AP's
BSSID is visible in the WebUI topology. If any assertion fails after the AP is
stopped, an exit trap restarts it before reporting failure.

Accepted VM samples on 2026-08-17 were:

| AP cycle | Affected clients | Client links recovered | Controller DB | Services | Backhaul | Tri-band ready | WebUI-visible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `bpiap-001` | 1 | 3.47 s | 0.49 s | 7.52 s | 18.71 s | 53.47 s | 54.91 s |
| `bpiap-003` | 2 | 1.47 s | 0.97 s | 7.45 s | 17.03 s | 49.03 s | 49.44 s |

Both cycles retained the wmediumd PID, all ten WLAN data paths and zero
EasyMesh service restarts. A ten-client commanded-steering matrix immediately
after the first cycle passed 10/10 link, database and WebUI assertions. Link
movement ranged from 0.66 to 1.65 seconds. Nine controller updates completed in
2.4-3.8 seconds; one took 21.4 seconds. The present matrix records packet loss
but does not impose a performance threshold, so its PASS result is functional,
not a latency/loss acceptance claim.

Do not delete the returned AP VAPs during a single-AP recovery test. That is a
whole-lab reconstruction operation performed by `easymesh-lab-runtime` only
after every managed container is stopped. Deleting them under a live mesh can
change the projected radio inventory and leave the restarted extender with an
incomplete band.

Administrative container stop and RF isolation are different fault models.
For complete RF isolation, IEEE1905 neighbor aging now triggers a bounded
controller Topology Query; an unanswered extender is suppressed from active
API/WebUI topology while its persistent identity is retained, and the same
node returns after valid traffic resumes. The dedicated
[wmediumd-extender-outage.md](wmediumd-extender-outage.md) test is the accepted
liveness oracle. During an abrupt container-stop test, continue to use
container/service state, backhaul link and traffic alongside the API because
hwsim may retain station link state until a real link-loss event is delivered.

A controller-process restart is intentionally not used as an AP recovery
action. In one diagnostic restart, four already-running agents were restored
but one agent's BSS inventory was absent (`5/15/36`) until that AP re-onboarded,
after which the model returned to `5/15/50`. Always run the model gate after a
controller-only restart; process liveness and ten working client links alone do
not prove the controller has all steering targets.

## WebUI access

From the lab LAN:

```text
http://192.168.2.130:8888    rev130
http://192.168.2.150:18889   rev150 VM
http://192.168.2.120:18889   rev120 VM
```

rev150 forwards the VM without reloading it:

```text
192.168.2.150:18889 -> 127.0.0.1:18888 -> VM:8888
```

The user socket is `easymesh-vm-webui-forward.socket`; `rev` user lingering is
enabled so it remains available without an interactive login.

The clean-install rev120 VM uses Vagrant's direct host forwarding instead:

```text
192.168.2.120:18889 -> VM:8888
```

Its working directory is `/home/rev/easymesh-lab/0820`; Vagrant selected host
SSH port `2201`. Use `vagrant ssh` from that directory rather than treating the
forwarded SSH port as a stable lab interface.

On the Network Topology page, **Optimize Layout** only rearranges the rendered
graph, caches the positions across topology refreshes and fits the result into
the viewport. It does not issue an EasyMesh, steering, policy or wmediumd
command. **Export** downloads the current topology as JSON data or the visible
diagram as a portable SVG or PNG; SVG and PNG exports embed the displayed node
icons.

The accepted graph has one synthetic green edge from `Controller` to the
colocated `Agent-1`; the four remote nodes are `Extender-1` through
`Extender-4` and use wireless-backhaul edges. Several green `Agent-*` links
that later turn into extenders indicate incomplete backhaul metadata, not a
real topology change. OneWifi `0012` fixes the duplicate-AL-MAC lookup that
caused that transient in the previous extender image. With the current pair,
an unchanged two-second poll also leaves an optimized or manually positioned
graph untouched. EasyMesh `0059` makes **Optimize Layout** release and settle
D3's cloned render nodes; operating on the immutable API nodes only changed
the viewport scale and left the graph itself fixed. The current controller
serves asset revision `topology-layout-optimized-1`.

## Parity procedure

Before comparing rev130 and the VM, record on both:

```sh
git rev-parse HEAD
uname -r
lxc config get bpibroadband user.image
lxc config get bpibroadband user.build
curl -fsS http://127.0.0.1:8888/api/v1/topology \
  | jq '[.nodes[].STAList[]?.staMAC] | unique | length'
```

Then run the same health audit, steering rounds and RF scenario. Store the CSV
and configurator JSON/JSONL artifacts with host, revision, hashes and timestamps.

```sh
gen/tests/steering-matrix.sh 1
gen/tests/health-audit.sh
```

Historical parity established on 2026-08-16, before the current P0 roll-up:

| Gate | rev130 | rev150 VM |
| --- | --- | --- |
| kernel | `7.0.0-28-generic` | `7.0.0-28-generic` |
| controller/extender images | accepted 20260816 pair | accepted 20260816 pair |
| model and clients | `5/15/50`, live topology 10 | `5/15/50`, live topology 10 |
| service restarts | zero | zero |
| final steering sample | 10/10 | 10/10 |
| two-AP crossover | passive and commanded pass; restored | passive and commanded pass; restored |

rev130's final steering sample averaged 1.68 seconds to the client link, 3.39
seconds to the controller database and 3.29 seconds to the API. Follow-up
traffic checks reported 0% loss on all ten clients. The commanded crossover
delivered 1,399/1,400 probes while retaining the same wmediumd PID. LXD itself
is an intentional platform variance: 6.9 on rev130 and 6.7 in the VM.

Current portability acceptance on 2026-08-19 used a new rev120 VM populated
only from the external thin artifacts. The first two reconstructions exposed a
lost-WSC-M2 recovery timer that was starved by continuous per-radio events.
After deploying the targeted EasyMesh `0056` extender agent, two consecutive
cold reconstructions passed `5/15/50/14`, 10/10 topology clients, the 120-second
stable window, zero monitored restarts and 10/10 traffic. The external WebUI
returned six rendered mesh nodes and ten clients on port `18889`.

On 2026-08-20, rev130, the rev150 VM and the rev120 VM were redeployed with the
earlier `20260820193228` controller and the same extender artifact. Each
runtime reached the complete `5/15/50/14` model, ten clients and 10/10 traffic
with zero monitored service restarts. The hwsim profile audit found 15 unique
radio parents on every host. Repeated topology responses remained
byte-identical across two-second polls, with `Controller`, colocated
`Agent-1`, and four `Extender-*` identities. Those controllers served the
then-current `topology-layout-isolated-1` asset.

The subsequent `20260820210038` controller above was deployed and accepted on
rev130 only. It passed a complete identity-preserving reconstruction,
`5/15/50/14`, ten-client topology and traffic, a 120-second stable window, and
zero monitored restarts. Three topology responses spanning two refresh
intervals had the same SHA-256, and the live
`topology-layout-optimized-1` asset passed its JavaScript regression.

## Troubleshooting order

| Symptom | First boundary to inspect |
| --- | --- |
| VAP missing or OneWifi crash | one-wiphy invariant, regulatory/channel configuration |
| extender absent from model | backhaul association/WDS, then 1905 and WSC logs |
| association but no DHCP | authorized WDS ports and `brlan0` forwarding |
| client absent from UI | OneWifi association delta, agent notification, controller STAList |
| flat signal | wmediumd not running or link matrix not applied |
| steering command succeeds but no roam | source VAP, raw-frame provider callback, BTM response |

Do not begin with policy debugging when the radio, bridge, protocol or model
gate is incomplete.
