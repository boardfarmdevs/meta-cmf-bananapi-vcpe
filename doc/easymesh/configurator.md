# wmediumd configurator

## Purpose and boundary

`wmdcfg` creates deterministic RF conditions for steering experiments. It does
not select an AP, deploy an EasyMesh policy or issue a steering request.

```text
scenario source -> compiler -> frozen event plan -> runner
                                                    |
                                                    v
                                             wmediumd SNR matrix
                                                    |
                                                    v
                                         hwsim frames/measurements
                                                    |
                           policy or explicit command decides whether to steer
```

Keeping stimulus and decision independent lets the same RF scenario test a
passive control, commanded steering, a controller optimizer or future
agent-initiated steering.

Implementation: `gen/wmediumd/configurator/`, Python 3.8+, no external parser
dependency.

## Scenario model

The first language version describes named roles and time phases. A two-AP
crossover is:

```text
time                 0 s          10 s          40 s          60 s
client <-> AP-A      42 dB --------+ 42 -> 10 ---- 10 dB -------+
client <-> AP-B      10 dB --------+ 10 -> 42 ---- 42 dB -------+
phase                baseline        crossover      hold
```

Source:

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
    }
    phase crossover for 30s {
        parallel {
            link client <-> ap_a snr 42dB -> 10dB linear
            link client <-> ap_b snr 10dB -> 42dB linear
        }
    }
    phase destination_hold for 20s { hold }
}
```

Supported constructs:

| Construct | Meaning |
| --- | --- |
| `tick` | ramp sample interval, 100 ms to 60 s |
| `role` | station or fronthaul AP binding |
| `phase ... for` | fixed monotonic duration |
| `parallel` | one atomic generation at a timestamp |
| `link ->`, `<-`, `<->` | directed or symmetric radio-pair SNR |
| `snr =` | constant integer dB value |
| `snr A -> B linear` | inclusive sampled ramp |
| `hold` | retain the previous matrix |
| `protect backhaul` | reject unsafe backhaul mutations |
| `restore captured` | capture, restore and verify touched links |

SNR is restricted to `[-20, 60]` dB. Unknown units, incomplete initial link
coverage, conflicting same-generation updates, unsafe role pairs or missing
bindings fail compilation.

## Why roles do not follow association

AP-A and AP-B are physical radio identities for the entire run. A roam changes
which AP receives client traffic; it does not change either link function.

An association-relative rule such as “current AP strong” becomes wrong after a
roam and couples RF input to the decision under test. Association is therefore
observed and recorded but does not rewrite the matrix.

## Workflow

Run inside the runtime that owns LXD/hwsim:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe-0815-codex/gen/wmediumd/configurator

python3 -m unittest discover -s tests -v
python3 -m wmdcfg.cli inventory -o /tmp/inventory.json
python3 -m wmdcfg.cli validate scenarios/two-ap-crossover.wmd
python3 -m wmdcfg.cli compile scenarios/two-ap-crossover.wmd \
  --inventory /tmp/inventory.json \
  --bind client=wlan-client \
  --bind ap_a=bpibroadband \
  --bind ap_b=bpiap \
  -o /tmp/crossover.plan.json
python3 -m wmdcfg.cli status
python3 -m wmdcfg.cli run /tmp/crossover.plan.json \
  --output-root /tmp/wmdcfg-runs
```

Inventory resolves container, wiphy, permanent MAC, hwsim transmitter MAC,
interfaces, frequencies, SSIDs, BSSIDs and current association. Compilation
freezes those bindings; it never changes the medium.

Inspect the generated plan before execution. Recompile after a clean deploy
because `-F` changes identities and BSSIDs.

## Live actuator

```text
/run/meta-cmf-wmediumd/wmediumd.cfg -> startup radio list/default SNR

/run/wmediumd-control.sock --------> live in-memory generations
                                      HELLO / STATUS
                                      APPLY
                                      GET_LINK / DUMP_LINKS
```

The Unix socket uses `SOCK_SEQPACKET`, fixed-width network-byte-order records
and a generation counter. One writer owns the connection. wmediumd validates
protocol version, daemon instance, generation, radio identity and SNR bounds
before applying a complete generation atomically.

Editing the startup configuration does not change a running daemon. Scenario
ramps use the control socket and leave the PID unchanged.

## Runner safety and artifacts

Preflight requires a complete topology and all expected clients active. The
runner then:

1. acquires the single writer;
2. verifies daemon identity/capabilities;
3. captures every touched directed link;
4. verifies frozen identities still exist;
5. applies and reads back each generation;
6. records deadline lateness and association observations; and
7. restores all captured values as one verified final generation.

Each run directory contains:

```text
event-plan.json        frozen inputs and timed generations
medium-events.jsonl    apply/readback/association/restore events
health-events.jsonl    preflight and postflight topology/API state
summary.json           outcome, timing, error and restoration result
```

An experiment is not complete unless `summary.json` reports `passed` and
`restored: true`.

## Validated behavior

- 9/9 Python/compiler/runner/real-daemon tests passed.
- The internal wmediumd multichannel/Linux-7 suite passed 9/9.
- A passive two-AP crossover applied 32 generations in 60 seconds, kept the
  same daemon PID, delivered 1,400/1,400 probes and restored every link.
- The passive client did not roam, proving RF alone is not an autonomous
  policy.
- Replaying the gradient with an explicit `steer.sh` action moved the client
  and converged the controller model while the medium still restored cleanly.

## Limits

- SNR is keyed by radio pair, not frequency; same-wiphy band steering needs a
  frequency-qualified actuator.
- `SIGKILL` or host loss cannot execute Python restoration; unattended use
  needs a daemon-side lease/watchdog.
- Health is gated before/after, not continuously used to advance phases.
- Parameters, loops, trace import, geometry, random models and conditional waits
  are not language features yet.
- The configurator is a CLI/library, not a long-running authenticated service.

