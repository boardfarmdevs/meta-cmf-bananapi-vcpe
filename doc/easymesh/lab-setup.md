# Lab setup and operation

## Supported labs

| System | Role |
| --- | --- |
| rev140 | Yocto build host; does not run the lab |
| rev130 | direct Linux 7.0/LXD runtime |
| rev150 Vagrant VM | portable Linux 7.0/LXD runtime; preferred reference result |

0815-codex is authoritative on all three. rev130 and the rev150 VM are peer
runtimes: results are comparable only when source revision, image hashes,
kernel, topology, clients, wmediumd and test parameters match.

## Accepted inputs

```text
image runtime revision    73e7c1e3dac94b91bd2e9c84c6183cd234258d93
host tooling              current codex/0815-clean head
kernel                    7.0.0-28-generic
controller image          X86EMLTRBPIBB_rdk-next_20260816060433.rootfs.lxc.tar.bz2
extender image            X86EMLTRBPIAP_rdk-next_20260816061331.rootfs.lxc.tar.bz2
```

Verify the images before use:

```sh
sha256sum X86EMLTRBPI*.rootfs.lxc.tar.bz2
```

Expected hashes:

```text
9b9809d71c916a199682556d850cecf365c9d8c8fa7f1d062d600e0d56c4d432  controller
62f143df46e7526c4b6af3cfe89e0454cb184daf09e70a265c65280a9e6efa92  extender
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
```

The rev150 VM source is
`/home/vagrant/git/meta-cmf-bananapi-vcpe-0815-codex`. Enter it with:

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
./bpi.sh -F -b br-wan105 /path/to/X86EMLTRBPIBB_rdk-next_20260816060433.rootfs.lxc.tar.bz2

# four wireless-only extenders
./bpi.sh -F /path/to/X86EMLTRBPIAP_rdk-next_20260816061331.rootfs.lxc.tar.bz2
./bpi.sh -F -i 1 /path/to/X86EMLTRBPIAP_rdk-next_20260816061331.rootfs.lxc.tar.bz2
./bpi.sh -F -i 2 /path/to/X86EMLTRBPIAP_rdk-next_20260816061331.rootfs.lxc.tar.bz2
./bpi.sh -F -i 3 /path/to/X86EMLTRBPIAP_rdk-next_20260816061331.rootfs.lxc.tar.bz2

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

Its gated `40-deploy-easymesh.sh` and `55-scale-topology.sh` accept:

```text
EASYMESH_REPO
EXPECTED_REPO_HEAD
BPI_NVRAM_ROOT
CONTROLLER_IMAGE
EXTENDER_IMAGE
```

Pin all paths and the expected revision when testing an alternate checkout. Do
not remove provenance checks to make a deployment proceed.

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
curl -fsS http://127.0.0.1:8888/api/v1/clients | jq '{total,active}'
lxc exec wlan-client -- iw dev wlan0 link
lxc exec wlan-client -- ip -4 -o addr show wlan0
lxc exec wlan-client -- ping -I wlan0 -c 3 10.0.0.1
```

Expected API result is ten total and ten active. Bind traffic to `wlan0`; client
`eth0` is not the WLAN data path.

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

Every launch runs the nine internal multichannel/Linux-7 tests. Do not accept a
daemon that logs registration failure, unknown senders or cross-frequency
delivery.

## WebUI access

From the lab LAN:

```text
http://192.168.2.130:8888    rev130
http://192.168.2.150:18889   rev150 VM
```

rev150 forwards the VM without reloading it:

```text
192.168.2.150:18889 -> 127.0.0.1:18888 -> VM:8888
```

The user socket is `easymesh-vm-webui-forward.socket`; `rev` user lingering is
enabled so it remains available without an interactive login.

## Parity procedure

Before comparing rev130 and the VM, record on both:

```sh
git rev-parse HEAD
uname -r
lxc config get bpibroadband user.image
lxc config get bpibroadband user.build
curl -fsS http://127.0.0.1:8888/api/v1/clients | jq '{total,active}'
```

Then run the same health audit, steering rounds and RF scenario. Store the CSV
and configurator JSON/JSONL artifacts with host, revision, hashes and timestamps.

```sh
gen/tests/steering-matrix.sh 1
gen/tests/health-audit.sh
```

Parity established on 2026-08-16:

| Gate | rev130 | rev150 VM |
| --- | --- | --- |
| kernel | `7.0.0-28-generic` | `7.0.0-28-generic` |
| controller/extender images | accepted 20260816 pair | accepted 20260816 pair |
| model and clients | `5/15/50`, API 10/10 | `5/15/50`, API 10/10 |
| service restarts | zero | zero |
| final steering sample | 10/10 | 10/10 |
| two-AP crossover | passive and commanded pass; restored | passive and commanded pass; restored |

rev130's final steering sample averaged 1.68 seconds to the client link, 3.39
seconds to the controller database and 3.29 seconds to the API. Follow-up
traffic checks reported 0% loss on all ten clients. The commanded crossover
delivered 1,399/1,400 probes while retaining the same wmediumd PID. LXD itself
is an intentional platform variance: 6.9 on rev130 and 6.7 in the VM.

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
