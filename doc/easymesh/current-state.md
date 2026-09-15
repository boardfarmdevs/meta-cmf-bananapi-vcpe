# Current RDK lab

Reviewed 14 September 2026. This is the deployment/release summary, not a live
health monitor. Use the browser and service checks in [operations](guide/operations.md)
to check a machine now.

## Source and deployments

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0913-clean` |
| Canonical checkout | `rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0913-clean/meta-cmf-bananapi-vcpe` |
| Deployed appliance | `rev140:rdkeasymesh-0913`, accepted from the exact 0913 thin tar |
| Packaged source | `40a9064`; native images rebuilt from `5d954ad` |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd |
| Fixed pool | 100 clients; default room selects 20 online; five mesh containers / six displayed roles |
| prplMesh peer | Separate repository and appliance on rev150; no prpl lab on rev140 |

Controller and Agent-1 share the root container. Four extenders complete the
mesh. The default twenty clients comprise ten private and ten IoT stations. A room may
make roles unavailable without destroying containers or resizing the appliance.
Outer VM autostart is disabled; manually starting the VM starts its lab and room.

0913 provides one 100-client-capacity appliance, a default room with 20 online
clients, and `fifty-client-counter-roam`. Both Yocto images have rebuilt using
`/home/rev/oe/downloads` and `/home/rev/oe/sstate-cache`. The 2026-09-14 bounded
room qualification passes **18/18 rooms**, including initial convergence,
playback, checkpoints, physical ownership and rendered topology. All 144
submitted steering actions verify with traffic; no native response timeouts
or unavailable candidate collections occur. Default twenty-client restoration
also passes. The exact sanitized thin tar independently passes fresh
zero-to-105-container provisioning, the 100-client native/traffic baseline,
50-client, 5-to-6-GHz and 10-client room playback, and default-20 restoration.
First provisioning took 84 minutes 56 seconds on this host; it is a one-time
operation, not room-switch latency. Inner/outer monitoring and subsequent
default-room traffic pass. The obsolete 0908 lab VM and its restricted metrics
certificate are removed. The stopped 0913 thin builder remains available.

## Browser addresses

| View | rev140 RDK |
| --- | --- |
| Live room | <http://192.168.2.140:48891/> |
| Network topology | <http://192.168.2.140:48889/> |
| wmediumd console | <http://192.168.2.140:48890/> |
| Inner LXD UI | <https://192.168.2.140:48892/ui/> |
| Grafana: inner containers and outer VM | <https://192.168.2.140:48893/> |

These ports now serve the accepted 0913 import; temporary 498xx test ports are
retired. Monitoring is installed after sanitized export so enrollment keys and
passwords cannot enter release images. Both authenticated Grafana dashboards
pass checks, with metrics for all 105 nested containers and the outer VM.
See [monitoring](reference/observability/monitoring.md) for browser enrollment.

No `?mode=` is needed. LXD proxy devices persist across host/VM reboots;
do not recreate them after every start. The destination services still need
time to reconstruct. Management access requires a trusted LAN/VPN; LXD UI and
Grafana additionally require enrollment/login.

## Distribution artifacts

[Release information](release-notes.md) explains where historical records belong.

Both rev140 and rev150 mirror the **0913** downloads under
`/home/rev/releases/0913/`:

- `rdkeasymesh-0913-thin.tar`: accepted universal LXD import; no profile selection.
- `rdkeasymesh-0913-virtualbox.tar`: Windows/Vagrant distribution wrapper.
- `rdkeasymesh-0913-virtualbox/rdkeasymesh-0913-virtualbox.box`: actual box.

Use the adjacent SHA-256 files, bundle `release.json`, and release-directory
`rdk-0913-acceptance.json` for exact source, image and accepted outer-tar
identities. The embedded candidate status records creation time; the adjacent
acceptance record applies to those unchanged bytes. Older downloads are
historical, not the current deployment.

The new box passes image integrity, OVF dry-run, Vagrant configuration and
checksum checks. Its separate `acceptance.json` explicitly says
**artifact-validated-boot-unverified**: rev120 was unreachable, so no actual
VirtualBox guest or Windows boot was tested. The running KVM labs were not
stopped to work around that limitation.

## Supported behavior and limits

- Worlds apply immediately on load; Play, drag, presence changes, shared signal
  colors, traffic-probe selection and both fullscreen views are implemented.
- The deployed profiling configuration uses an **external** client policy and
  unassisted native BTM. Backhaul is protected at startup, not automatically
  optimized from room geometry. A star is not necessarily a reporting defect.
- Band setup uses transaction-scoped client namespaces with process identity,
  native settings/readback and association checks. Band audits query their
  participants concurrently. World acknowledgements match the requested room,
  not a late reply to its predecessor.
- Profiling candidate caches now track committed RF changes per client, not
  only world and association changes. Moving an AP invalidates all affected
  client comparisons; moving clients invalidates their own cached and in-flight
  results without cancelling unrelated collection or resetting fair scheduling.
  This prevents steering with pre-drag measurements marked as current.
- The hwsim HAL preserves per-BSS receive context and requires a validated MLO
  link before frequency-only redirection. Off-channel legacy notifications no
  longer generate duplicate probe responses; live captures verify one response
  per private BSSID instead of three. Physical-driver behavior is unchanged.
- Strict convergence requires membership, physical/native ownership, fresh
  eligible candidates and traffic—not a green badge or an accepted request.
- Monitoring covers inner LXD containers and the outer VM's guest resources;
  it does not measure physical-host totals or subsecond steering latency.
- Host cooling/throttling is a separate unresolved capacity concern, not proof
  of memory exhaustion. Keep observer load out of native performance claims.
- Neighbor-network rooms remain a [proposal](reference/proposals/neighbor-rooms/design.md).

Current room, RF and native-to-browser evidence is indexed in
[room acceptance](reference/testing/room-acceptance.md); thin-import evidence
remains under `/home/rev/releases/0913/evidence/rdk-0913-final/`. All five
imported HAL libraries and the running medium match the qualified binary hashes.
These are bounded tests, not soak qualification or an intrinsic RDK/prpl speed
ranking. Use [room acceptance](reference/testing/room-acceptance.md) for new runs.
