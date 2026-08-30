# EasyMesh LXD VM appliance

The portable EasyMesh lab is distributed as an LXD virtual-machine backup.

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
