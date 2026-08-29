# Optional hwsim kernel medium

## Decision

Userspace wmediumd remains the lab default and reference RF implementation.
The kernel medium is an optional experimental data path for scale and
performance research. Installing the patched module does not enable it:
`kernel_medium=0` is the default, and a registered userspace wmediumd always
takes precedence even when `kernel_medium=1`.

The implementation extends mac80211_hwsim's existing same-channel in-kernel
frame-copy path. It does not introduce a second wireless driver or move the
configurator, optimizer, or Web interfaces into the kernel.

```text
default

  hwsim TX -> generic netlink -> userspace wmediumd -> cloned RX/TX status

optional, only when no userspace wmediumd is registered

  hwsim TX -> active kernel matrix -> cutoff/loss decision -> cloned RX/TX status
                       ^
                       |
              wmdcfg kernel adapter
              stages bank N, commits once
```

## Implemented phases

### Phase 0: controlled baseline

The evaluation uses the same Linux 7.0 module, two hwsim radios, channel,
namespace split, traffic generator, VM, and measurement code for every data
path. The accepted userspace wmediumd binary and normal netlink transport are
included as a configuration rather than compared with unrelated tooling.

### Phase 1: opt-in impaired kernel path

Patch `0003-mac80211_hwsim-optional-kernel-medium.patch` adds:

- `kernel_medium`, disabled by default;
- a configurable signal cutoff;
- deterministic global packet-loss percentage;
- receiver signal from the existing per-radio `rx_rssi` control;
- per-radio considered, delivered, and dropped counters.

The Linux 7.0 QEMU smoke test passed 20/20 packets at zero loss, dropped 10/10
at 100 percent loss, and passed 5/5 immediately after restoration.

### Phase 2: atomic link matrices

Patch `0004-mac80211_hwsim-kernel-medium-link-matrix.patch` adds two complete
matrix banks. An entry is directed and qualified by source radio, receiver
radio, and band. Each entry supplies signal dBm and deterministic loss percent.
The configurator fills the inactive bank, then one `kernel_medium_bank` write
switches the whole RF scene. The module increments
`kernel_medium_generation` once for that commit.

The matrix is addressed by permanent hwsim transmitter identities, such as
`42:00:00:00:01:00`; it does not depend on changing `phyN`, `virt-wlanN`, VAP,
or BSSID names. Capacity is currently 128 provisioned radios and the 2.4, 5,
and 6 GHz bands.

Each receiver has this experimental debugfs interface:

```text
/sys/kernel/debug/ieee80211/phyN/hwsim/kernel_medium_links
```

Read it to obtain receiver identity, active bank, defaults, staged entries, and
counters. Its write operations are:

```text
clear-bank BANK
set BANK SOURCE_MAC BAND SIGNAL_DBM LOSS_PERCENT
```

The `wmdcfg` adapter hides that ABI and preserves existing scenario units.
Scenario values are SNR dB; the adapter converts with an explicit default noise
floor of -91 dBm. Existing compiled plans can select the backend at execution:

```sh
cd gen/wmediumd/configurator

# Normal and still the default.
python3 -m wmdcfg.cli status
python3 -m wmdcfg.cli run /tmp/scenario.plan.json

# Optional kernel data path.
sudo python3 -m wmdcfg.cli status --backend kernel
sudo python3 -m wmdcfg.cli run /tmp/scenario.plan.json --backend kernel
```

`--noise-floor-dbm` changes the conversion when required. The adapter
serializes writers, checks module identity and generation, stages a complete
inactive bank, commits once, reads every update back, and restores the captured
baseline through the existing runner. Kernel control is deliberately root-only;
the userspace control socket retains its existing delegated group permissions.

## Build and selection

The build always applies the optional code, but ordinary behavior is unchanged:

```sh
gen/hwsim/build-hwsim.sh --6ghz --install
```

The normal lab loads the module without a kernel-medium option and starts
userspace wmediumd. An isolated kernel test can load it explicitly:

```sh
HWSIM_KERNEL_MEDIUM=1 \
HWSIM_KERNEL_MEDIUM_CUTOFF=-95 \
HWSIM_KERNEL_MEDIUM_LOSS_PCT=0 \
  gen/hwsim/build-hwsim.sh --6ghz --load
```

Do not reload hwsim beneath running BPI or WLAN-client containers. Select the
backend as part of an isolated cold start. If userspace wmediumd subsequently
registers, it owns frame delivery and the kernel counters stop.

## QEMU evaluation

The repeatable evaluator is:

```sh
sudo gen/hwsim/tests/evaluate-medium-backends.py \
  --duration 10 --rate 20M \
  --output /tmp/kernel-medium-eval-20m.json
```

It destructively owns its temporary two-radio pool and namespace, so it must
run only in an isolated VM with the lab stopped. It evaluates:

1. stock hwsim perfect medium;
2. default userspace wmediumd;
3. kernel medium with receiver defaults;
4. kernel medium with active per-band matrix entries;
5. kernel medium enabled while userspace wmediumd is registered.

Tests ran in `hwsim-kernel-dev-0829`, an LXD virtual machine backed by
QEMU/KVM, with Ubuntu 24.04, Linux `7.0.0-30-generic`, six vCPUs, two radios,
one 2.4 GHz IBSS, and 1200-byte UDP datagrams. CPU is aggregate guest CPU for
both iperf endpoints and the medium; equivalent-core percentage converts that
aggregate to one-core units. QEMU steal time is excluded and reported
separately.

### Sustained 20 Mbit/s

| Configuration | Received Mbit/s | Loss | Mean RTT ms | Jitter ms | Guest CPU, cores | wmediumd core CPU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stock built-in | 19.998 | 0% | 0.107 | 0.0347 | 1.025 | n/a |
| Userspace wmediumd | 19.998 | 0% | 0.824 | 0.2745 | 1.378 | 9.887% |
| Kernel default | 19.998 | 0% | 0.114 | 0.0050 | 1.022 | n/a |
| Kernel matrix | 19.998 | 0% | 0.111 | 0.0059 | 1.022 | n/a |
| Kernel enabled, userspace registered | 19.998 | 0% | 0.819 | 0.3235 | 1.387 | 9.188% |

At this load the kernel matrix overhead is below run-to-run resolution.
Userspace adds about 0.36 equivalent cores to the end-to-end workload and
raises mean RTT by roughly seven times.

### Requested 50 Mbit/s

| Configuration | Received Mbit/s | Request delivered | Loss reported | Mean RTT ms | Jitter ms | Guest CPU, cores | wmediumd core CPU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stock built-in | 49.994 | 100.0% | 0% | 0.114 | 0.0048 | 1.055 | n/a |
| Userspace wmediumd | 21.492 | 43.0% | 0% | 0.814 | 0.3920 | 0.220 | 11.942% |
| Kernel default | 49.995 | 100.0% | 0% | 0.097 | 0.0040 | 1.023 | n/a |
| Kernel matrix | 49.994 | 100.0% | 0% | 0.117 | 0.0043 | 1.019 | n/a |
| Kernel enabled, userspace registered | 21.552 | 43.1% | 0% | 0.881 | 0.0434 | 0.239 | 11.565% |

The userspace cases are sender-backpressure limited: only about 21.5 Mbit/s
enters and exits the radio path, so iperf reports no receiver loss. Their lower
CPU at this point is not greater efficiency; it reflects throttled offered
load. Both kernel modes sustain the requested rate. In the precedence case,
all kernel counters remained zero, directly proving userspace owned the frames.

Machine-readable results are in
[the 20 Mbit/s result](../experiments/results/kernel-medium-eval-20m-final.json)
and [the 50 Mbit/s result](../experiments/results/kernel-medium-eval-50m-final.json).

These are point results from a two-radio VM benchmark, not a claim about a
physical AP's forwarding rate or a completed 100-client EasyMesh profile.

### Full-lab gate

The five-mesh-node/twenty-client reconstruction gate did not reach medium
selection. Two bounded cold-start attempts in the cloned QEMU fixture failed
while starting the first extender, before any WLAN client or wmediumd process
was started. During both failures:

- `kernel_medium` remained `N`;
- no wmediumd process was registered;
- `bpiap` created no `private_ssid` or `iot_ssid` VAPs and its 5 GHz
  backhaul reported `Not connected`;
- the extender HAL repeatedly reported `No interface found for al_mac address`
  for its persisted identity;
- the appliance readiness gate ended with `bpiap did not receive its complete
  tri-band configuration`.

This is a cloned-fixture identity/startup failure in the unmodified built-in
medium state, not evidence for or against the optional kernel data path. The
Phase 1/2 functional tests and five-configuration measurements above are
accepted; Phase 3 full-lab acceptance remains open until the fixture passes
the same cold-start gate with the normal userspace backend first. No production
or accepted lab was changed during this evaluation. The outcome is preserved
in the [machine-readable gate result](../experiments/results/kernel-medium-full-lab-gate.json).

## Capability boundary

The kernel option currently provides:

- same-channel delivery across concurrent 2.4, 5, and 6 GHz contexts;
- atomic directed link signal and loss matrices;
- dynamic scenes without module or container restart;
- signal delivery into mac80211 telemetry;
- deterministic loss, cutoff, generation, readback, and receiver counters;
- reuse of the existing scenario compiler and runner.

It does **not** yet reproduce all wmediumd behavior:

- no rate/MCS-dependent PER table;
- no airtime, CCA, contention, collision, hidden-node, or interference model;
- no propagation delay, jitter, duplication, or reordering;
- frequency-qualified plans currently collapse to one entry per band;
- no per-link packet counters or wmediumd Console data source;
- debugfs is a root-only experimental lab ABI, not an upstream API.

For optimizer research that depends on those effects, userspace wmediumd is
still authoritative.

## Next phases and release gates

### Phase 3: accepted full-lab backend

- establish a clean cloned fixture that passes its userspace-wmediumd baseline
  cold start before comparing backends;
- cold-start five mesh nodes and twenty clients without userspace wmediumd;
- run inventory, crossover, RCPI, steering, multihop, outage, and restore
  acceptance with `--backend kernel`;
- expose backend and generation in the Console;
- prove ordinary userspace-wmediumd cold start remains unchanged.

### Phase 4: richer kernel model

- use frame rate/MCS plus SNR to select a versioned PER curve;
- add bounded delay queues and deterministic jitter;
- add channel occupancy and collision accounting before hidden-node behavior;
- use strict capability negotiation so scenarios cannot silently run with
  missing physics.

### Phase 5: scale and maintainability decision

- evaluate 20, 50, and 100-client profiles with identical offered load;
- use perf/ftrace to separate clone, mac80211 RX/TX, lock, and control costs;
- replace the global radio-list cloning lock only if measurements justify it;
- decide whether this remains a lab patch or needs an upstream-quality
  generic-netlink interface.

The kernel path must not become the default until Phase 3 correctness passes
and Phase 4 implements the physics needed by a specific test. Throughput alone
is insufficient: an optimizer lab needs controlled, interpretable physics.
