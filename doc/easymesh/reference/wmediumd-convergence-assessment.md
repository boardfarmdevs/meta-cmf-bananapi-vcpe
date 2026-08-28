# wmediumd convergence assessment

## Scope

This assessment answers one question: whether the current multichannel
wmediumd implementation is sufficiently converged for the EasyMesh steering
and optimizer research lab.

It evaluates the current fixed-roster lab at source revision
`c461c591afe8afef47d1b215fbcfbb09eb5abcb3`. It does not claim calibrated
physical-radio fidelity or appliance-quality dynamic inventory management.

## Conclusion

The medium implementation is **converged for fixed-roster, comparative
multichannel steering experiments**.

It is **not yet converged for arbitrary node lifecycle or topology mutation**.
The current launcher still derives its startup roster from active containers,
and adding or removing a provisioned radio requires a generated configuration
and daemon restart. That is the principal remaining medium-management
fragility.

The supported research claim is therefore:

> The lab can apply repeatable, directed, frequency-aware SNR conditions to a
> fixed provisioned set of hwsim radios while real Linux Wi-Fi and EasyMesh
> processes react to the resulting frame delivery, loss, retries, signal, and
> channel isolation.

The unsupported claim is:

> wmediumd automatically tracks any container or hwsim radio that appears,
> disappears, stops, or restarts.

## Evidence baseline

| Evidence | Current result |
| --- | --- |
| Kernel | Linux 7.0.0-28 with multichannel hwsim registration patch |
| Mesh radios | Five one-wiphy tri-band BPI nodes |
| WLAN clients | Twenty: ten private and ten IoT |
| Configured wmediumd identities | 25 |
| Directed base pairs | 600 |
| Active bands | 2.4, 5, and 6 GHz |
| Controller model | 5 devices / 15 radios / 50 BSSs / 24 associated STAs |
| Client signal | 20/20 nonzero RCPI in accepted rev120 reconstruction |
| Backhaul signal | 4/4 fresh in accepted rev120 reconstruction |
| Console | 25/25 identities, packet telemetry enabled, read-only controls |
| Steering | Focused round-trip steer passed before packaging |
| Long-duration 12-hour churn | Not yet claimed |
| 50/100-client runtime | Not yet claimed |

The accepted implementation consists of the ordered patch series
`gen/wmediumd/patches/0001` through `0014`, the generated launcher,
configurator, observer service, and focused repository tests. Runtime
acceptance is recorded in `current-state.md`.

No new live experiment was run for this assessment; it relies on the accepted
runtime evidence and current source contracts.

## Requirement assessment

| Requirement | State | Evidence and boundary |
| --- | --- | --- |
| Register one wmediumd against multichannel Linux 7 hwsim | Converged | Kernel registration support and the accepted 25-radio runtime |
| Prevent cross-channel unicast delivery and ACKs | Converged | Exact-frequency delivery eligibility and per-frequency scheduling patches |
| Prevent multicast fan-out to off-channel radios | Converged | Frequency-filtered multicast patch and current runtime traffic |
| Schedule independent frequency contexts | Converged | Queue tails and interference buckets are frequency-qualified |
| Resolve dynamic BSSID/VAP ownership | Converged for active radios | Transmit-learned VIF-to-base-radio ownership |
| Handle Linux 7 rate flags | Converged within documented model limits | HT/VHT mapping patch; no native HE/EHT PER model |
| Honor configured default SNR | Converged | Startup parser/default patch and generated baseline |
| Apply live directed SNR changes atomically | Converged | Versioned `-C` socket, generation checks, readback, and restore |
| Apply frequency-qualified SNR changes | Converged | Sparse per-frequency override table with exact restoration |
| Supply read-only candidate-link metrics | Converged | Multi-client `-R` endpoint used by the HAL |
| Supply bounded live observability | Converged for Phase 1/2 | Host-only `-O` telemetry and Go Console |
| Preserve behavior when observer is slow or absent | Converged by design/tests | Fixed counters, bounded rings/pages, no payload copying |
| Start from a complete provisioned roster while nodes are stopped | Not converged | Generator currently discovers active containers |
| Restart one provisioned node without restarting wmediumd | Not converged | Fixed startup roster remains restart-bound |
| Add/remove/reassign radios atomically | Not implemented | Control socket mutates link values, not inventory |
| Model adjacent-channel overlap and spectral masks | Not implemented | Exact center-frequency equality only |
| Native HE/EHT/MLO/channel-width radio fidelity | Not implemented | Legacy PER abstraction |
| Calibrated home propagation | Not claimed | Scenarios are repeatable research stimuli, not site calibration |
| Accepted long-duration and 50/100-client scale | Incomplete | Current accepted profile is 25 radios |

## What is scientifically usable now

The current medium is suitable for:

- deterministic crossover and threshold-hover scenarios;
- asymmetric directed links;
- band-specific SNR overrides;
- slow/fast mobility sequences generated by the configurator;
- disappear/reappear and extender RF-isolation scenarios;
- flash-crowd activation of preprovisioned clients;
- comparison of steering policies under identical golden stimuli;
- candidate-link RCPI experiments;
- frame, retry, delivery/drop, queue, VIF, and provenance observation; and
- correlation of medium stimulus with EasyMesh topology and client ownership.

The experiment must retain the startup inventory hash, scenario artifact,
wmediumd instance/generation, image hashes, controller observations, and
traffic result. A successful control-socket acknowledgement alone is not an
experiment pass.

## Important model boundaries

- wmediumd acts on hwsim radio pairs. EasyMesh roles, SSIDs, BSS ownership,
  steering policy, and topology aging are outside the daemon.
- A base SNR cell applies to the radio pair. Exact-frequency overrides can
  refine individual active channels.
- Reported signal derives from the configured/effective SNR and the model noise
  floor; it is not calibrated hardware RSSI.
- Different center frequencies are isolated. Partial overlap and
  adjacent-channel interference are not modeled.
- The rate/PER model is adequate for controlled comparative loss but is not a
  native Wi-Fi 6/7 PHY simulator.
- Stopping wmediumd returns hwsim to its built-in medium. Continued connectivity
  is therefore not proof that the configured experiment remains active.
- RF isolation does not delete a controller topology object. EasyMesh
  liveness/aging must be evaluated separately.

## Remaining convergence work

### P0: fixed intended inventory

Make the declarative provisioned roster authoritative. Include stopped nodes as
configured/dormant stations, resolve every radio by permanent identity, and
reject partial or ambiguous inventory.

Acceptance:

- the same normalized manifest always produces the same inventory hash;
- wmediumd starts with the complete roster while containers are stopped; and
- starting a provisioned container immediately resumes frames without daemon
  replacement.

### P1: restart-safe lifecycle

Move start/stop/restart behind `easymesh-labctl`. A routine node lifecycle
operation must preserve the inventory generation, wmediumd instance, PHY,
MACs, NVRAM, and unrelated traffic.

Acceptance:

```text
wmediumd restart count                  unchanged
unaffected container restart counts    unchanged
inventory generation/hash              unchanged
node permanent identity                 unchanged
manual recovery commands               zero
```

### P2: actual topology mutation

After fixed-roster restart behavior is accepted, add typed atomic station
add/update/disable/remove operations or a bounded atomic daemon replacement.
Link/scenario updates remain a separate transaction class.

Acceptance:

- add and remove one client and one extender without a partial pair matrix;
- reject stale generations; and
- retain the prior working medium after a failed mutation.

### P3: qualification

Complete the defined long-duration churn and medium/large scale campaigns.
Record CPU, PSS/RSS, frame/drop counters, queue health, netlink errors, VIF
count, controller ownership, and traffic.

## Decision

Do not replace the current medium or delay optimizer development while P0-P3
are completed. Use the accepted fixed-roster profile for optimizer research,
describe its model boundaries precisely, and prioritize inventory/lifecycle
work as an appliance improvement.
Do not broaden the scientific claim beyond comparative controlled experiments
until the scale, soak, and physical-model gaps have their own evidence.
