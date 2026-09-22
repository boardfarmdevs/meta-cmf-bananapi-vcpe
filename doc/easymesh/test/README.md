# Test a ready EasyMesh VM

Use after the BPI images and named LXD appliance are built and its baseline
check passes. Run `gen/tests/run-easymesh-suite.sh` from the **host layer checkout**,
not inside the VM. It does not build images or create VMs.

## Quick start

Select the existing appliance. `all` includes room mutations and P0 churn soak,
requiring `--yes-act`:

```sh
cd /path/to/meta-cmf-bananapi-vcpe
export EASYMESH_LXD_NAME=my-lab
gen/tests/run-easymesh-suite.sh all --yes-act
```

Results go into timestamped `test-results/` directories: per-command logs,
`results.tsv` scorecard and machine-readable `summary.json`. Nonzero exit means
an executed test failed. **Skipped is not passed.**

## Sections

| Section | Purpose | Lab changes |
|---|---|---:|
| `static` | Documentation, Python unit and source-contract tests | No |
| `webui` | Built EasyMesh WebUI JavaScript unit tests | No |
| `browser` | Isolated Playwright viewer and WebUI browser tests | No |
| `live` | VM health, hwsim, optimizer, candidate, medium and commanded steering | Yes |
| `rooms` | Default readiness, every room, geometry backhaul and RF access | Yes |
| `soak` | Duration-bound P0 RF churn, health and recovery checks | Yes |

Run selected sections instead of `all`:

```sh
gen/tests/run-easymesh-suite.sh static webui browser
gen/tests/run-easymesh-suite.sh live rooms --yes-act
gen/tests/run-easymesh-suite.sh soak --yes-act --soak-duration 900
gen/tests/run-easymesh-suite.sh live soak --yes-act --expected-clients 100
```

Default soak: **43,200 seconds (12 hours)**. Shorter runs are shakedowns,
not long-duration acceptance.

The runner detects provisioned `wlan-client` containers for health, optimizer
and P0 checks, using a temporary optimizer policy without changing checked-in
defaults. Override with `--expected-clients COUNT` or `EASYMESH_EXPECTED_CLIENTS`.

For 100 clients, room checks run first. The runner then guards/stops the
room service, reconstructs the full roster (VM-restart-scale cold-start time),
and waits up to two minutes for 100 live controller clients. This state persists
through all live/soak checks. The prior room-service state is restored once at
exit, including failure/interruption. No room-selection pre-step is needed;
**do not operate the room during these checks.**

Only after the reconstructed lab passes its baseline audit, the runner archives
any superseded room RF journal and checksum receipt under
`/home/easymesh/easymesh-evidence/recovery-archives/`. It restarts the room only
after all native live/soak work. Failed audits never remove the journal.

The guard is a runtime systemd condition, not a runtime mask: an installed
`/etc/systemd/system` unit can outrank a mask under `/run`. A second suite
cannot acquire the same guard. Restoration failures count as failures.
Commanded steering never runs concurrently with room-owned RF generations.

For a short **GET-only** RF check, without rebuilding or stopping the room:

```sh
python3 gen/tests/rf-access-smoke.py \
  --room-url "http://${EASYMESH_HOST_ADDRESS:-127.0.0.1}:$EASYMESH_ROOM_DEMO_PORT" \
  --output "test-results/rf-access-$(date -u +%Y%m%dT%H%M%SZ).json"
```

This checks access/freshness, not room convergence or new RF physics.
Use `--require-backhaul-load` to require fresh native utilization on every
reported wireless backhaul hop; unverified context fails.

## Prerequisites

Host tools: `python3`, `pytest`, Node 22+, `npm`, `lxc`, `ssh`, `curl`, plus appliance
access. Proxy ports derive from the lab name. Builds normally bind proxies to
the LAN address, not loopback. Inspect
`lxc config device show "$EASYMESH_LXD_NAME"` and export its `listen` host IP
as `EASYMESH_HOST_ADDRESS` when `127.0.0.1` cannot reach them.

Check Console NG before the suite stops the room service. `lab-config.sh`
sets ports, not the host address:

```sh
source doc/easymesh/build/scripts/lab-config.sh "$EASYMESH_LXD_NAME"
python3 gen/wmediumd/observer/check-ready.py \
  --url "http://${EASYMESH_HOST_ADDRESS:-127.0.0.1}:$WMEDIUMD_CONSOLE_PORT" \
  --require-room --require-survey
```

WebUI tests need the completed controller build's static directory containing
`script.js`, `room-topology.js` and `steering-cues.js`:

```sh
export WEBUI_STATIC_DIR=/path/to/unified-wifi-mesh/static
```

Browser/room tests need Playwright and compatible Chromium. Reuse
`NODE_PATH`, `PLAYWRIGHT_MODULE` and `CHROMIUM_PATH`, or install per checkout:

```sh
gen/tests/run-easymesh-suite.sh browser --install-browser-deps
```

Room tests automate browsers locally and invoke `lxc exec` through SSH.
Verify passwordless access to the LXD host:

```sh
ssh localhost true
```

Override SSH destination with `EASYMESH_SSH_HOST`. Set `PUBLIC_VIEWER_URL` for
the optional published-viewer test. Missing browser assets, URL or SSH access
are recorded as skips.

## Scope and safety

The room section restores the default room. Do not run concurrent room,
optimizer or manual traffic experiments. Excluded scripts:
`scale-soak-campaign.sh`, `p0-cold-reconstruction.sh`, `room-recovery-smoke.py`.
They reprovision, rebuild or assume another deployment; preserve evidence and
follow their separate procedures.
