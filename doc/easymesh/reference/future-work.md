# Virtual radio and medium future work

## Purpose

This document records future work for the `mac80211_hwsim` and wmediumd
subsystem. It deliberately does not propose additional room-viewer features.
The priority is to qualify the virtual medium as experimental infrastructure:
reliable lifecycle behavior, fail-closed operation, overload attribution,
correct receive and ACK semantics, defensible measurement provenance, and a
small physical-radio reference.

The recommendations were derived from a third-party source-and-evidence review
of revision `34ce1aa20798f49f1f90144473a123b65b9eb5fb`. No new lab tests were
performed as part of that review. Before implementation, every source-level
observation must be checked against the current branch, installed kernel,
wmediumd binary, RDK images, supplicant and active patch series.

## Intended claims and limits

Virtual operation is not itself a weakness. hwsim exercises the real Linux
mac80211 stack and real hostapd/wpa_supplicant management, association,
encryption and roaming behavior. The qualification problem is determining
which conclusions the virtual platform supports.

| Claim | Evidence required |
|---|---|
| EasyMesh works under controlled virtual conditions | real protocol exchanges, correct state transitions, independent association checks and repeatable tests |
| The optimizer is robust to plausible RF conditions | varied loss, measurement and client-behavior models; uncertainty testing; no simulator shortcuts entering policy inputs |
| Results predict physical Wi-Fi behavior | calibration and validation with physical devices, channels, traffic and client implementations |

A virtual steer directly supports the first claim, may contribute to the
second, and does not by itself establish the third. Correctness,
characterization and reproducibility take priority over a more elaborate RF
model.

## Existing baseline to preserve

The present convergence assessment characterizes the medium as useful for
fixed-roster, comparative, multichannel steering experiments, but not yet
qualified for arbitrary node lifecycle or calibrated physical-radio claims.
That distinction remains the baseline.

The platform should preserve:

- hwsim plus userspace wmediumd as the default reference backend;
- deterministic Golden Worlds for functional regression;
- real controller/agent/supplicant protocol paths;
- explicit simulator provenance on model-backed measurements;
- exact captured RF restoration where the medium instance remains valid; and
- the experimental kernel medium as a comparison backend, not a replacement
  justified solely by lower userspace overhead.

## Priority plan

| Priority | Work package | Exit criterion |
|---|---|---|
| P0 | Medium failure detection and fail-closed operation | a killed, hung, disconnected or restarted wmediumd cannot produce a valid-looking run through hwsim fallback |
| P0 | Overload classification and operating envelopes | infrastructure loss is measured and cannot be presented as modeled RF loss |
| P0 | Fixed-roster lifecycle reliability | any provisioned node can restart without medium replacement, identity drift or manual repair of unrelated nodes |
| P1 | Standalone medium conformance suite | scanning, channel, ACK, hidden-SSID, loss and lifecycle semantics pass independently of RDK |
| P1 | Reception-backed candidate measurement | fresh candidate quality requires qualifying receive evidence and reports unknown otherwise |
| P1 | Rate/airtime separation and capability gates | unsupported encodings cannot silently generate performance conclusions |
| P2 | Complete RF graph and qualified contention profiles | all relevant directed communication and carrier-sense relationships have explicit tested semantics |
| P2 | Physical reference and calibration | selected virtual conclusions have independently measured physical comparisons and bounded timing ranges |

## P0: fail-closed external medium

### Problem

When userspace wmediumd stops, hwsim can return to its built-in delivery path.
Continued connectivity can therefore conceal loss of the configured experiment:

```text
configured attenuation
        |
        v
wmediumd exits or loses registration
        |
        v
hwsim resumes built-in delivery
        |
        v
apparent client recovery under an unrecorded medium
```

A responsive PID or control socket is insufficient evidence that the expected
medium is still registered and processing frames.

### Future implementation

Add a lab-specific, kernel-enforced **external medium required** mode. Once an
experiment arms it, loss of the expected registration must block unintended
fallback delivery and invalidate the run. Track:

- expected medium instance and registration generation;
- registration/liveness at the hwsim boundary;
- actual frame-processing progress;
- last TX-status progress and outstanding cookies; and
- control-plane health separately from data-plane progress.

A userspace watchdog should report and coordinate recovery, but the fail-closed
property belongs at the kernel boundary so no fallback frames cross during a
detection race.

### Acceptance

Exercise clean exit, SIGTERM, SIGKILL, hang, control-socket failure,
registration loss and daemon restart. Each case must:

- produce an explicit infrastructure failure event;
- prevent a normal performance/optimizer conclusion;
- prove whether any frame crossed through fallback;
- retain evidence; and
- distinguish recovery of the room writer from recovery of wmediumd itself.

An in-daemon RF lease can recover from a room-controller crash. It cannot
restore state after the daemon containing that state disappears; those are
separate requirements.

## P0: overload classification and operating envelopes

### Existing evidence

The measured 20-client RDK VM workload showed a sharp overload transition even
though wmediumd CPU did not approach one full logical CPU:

| Offered ICMP rate per client | wmediumd CPU | Packet loss | Queue at end | Netlink errors/s |
|---:|---:|---:|---:|---:|
| 50 packets/s | 26.86% | 0.12% | 19 | 0 |
| 56 packets/s | 27.64% | 0.36% | 77 | 0 |
| 67 packets/s | 30.13% | 19.75% | 714 | 1,108 |
| 100 packets/s | 32.49% | 66.88% | 1,876 | 1,927 |

These are workload-, topology-, VM- and host-specific results, not universal
capacity numbers. They demonstrate that low apparent CPU utilization cannot be
used as the medium health gate. Earlier output-threading experiments also show
that naive netlink parallelism can damage correctness or throughput.

### Future implementation

Every experimental run should collect:

- input and output queue depth and oldest-item age;
- scheduler deadline lateness and distribution;
- outstanding TX-status cookies and their age;
- netlink send/receive errors by class;
- socket receive-buffer drops;
- accepted, completed and discarded frame rates;
- modeled loss separately from delivery/infrastructure loss; and
- medium instance, configuration and workload profile.

The evidence and UI must distinguish:

```text
modeled radio loss       configured channel/PER decision
infrastructure loss      platform failed to process/deliver correctly
```

Crossing a qualified infrastructure limit invalidates performance conclusions.
The system must not silently reduce traffic, change the backend, or continue
with a normal result.

Define conservative named envelopes:

- **presentation**: predictable visual/protocol demonstrations;
- **protocol stress**: management and lifecycle robustness; and
- **throughput characterization**: explicitly bounded data-plane measurement.

Each profile gets independent host/configuration acceptance. Faster CPU or
more RAM is not assumed to remove a single endpoint, scheduler or netlink
bottleneck.

## P0: fixed-roster lifecycle reliability

Arbitrary hot-add/hot-remove is not the first goal. First qualify the complete
provisioned 20-client roster while individual nodes are temporarily inactive.

The intended inventory must retain stopped radios. Restarting one client must
preserve:

- medium instance and inventory generation;
- permanent radio identity and ownership;
- unrelated node runtime and RF state;
- controller identity records; and
- an explicit reconciliation of runtime interface/channel state.

Acceptance sequence:

1. Run a room scenario.
2. Restart one non-hero client.
3. Verify the other 19 clients are unaffected.
4. Verify the restarted client recovers normally.
5. Continue without regenerating wmediumd or editing controller state.
6. Repeat for each client class.
7. Repeat for an extender, allowing only the genuine downstream consequences.

This becomes a release gate for the fixed roster before dynamic topology work.

## P1: explicit receive eligibility

The reviewed wmediumd patch prevents delivery until a radio's receive
frequency has been learned from a prior transmission. That assumption is not a
general receive model: passive scanning legitimately receives without first
transmitting a Probe Request, and last-transmitted frequency does not always
equal current receive eligibility after scanning or a channel-context change.

Future work should obtain receive eligibility from explicit, event-driven
hwsim channel context:

```text
permanent radio identity
active receive channel contexts
scan dwell / remain-on-channel state
interface lifecycle generation
```

Transmit learning remains useful for VIF ownership and diagnostics, but not as
the sole receive authority. Do not poll `iw` or sysfs per frame; reconcile at
lifecycle boundaries and consume state-change events.

The first regression starts with an empty learned-transmit map and performs a
passive scan. Eligible beacons must be discovered without prior client TX.

## P1: reception-backed candidate measurements

### Current fidelity boundary

The reviewed hwsim HAL provider obtains configured frequency-qualified SNR
from the wmediumd read-only socket and converts it using a fixed-noise-floor
formula:

```text
RCPI = 2 * (SNR dB + 19)
```

This is acceptable as an explicitly model-backed value for deterministic
protocol and policy plumbing. Passing through a real EasyMesh request/response
does not make its source an independent reception measurement.

### Preserve two modes

| Mode | Source | Appropriate use |
|---|---|---|
| Model-backed | configured/effective link SNR | deterministic protocol plumbing and optimizer unit/integration tests |
| Reception-backed | qualifying frames actually observed at an eligible receiver | availability, freshness, silent-client, mobility and loss experiments |

Reception-backed evidence records:

- receiving radio and transmitting endpoint;
- frequency/channel context;
- observation window and timestamp;
- sample count and signal statistic;
- relevant medium instance/generation; and
- receiver acceptance stage, when observable.

No qualifying reception in the window returns **unknown**, not a fresh strong
candidate inferred from the matrix. A successful userspace send of an RX clone
is not alone proof that the receiver accepted it.

This enables credible tests for silent clients, missed windows, off-channel
receivers, burst loss, stale samples and asymmetric links while keeping the
optimizer boundary unchanged: policy still consumes controller-reported facts.

## P1: ACK, delivery and association evidence

wmediumd can make a modeled success decision and synthesize ACK information in
captures. Simulator-generated ACK evidence is therefore not automatically an
independent receiver-side observation.

Record these stages separately:

```text
TX submitted
model delivery decision
RX injection attempted
receiver acceptance observed
TX status returned
protocol response observed
```

Unavailable stages remain unavailable. Do not collapse them into “delivered.”

Required tests include:

- strong forward link with weak reverse link;
- receiver channel change between enqueue and delivery;
- stopped receiver;
- stale VIF ownership;
- overloaded TX-status path; and
- broadcast/multicast delivery.

Document any ACK/reverse-link simplification explicitly. Association
verification must compare medium ownership, client actual BSSID and AP
authorization state; two consumers of the same simulated ownership map are not
independent confirmation.

## P1: rate, packet-error and airtime separation

The current HT/VHT compatibility path maps a 20 MHz long-GI rate to a nearby
legacy OFDM curve. If the mapped legacy rate also drives packet duration, one
approximation affects both success probability and channel occupancy.

Future rate descriptions should retain, when available:

- encoding;
- MCS;
- spatial streams;
- bandwidth;
- guard interval; and
- aggregation-relevant information.

Then separate:

```text
airtime(frame length, rate description)
packet error probability(signal conditions, rate description, frame length)
```

Legacy PER mapping may remain a declared compatibility fallback, but it must
not silently define airtime. Unsupported HE/EHT or wide-channel requirements
are counted and fail scenario capability validation when the experiment
depends on them. A complete Wi-Fi 7 PHY model is not the initial goal; the
used subset must be correct and characterized.

## P2: complete RF graph and contention semantics

Attenuation is not automatically interference. The current baseline disables
some same-frequency interference behavior and uses exact center-frequency
separation, without qualified partial-overlap or adjacent-channel effects.
An “interference region” that only subtracts SNR must be labelled attenuation
or noise abstraction, not a validated competing WLAN.

Before making contention- or load-sensitive optimizer claims, determine
whether other transmitters produce the intended occupancy, deferral,
collisions, retries and measurement changes.

The current Golden World graph covers station-to-AP, AP-to-station and AP-to-AP
links, but not station-to-station relationships. A full contention graph must
define every relevant directed radio pair and distinguish:

- intended communication paths;
- receive eligibility;
- carrier sense;
- interference/collision relationships; and
- measurement relationships.

The 30-key movement bound is valid for five APs, three bands and two fronthaul
directions. It is not the bound for an all-peer physical model. Private and IoT
SSIDs remain separate WLAN populations, but share physical airtime whenever
their radios occupy the same modeled channel.

## Explicit RF absence

`-20 dB` alone should not define disappearance. Its outcome can vary by loss
model, frame type and delivery path.

Add an explicit bidirectional radio/link availability primitive. The tested
contract for an absent role is:

- no relevant management, data or control delivery to or from it;
- no unintended ACK success;
- container and permanent identity remain intact; and
- reappearance restores the prior availability state before normal Wi-Fi
  discovery and recovery.

Ordinary weak-signal cases must retain legitimate low-rate discovery and
reception; **absent** is a separate deliberate state.

## Standalone medium conformance suite

Build an isolated hostapd/wpa_supplicant suite below OneWifi, EasyMesh,
MariaDB, the optimizer and the viewer. This provides the attribution boundary:

```text
medium defect | RDK HAL integration defect | EasyMesh implementation defect
```

| Test family | Required evidence |
|---|---|
| Active and passive scanning | discovery works without prior transmit-learning shortcuts |
| Hidden SSID | exact directed probe, populated ESS identity and real BTM accept/reject |
| Channel isolation | no unintended RX or ACK across incompatible contexts |
| Directed links and ACK | declared forward/reverse asymmetry behavior |
| Lifecycle | AP/client restart, VIF recreation and scan/channel changes |
| Loss and retries | modeled loss is distinguishable from infrastructure failure |
| Power save and idle clients | quiet traffic does not imply disappearance |
| Overload | bounded failure, classified errors and recoverable queues |
| Medium death | no silent fallback to another delivery path |

Run applicable tests against stock hwsim, patched hwsim/wmediumd and the
experimental kernel backend. Compare only shared capabilities.

Include negative controls that break an allowed virtual RF link and prove
traffic fails through the intended Wi-Fi path. This protects against host-local
or management-network shortcuts. Both private and hidden IoT cohorts remain in
complete-lab tests; hidden IoT discovery is a named conformance test, not a
demonstration workaround.

## Physical reference cell

Create a small reference cell rather than a second 25-radio lab:

- two available physical AP/agent devices; and
- one Linux WLAN client.

Compare association, hidden-SSID discovery, BTM accept/reject, source-AP
cleanup, measurement freshness, weak-link recovery and traffic interruption.
Compare behavior ordering and timing distributions, not identical packet
timestamps.

A useful bounded conclusion would be:

> Repeated virtual and physical crossovers exhibit the same ordering of
> candidate discovery, BTM response, reassociation and controller convergence,
> with separately reported timing ranges.

Controlled attenuation can follow later. Cross-stack RDK/prplMesh comparisons
are valuable but share medium blind spots and do not replace physical evidence.

## Scenario classes and repeatability

Define three RF profile classes:

- **Deterministic functional**: fixed propagation, no random fading and
  controlled traffic for debugging and regression.
- **Robustness**: bounded, spatially/temporally correlated signal variation,
  measurement delay, burst loss and diverse client responses.
- **Calibrated**: parameters and uncertainty derived from physical reference
  measurements.

Keep geometry variation separate from packet-loss randomness and record both.
A deterministic Golden World reproduces intended stimulus; it does not promise
identical scheduler timing, scan-cache history, packet order or client choice.
Report repeated-run variability.

An unchanged global medium generation is a useful stationary-test gate, but it
must not become the only valid model for continuous mobility. Mature mobile
measurement validity should use relevant-link history, bounded environmental
change, sample windows and age so unrelated room activity does not invalidate
the hero client's entire observation.

## Kernel medium role

Keep the experimental kernel medium as an alternative implementation of a
declared common capability subset. Use it to ask:

> Does the behavior persist without userspace transport and scheduling?

Do not claim equivalence where the kernel backend lacks complete
contention/collision behavior, exact frequency-qualified state or delayed
receive/ACK timing. Do not run multiple stock wmediumd processes against one
radio pool as a CPU-scaling shortcut; channel sharding requires kernel
interface and ownership architecture.

## Source, image and capability provenance

Generate a runtime manifest tying together:

- repository revision and patch-series digest;
- kernel build and hwsim module identity/options;
- wmediumd upstream base, binary hash and enabled patches;
- RDK/prplMesh image hashes;
- hostapd/wpa_supplicant versions and relevant patches;
- permanent radio inventory and medium instance;
- enabled model features and declared approximations; and
- conformance and acceptance suites completed by this exact combination.

Documentation must distinguish:

```text
implemented in source
installed in this image/runtime
qualified by named acceptance evidence
```

Newer hidden-SSID WNM lookup and BTM reliability fixes must be evaluated from
the actual installed image before carrying forward an older “unresolved”
statement. Current-state and release documents should be generated or checked
against the runtime manifest to prevent branch/image drift.

## Overall completion gate

The virtual medium is qualified for a stated workload only when the evidence
can independently answer:

1. Which RF condition was modeled?
2. Which radio was eligible to receive on which channel?
3. Which frame stages actually occurred?
4. Was loss modeled or caused by infrastructure overload/failure?
5. What did the controller report, with what provenance and freshness?
6. Was the medium instance continuously present and fail-closed?
7. Did node lifecycle preserve unrelated state?
8. Which behavior has a physical reference comparison?

The desired final claim is deliberately bounded:

> Real Wi-Fi and EasyMesh software operates over a controlled, characterized
> virtual medium. The lab records what the medium modeled, what an eligible
> receiver observed, what the controller reported, what the optimizer decided,
> and where physical validation supports the result.
