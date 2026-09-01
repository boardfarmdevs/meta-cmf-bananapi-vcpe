# Portable LXD VM releases

The distribution format is a stopped, coherent LXD virtual-machine appliance.
Two independent lab families use the same release contract:

| Stack | Profiles | Web interfaces |
| --- | --- | --- |
| RDK EasyMesh | 20, 50, 100 clients | EasyMesh `18889`, wmediumd `18890` |
| prplMesh | 20, 50, 100 clients | topology adapter `8090`, Controller UI `8091` |

Each client count is a separate appliance and is published in two flavors:

- `ready` contains the complete provisioned nested roster for the fastest cold
  start;
- `thin` contains the installed host, exact source and local runtime inputs,
  but zero provisioned mesh nodes. Its first boot builds the selected roster
  entirely offline and therefore takes longer.

Import never converts one profile into another. Stable radio identities, the
hwsim pool size, wmediumd roster and resource limits remain profile-specific.

## Release contents

A downloadable `*-bundle.tar` contains one directory:

```text
STACK-CLIENTS-DATE-COMMIT[-thin]-lxd/
|-- STACK-CLIENTS-DATE-COMMIT[-thin]-lxd.tar.zst  LXD VM backup
|-- import.sh                              portable import and proxy setup
|-- install-host.sh                        Ubuntu 22.04/24.04 LXD/KVM setup
|-- README.md                              empty-directory workflow
|-- release.json                           machine-readable identity
|-- release.env                            importer defaults
`-- SHA256SUMS                             inner integrity manifest
```

The adjacent `*-bundle.tar.sha256` authenticates the outer download. Neither
artifact contains a fixed outer-host IP address, host source mount, Git
credential or Google credential. Its checksum entry contains only the bundle
filename, never the release host's absolute path.

Before export, the builder removes both version-specific Secure-Boot settings
from the stopped VM. This prevents a backup made on an older LXD host from
retaining the retired `security.secureboot` key that current LXD rejects
during import. Before first boot, the importer disables Secure Boot using
`boot.mode=uefi-nosecureboot` or the guarded legacy fallback supported by its
destination LXD. Release metadata is populated from the instance's actual CPU,
memory and root-disk configuration rather than inferred profile defaults.

## Google Drive layout

Use one release folder and preserve the filenames produced by the packager:

```text
EasyMesh-LXD-0831/
|-- catalog.json
|-- rdkeasymesh-{20,50,100}-...-lxd-bundle.tar
|-- rdkeasymesh-{20,50,100}-...-lxd-bundle.tar.sha256
|-- rdkeasymesh-{20,50,100}-...-thin-lxd-bundle.tar
|-- rdkeasymesh-{20,50,100}-...-thin-lxd-bundle.tar.sha256
|-- prplmesh-{20,50,100}-...-lxd-bundle.tar
|-- prplmesh-{20,50,100}-...-lxd-bundle.tar.sha256
|-- prplmesh-{20,50,100}-...-thin-lxd-bundle.tar
`-- prplmesh-{20,50,100}-...-thin-lxd-bundle.tar.sha256
```

`catalog.json` lists the stack, profile, flavor, source commit, accepted
runtime-base commit where applicable, size, SHA-256, release status, Drive
file identifier and UI ports. Drive is only the transport; a release is
identified by its checked metadata and checksum. Publish a direct download
identifier only after uploading the immutable file.

## Empty-directory workflow

The operator downloads one profile and its checksum into an empty directory:

```sh
sha256sum -c DOWNLOADED-bundle.tar.sha256
tar -xf DOWNLOADED-bundle.tar
cd STACK-CLIENTS-DATE-COMMIT-lxd
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
./import.sh
```

`import.sh` selects the single VM backup beside it, detects the outer host's
default IPv4 address, chooses an unused guest address, installs the UI proxies,
starts the VM, and prints the monitor and health commands. Site overrides such
as instance name, LXD network, host address and ports remain environment
variables documented in the bundle README.

## Candidate versus accepted

Packaging creates `status: candidate`. A release engineer changes the catalog
status to `accepted` only after a clean import on another host passes:

1. exact source, client, radio and process cardinality;
2. cold reconstruction without an operator repair command;
3. both HTTP health gates and complete topology;
4. all-client data traffic and representative steering;
5. configurator and optimizer restoration gates;
6. a one-hour churn soak for that exact profile; and
7. bounded CPU, memory, storage, logs and startup/shutdown time.

A thin candidate additionally has to prove that its exported inventory is
empty, the first boot performs no clone, pull or download, the final inventory
matches the selected profile, and its pending marker is cleared only after the
normal acceptance gates pass. A longer first boot is expected and is not a
failure by itself.

Failure in one profile does not demote another profile, but a 20-client result
must never be used to label a 50- or 100-client artifact accepted. Userspace
wmediumd remains the portable release default; the kernel medium is an
explicit experimental selection.

At the current evaluation point, the release tooling supports all three
profiles. Acceptance evidence is still profile-specific: an artifact must not
be uploaded as accepted until its one-hour campaign and foreign-host import
have completed.
