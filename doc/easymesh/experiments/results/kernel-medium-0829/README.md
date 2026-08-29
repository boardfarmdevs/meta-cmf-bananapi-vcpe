# Kernel-medium evaluation evidence

These artifacts support the results summarized in
[`hwsim-kernel-medium.md`](../../../reference/hwsim-kernel-medium.md).

- `rate-per-margin.json` records the controlled rate-aware loss test.
- `delay-hrtimer-head.json` records the controlled delay/jitter test.
- `scale-20-50-100-final.json` compares 25, 55 and 105-radio fan-out with
  userspace and kernel delivery.
- `scale-50-summary.json` records the end-to-end 50-client cold comparison and
  its qualification boundary.
- `yocto-builds.json` records the fresh controller/extender image builds and
  artifact checksums.
- `full-lab/` is the successful five-node, 20-client kernel-backend cold start.
- `userspace-baseline/` is the successful systemd-owned userspace regression
  on the same patched runtime.
- `scale-50/userspace/` is the complete 25-private/25-IoT userspace cold run
  plus the post-run unique-address and resource audit.
- `scale-50/kernel/` is the repeated strict kernel cold run. It includes the
  new 50-row client-address evidence, kernel controls and metrics-proxy log.
- `regression/` contains health, candidate-RCPI, steering and multihop output.

An earlier 50-client kernel run satisfied the pre-existing topology, RCPI,
restart and traffic gates but retained a stale secondary DHCP address on one
client. It was rejected rather than published as the scale result. The client
hook and runtime were corrected, unique IPv4 ownership became an acceptance
gate, and `scale-50/kernel/` is the clean repeat.

The optimizer-recommend logs deliberately retain the post-steer stale-source
AP failure. They are negative evidence for a remaining hwsim/RDK station
lifecycle limitation, not a claimed optimizer pass.
