# Portable EasyMesh LXD appliance

This directory is an exported appliance bundle. It contains a fixed-capacity
EasyMesh lab: controller, four extenders, 100-client capacity, hwsim and
wmediumd. Rooms choose the online client subset; they do not resize the VM.

For a source build, use `doc/easymesh/build/README.md` in the repository. That
guide builds the BPI images first, then creates a named VM and selects test tiers.

## Import

On an Ubuntu 22.04 x86-64 host with hardware virtualization:

```sh
sha256sum -c SHA256SUMS
sudo ./install-host.sh
newgrp lxd
EASYMESH_LXD_NAME=my-lab ./import.sh
```

The importer creates `my-lab-pool` with the LXD `dir` driver when necessary,
uses it again for a later replacement, chooses a free bridge address, and derives
a port block from the VM name. The first three ports serve the topology WebUI,
wmediumd Console and room viewer. Set `EASYMESH_PORT_BASE` only when a site
requires a specific port range.

The initial offline client-pool provisioning can take substantial time on a
directory-backed pool. Later starts use the normal runtime path. Imported VMs
have outer LXD autostart disabled.

## Operate

```sh
EASYMESH_LXD_NAME=my-lab ./build.sh status
EASYMESH_LXD_NAME=my-lab ./build.sh stop
EASYMESH_LXD_NAME=my-lab ./build.sh start
EASYMESH_LXD_NAME=my-lab ./build.sh check
EASYMESH_LXD_NAME=my-lab ./build.sh delete
```

`delete` removes only the named VM. It retains the matching storage pool. Review
and remove that exact pool with LXD only when its rebuild state is no longer needed.

## Monitoring

Monitoring is optional and excluded from exported appliances because it stores
generated credentials and data. After import:

```sh
host_ip=$(ip -4 route get 1.1.1.1 | awk '{for (i=1;i<=NF;i++) if ($i == "src") {print $(i+1); exit}}')
LAB_MONITORING_ALLOW_RESTART=1 \
  bash observability/enable.sh my-lab "$host_ip"
```

LXD UI and Grafana use the fourth and fifth ports in the same named block. See
`observability/README.md` for browser enrollment and credentials.

## Release maintenance

Use `build.sh export-thin` only after the required VM and room tests pass. The
export contains no provisioned nested lab instances and reconstructs them
offline on first boot. Verify `SHA256SUMS` and the outer archive checksum before
distribution. Archive integrity does not establish room or fresh-import acceptance.
