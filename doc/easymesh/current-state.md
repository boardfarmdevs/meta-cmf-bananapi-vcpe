# Current RDK lab

Reviewed 13 September 2026. This is the deployment/release summary, not a live
health monitor. Use the browser and service checks in [operations](guide/operations.md)
to check a machine now.

## Source and deployments

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0913-clean` |
| Canonical checkout | `rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0913-clean/meta-cmf-bananapi-vcpe` |
| Qualification appliance | `rev140:rdkeasymesh-0913` (not yet release-accepted) |
| Last accepted appliance | `rev140:rdkeasymesh-20-0908`, stopped for rollback |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd |
| Fixed pool | 100 clients; default room selects 20 online; five mesh containers / six displayed roles |
| prplMesh peer | Separate repository and appliance on rev150; no prpl lab on rev140 |

Controller and Agent-1 share the root container. Four extenders complete the
mesh. The default twenty clients comprise ten private and ten IoT stations. A room may
make roles unavailable without destroying containers or resizing the appliance.
Outer VM autostart is disabled; manually starting the VM starts its lab and room.

0913 is being qualified in the new canonical checkout. It provides
one 100-client-capacity appliance, a default room with 20 online clients, and
`fifty-client-counter-roam`. Both Yocto images have rebuilt using
`/home/rev/oe/downloads` and `/home/rev/oe/sstate-cache`. Room initial-convergence
qualification remains in progress; there is no accepted 0913 thin tar or box
yet. A transmitter/frequency queue-head correction passes the focused band,
50-client and default-walk rooms. The full eighteen-room rerun must pass
before release packaging. The old VM stays stopped while qualification runs.

## Browser addresses

| View | Last accepted ports | 0913 qualification ports |
| --- | --- | --- |
| Live room | <http://192.168.2.140:48891/> | <http://192.168.2.140:49891/> |
| Network topology | <http://192.168.2.140:48889/> | <http://192.168.2.140:49889/> |
| wmediumd console | <http://192.168.2.140:48890/> | <http://192.168.2.140:49890/> |
| Inner LXD UI | <https://192.168.2.140:48892/ui/> | Not installed yet |
| Grafana: inner containers and outer VM | <https://192.168.2.140:48893/> | Not installed yet |

The last accepted ports do not serve the stopped rollback VM. Qualification
services may restart during builds and tests. Monitoring is installed after
sanitized export so enrollment keys and passwords cannot enter release images.

No `?mode=` is needed. LXD proxy devices persist across host/VM reboots;
do not recreate them after every start. The destination services still need
time to reconstruct. Management access requires a trusted LAN/VPN; LXD UI and
Grafana additionally require enrollment/login.

## Distribution artifacts

[Release information](release-notes.md) explains where historical records belong.

Latest packaged downloads are **0909**; **0908** is the stopped rollback
appliance, not the active qualification VM. Both hosts mirror
`/home/rev/releases/0909/`:

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
- Event-driven association publication and radio-retune reporting repairs are
  present. Earlier fourteen-room acceptance, including extender loss, does not
  qualify the new 100-client pool. The 0913 release requires all eighteen rooms
  to pass the unchanged gates. The latest full catalog passes seventeen of
  eighteen rooms: the 50-client room has an intermittent initial-convergence
  failure on a 2.4 GHz client, although its playback and final convergence pass.
  Passing focused runs do not qualify this failure. Band audits now query
  only their participants concurrently, rather than all 105 containers. Band settings now
  use transaction-scoped client namespaces, retaining process identity checks,
  native commands, settings readback and the original association deadlines.
  Controls enter the unprivileged client's user namespace and use its binary
  search paths, rather than inheriting the outer systemd service's paths.
  Under that service environment, a read-only three-client settings capture
  falls from 0.92–0.94 seconds with LXD exec to about 0.114 seconds through native
  namespaces, with identical results and no concurrent host storage maintenance;
  this is not steering latency. World acknowledgements must
  also match the requested room, not a late reply to its predecessor. These
  corrections still require a clean full-catalog pass; historical failures
  remain retained.
- Profiling candidate caches now track committed RF changes per client, not
  only world and association changes. Moving an AP invalidates all affected
  client comparisons; moving clients invalidates their own cached and in-flight
  results without cancelling unrelated collection or resetting fair scheduling.
  This prevents steering with pre-drag measurements marked as current. Live
  requalification is pending; the 2.4 GHz probe-response fanout investigation
  also remains open despite the earlier receive-context correction.
- Strict convergence requires membership, physical/native ownership, fresh
  eligible candidates and traffic—not a green badge or an accepted request.
- Monitoring covers inner LXD containers and the outer VM's guest resources;
  it does not measure physical-host totals or subsecond steering latency.
- Host cooling/throttling is a separate unresolved capacity concern, not proof
  of memory exhaustion. Keep observer load out of native performance claims.
- Neighbor-network rooms remain a [proposal](reference/proposals/neighbor-rooms/design.md).

Current room, RF and native-to-browser evidence is indexed in
[room acceptance](reference/testing/room-acceptance.md); thin-import evidence
remains under `/home/rev/releases/0909/evidence/`. Live fixes are newer than
those unchanged packaged downloads.
These are bounded tests, not soak qualification or an intrinsic RDK/prpl speed
ranking. Use [room acceptance](reference/testing/room-acceptance.md) for new runs.
