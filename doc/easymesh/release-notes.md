# EasyMesh lab release notes

Release identifiers describe tested lab delivery checkpoints, not upstream RDK-B or Wi-Fi EasyMesh versions.

## 0824

- Established the concise, current-state documentation set and the accepted container/hwsim/wmediumd architecture.
- Made controller, extender, and client onboarding repeatable with stable identities, deterministic steering helpers, recovery checks, and a reduced Boardfarm WAN/DHCP deployment.
- Added the usable topology view, client and backhaul visibility, configurator scenarios, reference optimizer, tests, and the packaged VirtualBox lab handoff.

## 0828

- Added the native LXD virtual-machine appliance and qualified bare-metal, VirtualBox, and LXD-VM deployment models.
- Made radio identity and deterministic steering independent of transient interface enumeration and bounded controller, nested-LXD, and wmediumd operations.
- Strengthened dynamic wmediumd scenario control, closed-loop optimizer tests, release provenance, and topology-aware WebUI layout.

## 0831

- Made LXD VM the primary portable appliance and supplied immutable 20-, 50-, and 100-client profiles with faster bounded lifecycle operations.
- Added the optional kernel-medium research backend while retaining userspace wmediumd as the default, including common telemetry, tests, and performance/scale evaluation.
- Fixed long-run AP-metrics memory growth, stale station ownership after roaming, medium/VIF ownership ambiguity, controller command lifetime, DHCP recovery, and cross-host appliance provisioning.
- Delivered portable, checksum-verified LXD bundles and import acceptance procedures suitable for redistribution.
