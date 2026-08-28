# Native LXD EasyMesh appliance

This directory builds the complete EasyMesh research lab as one LXD virtual
machine. Inside that VM, LXD continues to own the BPI and WLAN-client system
containers. The guest therefore retains its accepted Linux 7, hwsim,
wmediumd, Docker/Boardfarm and nested-LXD boundary without requiring
VirtualBox or Vagrant on the host.

```text
Linux host + LXD
`-- easymesh-lab-0828 (LXD virtual machine, Ubuntu 24.04/Linux 7)
    |-- Docker: Boardfarm DHCP/NAT and br-wan101
    |-- nested LXD: controller, four extenders, twenty clients
    |-- hwsim + multichannel wmediumd
    |-- WebUI :8888
    `-- wmediumd Console :8890
```

The initial implementation deliberately uses an LXD VM. hwsim is then owned
by the appliance kernel and can be recreated independently of the host. A
privileged outer system-container experiment is tracked separately because its
hwsim wiphys belong to the host kernel and must cross two network-namespace
boundaries before the inner BPI containers can own them.

## Build

The host needs LXD with VM support, hardware virtualization, Internet access,
the current clean source checkout, and the accepted controller/extender image
archives. The default allocation is six virtual CPUs, 6 GiB RAM and a dynamic
64 GiB root disk.

```sh
cd gen/vm/lxd

EASYMESH_CONTROLLER_IMAGE=/absolute/path/to/X86EMLTRBPIBB_*.rootfs.lxc.tar.bz2 \
EASYMESH_EXTENDER_IMAGE=/absolute/path/to/X86EMLTRBPIAP_*.rootfs.lxc.tar.bz2 \
  ./build.sh build
```

The builder performs all of these gates before creating the `accepted`
snapshot:

1. create a fresh Ubuntu 24.04 LXD VM;
2. install Ubuntu's Linux 7 kernel and reboot into it;
3. install Docker, nested LXD and the single Boardfarm repository;
4. create the 32-radio, three-channel hwsim pool;
5. deploy the controller, four extenders and 20 clients from explicit images;
6. install wmediumd and its Console;
7. reboot the complete appliance and let systemd reconstruct it; and
8. require the complete `easymesh-labctl check` result.

Source and Boardfarm are transferred as commit-bounded Git bundles. The BPI
images and bundles are checksum-verified inside the VM. Git credentials are
not copied into the appliance.

## Operation

```sh
./build.sh status
./build.sh check
./build.sh stop
./build.sh start
./build.sh restart
```

By default, host loopback ports are:

```text
http://127.0.0.1:18889/  EasyMesh WebUI
http://127.0.0.1:18890/  wmediumd Console
```

Set `EASYMESH_WEBUI_HOST_IP=0.0.0.0` and
`WMEDIUMD_CONSOLE_HOST_IP=0.0.0.0` only on a trusted lab network. Change the
port variables when another lab already owns the defaults.

## Portable image

After a passing check:

```sh
./build.sh snapshot
./build.sh export
```

`export` stops the VM, publishes it as `easymesh-lab-0828`, writes LXD's
portable image files under `gen/vm/lxd/artifacts/`, and creates an adjacent
checksum manifest. Import those files on another LXD host with `lxc image
import`, then initialize a VM from the imported alias.

Deleting is explicit and limited to `EASYMESH_LXD_NAME`:

```sh
./build.sh delete
```

The VirtualBox bundle remains a compatibility release. New LXD acceptance is
performed independently; it does not weaken or rewrite the 0828 VirtualBox
artifact.
