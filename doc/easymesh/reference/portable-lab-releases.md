# Portable LXD VM releases

The distribution format is a stopped, coherent LXD virtual-machine appliance.
There is one universal thin download for each mesh implementation:

| Artifact | Profiles selected at import | Web interfaces |
| --- | --- | --- |
| `rdkeasymesh-0831-thin.tar` | 20, 50, or 100 clients | EasyMesh `18889`, wmediumd `18890` |
| `prplmesh-0831-thin.tar` | 20, 50, or 100 clients | topology adapter `8090`, Controller UI `8091` |

The release contains the installed Ubuntu 24.04/Linux 7 VM, exact source,
runtime inputs and one reusable nested-client image, but zero provisioned mesh
nodes. Import requires `--profile 20`, `--profile 50`, or `--profile 100`.
That choice sets the tested CPU/RAM limits and active hwsim pool, writes an
immutable profile lock, and only then permits offline first-boot provisioning.
There is no silent default and the selected appliance cannot be resized into a
different profile later.

Ready VMs remain useful as internal accepted builders and fast local recovery
points. They are profile-specific because they contain complete rosters, but
they are not the normal portable download.

## Release contents

Each outer tar contains one directory:

```text
STACK-0831-thin/
|-- STACK-0831-COMMIT-thin-lxd.tar.zst  LXD VM backup
|-- import.sh                            profile, identity, network and proxy setup
|-- install-host.sh                      Ubuntu 22.04/24.04 LXD/KVM setup
|-- README.md                            empty-directory workflow
|-- release.json                         machine-readable profiles and identity
|-- release.env                          importer contract
|-- trim-report.txt                      package cleanup and archive evidence
`-- SHA256SUMS                           inner integrity manifest
```

The adjacent `.tar.sha256` authenticates the outer download. Neither artifact
contains a fixed outer-host address, source mount, Git credential or Google
credential. Checksum entries use basenames rather than release-host paths.

The portable default is userspace wmediumd. The kernel medium is an explicit
experimental performance backend and is not selected in these packages.

## Empty-directory workflow

Download one tar and its checksum into any empty directory:

```sh
sha256sum -c STACK-0831-thin.tar.sha256
tar -xf STACK-0831-thin.tar
cd STACK-0831-thin
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
./import.sh --profile 20
```

Use profile `50` or `100` only when the host has the resources declared in
`release.json`. Site variables documented in the included README can select
the LXD network/storage pool, outer-host address, ports, and instance name.

The importer refuses to overwrite an existing instance. It reseeds portable
VM identities, selects destination CPU/RAM, starts the unconfigured VM, and
locks the requested profile while the nested inventory is still empty. RDK
also reconciles the guest NIC to the selected site address before publishing
its proxies. First-boot provisioning is then started asynchronously and can be
followed with the printed journal and health commands.

The common sparse logical disk supports the largest profile. Sparse capacity
is not download size: a smaller profile consumes only the blocks it writes,
while the destination storage pool must still support the declared logical
maximum and normal operating headroom.

## Google Drive layout

Only these portable files are required:

```text
EasyMesh-LXD-0831/
|-- catalog.json
|-- QUALIFICATION.md
|-- rdkeasymesh-0831-thin.tar
|-- rdkeasymesh-0831-thin.tar.sha256
|-- prplmesh-0831-thin.tar
`-- prplmesh-0831-thin.tar.sha256
```

Drive is transport only. `catalog.json`, the checked inner metadata and the
outer SHA-256 identify a release. Publish a Drive identifier only after the
immutable file has been uploaded and rechecked.

## Candidate versus accepted

Packaging marks a bundle as `candidate`. The exact same outer artifact bytes
must be imported independently with profiles 20, 50, and 100. Every run must
prove:

1. zero initial nested mesh nodes and one verified local runtime image;
2. no clone, pull, package download, or other external provisioning input;
3. exact source, profile lock, radio, node, client and process cardinality;
4. cold reconstruction without an operator repair command;
5. complete topology, both SSIDs, three bands and all-client traffic;
6. representative steering, metrics, configurator restore and optimizer gates;
7. a one-hour churn campaign with bounded resources and no process, database,
   VIF, kernel, or memory leak; and
8. a warm VM restart with the profile and identities unchanged.

The first-boot marker is cleared only after the normal acceptance suite passes.
A longer thin first boot is expected and is not a failure by itself. Evidence
and pass/fail state remain profile-specific, but the universal artifact becomes
distributable only after all three selections pass. A rebuilt archive receives
a new checksum and invalidates the earlier qualification even when its filename
is unchanged.
