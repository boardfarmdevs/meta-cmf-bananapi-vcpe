# gen — host-side deployment tooling

Everything needed to deploy and run the EasyMesh LXD/hwsim lab from the images
this layer builds. It lives **in this layer** so there is one repo: the recipes
build the images, and `gen/` deploys and drives them. (Previously this tooling
lived in a separate `meta-lxd` repo, which caused two-repo drift.)

- **Build host** (`rev140`): builds the images; does not run `gen/`.
- **Runtime host** (`rev150`): checks this layer out under `~/git/` and runs
  `gen/` to deploy the containers on its LXD/hwsim.

For the lab procedure and validation, see
[../../doc/easymesh/deploy-and-test.md](../../doc/easymesh/deploy-and-test.md);
for the architecture, [../../doc/easymesh/architecture.md](../../doc/easymesh/architecture.md).

## Layout

```text
gen/
  gen-util.sh          core: hwsim radio pool, bridge checks, image import (sourced by the others)
  bpi.sh                deploy one container from a built image
  wlan-client.sh       bring up an Alpine client station (own container/MAC/radio)
  hwsim/               patched mac80211_hwsim (channels>1 wmediumd registration) + build script
  wmediumd/            the multichannel RF medium model — config generator, patched daemon, launcher
  wpa_supplicant/      a CONFIG_WNM=y wpa_supplicant (802.11v BTM-capable) for the client + build script
  doc/                 this document
```

`M_ROOT` is computed by `gen-util.sh` as the parent of `gen/` — i.e. the layer
checkout root — so the scripts work wherever the layer is cloned. Images are
staged under `M_ROOT/tmp/` (git-ignored).

## Host setup (LXD)

Preparing a fresh Ubuntu runtime host (like `rev150`/`rev120`) to run this
tooling. One-time, run as the deploy user.

**1. Install LXD (snap).** On modern Ubuntu the apt `lxd` package is deprecated;
snap is the supported path. Add yourself to the `lxd` group and re-login so
`lxc`/`lxd` work without sudo.

```sh
sudo snap install lxd
sudo usermod -aG lxd $USER      # then log out and back in (or: newgrp lxd)
```

**2. Initialize LXD.** A `dir` (or `zfs`) storage pool named `default` and the
default `lxdbr0` bridge (IPv4 NAT) are all this tooling needs.

```sh
lxd init --minimal              # or: lxd init  (accept defaults: pool "default", bridge lxdbr0)
```

`wlan-client.sh` bridges the Alpine client's `eth0` onto `lxdbr0`, so the client
gets management connectivity from the `lxdbr0` DHCP/NAT.

**3. Alpine image alias.** `wlan-client.sh` launches the `alpine` alias; create it
once from the remote image server:

```sh
lxc image copy images:alpine/3.19 local: --alias alpine
```

**4. hwsim kernel module.** This host provides the simulated radios. Load the pool
once:

```sh
sudo modprobe mac80211_hwsim radios=24 channels=2
```

For wmediumd at `channels>1` the stock in-tree module is not enough — use the
patched module built by `gen/hwsim` (see [`../hwsim`](../hwsim) and the
Prerequisites note below). To persist the options across reboots (optional), drop
`options mac80211_hwsim radios=24 channels=2` in `/etc/modprobe.d/hwsim.conf` and
add `mac80211_hwsim` to `/etc/modules-load.d/hwsim.conf`.

**5. Boardfarm bridges (external).** The controller's WAN/LAN bridges (e.g.
`br-wan105` / `br-lan205`) are provided by the lab slot, **not** created by this
tooling. They must already exist on the host before deploying a controller; check
with `ip link show br-wan105`. Extenders need no bridges.

**Verify.** `lxc list` returns (empty table is fine), and after the first
`bpi.sh`/`gen-util` run `iw dev` shows the renamed `virt-wlan*` radios in the host
pool.

```sh
lxc list
iw dev | grep virt-wlan          # after the first deploy
```

## Prerequisites (rev150 host, one-time)

- **hwsim pool** loaded once: `sudo modprobe mac80211_hwsim radios=24 channels=2`.
  For wmediumd at `channels=2` the module must be the patched one — build/install
  it with `gen/hwsim/build-hwsim.sh --load` (see `hwsim/`).
- **LXD `alpine` image alias** (used by `wlan-client.sh`):
  `lxc image copy images:alpine/3.19 local: --alias alpine`.
- **Bridges** for the controller's WAN/LAN (boardfarm slot), e.g. `br-wan105` /
  `br-lan205`. Extenders need none.

## Deploy

From `gen/` on rev150 (`cd ~/git/meta-cmf-bananapi-vcpe/gen`):

```sh
# controller (WAN+LAN); image path is on the build host
./bpi.sh rev@rev140:<.../qemux86bpibroadband/...X86EMLTRBPIBB...lxc.tar.bz2> -b br-wan105 -l br-lan205
# extenders (single-phy; -i gives an instance suffix)
./bpi.sh rev@rev140:<.../qemux86bpiap/...X86EMLTRBPIAP...lxc.tar.bz2> -i 1
./bpi.sh rev@rev140:<...same...> -i 2
# client(s)
./wlan-client.sh up private_ssid test-fronthaul          # single client
./wlan-client.sh -i 1 up private_ssid test-fronthaul     # more clients, own container/MAC/radio
```

**Hard invariant:** each bpi container gets exactly ONE hwsim phy (`bpi.sh`
default; `FEATURE_SINGLE_PHY`). Never `HWSIM_RADIOS=3` — three phys crash OneWifi.

**Identity on redeploy — use `-F`/`--fresh` for a clean baseline.** A plain
`bpi.sh` redeploy REUSES the container's persistent `<name>-nvram` volume, so the
node keeps its old radio RUIDs under a *new* AL-MAC. The EasyMesh controller
treats that as a stale-device / RUID collision and the fresh node never onboards
(the mesh stalls short of full convergence). `bpi.sh -F …` wipes the nvram volume
so the node regenerates a fresh `{AL-MAC, RUID-set}` and onboards cleanly. Omit
`-F` only to restart the *same* logical device with its identity preserved.
Measured: a clean-identity deploy reaches full convergence (DeviceList=3,
BSSList=30, 4 topology nodes) in ~90 s; a nvram-reusing redeploy stalls at 2/4.

`bpi.sh` imports the image, builds a per-container LXD profile (one clean
`virt-wlan*` radio renamed `wlan0`, a persistent `<name>-nvram` volume, bridges
if asked), and launches it. `gen-util.sh` owns the radio pool: a radio is *free*
iff its `virt-wlan*` netdev is host-resident, so radios simply move between host
and containers — no ledger, no leak. Delete a container to return its radio.

## Optional: wmediumd (RF gradient)

The default medium is flat-signal. To model per-link RF (for policy/RSSI-driven
behaviour) run wmediumd — see [../../doc/easymesh/wmediumd-multichan.md](../../doc/easymesh/wmediumd-multichan.md)
and the `wmediumd/` + `hwsim/` tooling here (`wmediumd/wmediumd-up.sh up|down`).

## Keeping in sync

The build host (`rev140`) also checks out this layer for building; `gen/` there
is unused. Keep the two checkouts in sync via git occasionally — deployment work
happens on rev150, code/recipe work on rev140.
