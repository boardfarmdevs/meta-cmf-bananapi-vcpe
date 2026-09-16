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
network access. 0913 has one fixed 100-client pool; the default room selects
20 online and other rooms select their own subset. There is no VM size profile.

The clean source build reuses `/home/rev/oe/downloads` and
`/home/rev/oe/sstate-cache` on the canonical build host, with external sstate
mirrors disabled. It records the effective BitBake configuration in build
evidence. This is a fresh workspace build, not a cache-empty rebuild.
The build guide owns cache overrides and reproducibility requirements.

## Topology RF hover

Hover an extender or Agent-1 to see native AP-reported BSS load: utilization
as percent and raw 0–255, associated stations per BSS, band/channel and report
receipt age. Interactive rooms collect reports passively; load-aware steering
remains opt-in. No hover-triggered measurement or policy change occurs.
Values older than five seconds, missing reports and collection errors show
unavailable, never fabricated zero. Shared-radio utilization is not additive
or calibrated physical capacity. Client-heard beacon BSS Load remains separate
in the room RF inspector. Both work without enabling Follow room layout.

## Everyday lifecycle

On the physical LXD host, replace VM with the name from `lxc list`:

```sh
VM=rdkeasymesh-0913
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
