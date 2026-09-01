# Portable LXD VM appliance

LXD VM is the supported portable EasyMesh lab. Bare metal remains the
performance and kernel-debug reference.

```text
Ubuntu 22.04/24.04 host + LXD/KVM
`-- rdkeasymesh-CLIENTS-0831 (Ubuntu 24.04/Linux 7 LXD VM)
    |-- Docker: Boardfarm DHCP/NAT and br-wan101
    |-- nested LXD: controller, four extenders, 20/50/100-client roster
    |-- hwsim + multichannel wmediumd
    |-- EasyMesh WebUI :8888
    `-- wmediumd Console :8890
```

The guest kernel owns hwsim. This keeps the radio module, wiphys and medium
lifecycle inside the appliance instead of crossing an outer system-container
namespace.

## Prepare an outer host

On an Ubuntu 22.04 or 24.04 x86-64 host:

```sh
sudo ./install-host.sh
newgrp lxd
lxc version
test -c /dev/kvm
```

The installer is idempotent. It installs LXD/KVM, adds the invoking user to the
`lxd` group, and initializes LXD only when no storage pool exists.

Validate profile metadata and import argument handling without creating an
appliance:

```sh
./test-profiles.sh
./test-build-storage.sh
./test-import-storage.sh
```

## Build a clean appliance

The source checkout must be clean. Select one immutable client profile and
provide the accepted controller and extender images explicitly:

```sh
EASYMESH_LAB_PROFILE=20 \
EASYMESH_CONTROLLER_IMAGE=/absolute/path/to/X86EMLTRBPIBB_*.rootfs.lxc.tar.bz2 \
EASYMESH_EXTENDER_IMAGE=/absolute/path/to/X86EMLTRBPIAP_*.rootfs.lxc.tar.bz2 \
  ./build.sh build
```

The builder:

1. creates a fresh Ubuntu 24.04 VM with six vCPUs, 8 GiB RAM and a sparse
   64-GiB disk;
2. installs and boots the accepted Linux 7 kernel;
3. installs Docker, nested LXD and the single Boardfarm repository;
4. builds and loads the patched 32-radio, three-channel hwsim module;
5. deploys the controller, four extenders, and the selected equally split
   private/IoT client roster;
6. keeps BPI NVRAM identities under `/var/lib/easymesh-lab/nvram`, outside
   the replaceable source checkout;
7. installs userspace wmediumd, the Console, configurator and optimizer;
8. reboots the VM and lets systemd reconstruct the lab; and
9. requires `easymesh-labctl check` plus both host-side HTTP health gates.

Source and Boardfarm enter the VM as commit-bounded Git bundles. Images are
checksum verified. Host Git credentials and host-mounted source directories do
not enter the appliance.

The acceptance audit rejects a mesh node whose `/nvram` bind source is missing
or empty. Updating or replacing `/home/easymesh/git/meta-cmf-bananapi-vcpe`
therefore cannot silently remove controller, Agent, AL-MAC or RUID identity.

## Operate and verify

```sh
./build.sh status
./build.sh check
./build.sh stop
./build.sh start
./build.sh restart
```

Profiles `20`, `50`, and `100` create separate instances named
`rdkeasymesh-PROFILE-0831`. A profile is immutable inside a release appliance:
download another profile instead of deleting and recreating client identities
after import. The builder detects the address
used by the outer host's IPv4 default route and exposes:

```text
http://HOST:18889/  EasyMesh WebUI
http://HOST:18890/  wmediumd Console
```

Override site-local settings without changing image identity:

```sh
EASYMESH_LXD_NAME=my-lab \
EASYMESH_LXD_STORAGE=bpi-lab \
EASYMESH_WEBUI_HOST_IP=192.168.2.140 \
EASYMESH_WEBUI_PORT=28889 \
WMEDIUMD_CONSOLE_PORT=28890 \
  ./build.sh start
```

The complete lab starts automatically after the VM boots. Imported appliance
VMs also default to LXD `boot.autostart=true`; disable it explicitly when an
outer host must not start the VM after reboot:

```sh
lxc config set rdkeasymesh-20-0831 boot.autostart false
```

## Ready and thin releases

Each 20-, 50-, and 100-client profile is published in two forms:

- `ready` retains every provisioned nested controller, extender, and client.
  Its first start reconstructs the accepted lab immediately, but the download
  grows with the client count.
- `thin` retains the installed VM, exact source, controller/extender archives,
  and one reusable WLAN-client image, but contains zero provisioned lab
  instances. Its first boot provisions the selected roster entirely offline,
  records `/var/lib/easymesh-lab/thin-firstboot-report.json`, and then passes
  through the same runtime and health gates as a ready appliance. Later boots
  use the normal fast reconstruction path.

The selected profile is immutable in both forms. A thin release is not a
network installer: its longer first boot does not clone repositories or fetch
container images.

## Export a release

After a passing check:

```sh
./build.sh export
```

After producing the ready release, the same accepted builder VM can be turned
into a thin release. Supply the original checksummed images because a ready
export deliberately removed its staging cache:

```sh
EASYMESH_LAB_PROFILE=20 \
EASYMESH_CONTROLLER_IMAGE=/absolute/path/to/X86EMLTRBPIBB_*.rootfs.lxc.tar.bz2 \
EASYMESH_EXTENDER_IMAGE=/absolute/path/to/X86EMLTRBPIAP_*.rootfs.lxc.tar.bz2 \
  ./build.sh export-thin
```

`export-thin` first reruns full ready-lab acceptance. It then removes all
provisioned nested instances and transient NVRAM/model state, retains exactly
the offline inputs required by first boot, and verifies that the exported VM
has zero lab definitions plus the `wlan-client-base` image and pending
first-boot manifest.

`export` reruns the complete acceptance check. An `accepted` snapshot is not
required by the release and is not created automatically because non-copy-on-
write LXD pools duplicate the complete VM disk. On a copy-on-write pool, a
release engineer may create the optional local rollback point with
`./build.sh snapshot`; it is excluded from the portable export.

`export` creates `artifacts/rdkeasymesh-CLIENTS-0831-COMMIT-lxd/` containing
one zstd-compressed instance backup, importer, installer, release metadata,
this README, and `SHA256SUMS`. The VM is stopped before export so its nested
LXD database, radio state and filesystems are coherent. Create the single file
for Google Drive with:

```sh
./package-release.sh artifacts/rdkeasymesh-CLIENTS-0831-COMMIT-lxd
```

Upload the resulting `*-bundle.tar` and its adjacent `.sha256`. Google Drive
is transport only; the checksum and `release.json` identify the release. The
outer checksum records only the bundle filename, so verification works from
any empty download directory. Export also records the VM's actual CPU, memory
and disk settings, plus the source host's storage-pool name for traceability.
That pool name is not imposed on a destination host. The backup remains
neutral between the old and current LXD
Secure-Boot keys; the importer disables Secure Boot using the spelling
supported by the destination host before the VM's first boot.

Export first stops the lab and removes only reconstructible package, journal,
Docker and nested-LXD image caches. It then issues filesystem discard before
the instance-only export; it does not fill a thin disk with zeros. Provisioned
containers, NVRAM identities, configuration and source are retained. The
checksummed `trim-report.txt` records before/after guest usage, discard output
and the final compressed archive size.

## Import on another host

Download the selected profile into any empty working directory, verify and
extract it:

```sh
sha256sum -c rdkeasymesh-CLIENTS-0831-COMMIT-lxd-bundle.tar.sha256
tar -xf rdkeasymesh-CLIENTS-0831-COMMIT-lxd-bundle.tar
cd rdkeasymesh-CLIENTS-0831-COMMIT-lxd
sha256sum -c SHA256SUMS
```

Import requires no archive argument when the bundle is intact:

```sh
EASYMESH_WEBUI_HOST_IP=192.168.2.150 \
  ./import.sh
```

The importer refuses to overwrite an existing instance, chooses an address on
the selected LXD network, replaces site-specific proxy devices, starts the VM,
and prints the UI and acceptance commands. Use `EASYMESH_LXD_NAME`,
`EASYMESH_LXD_NETWORK`, `EASYMESH_LXD_STORAGE`, `EASYMESH_WEBUI_PORT`, and
`WMEDIUMD_CONSOLE_PORT` when the defaults collide.

When the host's default storage pool cannot hold the selected sparse disk,
choose an existing pool explicitly for both build and import:

```sh
EASYMESH_LXD_STORAGE=bpi-lab ./import.sh
```

The importer validates the pool before creating the VM. The source host's
pool name is recorded for traceability but is not imposed on a destination
host.

Monitor the first imported cold reconstruction:

```sh
lxc console rdkeasymesh-20-0831 --show-log
lxc exec rdkeasymesh-20-0831 -- journalctl -fu easymesh-lab.service
lxc exec rdkeasymesh-20-0831 -- /usr/local/sbin/easymesh-labctl check
```

For a thin release, follow both provisioning and normal runtime gates:

```sh
lxc exec rdkeasymesh-20-0831 -- \
  journalctl -fu easymesh-thin-firstboot.service -u easymesh-lab.service
lxc exec rdkeasymesh-20-0831 -- \
  jq . /var/lib/easymesh-lab/thin-firstboot-report.json
```

Acceptance requires `result: "pass"`, `initial_instances: 0`, and
`final_instances` equal to five mesh nodes plus the profile's client count.

## Remove

Review the exact target, then delete only that instance:

```sh
EASYMESH_LAB_PROFILE=20 ./build.sh delete
```

The delete command is destructive. It does not delete LXD itself, storage
pools, networks, source checkouts, or another lab instance.
