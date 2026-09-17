# Current RDK lab

Reviewed 17 September 2026. This is a deployment summary, not a live health
monitor; use [operations](guide/operations.md) for current service checks.

## Identity and release status

| Item | Current value |
| --- | --- |
| Canonical branch | `codex/0916-clean` |
| Canonical checkout | `rev140:/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0916-clean/meta-cmf-bananapi-vcpe` |
| Candidate appliance | `rev140:rdkeasymesh-0916` |
| Packaged runtime/source origin | `294dd6d394663d08edf2cd68f31d496ad4b7b6cc` |
| Guest checkout | `/home/easymesh/git/meta-cmf-bananapi-vcpe` |
| Platform | Ubuntu 24.04 / Linux 7 radio host, RDK-B containers, userspace wmediumd |
| Fixed pool | 100 clients; five mesh containers / six displayed roles |
| Release classification | 0916 candidate with known issues; not fully room-qualified |
| prplMesh peer | Separate repository and appliance on rev150 |

Controller and Agent-1 share the root container; four extenders complete the
mesh. Default selects ten private and ten IoT clients. Loading a room does not
resize the permanent container/radio pool. Outer VM autostart is disabled.

Both final Yocto images build using `/home/rev/oe/downloads` and
`/home/rev/oe/sstate-cache`. The station-lifetime repair, native AP threshold/query
handling and proactive native backhaul steering remain included. Documentation
updates after the runtime commit do not imply rebuilt native binaries.

## Qualification and remaining failures

The latest normal lifecycle passes all 105 containers, 100 client identities and
an independent audit covering exactly 100 unique clients with zero packet loss.
Final-image/runtime alignment, retained assets, initial Default-20 restoration
and the bounded zero-additional-medium-receive-drop observation also pass.

**The subsequent geometry branch room fails complete convergence and its bounded
Default recovery check.** It does form valid rooted branches:
ext3→ext1→agent-1 and ext4→ext2→agent-1. The combined uplink/client/traffic/two-view
predicate fails; a visible branch is not full-room acceptance. Samples include
missing fresh candidate metrics, incomplete model associations and HTTP 503
candidate-query responses. These are symptoms, not an established root cause.

That focused failure stopped the latest full 22-client-room + 3-geometry-room
campaign and later pool qualification. Older room passes do not qualify this
exact runtime. Current-source handover and outage acceptance remain incomplete.
Live medium replacement is not qualified; use the normal lab stop/start lifecycle.

The later export prerequisite again passed all 100 traffic probes but failed
the expected 5-device/15-radio/50-BSS/104-STA topology-model counts. Its failed
audit is retained. A private, explicitly recorded candidate-packaging wrapper
skips that qualification call; tracked acceptance gates and native code remain
unchanged. Packaging is not a topology-audit pass.

The owner requested packaging with these limitations on 17 September, without
further debugging. This supersedes the earlier hold for complete room acceptance;
it does not turn failed or unexecuted tests into passes.

Evidence on rev150 is under `/home/rev/work/release-0916/`, particularly:

- `evidence/rdk-native-reconstruction-294dd6d-medium-01/`
- `evidence/rdk-image-runtime-alignment-294dd6d-medium-01/`
- `evidence/rdk-native-geometry-294dd6d-medium-01/rdk-native-geometry-20260917T155634Z/results/report.json`

## Access and distribution

Candidate forwarding is configured for these addresses. Packaging temporarily
stops services; an address is not a promise of current health.

| View | rev140 RDK |
| --- | --- |
| Live room | <http://192.168.2.140:49891/> |
| Network topology | <http://192.168.2.140:49889/> |
| wmediumd console | <http://192.168.2.140:49890/> |

Packaging alone does not promote production ports 48889/48890/48891 or enroll
monitoring on 48892/48893. Use the [monitoring guide](reference/observability/monitoring.md)
for nested-container and outer-VM metrics. No `?mode=` is needed. Proxy devices
survive reboot; management interfaces require a trusted LAN/VPN.

### Post-export appliance state

The 0916 export thinned the running qualification appliance and started its
normal 100-client reconstruction. At the final packaging check, the bounded
outer restoration wrapper had ended while `easymesh-thin-firstboot.service` was
still active. `easymesh-lab.service` and `easymesh-room-demo.service` were
inactive, so the RDK room URL must be treated as unavailable until that normal
first-boot service completes. This is an operational recovery limitation; it was
recorded without debugging or forcing the service. See the release-side
`PACKAGING-STATUS.md` for the timestamp and evidence location.

0916 artifacts belong under `/home/rev/releases/0916/`: RDK thin tar, RDK
VirtualBox box and its Windows/Vagrant wrapper. Adjacent SHA-256 files,
`release.json`, `KNOWN-ISSUES-0916.md` and packaging receipts identify actual
inputs and completed checks. Archive integrity, exact-archive fresh import,
Linux VirtualBox boot and Windows testing are separate claims. Unrecorded
checks are not passed. See [release information](release-notes.md).

The 0916 box builds and passes archive checks. Its bounded rev120 Vagrant smoke
stopped before boot because querying a pre-existing inaccessible VirtualBox
registration returned `E_ACCESSDENIED`. Boot/login, native pool provisioning and
Windows operation remain unverified. `CANDIDATE-BOOT.json` and `BOOT-LOG.txt`
inside the VirtualBox wrapper record the attempt; no unrelated VM was modified
to work around the failure.

Verified older downloads and rollback material remain on rev140. Redundant
rev150 copies were removed only after full hash verification, recovering
77.17 GiB; shared OE caches and unique evidence were preserved.

## Supported behavior and boundaries

- Loading immediately applies a world. Play, drag, presence, traffic probes,
  shared signal colors, fullscreen and room-following topology remain supported.
- The external reference optimizer supplies client policy through native BTM;
  this is not a claim of native autonomous client optimization.
- Most rooms protect startup backhaul; three geometry rooms change AP-to-AP RF
  without externally choosing parents. Loss recovery and proactive steering differ.
- Convergence requires membership, native ownership, fresh eligible candidates
  and traffic, not just a green badge or an accepted steering request.
- Keep host cooling and observer load separately attributed. Grafana guest
  resource metrics do not measure physical-host totals or subsecond roam latency.
- [Neighbor-network rooms](reference/proposals/neighbor-rooms/design.md) remain
  proposed; [room acceptance](reference/testing/room-acceptance.md) defines tests.
