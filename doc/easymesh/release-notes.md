# EasyMesh lab release notes

Release identifiers describe tested lab delivery checkpoints, not upstream RDK-B or Wi-Fi EasyMesh versions.

## 0905

- Establishes `codex/0905-clean` and the rev140 workspace
  `/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean` as canonical. Rebuilds both
  role images from fresh Yocto build directories using an immutable upstream
  lock, before producing the universal `rdkeasymesh-0905-thin.tar` appliance.
- Includes the searchable 17-section in-viewer manual, complete fleet
  reconciliation, movable mesh nodes, bounded fronthaul outages, and recorded
  interactive movement controls.
- Keeps the interactive viewer running during temporary candidate-metric
  transport outages. Steering pauses, stale convergence is cleared, and a
  capped retry backoff requires new measurements before evaluation resumes.
  Malformed measurements and scripted-run failures remain fail-closed.
- Adds extender uplink signal bars, larger station identities, quoted
  color-matched IoT/private labels, and a compact centered initial star.
  Optimize Layout fits the available pane without undoing manual device or
  client positions.
- Targets fresh 20-client imports on rev140 and rev150. Build, import, and
  interactive-room acceptance results are recorded in
  [current state](https://github.com/boardfarmdevs/meta-cmf-bananapi-vcpe/blob/codex/0905-clean/doc/easymesh/current-state.md);
  this section alone does not certify an untested artifact.
- Fixes an onboarding race found by the fresh builder's reboot gate:
  answering a client-capability query no longer marks an unconfigured radio
  configured. Both complete role images include patch `0154`.
- Pins the Boardfarm WAN AFTR build-stage migration to Bookworm, avoiding
  the obsolete Bullseye package downloads encountered during the clean build.
- Installs a checkout-aware health-audit wrapper so the appliance command
  finds its shared observer helpers instead of resolving them below `/usr`.
- Uses bounded HTTP retry loops compatible with rev140's curl 7.68, without
  requiring the newer `--retry-all-errors` option.
- Records and exports movement of the colocated gateway/Agent-1 as well as
  clients and extenders. Gateway movement during recording no longer faults
  the room; its protected presence control is unchanged.
- Serializes orchestrator command lifetime with candidate responses, rejection
  ACKs and controller radio timers. Patch `0155` prevents completion from
  freeing active command statistics during a manager timeout, while preserving
  immediate follow-up queries. Its compiled concurrency regression reproduces
  the previous race; replacement image and appliance acceptance are required.
- Keeps explicitly band-selected clients eligible for supported same-band AP
  channels after reboot, rather than pinning them to channels active during
  provisioning. Pool resume migrates legacy configurations; boundary tests
  exclude hwsim's 5925 MHz 5 GHz edge from the 6 GHz allow-list.
- Adds an opt-in nested LXD web UI and Prometheus/Grafana setup bundle with
  loopback access, metrics-only TLS credentials, a provisioned container
  dashboard, and documented rollback. Monitoring remains disabled in the
  portable base image; credentials are generated separately after import.

## 0824

- Established the concise, current-state documentation set and the accepted container/hwsim/wmediumd architecture.
- Made controller, extender, and client onboarding repeatable with stable identities, deterministic steering helpers, recovery checks, and a reduced Boardfarm WAN/DHCP deployment.
- Added the usable topology view, client and backhaul visibility, configurator scenarios, reference optimizer, tests, and the packaged VirtualBox lab handoff.

## 0828

- Added the native LXD virtual-machine appliance and qualified bare-metal, VirtualBox, and LXD-VM deployment models.
- Made radio identity and deterministic steering independent of transient interface enumeration and bounded controller, nested-LXD, and wmediumd operations.
- Strengthened dynamic wmediumd scenario control, closed-loop optimizer tests, release provenance, and topology-aware WebUI layout.

## 0831

- Made LXD VM the primary portable appliance. One thin artifact per mesh stack
  now selects and locks an immutable 20-, 50-, or 100-client profile at import,
  instead of duplicating the installed VM in three downloads.
- Added the optional kernel-medium research backend while retaining userspace wmediumd as the default, including common telemetry, tests, and performance/scale evaluation.
- Fixed long-run AP-metrics memory growth, stale station ownership after roaming, medium/VIF ownership ambiguity, controller command lifetime, DHCP recovery, and cross-host appliance provisioning.
- Delivered portable, checksum-verified LXD bundles and import acceptance procedures suitable for redistribution.
- Fixed the common multichannel hwsim monitor-ACK null-channel fault and added
  a live regression that rejects a kernel Oops, wmediumd death, or nl80211
  deadlock.
- Reduced the portable handoff to `rdkeasymesh-0831-thin.tar` and
  `prplmesh-0831-thin.tar`. Each archive requires an immutable 20-, 50-, or
  100-client selection at import and provisions entirely from local inputs.
- Made import wait for the nested LXD API before publishing the profile lock
  and UI proxies, eliminating a first-boot race on a newly imported VM.

## 0901

- Eliminated the second whole-lab reconstruction after offline thin
  provisioning. A boot-scoped, one-use handoff preserves the validated running
  roster while retaining the normal final health audit and cold-start fallback.
- Aligned the RDK and prplMesh controller topology presentation and wmediumd
  Console, including filtering inactive reserve radios from the operational
  graph without removing them from raw inventory.
- Documented the MediaTek single-wiphy to three-logical-radio contract, its
  hwsim projection, and the resulting patch, steering, metric, lifecycle and
  performance boundaries.
- Made portable release identifiers explicit in bundle metadata and import
  defaults so a 0901 artifact creates clearly named 0901 instances while old
  0831 bundles remain reproducible.

## 0902

- Rebased the complete RDK EasyMesh lab layer onto a fresh current RDK Central
  checkout and removed recipe patches whose fixes are now present upstream.
- Refreshed the remaining OneWifi, Wi-Fi HAL and Unified Wi-Fi Mesh patches to
  their current source locations, including correct topology-response parsing
  and ownership-safe JSON and client-stat cleanup.
- Verified the five recipes that originally failed during fetch or patch and
  compiled the four affected Wi-Fi/EasyMesh components successfully.
- Locked the successful `kirkstone`/`rdk-next` source state to immutable commit
  IDs so later builds do not silently consume moving RDK Central branches.
- Restored controller-first appliance startup after clean reboot acceptance
  proved that controller/extender overlap can miss all four backhaul STA model
  rows even though their physical links are connected.

## 0903

- Consolidated the current RDK and prplMesh deliveries into one universal thin
  LXD appliance per stack. Each appliance selects 20, 50, or 100 clients at
  import and contains the exact offline inputs needed for first provisioning.
- Corrected hidden-SSID BTM candidate selection so a station uses an actually
  discovered `(BSSID, current SSID)` record instead of an empty hidden-beacon
  cache entry, while retaining the normal ESS and security checks.
- Made deterministic steering derive the target channel and operating class
  from the live AP interface. This corrected private-SSID steering on the
  lab's actual 5955 MHz 6 GHz channel rather than trusting stale model data.
- Added `steer-soak.sh` for one live pass or a bounded number of topology-aware
  sequential steers, and `steer-batch.sh` for one atomic RF transaction with
  multiple concurrent station moves and independent verification.
- Documented the exact single-steer and carousel RF behavior and added the
  initial live-room demonstration implementation plan.
- Retained one known limitation explicitly: directed discovery of the hidden
  IoT secondary BSS on the 6 GHz RDK multi-VAP radio is not yet reliable. The
  2.4 and 5 GHz IoT paths and private-SSID tri-band steering remain available.

## 0904

- Added the closed-loop live-room presentation to both RDK EasyMesh and
  prplMesh. A common Golden World drives the configurator and wmediumd while a
  browser follows motion, RF state, observations, decisions and steering
  outcomes on one synchronized timeline.
- Added a portable live-room endpoint to both universal thin appliances and
  retained the same viewer contract and appearance across the two mesh stacks.
- Added link-aware vertical client signal meters to make live RF changes easy
  to recognize without obscuring the radio-link animation.
- Kept the stack-specific adapters local to each repository for this release;
  extracting the common room, scenario and visualization components remains a
  later refactoring step.
