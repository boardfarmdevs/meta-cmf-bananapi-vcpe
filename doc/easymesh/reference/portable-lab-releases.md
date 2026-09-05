# Portable LXD VM releases

Each EasyMesh implementation has one universal thin appliance. RDK EasyMesh
0905 is the new release under qualification; prplMesh remains at its separate
0904 checkpoint. See the RDK [current state](../current-state.md) for acceptance
evidence rather than treating the release name as proof of qualification.

| Artifact | Selectable clients | Default host ports |
| --- | --- | --- |
| `rdkeasymesh-0905-thin.tar` | 20, 50, or 100 | EasyMesh WebUI `18889`, wmediumd Console `18890`, live room `18891` |
| `prplmesh-0904-thin.tar` | 20, 50, or 100 | wmediumd Console `8090`, Controller UI `8091`, live room `18891` |

There are no profile-specific downloads. Import selects exactly one immutable
20-, 50-, or 100-client profile. Each archive contains an installed Ubuntu
24.04/Linux 7 LXD VM, the exact source and offline runtime inputs, and no
provisioned mesh nodes. Userspace wmediumd remains the default medium; the
kernel-medium implementation remains optional research work.

The adjacent `.tar.sha256` is the download identity. After extraction,
`release.json` records the source commit, release ID, supported profiles, VM
backup name and resource contract. Do not infer identity from the filename
alone.

## Install from an empty directory

Place one archive and its adjacent checksum in an empty directory:

```sh
sha256sum -c rdkeasymesh-0905-thin.tar.sha256
tar -xf rdkeasymesh-0905-thin.tar
cd rdkeasymesh-0905-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
./import.sh --profile 20
```

For prplMesh use `prplmesh-0904-thin` instead. Select profile `50` or `100`
only when the host meets the resources in `release.json`. Import refuses a
missing or invalid choice and does not overwrite an existing instance.

The importer verifies the release, imports and reseeds the VM, waits for the
outer VM agent and nested LXD, writes the immutable profile lock, publishes
site-local UI proxies, and starts offline first-boot provisioning. First boot
is longer than a normal restart because it creates the selected nested roster.
Later VM starts use the normal runtime reconstruction path.

## Profiles

| Stack | Profile | vCPU | RAM | hwsim radios | Sparse disk |
| --- | ---: | ---: | ---: | ---: | ---: |
| RDK EasyMesh | 20 | 6 | 8 GiB | 32 | 96 GiB |
| RDK EasyMesh | 50 | 8 | 12 GiB | 64 | 96 GiB |
| RDK EasyMesh | 100 | 12 | 20 GiB | 128 | 96 GiB |
| prplMesh | 20 | 6 | 8 GiB | 40 | 160 GiB |
| prplMesh | 50 | 8 | 12 GiB | 72 | 160 GiB |
| prplMesh | 100 | 12 | 20 GiB | 120 | 160 GiB |

The prplMesh stress disk is 160 GiB. Sparse capacity is not archive size;
physical destination use grows as the selected profile provisions clients and
writes runtime state.

## Site overrides

The archive contains no fixed LAN address. Use the receiving host address and
an existing storage pool when defaults are unsuitable:

```sh
EASYMESH_LXD_STORAGE=bpi-lab \
EASYMESH_WEBUI_HOST_IP=192.168.2.140 \
  ./import.sh --profile 50
```

```sh
PRPLMESH_LXD_STORAGE=bpi-lab \
PRPLMESH_UI_HOST_IP=192.168.2.140 \
  ./import.sh --profile 50
```

Default instance names are `rdkeasymesh-PROFILE-0905` and
`prplmesh-PROFILE-0904`. The bundled README documents name and port overrides
for multiple labs on one host.

When replacing an existing lab, first qualify the new instance on spare host
ports if resources permit. Before reassigning the normal ports, stop any active
room gracefully and verify its RF-restoration record. Retain the old VM for
rollback, stop it, and set its `boot.autostart` to `false`; do not leave two
auto-starting instances claiming the same host ports. The importer never
overwrites an existing instance or chooses which old VM to retire.

## Verify and operate

RDK EasyMesh:

```sh
lxc exec rdkeasymesh-20-0905 -- \
  /usr/local/sbin/easymesh-labctl check
lxc exec rdkeasymesh-20-0905 -- \
  journalctl -fu easymesh-lab.service
```

prplMesh:

```sh
lxc exec prplmesh-20-0904 -- prplmesh-lab-start status
lxc exec prplmesh-20-0904 -- \
  journalctl -fu prplmesh-lab.service
```

Both imported VMs default to `boot.autostart=true`. `lxc stop INSTANCE` and
`lxc start INSTANCE` provide normal warm lifecycle control.

## Archive layout

Each outer tar contains one directory:

```text
STACK-RELEASE-thin/
|-- STACK-RELEASE-COMMIT-thin-lxd.tar.zst  LXD VM backup
|-- import.sh                            profile and site reconciliation
|-- install-host.sh                      Ubuntu 22.04/24.04 host setup
|-- README.md                            operator instructions
|-- RELEASE-NOTES.md                     delivered checkpoint summary
|-- release.json                         profiles and source identity
|-- release.env                          importer contract
|-- trim-report.txt                      packaging evidence
`-- SHA256SUMS                           inner integrity manifest
```

For the RDK 0905 release, distribute these two files together:

```text
EasyMesh-LXD-0905/
|-- rdkeasymesh-0905-thin.tar
`-- rdkeasymesh-0905-thin.tar.sha256
```

Google Drive is transport only. Never replace an archive without also
publishing its newly generated checksum.
