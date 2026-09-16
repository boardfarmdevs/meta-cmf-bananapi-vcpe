# Current RDK lab

Reviewed 16 September 2026. This is a deployment summary, not a live health
monitor; use [operations](guide/operations.md) for current service checks.

## Source and deployments

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0916-clean` |
| Canonical checkout | `rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0916-clean/meta-cmf-bananapi-vcpe` |
| Running qualification appliance | `rev140:rdkeasymesh-0916`; fresh Yocto build, not released |
| Qualified room/runtime source | `0e1dce8` |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd |
| Fixed pool | 100 clients; five mesh containers / six displayed roles |
| Rollback | `rdkeasymesh-0913` stopped; previous downloads retained |
| prplMesh peer | Independent repository and appliance on rev150 |

Controller and Agent-1 share the root container; four extenders complete the
mesh. Default selects ten private and ten IoT clients. Loading a room does not
resize the permanent container/radio pool. VM autostart is disabled; manually
starting the VM starts its lab.

Both fresh 0916 Yocto images build using `/home/rev/oe/downloads` and
`/home/rev/oe/sstate-cache`. The patched controller retains the station-lifetime
repair and native AP threshold/query handling.

The 100-client baseline and **22/22 client rooms** pass, with independent
report validation, unchanged native identities and default twenty restoration.
Geometry branch and isolation/recovery also pass. The new stronger-parent
handover assertion remains unresolved: a usable 11 dB parent is retained despite
a 26 dB relay. The original room observed native choice, not guaranteed
proactive strongest-parent policy. This is not 25/25 qualification.
Evidence remains under `/home/rev/work/release-0916/evidence/` on rev150.

## Browser addresses

These temporary ports serve the running qualification VM:

| View | rev140 RDK |
| --- | --- |
| Live room | <http://192.168.2.140:49891/> |
| Network topology | <http://192.168.2.140:49889/> |
| wmediumd console | <http://192.168.2.140:49890/> |

Normal 48889/48890/48891 and monitoring 48892/48893 ports still target the stopped
rollback, not the candidate. Monitoring follows accepted sanitized export so
enrollment credentials cannot enter release images; it is not installed on
0916 yet. The supported setup covers all 105 nested containers and the outer VM;
see [monitoring](reference/observability/monitoring.md).

No `?mode=` is needed. Proxy devices survive reboot; wait for guest services
rather than recreating forwarding. Management requires a trusted LAN/VPN.

## Distribution artifacts

**No 0916 thin tar or VirtualBox box has been published.** Exact-tar import,
monitoring promotion and old-download cleanup remain pending acceptance.
See [release information](release-notes.md).

Recorded rollback artifacts are mirrored under `/home/rev/releases/0913/`:

- `rdkeasymesh-0913-thin.tar`: universal LXD import.
- `rdkeasymesh-0913-virtualbox.tar`: Windows/Vagrant wrapper.
- `rdkeasymesh-0913-virtualbox/rdkeasymesh-0913-virtualbox.box`: actual box.

Adjacent SHA-256 files, bundle `release.json` and `rdk-0913-acceptance.json`
record exact source/image/archive identities. Historical acceptance does not
qualify the current candidate. The previous box is artifact-validated but
boot-unverified; rev120 remains unreachable, so no new actual VirtualBox or
Windows boot is claimed.

## Supported behavior and limits

- Loading applies a world immediately. Play, drag, presence, traffic probes,
  shared signal colors, fullscreen and room-following topology are implemented.
- The reference optimizer supplies client policy through unassisted native BTM;
  this does not assert native autonomous optimization.
- Most rooms protect startup backhaul; three geometry rooms change AP-to-AP RF
  without selecting parents. Recovery and proactive parent optimization differ.
- RF/association-scoped caches, generation guards and native band/ownership
  audits remain required. No stale measurement may become fresh by retrying.
- Strict convergence includes membership, physical/native ownership, fresh
  eligible candidates and traffic, not just a green badge or accepted request.
- Keep host cooling, observer load and native performance separately attributed.
  Monitoring guest resources is not measuring physical-host totals or
  subsecond steering latency.
- [Neighbor-network rooms](reference/proposals/neighbor-rooms/design.md) remain
  proposed; use [room acceptance](reference/testing/room-acceptance.md) for
  bounded test contracts and retained evidence.
