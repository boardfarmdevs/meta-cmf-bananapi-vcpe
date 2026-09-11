# Current RDK lab

Reviewed 10 September 2026. This is the deployment/release summary, not a live
health monitor. Use the browser and service checks in [operations](guide/operations.md)
to check a machine now.

## Source and deployments

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0908-clean` |
| Canonical checkout | `rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0908-clean/meta-cmf-bananapi-vcpe` |
| Running appliance | `rev140:rdkeasymesh-20-0908` |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd |
| Default pool | 20 clients, five physical mesh containers / six displayed roles |
| prplMesh peer | Separate repository and appliance on rev150; no prpl lab on rev140 |

Controller and Agent-1 share the root container. Four extenders complete the
mesh. The twenty clients comprise ten private and ten IoT stations. A room may
make roles unavailable without destroying containers or resizing the appliance.
Outer VM autostart is disabled; manually starting the VM starts its lab and room.

## Browser addresses

| View | rev140 RDK |
| --- | --- |
| Live room | <http://192.168.2.140:48891/> |
| Network topology | <http://192.168.2.140:48889/> |
| wmediumd console | <http://192.168.2.140:48890/> |
| Inner LXD UI | <https://192.168.2.140:48892/ui/> |
| Grafana: inner containers and outer VM | <https://192.168.2.140:48893/> |

No `?mode=` is needed. LXD proxy devices persist across host/VM reboots;
do not recreate them after every start. The destination services still need
time to reconstruct. Management access requires a trusted LAN/VPN; LXD UI and
Grafana additionally require enrollment/login.

## Distribution artifacts

[Release information](release-notes.md) explains where historical records belong.

Latest packaged downloads are **0909**; the existing production VM is still
**0908**. Both hosts mirror `/home/rev/releases/0909/`:

- `rdkeasymesh-0909-thin.tar`: universal LXD import; select profile 20 for rooms.
- `rdkeasymesh-0909-virtualbox.tar`: Windows/Vagrant distribution wrapper.
- `rdkeasymesh-0909-virtualbox/rdkeasymesh-0909-virtualbox.box`: actual box.

Use the adjacent SHA-256 files, bundle `release.json`, and release-directory
acceptance/evidence for exact source and image identities. 0909 reuses accepted
0908 native builds with newer lab tooling; it is not another full Yocto rebuild.
Fresh thin imports passed bounded native/traffic checks. 0909 VirtualBox had
artifact checks, not a new guest-boot or Windows acceptance run. Packaging is
not proof of live deployment or complete room convergence.

## Supported behavior and limits

- Worlds apply immediately on load; Play, drag, presence changes, shared signal
  colors, traffic-probe selection and both fullscreen views are implemented.
- The deployed profiling configuration uses an **external** client policy and
  unassisted native BTM. Backhaul is protected at startup, not automatically
  optimized from room geometry. A star is not necessarily a reporting defect.
- RDK native candidate admission/HTTP 503–504 failures can leave incomplete
  measurements. Some 6-GHz target verifications fail. Do not claim all-room
  best-AP convergence or zero outside-stack latency.
- Strict convergence requires membership, physical/native ownership, fresh
  eligible candidates and traffic—not a green badge or an accepted request.
- Monitoring covers inner LXD containers and the outer VM's guest resources;
  it does not measure physical-host totals or subsecond steering latency.
- Host cooling/throttling is a separate unresolved capacity concern, not proof
  of memory exhaustion. Keep observer load out of native performance claims.
- Neighbor-network rooms remain a [proposal](reference/proposals/neighbor-rooms/design.md).

The retained room improvement evidence is under
`/home/rev/releases/0908/room-feature-improvements-20260909/`; newer thin-import
evidence is under `/home/rev/releases/0909/evidence/`.
These are bounded tests, not soak qualification or an intrinsic RDK/prpl speed
ranking. Use [room acceptance](reference/testing/room-acceptance.md) for new runs.
