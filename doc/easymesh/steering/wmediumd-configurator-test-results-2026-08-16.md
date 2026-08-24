# wmediumd configurator test results — 2026-08-16 UTC

## Lab

- Host: rev150, VirtualBox/Vagrant guest `easymesh-lab`
- Guest: Ubuntu 24, Linux 7.0.0-28, LXD 6.7
- Topology: one controller/co-located agent, four extenders, ten WLAN clients
- hwsim/wmediumd: 15 active radios from a 24-radio pool, three bands
- EasyMesh state before tests: 6/6 nodes complete, 10/10 clients active

## Automated tests

The Python suite passed 9/9 tests, including tests against the real patched daemon binary. It
covers deterministic compilation, direction expansion, complete first-phase
coverage, protected backhaul, strict units/range, binding types, and the binary
control protocol.

The actuator integration test starts a real wmediumd process and verifies:

- status/capability discovery and matrix dump;
- single-writer exclusion;
- atomic apply and exact readback;
- stale-generation rejection without mutation;
- invalid-value rejection without mutation;
- captured restoration;
- unchanged daemon PID; and
- effective `model.default_snr` on an unspecified radio pair.

Two runner tests also prove successful restore/reporting and that a restoration
readback mismatch raises an error and persists `outcome: failed` rather than a
false pass.

The wmediumd internal suite passed all nine multichannel/Linux 7 checks. A clean
pinned upstream clone applied all nine patches and rebuilt successfully.

## Live scenarios

### All-strong negative control

- Four directed links applied as one generation.
- 300/300 traffic probes received; 0% loss.
- Captured links restored and read back exactly.
- wmediumd PID unchanged.

After the runner timing fix, a second all-strong run applied generation zero
0.267 ms after its deadline. Preflight and postflight were 6/6 topology nodes
and 10/10 clients; restore values were `[40, 50, 40, 50]`.

### Passive two-AP crossover

The controller/client link changed 42→10 dB while extender-1/client changed
10→42 dB, symmetrically, over 30 one-second ramp steps. Final values were held
for 20 seconds.

- 32 atomic generations over a 60-second scenario.
- 1,400/1,400 traffic probes received; 0% loss.
- The client remained on the controller for all 71 association samples.
- Every generation after startup was within 4.922 ms of its deadline.
- Captured values restored and verified.
- wmediumd PID unchanged.
- EasyMesh remained 6/6 nodes and 10/10 clients.

This is the expected architectural boundary: an RF gradient alone does not
guarantee a roam. The policy or an explicit steering action decides placement.

### Crossover plus EasyMesh steering

The identical gradient was replayed. During the destination hold, a separate
process invoked the existing controller `steer.sh` for extender-1.

- Steering command succeeded.
- Client association changed to extender-1 about 1.7 seconds after the command.
- 1,339/1,400 probes received; 4% reported loss (61 probes) over the full run.
- 32 RF generations completed and captured state restored exactly.
- wmediumd PID unchanged.
- Preflight/postflight remained 6/6 nodes and 10/10 clients.
- The controller data model converged to the new BSSID.

The 4% loss is now a measurable steering-policy outcome. It was not caused by a
wmediumd restart or incomplete topology.

## Root-cause correction found during testing

`gen-config.sh 40` emitted `model.default_snr = 40`, but unspecified matrix
entries read back as 30 dB. The daemon ignored this field and initialized every
entry from the compiled constant. Patch 0009 now parses, bounds-checks, and uses
the configured default. Live readback after deployment showed:

```text
client -> controller       40 dB  (unspecified/default)
controller -> client       40 dB  (unspecified/default)
client -> current extender 50 dB  (explicit override)
```

After the daemon replacement, all ten clients remained associated, retained
IPv4 addresses, passed traffic with 0% loss in the health check, and agreed with
the controller model.

## Conclusion

The lab is stable enough to begin radio-pair steering-policy prototyping with
the configurator. The tested v0.1 path is deterministic, atomic, observable,
and restorative. Unattended use still requires the documented daemon-side
lease/watchdog, and same-node band steering still requires frequency-keyed SNR.
