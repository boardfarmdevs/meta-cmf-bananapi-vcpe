# Direct radio-host operation

[Deployment reference](README.md)

For development on a dedicated Ubuntu 24.04/Linux 7 host, use the same native
images, stable identities and health gates as the appliance. Prefer the managed
LXD VM for normal demonstrations. Never share an hwsim pool with another lab.

## Prerequisites

Build the role images with [the source guide](../../../build/README.md).
Prepare LXD storage/management networking, Boardfarm's `br-wan101` WAN/DHCP
path, the WNM-capable client image, patched
[hwsim](../../../../gen/hwsim/README.md) and
[wmediumd](../radio/wmediumd-internals.md).
LXD image conversion may need `fakeroot`; record original archive hashes.

The twenty-client RDK profile uses a 32-radio pool with `channels=3 regtest=5`
and exactly one wiphy per BPI container. Check `uname -r`, `lxc version`,
`ip link show br-wan101`, `iw phy` and the hwsim module parameters.
Never unload hwsim while containers own radios.

## Provision deliberately

Run from `gen/` on the prepared host:

```sh
./bpi.sh -F -b br-wan101 /absolute/path/controller.rootfs.lxc.tar.bz2
./bpi.sh -F /absolute/path/extender.rootfs.lxc.tar.bz2
lxc exec bpiap -- systemctl is-active onewifi
SNR=40 ./wmediumd/wmediumd-up.sh up
lxc exec bpiap -- iw dev wifi1.3 link
lxc exec bpiap -- systemctl is-active em_agent
```

Pass the first extender's physical and controller gates before repeating
`bpi.sh -F -i 1`, `-i 2` and `-i 3` with the extender image.
Refresh the medium registration matrix when the active inventory changes.

Expected controller model growth is 1/3/10, 2/6/20, 3/9/30, 4/12/40 and
5/15/50 device/radio/BSS records. Do not continue after failed onboarding.
The UI additionally displays the separate controller role.

Then provision the fixed private/IoT cohort:

```sh
./wlan-client-pool.sh plan --profile small
./wlan-client-pool.sh up --profile small
./tests/health-audit.sh
```

Require twenty clients, 24 associations including backhaul, valid metrics,
all-client traffic and no unexpected native restarts. Container suffixes are
not necessarily displayed extender numbers; discover live identities.

`-F` resets the named node's persistent identity and is only for a new clean
baseline, not normal recovery. Preserve the checkout's NVRAM ownership and
complete identity when restarting the same logical device. Do not paste this
provisioning sequence into a running managed appliance.

## Lifecycle

The appliance owns boot reconstruction through its installed units. A direct
host does not gain that management merely by running `bpi.sh`: after a host
reboot, restore WAN, module/pool and native nodes in dependency order, preserving
identity. Use the scripts' status/help and health gates; do not force-create a
second inventory. See [host tool entry points](../../../../gen/doc/README.md).

Stop the room before standalone RF/steering tests, restore touched medium
state afterward and retain failures. For ordinary portable deployment and
recovery, return to [operations](../../guide/operations.md).
