# Deploy and operate RDK

[Home](../README.md) · [Deployment reference](../reference/deployment/README.md)

## Install once

| Need | Authoritative procedure |
| --- | --- |
| Import an LXD thin tar | [LXD appliance](../../../gen/vm/lxd/README.md) |
| Windows, Vagrant and VirtualBox | [VirtualBox guide](../../../gen/vm/virtualbox/README.md) |
| Build RDK images from a fresh checkout | [Source build](../../build/README.md) |
| Direct Linux/radio-host setup | [Direct radio-host guide](../reference/deployment/bare-metal.md) |
| Add LXD UI, Grafana and outer-VM metrics | [Monitoring](../reference/observability/monitoring.md) |

Use [current state](../current-state.md) for artifact names and live VM identity.
Verify outer and extracted checksums before import. A thin import provisions
locally; source builds and optional monitoring dependency installation need
network access. Keep room deployments on profile 20.

The audited clean source build deliberately uses workspace-local downloads and
sstate, with external mirrors disabled. Do not assume it uses `~/oe/` merely
because a separate development build does; verify effective BitBake configuration.
The build guide owns cache overrides and reproducibility requirements.

## Everyday lifecycle

On the physical LXD host, replace VM with the name from `lxc list`:

```sh
VM=rdkeasymesh-20-0908
lxc config get "$VM" boot.autostart
lxc start "$VM"
lxc exec "$VM" -- systemctl is-active easymesh-lab.service easymesh-room-demo.service
lxc exec "$VM" -- journalctl -u easymesh-lab.service -u easymesh-room-demo.service -n 80 --no-pager
```

Start only a stopped instance. Imports default to `boot.autostart=false`.
Inside a started VM, systemd starts the nested lab and room automatically.
Use `lxc stop "$VM"` for normal shutdown, not forced termination.

The guest checkout is `/home/easymesh/git/meta-cmf-bananapi-vcpe`.
Use the packaged units instead of running another room conductor or recreating
the containers. Preserve current client/mesh identities during feature tests.

## After a reboot or an unreachable URL

LXD NAT proxy devices are persistent instance configuration, not manually
recreated shell forwarders. Inspect before changing anything:

```sh
lxc list
lxc config device show "$VM"
lxc exec "$VM" -- ip -4 address
lxc exec "$VM" -- systemctl --failed
lxc exec "$VM" -- curl -fsS http://127.0.0.1:8891/api/demo/state
```

Wait for native reconstruction; first import takes longer than a warm start.
If guest HTTP works but the host URL fails, check the configured bind address,
guest address, NAT proxy and firewall. If guest HTTP fails, inspect service
journals first. Do not stack duplicate proxies or reimport over a working VM.

## Recovery and safe testing

Stop `easymesh-room-demo.service` before a native acceptance script or another
RF writer. Restart it after the test. A paused browser is not the same as
stopping the room's optimizer. Preserve the original service configuration.

Room RF restoration uses a checksummed ownership journal and stable inventory.
A mismatched generation, daemon identity or inventory must fail closed. Retain
the fault/journal and diagnose it; deleting the journal to bypass recovery can
leave hidden RF changes. See [coordination](../reference/rooms/architecture.md).

Delete a VM only after positively identifying it as obsolete, stopping it and
preserving wanted evidence. Monitoring removal has additional credential cleanup;
follow its guide rather than copying an installed monitoring directory into a tar.
