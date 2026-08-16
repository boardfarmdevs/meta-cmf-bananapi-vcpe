# wmediumd configurator

## Purpose

`wmdcfg` creates repeatable RF conditions for EasyMesh steering experiments in
the LXD/hwsim lab. It controls only the simulated medium. It does not select an
AP, change an EasyMesh policy, or send a steering request.

```text
scenario.wmd             EasyMesh measurements         policy/engine
     |                              |                        |
     v                              v                        v
  wmdcfg ---------------------> OneWifi/agent ----------> steer request
     |                                                       |
     v                                                       v
 wmediumd <--- hwsim frames ---> AP/controller/client <--- reassociation
```

This boundary is essential. The same RF scenario can be replayed against a dry
run policy, the WebUI policy, `em_cli`, or an explicit `steer.sh` command without
changing the stimulus.

## Current implementation

Version 0.1 is under `gen/wmediumd/configurator/`. It provides:

- a dependency-free Python parser for the `.wmd` language;
- semantic validation with strict time/SNR units and safe bounds;
- live LXD, hwsim, VIF, frequency, BSSID, and association inventory;
- role binding frozen to the hwsim transmitter MAC (`perm_addr | 0x40`);
- deterministic compilation to a fully resolved JSON event plan;
- a monotonic runner with preflight/postflight mesh health gates;
- atomic live SNR generations, per-link readback, and captured restoration;
- JSON/JSONL run artifacts; and
- a dedicated binary control socket in patched wmediumd.

The current source tree is deliberately small:

```text
gen/wmediumd/configurator/
|-- pyproject.toml
|-- wmdcfg/
|   |-- model.py       source model and errors
|   |-- parser.py      .wmd tokenizer/parser
|   |-- inventory.py   live LXD/hwsim discovery
|   |-- compiler.py    validation, binding, event-plan expansion
|   |-- actuator.py    wmediumd protocol client
|   |-- observers.py   association and EasyMesh health reads
|   |-- runner.py      timing, apply/readback, health, restore
|   `-- cli.py
|-- scenarios/
|   |-- all-strong.wmd
|   `-- two-ap-crossover.wmd
`-- tests/
```

The first version uses a hand-written parser rather than a parser framework.
That keeps the grammar and failure behavior visible while the language is
small. A parser generator is an implementation option if the grammar grows.

## Why association does not drive RF

A movement scenario defines a link function for every relevant physical AP:

```text
time               0 s             25 s             40 s
client <-> AP-A     42 dB ----------26 dB------------10 dB
client <-> AP-B     10 dB ----------26 dB------------42 dB
association         AP-A ----------- ? ---------------AP-B
```

`AP-A` and `AP-B` remain the same radios for the complete run. When the client
roams, hwsim continues to use the same client radio identity and wmediumd uses
the already-defined link to the new AP. No feedback loop needs to flip the
matrix after the roam.

An association-relative rule such as “current AP strong, all others weak” is
not a movement model. It becomes stale after a roam and makes the RF stimulus
depend on the policy being tested. `gen-config.sh` may use current association
to create a safe startup baseline, but a scenario must define all candidate-AP
links in its first phase.

Phases make the timing explicit:

1. `baseline` establishes every candidate link.
2. `crossover` changes physical links over monotonic time.
3. `destination_hold` keeps the final RF state long enough for a policy,
   reassociation, and controller convergence.
4. The runner restores the exact state captured before execution.

Feedback is read-only in v0.1. It records association and gates lab health; it
does not choose SNR values or steer.

## Implemented language subset

```text
scenario two_ap_crossover {
    language 1
    tick 1s
    require radio_pair_snr
    require atomic_generations
    require readback
    protect backhaul
    restore captured

    role client : station
    role ap_a : fronthaul_ap
    role ap_b : fronthaul_ap

    phase baseline for 10s {
        parallel {
            link client <-> ap_a snr = 42dB
            link client <-> ap_b snr = 10dB
        }
        mark "baseline established"
    }

    phase crossover for 30s {
        parallel {
            link client <-> ap_a snr 42dB -> 10dB linear
            link client <-> ap_b snr 10dB -> 42dB linear
        }
    }

    phase destination_hold for 20s {
        hold
    }
}
```

The implemented constructs are:

| Construct | Current behavior |
| --- | --- |
| `scenario`, `language 1` | Named v1 source |
| `tick` | Ramp sampling from 100 ms to 60 s |
| `require` | `radio_pair_snr`, `atomic_generations`, `readback` |
| `protect backhaul` | Required; v0.1 only permits station/AP links |
| `restore captured` | Required |
| `role` | `station` or `fronthaul_ap` |
| `phase ... for` | Fixed duration in `ms` or `s` |
| `parallel` | Same-timestamp updates compile into one generation |
| `link` | Directed `->`, reverse `<-`, or symmetric `<->` |
| `snr =` | Constant integer dB value |
| `snr A -> B linear` | Inclusive linear ramp sampled at `tick` |
| `hold` | Preserve the previous RF state |
| `mark` | Timestamped annotation with no RF mutation |

SNR must be an integer in `[-20dB, 60dB]`. Unknown syntax, units, roles,
requirements, conflicts, unsafe link types, missing bindings, or an incomplete
first phase are errors. Compilation never changes the live medium.

Not yet implemented: parameters, repeat, traces, conditional waits, geometry,
frequency-qualified SNR, random models, or traffic actions. These remain
roadmap features rather than accepted syntax.

## Compile and run workflow

Run the tool inside the VM containing the nested LXD lab:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe

PYTHONPATH=gen/wmediumd/configurator python3 -m wmdcfg.cli inventory \
    --output /tmp/inventory.json

PYTHONPATH=gen/wmediumd/configurator python3 -m wmdcfg.cli validate \
    gen/wmediumd/configurator/scenarios/two-ap-crossover.wmd

PYTHONPATH=gen/wmediumd/configurator python3 -m wmdcfg.cli compile \
    gen/wmediumd/configurator/scenarios/two-ap-crossover.wmd \
    --inventory /tmp/inventory.json \
    --bind client=wlan-client \
    --bind ap_a=bpibroadband \
    --bind ap_b=bpiap \
    --output /tmp/crossover.plan.json

PYTHONPATH=gen/wmediumd/configurator python3 -m wmdcfg.cli status

PYTHONPATH=gen/wmediumd/configurator python3 -m wmdcfg.cli run \
    /tmp/crossover.plan.json --output-root /tmp/wmdcfg-runs
```

The plan records source and inventory hashes, frozen bindings, phases, total
duration, required capabilities, protected resources, and every timed atomic
generation. Operators can inspect it before running.

## Live wmediumd interface

`wmediumd-up.sh` starts the patched daemon with two distinct inputs:

```text
/tmp/wmediumd.cfg --------> startup radio list and baseline
                                  |
                                  v
                          wmediumd in-memory SNR
                                  ^
                                  |
/run/wmediumd-control.sock <------+ live atomic generations
```

Editing `/tmp/wmediumd.cfg` does not alter a running daemon. Ramps therefore use
the control socket and never restart wmediumd.

The v1 interface is a local Unix `SOCK_SEQPACKET` protocol with network byte
order, fixed-width records, a 64 KiB frame cap, and these operations:

| Operation | Purpose |
| --- | --- |
| `HELLO` | Version, capability set, instance ID, limits, station count |
| `STATUS` | Current daemon generation and identity |
| `APPLY` | Validate then atomically apply one exact next generation |
| `GET_LINK` | Read one directed radio-pair SNR |
| `DUMP_LINKS` | Read the complete directed matrix |

The daemon accepts only one control writer. It rejects wrong protocol versions,
lengths, generations, radio identities, values, and oversized updates before
mutating the matrix. Each daemon start creates a new random 128-bit instance ID
and resets generation to zero.

The socket is group-owned by `lxd` and mode `0660`. It is a machine interface,
not a UI API. A future WebUI must call a Python service that applies the same
validation and safety rules.

Patch 0009 also makes `model.default_snr` effective. Previously the generator
emitted this field but unspecified links silently used wmediumd's compiled
30 dB constant. The daemon now validates and applies the configured default;
explicit links still override it.

## Runner safety and artifacts

Before starting its monotonic timeline, the runner:

- acquires the single writer connection;
- verifies daemon capabilities;
- dumps the full matrix and captures every touched directed link;
- verifies all compiled identities still exist; and
- requires all API clients active and all topology nodes complete.

For each generation it applies all updates atomically, reads every link back,
records deadline lateness, and observes the current client BSSID. At the end or
after a handled `SIGINT`/`SIGTERM`, it applies the captured values as one final
generation and verifies every restored link. Postflight repeats the mesh health
gate.

Each run currently contains:

```text
event-plan.json        exact frozen plan
medium-events.jsonl    applied generations, timing, observations, restore
health-events.jsonl    preflight and postflight mesh state
summary.json           outcome, elapsed time, error, restoration result
```

## Current boundary and next increments

Version 0.1 is suitable for controlled radio-pair steering experiments, with
these explicit limits:

- SNR is keyed by source/destination radio, not frequency. Same-node 5/6 GHz
  band steering needs a frequency-keyed actuator extension.
- `SIGKILL`, host loss, or runner process loss cannot execute Python cleanup.
  A daemon-side lease/watchdog is required before unattended experiments.
- Health is gated before and after a run; continuous health sampling and
  conditional phase waits are not implemented.
- Artifacts still need source, full start/end inventories, component versions,
  and a human-readable summary for complete exportability.
- There is no long-running service, WebUI integration, run queue, `abort`, or
  authenticated multi-user control yet.

The next useful work is: add runner failure-path tests and a daemon lease;
complete the artifact manifest; add calibration/static/step/reverse scenarios;
then expose the proven application layer through a small API. Frequency-keyed
SNR and geometry should follow only after radio-pair scenarios are repeatable.
