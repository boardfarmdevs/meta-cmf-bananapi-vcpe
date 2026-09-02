# Portable LXD VM releases

The 0901 handoff has exactly two portable downloads:

| Artifact | Selectable clients | Default host ports |
| --- | --- | --- |
| `rdkeasymesh-0901-thin.tar` | 20, 50, or 100 | EasyMesh `18889`, wmediumd Console `18890` |
| `prplmesh-0901-thin.tar` | 20, 50, or 100 | wmediumd Console `8090`, Controller UI `8091` |

Published 0901 identities:

| Artifact | Bytes | SHA-256 | Source commit |
| --- | ---: | --- | --- |
| `rdkeasymesh-0901-thin.tar` | 2,075,002,880 | `e3128133f79073036addc5f9027bd0edaeec6f22ef00eb0b609ffe322e788684` | `8753e4762537f263ddaa46fef48f7167c4e8ce99` |
| `prplmesh-0901-thin.tar` | 1,816,176,640 | `250dc99e7390a916984478f5269c168d3dc9fbd2705b5e83bca95cf1f5d144cd` | `71102b3aae319d378c36c7bf80bca11cae0b5d59` |

There are no separate 20-, 50-, or 100-client downloads. The profile is an
explicit, immutable import choice. Each archive contains an installed Ubuntu
24.04/Linux 7 LXD VM, exact source and offline runtime inputs, but zero
provisioned mesh nodes.

Userspace wmediumd is the portable default. The kernel medium remains an
optional research backend and is not enabled in these appliances.

## Install from an empty directory

Place one tar and its adjacent checksum in an empty directory, then run:

```sh
sha256sum -c STACK-0901-thin.tar.sha256
tar -xf STACK-0901-thin.tar
cd STACK-0901-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
./import.sh --profile 20
```

Replace `STACK` with `rdkeasymesh` or `prplmesh`. Select profile `50` or `100`
only when the host has the resources declared in `release.json`. A missing or
invalid profile is rejected; import never chooses one silently.

The importer:

1. verifies the destination LXD network and optional storage pool;
2. imports and reseeds the VM without overwriting an existing instance;
3. waits for the outer VM agent and the nested LXD API;
4. writes the immutable 20-, 50-, or 100-client profile lock;
5. exposes site-local UI proxy ports; and
6. starts offline first-boot provisioning.

First boot is longer than a normal restart because it creates the selected
nested roster. It does not clone repositories, pull images, or require an
operator recovery sequence. Later boots use normal reconstruction.

## Profiles

| Stack | Profile | vCPU | RAM | hwsim radios | Sparse disk |
| --- | ---: | ---: | ---: | ---: | ---: |
| RDK EasyMesh | 20 | 6 | 8 GiB | 32 | 96 GiB |
| RDK EasyMesh | 50 | 8 | 12 GiB | 64 | 96 GiB |
| RDK EasyMesh | 100 | 12 | 20 GiB | 128 | 96 GiB |
| prplMesh | 20 | 6 | 8 GiB | 40 | 160 GiB |
| prplMesh | 50 | 8 | 12 GiB | 72 | 160 GiB |
| prplMesh | 100 | 12 | 20 GiB | 120 | 160 GiB |

Sparse logical capacity is not download size. The destination storage pool
must support the declared disk, while physical usage grows only as the selected
profile writes data.

## Site overrides

The included README documents all variables. Common examples are:

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

Instance names default to `rdkeasymesh-PROFILE-0901` and
`prplmesh-PROFILE-0901`. Override the documented name and port variables when
multiple labs share a host.

## Archive contents and identity

Each outer tar contains one directory:

```text
STACK-0901-thin/
|-- STACK-0901-COMMIT-thin-lxd.tar.zst  LXD VM backup
|-- import.sh                            profile and site reconciliation
|-- install-host.sh                      Ubuntu 22.04/24.04 LXD/KVM setup
|-- README.md                            operator instructions
|-- RELEASE-NOTES.md                     delivered checkpoint summary
|-- release.json                         profiles and source identity
|-- release.env                          importer contract
|-- trim-report.txt                      package evidence
`-- SHA256SUMS                           inner integrity manifest
```

The adjacent `.tar.sha256` verifies the outer download. `release.json` records
the source commit and supported profiles. The packages contain no host source
mount, Git credential, Google credential, fixed LAN address, or preselected
profile.

## Distribution layout

Only these files need to be uploaded:

```text
EasyMesh-LXD-0901/
|-- rdkeasymesh-0901-thin.tar
|-- rdkeasymesh-0901-thin.tar.sha256
|-- prplmesh-0901-thin.tar
`-- prplmesh-0901-thin.tar.sha256
```

Google Drive is transport only. Do not rename or rebuild an uploaded tar
without publishing its new adjacent checksum.
