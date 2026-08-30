# Portable LXD VM appliance

LXD VM is the supported portable EasyMesh lab. Bare metal remains the
performance and kernel-debug reference.

```text
Ubuntu 22.04/24.04 host + LXD/KVM
`-- easymesh-lab-0829 (Ubuntu 24.04/Linux 7 LXD VM)
    |-- Docker: Boardfarm DHCP/NAT and br-wan101
    |-- nested LXD: controller, four extenders, twenty clients
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

## Build a clean appliance

The source checkout must be clean. Provide the accepted controller and
extender images explicitly:

```sh
EASYMESH_CONTROLLER_IMAGE=/absolute/path/to/X86EMLTRBPIBB_*.rootfs.lxc.tar.bz2 \
EASYMESH_EXTENDER_IMAGE=/absolute/path/to/X86EMLTRBPIAP_*.rootfs.lxc.tar.bz2 \
  ./build.sh build
```

The builder:

1. creates a fresh Ubuntu 24.04 VM with six vCPUs, 6 GiB RAM and a sparse
   64-GiB disk;
2. installs and boots the accepted Linux 7 kernel;
3. installs Docker, nested LXD and the single Boardfarm repository;
4. builds and loads the patched 32-radio, three-channel hwsim module;
5. deploys the controller, four extenders, ten private and ten IoT clients;
6. installs userspace wmediumd, the Console, configurator and optimizer;
7. reboots the VM and lets systemd reconstruct the lab; and
8. requires `easymesh-labctl check` plus both host-side HTTP health gates.

Source and Boardfarm enter the VM as commit-bounded Git bundles. Images are
checksum verified. Host Git credentials and host-mounted source directories do
not enter the appliance.

## Operate and verify

```sh
./build.sh status
./build.sh check
./build.sh stop
./build.sh start
./build.sh restart
```

The default instance is `easymesh-lab-0829`. The builder detects the address
used by the outer host's IPv4 default route and exposes:

```text
http://HOST:18889/  EasyMesh WebUI
http://HOST:18890/  wmediumd Console
```

Override site-local settings without changing image identity:

```sh
EASYMESH_LXD_NAME=my-lab \
EASYMESH_WEBUI_HOST_IP=192.168.2.140 \
EASYMESH_WEBUI_PORT=28889 \
WMEDIUMD_CONSOLE_PORT=28890 \
  ./build.sh start
```

The complete lab starts automatically after the VM boots. Imported appliance
VMs also default to LXD `boot.autostart=true`; disable it explicitly when an
outer host must not start the VM after reboot:

```sh
lxc config set easymesh-lab-0829 boot.autostart false
```

## Export a release

After a passing check:

```sh
./build.sh snapshot
./build.sh export
```

`export` creates `artifacts/easymesh-lab-0829-COMMIT-lxd/` containing one
zstd-compressed instance backup, `import.sh`, `install-host.sh`, this README,
and `SHA256SUMS`. The VM is stopped before export so its nested LXD database,
radio state and filesystems are coherent.

## Import on another host

Copy the exported directory into any empty working directory:

```sh
sha256sum -c SHA256SUMS
EASYMESH_WEBUI_HOST_IP=192.168.2.150 \
  ./import.sh easymesh-lab-0829-COMMIT-lxd.tar.zst
```

The importer refuses to overwrite an existing instance, chooses an address on
the selected LXD network, replaces site-specific proxy devices, starts the VM,
and prints the UI and acceptance commands. Use `EASYMESH_LXD_NAME`,
`EASYMESH_LXD_NETWORK`, `EASYMESH_WEBUI_PORT`, and
`WMEDIUMD_CONSOLE_PORT` when the defaults collide.

Monitor the first imported cold reconstruction:

```sh
lxc console easymesh-lab-0829 --show-log
lxc exec easymesh-lab-0829 -- journalctl -fu easymesh-lab.service
lxc exec easymesh-lab-0829 -- /usr/local/sbin/easymesh-labctl check
```

## Remove

Review the exact target, then delete only that instance:

```sh
EASYMESH_LXD_NAME=easymesh-lab-0829 ./build.sh delete
```

The delete command is destructive. It does not delete LXD itself, storage
pools, networks, source checkouts, or another lab instance.
