# EasyMesh VM appliances

The portable RDK EasyMesh lab is available as an LXD virtual-machine backup
or a Vagrant/VirtualBox box. Both run the same Linux guest and nested LXD
containers; Windows does not need to run LXD itself.

The VM contains Ubuntu 24.04, Linux 7, Docker/Boardfarm, nested LXD, the BPI
controller and extender containers, WLAN clients, hwsim, wmediumd, the WebUI,
the wmediumd Console, configurator, optimizer, and acceptance tools. The lab
reconstructs automatically when the VM boots. A bare-metal host never starts
the lab automatically merely because it rebooted.

## Supported choices

| Deployment | Use |
| --- | --- |
| Bare metal | Development, kernel and medium debugging, maximum scale, and performance reference |
| LXD VM | Portable, isolated, reproducible engineering and demonstration appliance |
| Vagrant / VirtualBox | Windows x86-64 demonstrations using a local `.box` and `vagrant up --provider=virtualbox` |

For Windows installation, browser URLs, lifecycle and release building, use
[`virtualbox/README.md`](virtualbox/README.md). This provider supports RDK's
default 20-client lab, not prplMesh. A VirtualBox `.vbox` is just a machine
configuration; the portable download is a Vagrant `.box` containing the disk
and OVF, accompanied by a `Vagrantfile`.

Read the [0908 VirtualBox qualification](virtualbox/ACCEPTANCE-0908.md) for
the tested scope and the known native metrics/convergence limitation.

Use [`lxd/README.md`](lxd/README.md) for host installation, clean appliance
build, import, lifecycle, acceptance, export, and removal.

## Daily LXD VM operation

```sh
cd gen/vm/lxd
./build.sh status
./build.sh check
./build.sh restart
./build.sh stop
./build.sh start
```

The host exposes these guest services through LXD NAT proxy devices:

- EasyMesh WebUI: guest `8888`, default host `18889`;
- wmediumd Console: guest `8890`, default host `18890`.

The host address is selected at build or import time and is not baked into the
VM. Userspace wmediumd remains the default. The optional kernel medium is an
experimental backend selected inside the same appliance.

## Release artifacts

After a complete passing check:

```sh
./build.sh snapshot
./build.sh export
```

The export is one instance backup plus `SHA256SUMS`, `import.sh`,
`install-host.sh`, and this documentation. Import acceptance must be performed
on a second LXD host before publishing a release.
