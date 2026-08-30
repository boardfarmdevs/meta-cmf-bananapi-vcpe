# Optional hwsim kernel medium

## Decision

Userspace wmediumd remains the default and reference RF implementation. The
kernel medium is an optional experimental data path for performance and scale
research. Installing the patched `mac80211_hwsim.ko` does not enable it:
`kernel_medium=0` is the default, and a registered userspace wmediumd always
takes precedence.

```text
default

  hwsim TX -> generic netlink -> userspace wmediumd -> hwsim RX/TX status

optional, only while no userspace wmediumd is registered

  hwsim TX -> active kernel matrix -> signal/PER/delay -> hwsim RX/TX status
                       ^
                       |
              wmdcfg kernel adapter
              stage bank N, commit once
```

The configurator, scenario language, optimizer, EasyMesh processes, WebUI and
wmediumd Console remain in userspace. This work changes only the optional
frame-delivery path inside hwsim.

## Capabilities by phase

### Phase 0: controlled baseline

The evaluator holds the VM, Linux 7.0 kernel, hwsim radios, channel, namespace
split, traffic generator and measurement code constant. Stock hwsim,
userspace wmediumd and the optional kernel path are configurations of the same
test, not unrelated benchmarks.

### Phase 1: opt-in impaired delivery

Patch `0003-mac80211_hwsim-optional-kernel-medium.patch` adds a disabled-by-
default kernel path with signal cutoff, global deterministic loss and
per-receiver considered/delivered/dropped counters.

### Phase 2: atomic directed link matrices

Patch `0004-mac80211_hwsim-kernel-medium-link-matrix.patch` adds two complete
matrix banks. Entries are directed and keyed by permanent source-radio
identity, receiver radio and band. A writer fills the inactive bank and one
module-parameter write publishes the scene. `kernel_medium_generation`
increments once per commit.

The permanent identities, such as `42:00:00:00:01:00`, do not depend on
changing `phyN`, `virt-wlanN`, VAP or BSSID names. The matrix covers 2.4, 5 and
6 GHz and is bounded to 128 provisioned radios.

Each receiver exposes the experimental debugfs interface:

```text
/sys/kernel/debug/ieee80211/phyN/hwsim/kernel_medium_links
```

Writes use these operations:

```text
clear-bank BANK
set BANK SOURCE_MAC BAND SIGNAL_DBM LOSS_PERCENT
```

The `wmdcfg` kernel adapter owns this ABI. It serializes writers, validates
module identity and generation, stages a complete inactive bank, commits once,
reads the result back, and restores the captured baseline after a scenario.
Existing scenario plans select a backend only at execution:

```sh
cd gen/wmediumd/configurator

# Reference path and default.
python3 -m wmdcfg.cli run /tmp/scenario.plan.json

# Experimental path.
sudo python3 -m wmdcfg.cli run /tmp/scenario.plan.json --backend kernel
```

Scenario values remain SNR dB. The adapter uses an explicit noise floor,
defaulting to -91 dBm, to derive the signal placed in the matrix.

### Phase 3: complete 20-client lab path

The runtime can select the backend atomically at cold start. Kernel mode:

- prevents a userspace wmediumd registration;
- publishes the same permanent-radio inventory used by steering and the
  Console;
- starts a read-only, systemd-owned metrics proxy so the existing controller
  telemetry provider consumes the kernel matrix;
- exposes backend and generation through the normal tooling; and
- restores every scenario through the same configurator runner.

The five-mesh-node, 20-client cold reconstruction passed on Linux
`7.0.0-30-generic` with model `5/15/50`, 20 unique clients, 24 associated STA
records including four backhauls, all 20 client metrics, all 20 gateway paths,
and zero OneWifi/EasyMesh restarts.

The supported userspace backend was then selected from `/etc/default/easymesh-lab`
and run through the same systemd-owned cold reconstruction. It produced the
same `5/15/50`, `20/20`, `24` and zero-restart result. This is the regression
control that matters: installing the patched module and runtime does not move
the lab away from userspace wmediumd unless `EASYMESH_MEDIUM_BACKEND=kernel`
is explicitly selected.

Additional kernel-mode acceptance passed:

- health audit: 5 devices, 15 radios, 50 BSS records and 20/20 clients;
- candidate link query: requested SNR 25 dB produced RCPI 88;
- deterministic steer: `sta-0c` moved to Extender-2 and converged physically
  and in the controller model;
- full four-hop chain: passed backhaul, signal, forwarding, database and all
  20 client checks; and
- return to star: the first immediate traffic gate observed one transient
  client miss, while the repeat passed 20/20 and the affected client passed
  direct probes between runs.

The raw artifacts are under
[`kernel-medium-0829`](../experiments/results/kernel-medium-0829/).

One post-steer optimizer run also exposed an existing hwsim/RDK lifecycle
limit: the old AP retained the roamed STA as an authorized kernel station. Its
unassociated-STA query consequently omitted that STA and the strict optimizer
snapshot failed closed. This is not a kernel-medium matrix failure—the direct
candidate query, steer and topology all passed—but it remains a lab cleanup
issue for repeated immediate optimization cycles.

### Phase 4: rate-aware packet errors

Patch `0005-mac80211_hwsim-kernel-medium-rate-per.patch` adds an independently
opt-in deterministic approximation:

```text
kernel_medium_rate_per=0       # default
kernel_medium_noise_floor=-91
```

It maps legacy/HT/VHT rate metadata to a required SNR and applies a small loss
curve near that threshold. Matrix loss and rate loss are independent and are
combined as `a + b - a*b/100`. This is deliberately not presented as an
RF-accurate PHY model.

In the controlled 11 Mbit/s legacy case, SNR 7 dB against an 8 dB requirement
selected 30 percent rate loss. The receiver recorded 827 drops from 2,758
decisions and UDP observed 29.416 percent loss. The decision, rate encoding,
required SNR and combined loss are visible in debugfs.

### Phase 5: delay, jitter and occupancy observations

Patch `0006-mac80211_hwsim-kernel-medium-timing-observability.patch` adds a
per-receiver high-resolution timer queue with a hard limit and teardown drain:

```text
kernel_medium_delay_us=0
kernel_medium_jitter_us=0
kernel_medium_delay_queue_limit=4096
```

All defaults are neutral. With 2,000 microseconds delay and deterministic
plus/minus 500 microseconds jitter, the controlled 5 Mbit/s run delivered with
zero loss, 3.878 ms mean RTT and 0.0337 ms UDP jitter. Queue high-water,
overflow, delayed delivery, approximate airtime and per-band temporal overlap
are reported in debugfs.

The overlap counter is observational only. It does not yet cause collision
loss. Delay schedules receive delivery; it does not defer the sender's
synthetic ACK decision.

### Phase 6: bounded 20/50/100 medium scale and 50-client lab

Patch `0007-mac80211_hwsim-allow-128-static-radios.patch` raises the static
module-load bound from 100 to the already checked 128-radio matrix bound. The
default radio count remains unchanged. This allows five mesh radios plus 100
client radios to be represented without dynamic radio creation.

`evaluate-medium-scale.py` uses 25, 55 and 105 active same-channel radios. One
IBSS transmitter submits paced 5 Mbit/s broadcast traffic; another radio is an
IBSS peer and the remainder are active monitors. Broadcast deliberately makes
both backends process the complete receiver roster.

| Client equivalent | Radios | Backend | Submitted Mbit/s | Guest CPU, equivalent core | Medium process CPU | Module SUnreclaim delta |
| ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 20 | 25 | userspace | 5.002 | 13.801% | 7.664% | 10.5 MiB |
| 20 | 25 | kernel | 5.002 | 8.908% | n/a | 10.5 MiB |
| 50 | 55 | userspace | 5.002 | 12.981% | 7.664% | 23.5 MiB |
| 50 | 55 | kernel | 5.001 | 12.451% | n/a | 23.3 MiB |
| 100 | 105 | userspace | 5.002 | 13.969% | 7.831% | 44.7 MiB |
| 100 | 105 | kernel | 5.001 | 16.307% | n/a | 44.5 MiB |

Neither backend saturated at this fixed offered load. The kernel path shifts
work into system/softirq processing and its receiver cloning cost grows with
the roster. The userspace daemon remained near eight percent of one core in
this particular paced broadcast test. These results are a medium fan-out
benchmark, not acceptance of 100 simultaneous EasyMesh client containers or
100 independent traffic flows.

The complete five-node lab was then expanded to 25 private and 25 IoT clients
over a 64-radio pool. Both cold-reconstruction runs included ordered teardown,
controller and extender onboarding, all 50 client starts, medium selection,
controller-model convergence, RCPI reporting, a two-minute stable topology
window, service restart checks and gateway traffic:

| Backend | Result | Model | Client/API/RCPI | IPv4 ownership | Monitored restarts | Time to PASS | Time to `active/exited` |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| userspace wmediumd | PASS | `5/15/50/54` | `50/50/50` | 50 unique, one per client | 0 | 25m12s | 27m01s |
| kernel medium | PASS | `5/15/50/54` | `50/50/50` | 50 unique, one per client | 0 | 24m13s | 26m29s |

The userspace run used about 3.4 GiB of the 7.7 GiB VM. A steady-state sample
showed the single-thread wmediumd at 16.7 percent of one CPU and 3.7 MiB RSS.
The kernel run used about 3.3 GiB; its compatibility metrics proxy sampled at
0.0 percent CPU and 19 MiB RSS. These are point observations, not peak packet-
rate benchmarks. The synthetic fan-out table above remains the controlled
backend comparison.

The first kernel run revealed a client with two global IPv4 addresses after a
WLAN recovery retry. BusyBox `udhcpc` had added the new lease without deleting
the old one. That run was rejected even though the older gates passed. The
client startup transaction now flushes the prior global lease, the runtime and
health audit require exactly one unique IPv4 address per client, and the full
kernel cold reconstruction was repeated successfully with the stricter gate.
Client shutdown is also batched, reducing the 50-client stop phase to about
100 seconds and keeping it below the service's 240-second stop budget.

This accepts the 50-client medium profile for bounded cold reconstruction in
the isolated evaluation VM. It is not a duration soak or acceptance of the
100-client stress profile. A full 100-client container run was deliberately
not attempted in the 8 GiB VM; the 105-radio synthetic result establishes the
medium mechanism, not enough memory or lifecycle margin for that topology.

## Build and backend selection

Fresh Yocto TMPDIR builds also passed for `rdk-generic-broadband-image` and
`rdk-generic-ap-extender-image` at the experimental layer revision. Artifact
names, sizes, checksums, task counts and the one build-time assertion corrected
during this gate are recorded in
[`yocto-builds.json`](../experiments/results/kernel-medium-0829/yocto-builds.json).

Build and install without changing the default path:

```sh
gen/hwsim/build-hwsim.sh --6ghz --install
```

Load an isolated kernel test pool only while all hwsim-owning containers are
stopped:

```sh
HWSIM_RADIOS=32 \
HWSIM_KERNEL_MEDIUM=1 \
HWSIM_KERNEL_MEDIUM_RATE_PER=0 \
HWSIM_KERNEL_MEDIUM_DELAY_US=0 \
  gen/hwsim/build-hwsim.sh --6ghz --load
```

Never reload hwsim beneath a BPI or WLAN-client container. Backend selection
belongs to a cold lifecycle transaction, not a live toggle.

Run the two-radio functional evaluator only in an isolated VM with the lab
stopped:

```sh
sudo gen/hwsim/tests/evaluate-medium-backends.py \
  --module gen/hwsim/build/mac80211_hwsim.ko \
  --wmediumd gen/wmediumd/wmediumd.patched \
  --duration 10 --rate 20M \
  --output /tmp/kernel-medium.json
```

Run the destructive fan-out benchmark in the same conditions:

```sh
sudo gen/hwsim/tests/evaluate-medium-scale.py \
  --module gen/hwsim/build/mac80211_hwsim.ko \
  --wmediumd gen/wmediumd/wmediumd.patched \
  --output /tmp/kernel-medium-scale.json
```

## Capability boundary

The optional kernel path now provides:

- concurrent same-channel delivery in 2.4, 5 and 6 GHz contexts;
- atomic directed signal/loss matrices and dynamic scene restore;
- permanent-radio addressing and generation-checked readback;
- signal telemetry, deterministic configured loss and optional rate-aware PER;
- optional bounded receive delay and deterministic jitter;
- approximate airtime, overlap, queue and delivery counters;
- reuse of configurator scenarios, steering helpers and controller candidate
  telemetry; and
- a statically bounded 128-radio experimental pool.

It does not provide complete wmediumd or physical-medium fidelity:

- no CCA, contention, collision enforcement or hidden-node behavior;
- no exact PHY preamble/aggregation/retry/airtime model;
- occupancy is grouped by band rather than exact channel;
- no packet duplication or reordering model;
- delayed receive does not change synthetic ACK timing;
- frequency-qualified scenarios currently collapse to one matrix value per
  band; and
- debugfs is a root-only lab ABI, not an upstream control interface.

## Conclusion

Phases 0 through 6 are complete within their stated experimental boundaries:
the module and Yocto images build from clean sources; signal/loss matrices,
rate loss, timing, telemetry, scenario restore, steering and multihop work;
25/55/105-radio fan-out is measured; and the five-node, 50-client lab passes
the same cold-reconstruction gates on both backends. The remaining work is no
longer implementation of these phases. It is deciding whether a particular
future experiment needs this reduced-physics data path, then running its own
duration and packet-rate acceptance.

The kernel path is now useful as an explicit high-scale comparison backend and
for experiments whose required physics are signal, deterministic loss,
rate-threshold loss, bounded delay and observable fan-out. It is not a
replacement for userspace wmediumd when policy research depends on
contention, collisions or richer channel behavior.

Keep userspace wmediumd as the release default. Promote individual kernel
capabilities only when a scenario declares them and the capability check can
reject unsupported physics instead of silently approximating them.
