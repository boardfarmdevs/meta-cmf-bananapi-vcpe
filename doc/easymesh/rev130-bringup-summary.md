# rev130 EasyMesh tri-band lab bring-up summary

Status date: 2026-08-15

This document records the work performed to establish the EasyMesh controller,
two wireless extenders, five steerable WLAN clients, and multichannel wmediumd
on `rev130`. It records the verified stable baseline, the first successful
steering test, and the remaining scenario-language work.

## 1. Result

`rev130` now runs a repeatable Linux 7.0/mac80211_hwsim EasyMesh lab with:

- one `bpibroadband` controller container;
- two independently identified wireless extenders, `bpiap` and `bpiap-001`;
- tri-band 2.4, 5, and 6 GHz operation on every EasyMesh agent;
- five WNM-capable client containers, `wlan-client` through
  `wlan-client-004`;
- a patched wmediumd which can handle concurrent frequency contexts; and
- the EM CLI WebUI exported on `http://rev130:8888`.

The final packaged controller and two factory-clean extenders reached the
target device/radio/BSS shape in 3 minutes 26 seconds without manual restarts
or onboarding nudges. Each client was then reprovisioned through the corrected
single-command workflow; association, DHCP, and WebUI reporting all completed
inside `wlan-client.sh up`:

| Model object | Verified count |
|---|---:|
| EasyMesh devices | 3 |
| Radios | 9 |
| BSSes | 30 |
| Associated STAs | 7 |

The seven controller-database STA rows are five fronthaul clients plus both
wireless-backhaul STAs. Both extenders independently have a live 5 GHz
`mesh_backhaul` link and both are represented in `STAList`. The EasyMesh agent
service restart count was zero on the controller and both extenders. All
five clients appeared in the EM CLI WebUI, a concurrent 1,000-packet aggregate
test completed with zero loss, and the wmediumd netlink socket recorded zero
drops.

## 2. Host and source roles

The hosts were deliberately separated by role:

| Host/path | Role |
|---|---|
| `rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0814/meta-cmf-bananapi-vcpe` | Reference only; not modified |
| `rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0814-codex/meta-cmf-bananapi-vcpe` | Codex development and Yocto image builds |
| `rev130:/home/rev/git/meta-cmf-bananapi-vcpe` | Runtime/deployment clone |
| `rev130` | LXD, hwsim, wmediumd, controller, extenders, and clients |

Changes were developed and retained in the `0814-codex` tree. The original
`0814` tree remained a reference. Runtime copies of scripts and binaries were
then synchronized to the clean clone on `rev130`.

## 3. Current architecture

```text
                    rev130, Linux 7.0.0-28-generic

             patched mac80211_hwsim, channels=3
                         |
                         | generic-netlink frames
                         v
             patched multichannel wmediumd
                         |
       +-----------------+-------------------+
       |                 |                   |
       v                 v                   v
 bpibroadband          bpiap             bpiap-001
 controller +       extender agent     extender agent
 co-located agent       3 radios           3 radios
     3 radios              \                 /
       |                    wireless backhaul
       |
       +---------------- private_ssid ----------------+
       |           |           |           |          |
       v           v           v           v          v
 wlan-client   client-001  client-002  client-003 client-004
    WNM            WNM         WNM         WNM        WNM
```

The controller and its co-located agent are separate nodes in the WebUI graph,
so `/api/v1/topology` contains four visual nodes even though the EasyMesh
`DeviceList` correctly contains three managed devices.

## 4. Space and LXD stabilization

The initial `rev130` root filesystem was constrained. Unused Docker images and
package/build caches were removed before deploying the lab. At the time of this
record, `/dev/sda2` has approximately 16 GiB free and is 71% used.

The LXD layout was then made deterministic:

- `bpi-lab`, a directory-backed pool, holds the lab containers and avoids the
  loop-backed ZFS failure mode encountered during repeated creation;
- `bpi-nvram`, also directory-backed, holds the persistent BPI `/nvram`
  datasets outside the loop-backed default ZFS pool;
- BPI deploys are serialized to avoid concurrent image/import/storage races;
- unchanged images are not imported again;
- failed or replaced nvram mounts are retired safely rather than recreated
  underneath a running container;
- hwsim devices are attached only after `lxc init`, before container start,
  because attaching physical hwsim devices during LXD image materialization
  could wedge LXD 6.7; and
- a stopped or replaced hwsim node returns its radios to the host pool before
  the deployment function exits.

Persistent EasyMesh identity was also made explicit. A normal redeploy keeps a
coherent `{AL-MAC, RUID set}` in `/nvram`; `bpi.sh -F` clears the identity and
creates a genuinely new logical node. This prevents stale-device and RUID
collisions at the controller.

## 5. Linux 7.0 and tri-band hwsim

Linux 7.0 was selected as the supported tri-band platform. Linux 6.8 remains a
useful dual-band platform, but the proven 6 GHz regulatory and concurrent
channel behavior is on 7.0.

`rev130` is running:

```text
kernel:  7.0.0-28-generic
LXD:     6.7 client/server
hwsim:   channels=3
```

An exact-kernel `mac80211_hwsim.ko` was built on `rev130` with the project hwsim
changes. The installed module has SHA-256:

```text
04db1a471519a28778a18797f52bee5bc462befa3cc6415c23aecf937b2cfe0d
```

`gen/hwsim/build-hwsim.sh` was corrected to apply the flattened driver patch at
the right strip level and to fail loudly when it does not apply. Previously, a
nominally successful build could silently omit the required hwsim change. The
module is loaded with three channel contexts so one virtual wiphy can host the
2.4, 5, and 6 GHz radios required by the single-phy product model.

## 6. Controller and extender images

Fresh controller and AP-extender images were built from the `0814-codex` tree
on `rev140`:

| Image | Build artifact | SHA-256 prefix / LXD fingerprint |
|---|---|---|
| Controller | `X86EMLTRBPIBB_rdk-next_20260815224924.rootfs.lxc.tar.bz2` | `62050da33f39` |
| Extender | `X86EMLTRBPIAP_rdk-next_20260815221236.rootfs.lxc.tar.bz2` | `4caa09db6f93` |

The artifacts were copied to `rev130`. The controller image supersedes the
initial `ofw-bpibroadband-0815` build `20260815185824`. The same extender image
is used for `bpiap` and `bpiap-001`;
`-i 1` supplies a separate container, nvram volume, identity, profiles, and
hwsim radios.

The important EasyMesh/container fixes included in this build are summarized
below.

### Startup and transport

- The controller waits for its real LAN/1905 transport instead of starting on
  an incomplete interface set.
- EasyMesh retries AL-SAP registration while the forking `ieee1905` service is
  still making its Unix sockets ready, avoiding startup SIGABRTs.
- Disabled radios are excluded from onboarding state machines.
- The topology-query path elects an active radio rather than waiting forever
  on a disabled or stranded radio.

### Onboarding and WSC

- Lost WSC M2 transactions can recover by resending M1.
- A radio stuck at `wsc_m2_sent` during topology synchronization is recovered,
  allowing BSS and STA data to self-heal.
- The controller now refreshes the WSC registrar key material for each new M1.
  Reusing the registrar Diffie-Hellman key was the root cause of intermittent
  5 GHz WSC failure during repeated/fresh onboarding.
- WSC security translation was corrected so WPA2/CCMP remains coherent on
  2.4/5 GHz and 6 GHz is upgraded to the required SAE/PMF configuration.

### Tri-band AP and wireless backhaul

- hwsim defaults were constrained to capabilities the simulator can actually
  start, including 20 MHz operation for concurrent single-phy contexts.
- 6 GHz uses an IR-capable regulatory setup and operating class 131.
- Each AP VIF carries its own channel in `START_AP`, avoiding the Linux 7.0
  single-phy `SET_WIPHY` conflict.
- Four-address WDS-STA creation is deferred until station authorization. Doing
  it at initial association diverted EAPOL M4 and produced reason-15 backhaul
  failures.
- Reconfiguration restores the extender fronthaul after a OneWifi restart.

### Client reporting and steering prerequisites

- Full association status reports are translated into Client Association
  Events, not just incremental delta reports. This is required for clients to
  enter the controller `STAList`.
- Association events arriving while an extender is still completing AP
  capability/topology synchronization are sent immediately without displacing
  the onboarding radio state. Previously the queued STA-list command expired,
  so an early client could associate over WLAN but never reach the controller.
- The controller's hexadecimal association-frame scratch buffers now include
  the terminating byte. A maximum 512-byte capability frame needs 1,025 bytes;
  the prior 1,024-byte buffer made `hex()` fail and fed uninitialized data to
  SQL, dropping that client from `STAList`.
- The data model enforces one non-MLO active association per client, preventing
  stale source-BSS entries after roaming.
- The AP management-frame transmit and receive paths were fixed for BTM action
  frames.
- The existing ClientSteer path was repaired through serialization, 1905 ACK
  routing, BTM request transmission, BTM report completion, and CLI request
  handling. `steer.sh` is installed in the controller as the command-line
  driver for subsequent policy experiments.

## 7. Five steerable WLAN clients

The client helper was changed from an ad-hoc runtime install into a reusable,
self-contained `wlan-client-base` image. It contains `iw`, its runtime
dependencies, and a project-built `CONFIG_WNM` wpa_supplicant at
`/usr/local/sbin/wpa_supplicant-wnm`.

WNM support matters: a stock minimal supplicant may associate successfully but
silently ignore an 802.11v BSS Transition Management request. Each client also
stores its wpa_supplicant configuration and reconnects on container restart.

The live clients and WLAN addresses are:

| Container | STA MAC | Current BSSID at status capture | DHCP address |
|---|---|---|---|
| `wlan-client` | `02:00:00:00:03:00` | `02:00:00:f2:06:7f` (`Extender-1`) | `10.0.0.73` |
| `wlan-client-001` | `02:00:00:00:04:00` | `02:00:00:f2:06:7f` (steered to `Extender-1`) | `10.0.0.152` |
| `wlan-client-002` | `02:00:00:00:05:00` | `02:00:00:f2:06:7f` (`Extender-1`) | `10.0.0.231` |
| `wlan-client-003` | `02:00:00:00:06:00` | `02:00:00:1c:32:6c` (`Extender-2`) | `10.0.0.58` |
| `wlan-client-004` | `02:00:00:00:07:00` | `02:00:00:f2:06:7f` (`Extender-1`) | `10.0.0.137` |

Addresses and attachment can change during steering; the table is a status
capture, not scenario configuration.

## 8. Multichannel wmediumd

The running wmediumd is not the unmodified upstream daemon. The active binary
contains the multichannel work and uses `/tmp/wmediumd.cfg`. Its current
SHA-256 is:

```text
bfe106f86ac8f3fdf4d17bbdaf4d2aa937353b4dc9f6dd1d35397e02be769362
```

The applied work is:

1. Per-frequency interference domains, so frames on different channels do not
   interfere merely because they share one daemon.
2. Learned VIF ownership is used for delivery. Registration filter lists are
   not ownership maps: an associated STA MAC can legitimately occur in an AP
   filter. This fix restored correct ARP/data delivery after wmediumd registers
   after VAP creation.
3. Per-frame ACK file open/write/close logging was removed from the hot path.
4. Scheduling is independent per frequency rather than serializing all bands
   behind a single global queue tail.
5. Linux 7 HT/VHT transmit-rate flags are interpreted as MCS flags and mapped
   to valid 20 MHz OFDM PER curves rather than misread as legacy-rate indices.
6. Multicast delivery is frequency-filtered, preventing 2.4/5/6 GHz beacon
   clones from flooding radios which are listening on another channel.
7. The generic-netlink receive buffer is enlarged to 4 MiB, preventing the
   sustained beacon/data load from overflowing libnl's small default buffer.
8. Startup generation includes only active assigned hwsim radios; unused pool
   radios must not be presented to wmediumd as live interfaces.

The active configuration contains eight radio IDs: the three EasyMesh agents
and five clients. Strong links are currently used as a stable baseline before
introducing controlled gradients. With all five clients transmitting at once,
the final daemon delivered 1,000/1,000 ICMP packets and retained `Drops=0` on
its hwsim netlink socket.

The source build is pinned to upstream commit
`717e5d7fcc23eecbc8e32bd897a8fd4b1e3ba640`. `build-wmediumd.sh` records the
patch-series and prepared-source hashes, refuses ambiguous/context-drifted
trees, and was verified through two consecutive builds plus the full self-test
on `rev140`. The host build dependencies are `libnl-3-dev`,
`libnl-genl-3-dev`, and `libconfig-dev`.

## 9. EM CLI WebUI

The controller-side `onewifi_em_cli` is installed and exposed from the
container to the host at:

```text
http://rev130:8888
```

The dashboard `/api/v1/devices` and `/api/v1/clients` handlers were changed to
use the live controller tree rather than built-in demo data. Current verification
shows:

```text
/api/v1/clients:  total=5, active=5
```

### Network Topology client fix

The controller database and `/api/v1/clients` contained all five associated
fronthaul clients, but the Network Topology handler's independent libemcli tree
walk emitted only the two clients attached to one extender. The WebUI now keeps
the existing device/radio/haul layout and overlays station ownership from the
same successful live snapshot used by `/api/v1/clients`.

The verified result is:

```text
Controller:  0 visible clients
Agent-1:     0 visible clients
Extender-1:  4 visible clients
Extender-2:  1 visible client
Total:       5 visible clients
```

This was validated through repeated topology requests, an EM CLI service
restart, and a completed BTM roam. After the roam, the EasyMesh tree correctly
placed the STA under its target BSS but left the redundant STA-level `SSID`
empty. The WebUI had incorrectly treated that empty field as "not a client"
and displayed only four clients. It now classifies the association from the
authoritative parent BSS (`SSID` plus `HaulType`) and continues to display all
five clients after steering.

A related service-unit defect was fixed at the same time: systemd
expanded `printf "%s"` to the user shell path and consumed the JSON quoting,
corrupting `/nvram/remoteCtrl.json`. The drop-in now escapes both systemd's
percent specifier and the JSON quotes, consistently producing the loopback
controller endpoint.

### Rebuilding the precompiled WebUI helper

The recipe ships `onewifi_em_cli` as a precompiled 32-bit Go/CGO binary because
the stock Go recipe does not build reliably in this image. Its source changes
remain reviewable as three patches, applied in this order:

1. `em-cli-live-devices-clients.patch`
2. `em-cli-live-topology-clients.patch`
3. `em-cli-live-client-bss-classification.patch`

Use a scratch copy of Yocto's patched unified-wifi-mesh source, apply those
patches, and cross-build against the recipe sysroot and freshly built
`libemcli.so`. The result must be a stripped i386 ELF with the same target
dependencies as the existing helper. Replace only `onewifi_em_cli` inside
`em-cli.tar.gz`, retain the `static/` tree, rebuild the controller image, and
verify the embedded binary hash. The final tested helper hash is:

```text
4141d5b3195e47631262a8993c9004af9edbd6f85c0a92a7d1b12c8b1b40632f
```

## 10. Commanded steering acceptance

The final packaged-image steering test used the existing controller-side
driver:

```sh
/usr/bin/steer.sh 02:00:00:00:04:00 02:00:00:f2:06:7f
```

The source was the controller-agent 5 GHz BSS `02:00:00:33:a1:83`; the target
was Extender-1's 5 GHz BSS `02:00:00:f2:06:7f`. The complete
ClientSteer/1905/BTM exchange finished in approximately two seconds. The client
link and controller `STAList` both moved to the target, a 100-packet post-roam
ping had zero loss,
and the WebUI converged to five clients with ownership on the new extender.

The target capability report carried the maximum 512-byte frame body and was
inserted without an SQL error, directly exercising the 1,025-byte hex-buffer
fix. wmediumd retained zero netlink drops throughout the operation.

## 11. Repeatable deployment outline

From the runtime clone on `rev130`:

```sh
cd /home/rev/git/meta-cmf-bananapi-vcpe/gen

# Build/load the exact Linux 7.0 tri-band module and reserve the hwsim pool.
cd hwsim
./build-hwsim.sh --6ghz --load
cd ..

# Fresh controller identity; WAN/LAN bridge names are site-specific.
./bpi.sh -F -b <wan-bridge> -l <lan-bridge> \
  /home/rev/X86EMLTRBPIBB_rdk-next_20260815224924.rootfs.lxc.tar.bz2

# Two independent, wireless-only extenders.
./bpi.sh -F \
  /home/rev/X86EMLTRBPIAP_rdk-next_20260815221236.rootfs.lxc.tar.bz2
./bpi.sh -F -i 1 \
  /home/rev/X86EMLTRBPIAP_rdk-next_20260815221236.rootfs.lxc.tar.bz2

# Start the medium for the three EasyMesh radios. Each subsequent client `up`
# automatically replaces it with an expanded active-radio matrix.
SNR=40 ./wmediumd/wmediumd-up.sh up

# Five WNM-capable clients.
./wlan-client.sh up private_ssid test-fronthaul
for i in 1 2 3 4; do
  ./wlan-client.sh -i "$i" up private_ssid test-fronthaul
done
```

The actual WAN/LAN bridge names must be taken from the host deployment. A
same-node redeploy should omit `-F`; use `-F` only when a new logical EasyMesh
identity is intended.

`wmediumd-up.sh up` is idempotent: it terminates the daemon that owns the hwsim
registration before starting its replacement and rejects `EBUSY` at startup.
`wlan-client.sh up` refreshes the matrix after attaching its new radio and does
not return success until both association and DHCP are complete. A client that
has not associated yet is a normal configurator input; `gen-config.sh` skips
the empty current-BSSID lookup instead of indexing an associative array with an
empty key.

## 12. Validation checklist

The following checks were used after clean deployment:

```sh
# Runtime objects and addresses
lxc list

# Tri-band hwsim
uname -r
cat /sys/module/mac80211_hwsim/parameters/channels

# Controller model
lxc exec bpibroadband -- mysql -N -u root -D OneWifiMesh \
  -e 'select count(*) from DeviceList'
lxc exec bpibroadband -- mysql -N -u root -D OneWifiMesh \
  -e 'select count(*) from RadioList'
lxc exec bpibroadband -- mysql -N -u root -D OneWifiMesh \
  -e 'select count(*) from BSSList'
lxc exec bpibroadband -- mysql -N -u root -D OneWifiMesh \
  -e 'select MACAddress,BSSID,Associated from STAList order by MACAddress'

# Live UI model
curl -s http://127.0.0.1:8888/api/v1/clients | jq
curl -s http://127.0.0.1:8888/api/v1/topology | jq

# Client-side association, WNM supplicant log, DHCP, and data path
lxc exec wlan-client -- iw dev wlan0 link
lxc exec wlan-client -- grep -E \
  'CTRL-EVENT-CONNECTED|Key negotiation completed' /tmp/wpa.log
lxc exec wlan-client -- ip -4 addr show wlan0
lxc exec wlan-client -- ping -I wlan0 -c 3 10.0.0.1
```

## 13. Relevant bring-up commits

The latest bring-up changes in the `0814-codex` tree are:

```text
ffb5742 easymesh: refresh WSC registrar crypto per M1
4224b30 hwsim: apply flattened driver patches reliably
c91a09e wmediumd: make the multichannel fast path reproducible
44d2887 gen: serialize BPI deploys and retire nvram after unmount
b818df5 gen: clear fresh BPI nvram with BusyBox-compatible find
e9e4e2b gen: publish the EasyMesh web UI on the lab host
93b68eb easymesh: elect an active topology-query radio
b9c73ce ieee1905: gate controller on its LAN transport
faedcc3 gen: defer hwsim attachment until after container init
f1df552 gen: separate hwsim container init from start
d6eb171 gen: stop hwsim nodes before returning their radios
5f19297 gen: place the hwsim lab on a deterministic dir pool
e27bfc9 gen: bind BPI nvram outside LXD storage pools
a7caf70 gen: rotate BPI nvram volumes without recreate races
df67c34 gen: skip unchanged BPI image imports
3639b4e gen: disambiguate migrated BPI nvram volumes
034923e gen: keep BPI nvram off loop-backed ZFS
b859772 gen: require a valid tri-band hwsim pool on Linux 7.0
d3e6544 easymesh: agent re-sends M1 to recover a lost WSC M2
b657e05 easymesh: recover a wsc_m2_sent radio during topo-sync
77d3551 gen/wlan-client.sh: self-contained client image with baked WNM
```

The final change set also contains the Linux 7 rate, multicast-frequency, and
netlink-buffer wmediumd fixes; the onboarding association-delivery and
maximum-frame SQL fixes; and the post-roam WebUI classification fix described
above.

## 14. Remaining work

1. Convert the proven medium-control concepts into the planned Python scenario
   configurator and definition language.
2. Introduce controlled wmediumd gradients and run repeatable policy-response
   scenarios across both extenders.
3. Extend acceptance from commanded steering to repeated policy-driven
   steering, including dwell time, hysteresis, rejected BTM requests, and
   recovery assertions.
