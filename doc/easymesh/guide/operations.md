# Lab setup and operation

> The reproducible LXD VM appliance, including Docker and the lean Boardfarm
> installation, is maintained under `gen/vm/lxd/`. Its README is the canonical
> VM build, import, lifecycle, acceptance, export and removal guide.

## Supported labs

| System | Role |
| --- | --- |
| Bare-metal Ubuntu 24.04/Linux 7 host | performance, scale and kernel debugging |
| Ubuntu 22.04/24.04 LXD host | portable appliance import and operation |

`codex/0905-clean` is authoritative. Runtime results are comparable only
when source revision, image hashes, kernel, topology, clients, medium backend
and test parameters match.

## Image provenance

Every deployment must record the exact image filenames and hashes. The
historical accepted pair below predates 0905; use the current build's actual
outputs and the acceptance record in [current state](../current-state.md),
not these old filenames, for a 0905 deployment:

```text
host/runtime source       codex/0831-clean
image content             EasyMesh 0127; OneWifi 0022; Wi-Fi HAL 0030
kernel                    7.0.0-30-generic
controller image          X86EMLTRBPIBB_rdk-next_20260830064504.rootfs.lxc.tar.bz2
extender image            X86EMLTRBPIAP_rdk-next_20260830064504.rootfs.lxc.tar.bz2
```

These hashes identify this pair; do not apply them to a newer rebuild:

```sh
sha256sum X86EMLTRBPI*.rootfs.lxc.tar.bz2
```

```text
69cb6f064b779438264fdefbd54f4ef74367d917ffdf78a96685b40974c0719f  controller
32d54805de07a5dd4d45412cd5664c49a9d028da755ec14dda8342cb60767d76  extender
```

For any current pair, verify and retain its hashes before use:

```sh
sha256sum X86EMLTRBPI*.rootfs.lxc.tar.bz2
```

Artifacts are built from a clean canonical source checkout. Build instructions
are in [the build guide](../../build/README.md).

## Runtime prerequisites

- Linux 7.0.0-30 with the patched hwsim module;
- LXD 6.7 or 6.9 with a storage pool and management bridge;
- a 32-radio hwsim pool loaded with `channels=3 regtest=5` for the current
  20-client profile;
- patched `wmediumd.patched` from this repository;
- the prebuilt WNM-capable WLAN-client image; and
- Boardfarm `ca-desk6` with `br-wan101`, DHCP and Internet for controller
  `erouter0`.

`gen/bpi.sh` automatically converts unified Yocto image archives to split LXD
metadata/rootfs imports on LXD 6.9, whose unified-image instance creation can
stall. That compatibility path requires the host `fakeroot` package. The
source-archive SHA is retained as an image property so an unchanged image is
not converted or imported again.

Each BPI container gets exactly one hwsim wiphy. Never deploy three physical
wiphys to represent the three bands.

Check the host before deployment:

```sh
uname -r
lxc version
ip link show br-wan101
cat /sys/module/mac80211_hwsim/parameters/radios
cat /sys/module/mac80211_hwsim/parameters/channels
cat /sys/module/mac80211_hwsim/parameters/regtest
iw phy | head
```

Do not unload hwsim while any lab container owns a radio.

## Source layout

Run host-side commands from the current source checkout. Entry points are:

```text
gen/bpi.sh                         deploy controller/extender containers
gen/wlan-client.sh                 deploy one WNM client station
gen/wlan-client-pool.sh            plan/provision private and IoT client cohorts
gen/hwsim/                         build/load patched hwsim
gen/wmediumd/wmediumd-up.sh        generate/start/stop the medium
gen/wmediumd/configurator/         compile and run RF scenarios
gen/steer.sh                       host-side steering convenience wrapper
gen/steer-soak.sh                  repeated live-topology steering driver
gen/steer-batch.sh                 concurrent steering under one RF transaction
gen/tests/steering-matrix.sh       portable ten-client steering acceptance
gen/tests/health-audit.sh          topology, restart and traffic audit
gen/tests/p0-cold-reconstruction.sh repeatable managed cold-reconstruction gate
gen/tests/bpibroadband-memory-profile.py whole-container PSS/RSS/storage profile
gen/tests/p0-churn-soak.py          requirements-driven long-duration gate
```

An LXD appliance installs its source at
`/home/easymesh/git/meta-cmf-bananapi-vcpe`. Enter it from the outer host with
`lxc exec INSTANCE -- bash`.

## Deployment order

Always deploy and pass the gate for one node before adding the next:

```text
controller              1 device / 3 radios / 10 BSSs
first extender          2 / 6 / 20
second extender         3 / 9 / 30
five clients            API active=5 total=5
third extender          4 / 12 / 40
fourth extender         5 / 15 / 50
twenty clients          API private=10 IoT=10 total=20
```

The controller topology additionally displays a controller model node, so five
agents appear as six UI topology nodes.

### Deploy components directly

From `gen/` on a prepared runtime:

```sh
# controller; -F creates one coherent new AL-MAC/RUID identity set
./bpi.sh -F -b br-wan101 /path/to/controller.rootfs.lxc.tar.bz2

# First wireless-only extender.
./bpi.sh -F /path/to/extender.rootfs.lxc.tar.bz2

# As soon as OneWifi is active, refresh wmediumd's fixed radio matrix. Then
# require the physical backhaul, agent and 2/6/20 controller model gates.
lxc exec bpiap -- systemctl is-active onewifi
SNR=40 ./wmediumd/wmediumd-up.sh up
lxc exec bpiap -- iw dev wifi1.3 link
lxc exec bpiap -- systemctl is-active em_agent

# Repeat that same gated sequence for -i 1, -i 2 and -i 3. Require model
# 3/9/30, 4/12/40 and 5/15/50 respectively before adding the next extender.
./bpi.sh -F -i 1 /path/to/extender.rootfs.lxc.tar.bz2
# wait, refresh wmediumd, and pass 3/9/30
./bpi.sh -F -i 2 /path/to/extender.rootfs.lxc.tar.bz2
# wait, refresh wmediumd, and pass 4/12/40
./bpi.sh -F -i 3 /path/to/extender.rootfs.lxc.tar.bz2
# wait, refresh wmediumd, and pass 5/15/50

# resumable 10-private + 10-IoT client profile
./wlan-client-pool.sh plan --profile small
./wlan-client-pool.sh up --profile small
```

Adding an extender or client changes wmediumd's fixed radio registration
matrix. The single-client helper refreshes the daemon as required. The pool
helper instead creates and verifies the cohort over hwsim's built-in medium,
then registers the completed active-radio set once. Each new client still waits
for association, DHCP and controller model export before returning. See
[client scale](../experiments/scenarios/client-scale.md).

`-F` destroys the named node's old `/nvram` identity and is correct for a clean
baseline. Omit it only when restarting the same logical device with its complete
identity preserved. The NVRAM root ownership guard prevents one checkout from
silently deleting another checkout's identities.

### LXD VM runtime

The appliance VM installs an enabled `easymesh-lab.service` that reconstructs
controller, extenders, clients and wmediumd after the guest boots.

```sh
cd gen/vm/lxd
./build.sh status
./build.sh check
./build.sh restart
```

Host installation, clean build, portable import, acceptance, export and
removal are maintained in `gen/vm/lxd/README.md`.

### Bare-metal recovery after a host reboot

LXD node and client profiles deliberately use `boot.autostart=false`; Docker's
Boardfarm WAN/DHCP containers also use `restart: "no"`. A host reboot therefore
does not reconstruct the lab merely by starting LXD. Preserve the existing BPI
containers and `/nvram` identities, but recreate the host medium and clients in
this order.

From the lab host, reconstruct the lean Boardfarm profile rather than merely
starting its old containers. The only Boardfarm source checkout is
`boardfarm-lab-staging`; `ca-desk6` creates one DHCP provider, one WAN gateway
and no LAN or shared-service containers:

```sh
mkdir -p /home/rev/boardfarm-lab
cd /home/rev/boardfarm-lab
uv venv --python 3.13 --prompt bf-venv .venv
source .venv/bin/activate
git clone git@github.com:robvogelaar/boardfarm-lab-staging.git
uv pip install -e boardfarm-lab-staging

export BF_LAB_CONFIG=ca-desk6.json
export BF_INVENTORY=ca-desk6.json
cd /home/rev/boardfarm-lab/boardfarm-lab-staging/lab
../../.venv/bin/bf-lab teardown,setup,status

# The lean profile must contain exactly these two containers.
docker ps --format '{{.Names}}' | sort
ip link show br-wan101
docker exec dhcp-cpe1 ip -4 address show eth1 | grep '10.101.0.10/24'
docker exec dhcp-cpe1 pgrep -x kea-dhcp4
docker exec dhcp-cpe1 ss -lun | grep ':67 '

cd /path/to/meta-cmf-bananapi-vcpe/gen

# Load the already-installed patched module. Kernel headers are needed to build
# it, not to recover with the installed updates/mac80211_hwsim.ko.
sudo modprobe mac80211_hwsim radios=32 channels=3 regtest=5

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

After all extenders reach `5/15/50`, resume the accepted mixed client profile.
The pool helper retains any healthy client, repairs only missing/inconsistent
members, then registers the full active-radio set with wmediumd once:

```sh
./wlan-client-pool.sh up --profile small
```

Finish with the normal acceptance gate:

```sh
./tests/health-audit.sh
```

The expected operational result is `5/15/50/24`, API cohorts `10/10`, 20
working WLAN data paths and a running wmediumd. Nonzero restart counters mean the
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

Expected small-profile live topology result is 20. `/api/v1/devices` and
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
[extender-outage test](../experiments/scenarios/extender-outage.md) is the accepted
liveness oracle. During an abrupt container-stop test, continue to use
container/service state, backhaul link and traffic alongside the API because
hwsim may retain station link state until a real link-loss event is delivered.

## WebUI access

From the lab LAN:

```text
http://BARE-METAL-HOST:8888   EasyMesh WebUI
http://BARE-METAL-HOST:8890   wmediumd Console
http://LXD-VM-HOST:18889      proxied EasyMesh WebUI
http://LXD-VM-HOST:18890      proxied wmediumd Console
```

The LXD appliance host owns direct NAT proxy devices:

```text
HOST:18889 -> VM:8888
HOST:18890 -> VM:8890
```

The Console observes wmediumd; it is not served by `em_cli`. Its managed
service must report read-only mode during ordinary lab operation:

```sh
systemctl status wmediumd-console.service
curl -fsS http://127.0.0.1:8890/api/v1/controls | jq .
```

Use `lxc exec INSTANCE -- bash` for guest access. There is no provider-specific
SSH port or mounted host directory.

On the Network Topology page, **Optimize Layout** fits the complete graph to
the available pane without rearranging devices or clients. Swapping extenders
between the top/bottom or left/right, or moving Agent-1 and Controller, keeps
that arrangement. It changes only the view's zoom and pan, accounts for SSID
and client extents, and retains positions across topology refreshes. Initial
display still uses a compact centered star or the branch/chain hierarchy.
It does not issue an EasyMesh, steering, policy or wmediumd
command. **Export** downloads the current topology as JSON data or the visible
diagram as a portable SVG or PNG; SVG and PNG exports embed the displayed node
icons.

The graph has one synthetic green edge from `Controller` to the colocated
`Agent-1`. `Extender-1` through `Extender-4` use their observed wireless
backhaul edges. An unchanged two-second API poll must not move an optimized or
manually positioned graph.

## Deployment parity procedure

Before comparing a bare-metal run and an appliance VM, record on both:

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

Parity passes only when both runtimes use the same source revision, image
hashes, kernel parameters, topology, policy, wmediumd binary/configuration, and
test arguments. Compare the complete artifacts rather than selected timing
figures.

`health-audit.sh` defaults to ten one-second probes per client and fails if any
packet is lost. Higher offered loads are explicit experiments, for example:

```sh
HEALTH_PING_COUNT=40 \
HEALTH_PING_INTERVAL=0.05 \
HEALTH_PING_MAX_LOSS=100 \
  gen/tests/health-audit.sh
```

That example offers 400 echo requests per second across twenty clients and is
a wmediumd/data-path load characterization, not the normal health gate.

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
