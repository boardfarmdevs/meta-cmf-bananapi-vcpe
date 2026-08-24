# EasyMesh deploy and test (LXD + hwsim)

Deploy the RDK-B EasyMesh/OneWifi stack into x86 LXD containers backed by
`mac80211_hwsim` radios, then validate that the mesh forms and carries a client
end to end. The commands inside the containers match the Banana Pi R4 hardware
procedure; only the radios (`mac80211_hwsim`, not MT7988) and the nodes (LXD
containers, not boards) differ.

- Radio model, single-phy projection, and the 1905/WSC onboarding sequence: see
  [architecture.md](architecture.md).
- Building the images: see [../build](../build/README.md) -- not covered here.
- Directed client steering (`steer_drv`/`steer.sh`): see [steering.md](steering/steering.md)
  -- run it once the baseline lab below passes.

## Lab layout

Two hosts:

| Host | Role |
| --- | --- |
| `rev140` | Builds the controller and extender images. |
| `rev150` | LXD/hwsim runtime host. All deploy and test commands run here. |

Roles, all on rev150:

| Container | Build target | Role | Wired legs |
| --- | --- | --- | --- |
| `bpibroadband` | `qemux86bpibroadband` | Controller + colocated agent | WAN + LAN |
| `bpiap`, `bpiap-001` | `qemux86bpiap` | Extender agent(s) | none (wireless backhaul) |
| `wlan-client[-NNN]` | Alpine helper | WNM/BTM station | mgmt eth |

Deploy tooling lives on rev150 in `~/git/meta-cmf-bananapi-vcpe/gen`:

- `bpi.sh <image> [-i N] [-b br-wanNNN] [-l br-lanNNN]` -- deploy one container.
  Detects the role from the image path, imports the tarball, builds the profile
  (one clean hwsim wiphy renamed `wlan0`, `/nvram` volume), and launches it.
- `wlan-client.sh up <ssid> <psk>` -- bring up a client station (own container,
  netns, MAC, and a radio from the pool).

All radios come from one host `mac80211_hwsim` instance, so every node shares one
simulated RF medium.

## Prepare the rev150 host

```sh
ssh rev150
cd ~/git/meta-cmf-bananapi-vcpe/gen
lxc list
```

**hwsim pool.** Loaded once, shared by every lab container. `channels=2` lets one
wiphy hold two channel contexts so 2.4 GHz and 5 GHz VAPs run at once.

```sh
cat /sys/module/mac80211_hwsim/parameters/{radios,channels}     # 24, 2
iw phy; iw dev
```

Do not unload or reload `mac80211_hwsim` while any container holds a radio -- it
destroys every simulated radio and invalidates all running wireless state. Only
in a maintenance window, after every hwsim-backed container is stopped and
deleted:

```sh
sudo modprobe -r mac80211_hwsim
sudo modprobe mac80211_hwsim radios=24 channels=2
```

`bpi.sh` renames free host interfaces to `virt-wlanN` and only allocates clean
phys; a phy left dirty by a deleted container (stale VAPs) is skipped rather than
reused. Reclaim one with `iw dev wifiN del` once nothing uses it.

**Single-phy invariant (hard).** The BPI image is `FEATURE_SINGLE_PHY`: OneWifi
projects one physical wiphy into three logical radios (`wifi0`/`wifi1`/`wifi2` =
2.4/5/6 GHz). Give each BPI container **exactly one** hwsim phy -- the `bpi.sh`
default. Never override with `HWSIM_RADIOS=3`: three physical wiphys are not the
single-phy topology and crash OneWifi in `init_nl80211`. (On the **6.8 lab** host
regulatory marks 6 GHz `NO-IR`, so `wifi2` is logical-only and the baseline runs
2.4 + 5 GHz. On a **7.0** host loaded `regtest=5` 6 GHz *is* IR-capable and beacons
standalone — proven in
[6ghz.md](6ghz.md) (appendix) —
but EasyMesh tri-band is still gated by the layer, see [TODO.md](TODO.md) 2–3.)

**Bridges.** The controller examples use existing boardfarm bridges; substitute
your slot's names and pass them via `-b`/`-l`. The extender gets neither.

```sh
lxc network list; ip link show br-wan105; ip link show br-lan205
```

## Deploy in order

Bring up one node, pass its gate, then continue. `RUNNING` is not proof the
EasyMesh model synchronized.

### 1. Controller

```sh
cd ~/git/meta-cmf-bananapi-vcpe/gen
./bpi.sh rev@rev140:.../X86EMLTRBPIBB_rdk-generic-broadband-image-qemux86bpibroadband.lxc.tar.bz2 \
        -b br-wan105 -l br-lan205
```

Creates `bpibroadband` (controller + colocated agent, with WAN+LAN for DHCP and
internet). Confirm provenance and the one-radio assignment, then wait for all
services:

```sh
lxc config get bpibroadband user.build; lxc config get bpibroadband user.image
lxc exec bpibroadband -- iw phy                                 # exactly one wiphy
for s in onewifi ieee1905_em_ctrl em_ctrl ieee1905_em_agent em_agent em_cli; do
  lxc exec bpibroadband -- systemctl is-active $s; done          # all: active
```

Confirm the controller database bootstrapped and the colocated device enrolled:

```sh
lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
  'select count(*) from DeviceList; select count(*) from NetworkSSIDList;'
```

`DeviceList` holds the controller device; `NetworkSSIDList` holds five policy
rows (Fronthaul, IoT, Configurator, Backhaul, Hotspot) -- the SSIDs/passphrases
the controller hands each leaf in WSC M2. Do not deploy an extender until this
passes.

### 2. Extender(s)

No wired leg -- the extender's `brlan0` reaches the LAN over the wireless
backhaul; a second wired path between the `brlan0`s is an Ethernet loop.

```sh
./bpi.sh rev@rev140:.../X86EMLTRBPIAP_rdk-generic-ap-extender-image-qemux86bpiap.lxc.tar.bz2        # bpiap
./bpi.sh rev@rev140:.../X86EMLTRBPIAP_rdk-generic-ap-extender-image-qemux86bpiap.lxc.tar.bz2 -i 1   # bpiap-001
```

Extender services (no controller/CLI units here):

```sh
for s in onewifi ieee1905_em_agent em_agent; do
  lxc exec bpiap -- systemctl is-active $s; done                # all: active
```

On a cold start `em_agent` sits in `activating (start-pre)` until its mesh STA is
associated and a `brlan0` port -- the condition for its 1905 frames to reach the
controller. It fires AP-Autoconfiguration Search once, so a cold leaf takes a
couple of minutes. Give the controller a head start.

### 3. Client

```sh
./wlan-client.sh up private_ssid test-fronthaul       # fronthaul creds
./wlan-client.sh status
./wlan-client.sh down                                 # radio back to pool
```

Fronthaul creds are SSID `private_ssid` / PSK `test-fronthaul` (IoT haul:
`iot_ssid`). The helper builds an Alpine container, attaches one hwsim wiphy as
`wlan0`, runs the WNM-capable `wpa_supplicant`, associates, and requests DHCP.
Since all radios share one medium the client sees every matching AP; pin
`bssid=` (or `wpa_cli set_network`) when directing it at a specific node.

### wmediumd (optional, advanced)

The default lab runs **bare hwsim**: frames are delivered at a flat, fixed signal
level, so every AP looks equally strong. That is fine for mesh formation and
commanded steering. To get an RSSI gradient (attenuation, RSSI-driven policy),
run wmediumd -- its build and config-generation tooling lives in this layer's gen/
repo (`gen/hwsim`, `gen/wmediumd`). Do not reproduce it here; see
[wmediumd-multichan.md](wmediumd-multichan.md). Note wmediumd takes over the
entire hwsim medium (every radio on the host), so re-verify plain mesh formation
after enabling it.

## Validate

**Mesh formed.** One EasyMesh device per node; each agent must contribute its BSS
rows (controller + colocated agent + 2 extenders = 4 EasyMesh devices). Check
per-agent, not just the total:

```sh
lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh -e \
  'select count(*) from DeviceList; select count(*) from RadioList;'
lxc exec bpibroadband -- mysql -t -ubpi -proot OneWifiMesh -e \
  "select substring_index(substring_index(ID,'@',2),'@',-1) Agent, count(*) BSSes \
   from BSSList group by Agent;"
```

Controller DB is `mysql -ubpi -proot OneWifiMesh`; key tables `DeviceList`,
`RadioList`, `BSSList`, `STAList`. Do not treat a single historical BSS count as
the only gate -- the DB can retain rows for configured-but-down VAPs. Reconcile
SQL against live `iw dev`, bridge, and SSID evidence.

**EasyMesh web UI / API** on the controller, port 8888 (`onewifi_em_cli`, "EasyMesh
R6" dashboard over a live view of the controller tree):

```sh
lxc exec bpibroadband -- systemctl is-active em_cli
lxc exec bpibroadband -- ss -lntp | grep :8888
lxc exec bpibroadband -- curl -s http://127.0.0.1:8888/api/v1/devices
lxc exec bpibroadband -- curl -s http://127.0.0.1:8888/api/v1/clients
lxc exec bpibroadband -- curl -s http://127.0.0.1:8888/api/v1/topology
```

From your workstation, tunnel to the container's `erouter0` (address changes per
deploy -- read it live, don't copy it):

```sh
ssh -L 8888:$(lxc exec bpibroadband -- ip -4 -o addr show erouter0 | awk '{print $4}' | cut -d/ -f1):8888 rev@192.168.2.150
# then browse http://localhost:8888
```

**VAPs and credentials.** Validate SSID/type/channel/BSSID from `iw dev`, not
interface names:

```sh
lxc exec bpiap -- iw dev
lxc exec bpiap -- grep -E 'analyze_m2ctrl|##authtype' /tmp/em_agent.log
```

Expect `private_ssid / test-fronthaul` and `mesh_backhaul / test-backhaul`, and
`authtype 20` (WPA2/WPA3 transition PSK). `authtype 10` is Enterprise and wrong
-- the agent then configures the mesh STA for SAE against a PSK AP and the 4-Way
Handshake fails silently.

**Backhaul link.** Extender STA associated on 5 GHz, and its WDS port a
forwarding `brlan0` member on the controller (without the port there is no data
path):

```sh
lxc exec bpiap -- iw dev wifi1.3 link                    # Connected, mesh_backhaul, 5180
lxc exec bpiap -- bridge link show master brlan0         # wifi1.3 forwarding
lxc exec bpibroadband -- iw dev wifi1.1 station dump
lxc exec bpibroadband -- sh -c 'ls /sys/class/net/brlan0/brif | grep sta'   # wifi1.1.sta1
```

**Client reporting path.** A client that associates -- including on the
controller's own colocated agent -- must appear in the API (active) and in the
controller STAList with `Associated=1` under the correct BSSID:

```sh
STA=$(lxc exec wlan-client -- cat /sys/class/net/wlan0/address)
lxc exec bpibroadband -- curl -s http://127.0.0.1:8888/api/v1/clients | grep -i "$STA"
lxc exec bpibroadband -- mysql -t -ubpi -proot OneWifiMesh -e \
  "select MACAddress,BSSID,Associated from STAList where MACAddress='$STA';"
```

**End-to-end data path.** Success is the handshake completing and a lease
arriving, not association. Prove the WLAN path, not the management eth:

```sh
lxc exec wlan-client -- iw dev wlan0 link                # Connected to <extender BSSID>
lxc exec wlan-client -- grep -E 'CTRL-EVENT-CONNECTED|Key negotiation completed' /tmp/wpa.log
lxc exec wlan-client -- ip -4 addr show wlan0            # mesh-LAN address, 10.0.0.0/24
lxc exec wlan-client -- ping -I wlan0 -c 3 10.0.0.1
```

`Connected to ...` alone is not success (it precedes the 4-Way Handshake, and
appears in the failure case). To prove attachment through the intended node,
match the client's connected BSSID against that node's `iw dev` and its station
dump.

## Troubleshoot by symptom

| Symptom | First boundary |
| --- | --- |
| No VAPs / OneWifi crashes in `init_nl80211` | 3-phy misdeploy -- confirm one hwsim phy per node; redeploy single-phy. Never `HWSIM_RADIOS=3`. |
| Second band fails `EBUSY` | hwsim `channels` must be 2. |
| Extender active but BSSList did not grow | unique radio; `onewifi`/`ieee1905_em_agent`/`em_agent` active; WSC M1/M2 done (`grep analyze_m2ctrl /tmp/em_agent.log`); `wifi1.3` associated; reports reached controller. |
| Backhaul associated, no traffic | controller WDS/AP_VLAN port and `brlan0` forwarding state. |
| No AP-Autoconfig Search | agent `start-pre` / backhaul / 1905 path. |
| One band retains factory SSID | per-radio M2 analysis; retry onboarding (one radio can miss first-pass M2). |
| Client not in the model | WNM supplicant is the live process, handshake completed (`/tmp/wpa.log`), association delta reached the controller (STAList `Associated=1`). |
| Client has IP only on `eth0` | management path used; bind the test to `wlan0`. |
| Flat signal at every AP | expected on bare hwsim; needs wmediumd for a gradient. |

Inspect a failing service with `systemctl status`, `journalctl -u SERVICE -b`,
`coredumpctl list`. A startup retry on the 1905 AL-SAP is normal; a core dump or
permanent failure is not. Crashes are captured as breakpad minidumps in
`/minidumps`. Key logs: `/tmp/em_ctrl.log`, `/tmp/em_agent.log`,
`/tmp/ieee1905_*_log.txt`, `/rdklogs/logs/WiFilog.txt.0`. Enable OneWifi debug
logs with marker files (they persist on `/nvram`; the logs do not):

```sh
lxc exec bpiap -- touch /nvram/wifiHalDbg /nvram/wifiCtrlDbg
lxc exec bpiap -- systemctl restart onewifi     # -> /tmp/wifiHal, /tmp/wifiCtrl
```

Diagnose bottom-up: radio/channel, association, bridging, 1905 transport, M1/M2,
RBus application, live VAPs, DB convergence, then policy. That order stops a
model-level symptom from being blamed on the radio medium.

## Teardown and clean redeploy

`bpi.sh` replaces a same-named container but deliberately **reuses** the persistent
`<container>-nvram` volume, so a plain redeploy carries the previous run's
`/nvram` (and its radio RUIDs) -- it is not factory-clean. Reusing old RUIDs
under a new AL-MAC is a known onboarding blocker (the controller sees a
stale-device / RUID collision and the node stalls short of full convergence).

**Simplest clean redeploy: `bpi.sh -F` (--fresh)** wipes the nvram volume for you,
so the node regenerates a fresh `{AL-MAC, RUID-set}`:

```sh
./bpi.sh rev@rev140:<...BPIBB...> -b br-wan105 -l br-lan205 -F   # clean controller
./bpi.sh rev@rev140:<...BPIAP...> -i 1 -F                        # clean extender
```

Measured impact: a `-F` clean-identity deploy reaches full convergence
(`DeviceList=3`, `BSSList=30`, 4 topology nodes, both colocated *and* remote
clients reported) in ~90 s; a plain nvram-reusing redeploy stalls at 2/4 nodes
with the remote extender's clients unreported. Omit `-F` only to restart the
*same* logical device with its identity preserved.

Full teardown (all state) if you prefer to do it by hand:

```sh
./wlan-client.sh down                            # radios back to pool
lxc delete -f bpiap; lxc profile delete bpiap
lxc storage volume delete default bpiap-nvram
```

Budget radios: one per bpi container, one per client, minus any dirty-phy drain.

## Pass criteria (baseline lab)

A one-controller / N-extender / one-client baseline passes when all hold:

- `mac80211_hwsim` reports `radios=24`, `channels=2`; each BPI container has
  exactly one physical wiphy.
- Controller, colocated-agent, and extender services active -- no crashes or
  AL-SAP retry storms.
- Mesh formed: DeviceList equals the node count (controller + colocated + 2
  extenders = 4 EasyMesh devices) and each agent contributes its BSS rows.
- Every extender's `wifi1.3` is associated to `mesh_backhaul` on 5180 MHz, and
  both backhaul ends are forwarding `brlan0` members (incl. the controller's WDS
  port).
- WSC M2 was analyzed and fronthaul/backhaul creds applied (`authtype 20`);
  live SSIDs agree with the controller model.
- The client associates, appears in `/api/v1/clients` and STAList
  (`Associated=1`), owns a mesh-LAN address on `wlan0`, and `ping -I wlan0
  10.0.0.1` succeeds.

Keep image provenance (`lxc config get <c> user.build|user.image`), controller
and agent logs, the client WPA log, and pre/post DB rows with every result.

Once this passes, run the directed steering acceptance ledger in
[steering.md](steering/steering.md).
