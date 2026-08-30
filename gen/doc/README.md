# Host-side lab tooling

`gen/` deploys and operates the LXD/hwsim lab built by this layer. Current
architecture and operating instructions live in:

- [architecture](../../doc/easymesh/concepts/architecture.md)
- [operations](../../doc/easymesh/guide/operations.md)
- [wmediumd configurator](../../doc/easymesh/reference/wmediumd-configurator.md)
- [steering policy](../../doc/easymesh/concepts/steering-policy.md)

Do not duplicate host setup or acceptance procedures here.

## Entry points

| Path | Purpose |
| --- | --- |
| `gen-util.sh` | shared LXD, hwsim-pool, identity and image helpers |
| `bpi.sh` | deploy a controller or extender from an LXC image |
| `wlan-client.sh` | deploy a WNM/802.11v-capable station |
| `wlan-client/wlan.start` | idempotent in-client association and DHCP replacement hook |
| `steer.sh` | resolve WebUI names such as `sta-03` and `extender-2`, then issue a directed EasyMesh steer |
| `hwsim/build-hwsim.sh` | build/load the validated multichannel hwsim module |
| `wmediumd/build-wmediumd.sh` | apply the pinned wmediumd patch series and build |
| `wmediumd/wmediumd-up.sh` | generate, test and start/stop the shared medium |
| `wmediumd/configurator/` | compile and run deterministic RF scenarios |
| `wpa_supplicant/` | build the client WNM supplicant |
| `tests/p0-cold-reconstruction.sh` | reconstruct and accept the full lab repeatedly |
| `tests/bpibroadband-memory-profile.py` | sample controller-container cgroup, PSS and storage state |
| `tests/p0-churn-soak.py` | requirements-driven long-duration churn and memory gate |

`gen-util.sh` derives the repository root from its own location, so the checkout
may be placed anywhere. Generated images/state belong under the ignored `tmp/`
tree unless an explicit runtime directory is documented.

## Hard invariants

- The official runtime is Linux 7.0.0-30.
- Load 32 patched hwsim radios with `channels=3 regtest=5` for the current
  five-node/20-client profile.
- Attach exactly one hwsim wiphy to each BPI container.
- Use `bpi.sh -F` for a new logical identity; preserve `/nvram` only when
  restarting the same device.
- Create clients sequentially; `wlan-client.sh` gates association, DHCP and
  controller export.
- Adding a radio requires a wmediumd registration-matrix refresh.
- Boardfarm `ca-desk6` must provide `br-wan101` before controller deployment.

## Minimal component usage

From `gen/` on a prepared runtime:

```sh
./bpi.sh -F -b br-wan101 /path/to/controller.rootfs.lxc.tar.bz2
./bpi.sh -F /path/to/extender.rootfs.lxc.tar.bz2
SNR=40 ./wmediumd/wmediumd-up.sh up
./wlan-client.sh up private_ssid test-fronthaul
./wmediumd/wmediumd-up.sh status
```

This is not a complete acceptance sequence. Follow the per-node model gates and
acceptance procedure in [operations](../../doc/easymesh/guide/operations.md).

## Shared wmediumd state

```text
/run/meta-cmf-wmediumd/wmediumd.cfg
/run/meta-cmf-wmediumd/wmediumd.pid
/run/meta-cmf-wmediumd/wmediumd.log
/run/wmediumd-control.sock
```

The runtime directory avoids sticky-`/tmp` cross-user ownership failures. The
control socket is the dynamic scenario interface; editing the startup config
does not mutate a running medium.
