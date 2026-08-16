# WNM / BTM-capable wpa_supplicant for the WLAN test clients

The alpine WLAN clients (`wlan-client`, `wlan-client-001`, … from
`../wlan-client.sh`) use Alpine's **stock** `wpa_supplicant`, which is built
**without** `CONFIG_WNM`. Such a client associates and roams on command, but it
does **not** honor an 802.11v BSS Transition Management (BTM) steer: the mesh
controller's steer reaches the AP, the AP transmits a valid BTM Request
(category 10 / action 7) to the client, and the client silently drops it. From
the controller's side the steer looks sent but "doesn't take".

To exercise EasyMesh-directed roaming you need a client that understands BTM.
This directory builds a **wpa_supplicant 2.10 with `CONFIG_WNM=y`** into the
client's `/tmp`, run from there, leaving the packaged system binary untouched
(so nothing about the base image changes).

## What `CONFIG_WNM=y` adds

It compiles in `wnm_sta.c`, which:

* receives the BTM Request action frame and parses the candidate list,
* sends the **BTM Response** (category 10 / action 8, status 0 = accept),
* advertises the **BSS Transition** bit in the Extended Capabilities IE of the
  (re)association request, so the AP knows the client is steerable,
* reassociates to the steer's target BSS.

Without it none of that code exists — hence the silent drop.

## Files

* `wpa_supplicant-wnm.config` — the build `.config`. `CONFIG_WNM=y` is the point;
  the rest is the minimum for an nl80211 station on this lab (NL80211 + libnl-3.0,
  a control interface for `wpa_cli`, OpenSSL TLS, 11ac/11w/SAE/FT).
* `build-wnm-supplicant.sh` — builds it inside a client container.

## Quick build

```bash
# into wlan-client (default), leaving its running supplicant alone:
./build-wnm-supplicant.sh

# into a second instance, and start it on the bpi mesh in one go:
./build-wnm-supplicant.sh wlan-client-001 --run private_ssid test-fronthaul
```

The binary lands at
`/tmp/wpa_supplicant-2.10/wpa_supplicant/wpa_supplicant` inside the container.

The script handles two lab-specific snags automatically, so the quick build
above just works:

* **Internet.** The client holds a DHCP default route from `wlan0` that outranks
  `eth0`, so `apk`/`wget` cannot reach the network. The script drops that route
  and DHCPs `eth0` when it detects no connectivity.
* **Memory.** Compiling gcc/wpa_supplicant OOMs at the client's default 128 MB.
  The script raises the container to 512 MB for the build and restores the
  previous limit afterward.

## Manual build (what the script does)

```bash
CT=wlan-client-001                      # target client
lxc exec $CT -- sh -c '
  apk add --no-cache gcc make musl-dev openssl-dev libnl3-dev linux-headers pkgconf wget tar
  cd /tmp
  wget -q https://w1.fi/releases/wpa_supplicant-2.10.tar.gz
  echo "20df7ae5154b3830355f8ab4269123a87affdea59fe74fe9292a91d0d7e17b2f  wpa_supplicant-2.10.tar.gz" | sha256sum -c -
  tar xzf wpa_supplicant-2.10.tar.gz
'
lxc file push wpa_supplicant-wnm.config \
    $CT/tmp/wpa_supplicant-2.10/wpa_supplicant/.config
lxc exec $CT -- sh -c 'cd /tmp/wpa_supplicant-2.10/wpa_supplicant && make -j$(nproc)'
```

## Run it

Replace the stock supplicant with the WNM build on `wlan0`:

```bash
lxc exec <client> -- sh -c '
  pkill -f wpa_supplicant; sleep 1
  ip link set wlan0 up
  /tmp/wpa_supplicant-2.10/wpa_supplicant/wpa_supplicant \
      -B -P /tmp/wpa.pid -i wlan0 -c /tmp/wpa.conf -D nl80211 >/tmp/wpa.log 2>&1'
```

`/tmp/wpa.conf` is the same network block `wlan-client.sh` writes, e.g. for the
bpi mesh:

```text
network={
 ssid="private_ssid"
 psk="test-fronthaul"
 key_mgmt=WPA-PSK
}
```

## Verify it honors a steer

With the WNM build running, steer the client from the controller and watch it
move and answer:

```bash
# on the client:
lxc exec <client> -- tail -f /tmp/wpa.log        # look for WNM: BSS Transition Management
# on bpibroadband, after a ClientSteer():
#   agent transmits the BTM Request; the client sends a BTM Response status 0
#   and reassociates to the target BSS.
```

A stock client stays put; the WNM build reassociates to the named target.

## Known issue: association on a fresh instance

The from-source WNM build **associates on the original `wlan-client`** (it has
run there all along, honoring steers), but on a freshly created instance
(`wlan-client-001`) the same binary starts, logs `nl80211`/`rfkill` init, then
stalls before scanning and never associates -- while the container's **stock**
`wpa_supplicant` associates fine on the very same radio. The reference binary
copied from `wlan-client` fails there too, so it is an environment difference
between the instances, not the build. Root cause is still open (suspect a
libnl-3 / nl80211 wiphy-query interaction in the fresh alpine rootfs).

Because of this, `wlan-client.sh --wnm` **builds** the WNM binary into the
instance but leaves the client on the working stock supplicant; swapping to the
WNM build is manual (above) and currently only reliable on `wlan-client`.

## Notes

* `/tmp` is not persistent — a client teardown/redeploy loses the build. Re-run
  the script. (If this becomes routine, bake the WNM build into the alpine
  client image or have `wlan-client.sh` invoke this script on `up`.)
* Same binary works in every alpine x86_64 client, so you can build once and
  `lxc file pull`/`push` it between instances instead of rebuilding.
