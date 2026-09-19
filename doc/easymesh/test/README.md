# Test a ready EasyMesh VM

Use this guide after the BPI images and named LXD appliance have been built and
the appliance baseline check passes. It does not build an image or create a VM.
The top-level runner is `gen/tests/run-easymesh-suite.sh`; run it from the layer
checkout, not from inside the appliance.

## Quick start

Set the name used when the appliance was built, then run the complete ordered
qualification. The `all` profile includes room mutations and the duration-bound
P0 churn soak, so it requires an explicit acknowledgement.

```sh
cd /path/to/meta-cmf-bananapi-vcpe
export EASYMESH_LXD_NAME=my-lab
gen/tests/run-easymesh-suite.sh all --yes-act
```

It creates a timestamped directory below `test-results/`. Each command has its
own complete log; `results.tsv` is a compact scorecard and `summary.json` is a
machine-readable result. A nonzero exit status means at least one executed test
failed. A skipped test is recorded separately and is not a pass.

## Sections

| Section | Purpose | Lab changes |
|---|---|---:|
| `static` | Documentation, Python unit and source-contract tests | No |
| `webui` | Built EasyMesh WebUI JavaScript unit tests | No |
| `browser` | Isolated Playwright viewer and WebUI browser tests | No |
| `live` | VM health, hwsim, optimizer, candidate and medium checks | Bounded traffic only |
| `rooms` | Default readiness, every room, geometry backhaul and steering | Yes |
| `soak` | Duration-bound P0 RF churn, health and recovery checks | Yes |

Run one or several sections instead of `all`, for example:

```sh
gen/tests/run-easymesh-suite.sh static webui browser
gen/tests/run-easymesh-suite.sh live rooms --yes-act
gen/tests/run-easymesh-suite.sh soak --yes-act --soak-duration 900
gen/tests/run-easymesh-suite.sh live soak --yes-act --expected-clients 100
```

The default soak is 43,200 seconds (12 hours). A shorter duration is a
shakedown, not long-duration acceptance.

The runner counts provisioned `wlan-client` containers inside the appliance and
uses that value for the health and P0 checks. Override the detected profile with
`--expected-clients COUNT` (or `EASYMESH_EXPECTED_CLIENTS`) when intentionally
testing a different provisioned roster.

## Prerequisites

The host needs `python3`, `pytest`, `node`, `npm`, `lxc`, `ssh`, `curl`, and
access to the named appliance. The runner derives proxy ports from the lab name;
set `EASYMESH_HOST_ADDRESS` only when the proxies are not reachable through
`127.0.0.1`.

WebUI unit and fixture tests require the static directory from the completed
controller image build. Point `WEBUI_STATIC_DIR` at the directory containing
`script.js`, `room-topology.js`, and `steering-cues.js`:

```sh
export WEBUI_STATIC_DIR=/path/to/unified-wifi-mesh/static
```

Browser and room tests require Playwright plus a compatible Chromium. Reuse an
existing installation with `NODE_PATH`, `PLAYWRIGHT_MODULE`, and
`CHROMIUM_PATH`, or allow a per-checkout installation and browser download:

```sh
gen/tests/run-easymesh-suite.sh browser --install-browser-deps
```

The room catalog and geometry tests run browser automation locally and use SSH
to invoke `lxc exec` on the LXD host. For a local appliance, ensure this works
without a password first:

```sh
ssh localhost true
```

Set `EASYMESH_SSH_HOST` when the LXD host has another reachable SSH name. The
published-viewer browser test is optional; set `PUBLIC_VIEWER_URL` to include
it. Absent browser assets, published URL, or SSH access are shown as skips in
the scorecard.

## Scope and safety

The runner restores the default room after its room section. Do not run another
room controller, optimizer experiment, or manual traffic test concurrently.
It deliberately excludes `scale-soak-campaign.sh`, `p0-cold-reconstruction.sh`,
and `room-recovery-smoke.py`: those reprovision the lab, rebuild the appliance,
or contain a different fixed deployment assumption. Run those only from their
specific procedures after preserving this suite's evidence.
