# Test a ready EasyMesh VM

[Documents](../README.md)

Run `gen/tests/run-easymesh-suite.sh` from the **host checkout** against an
existing baseline-checked appliance.

## Quick start

`all` includes room mutations and P0 churn soak, requiring `--yes-act`:

```sh
cd /path/to/meta-cmf-bananapi-vcpe
export EASYMESH_LXD_NAME=my-lab
gen/tests/run-easymesh-suite.sh all --yes-act
```

Results go into timestamped `test-results/`: per-command logs,
`results.tsv` scorecard and machine-readable `summary.json`. Nonzero exit means
failure or blocked qualification. **Skipped/blocked is not passed.**

## Sections

| Section | Purpose | Lab changes |
|---|---|---:|
| `static` | Documentation, Python unit and source-contract tests | No |
| `webui` | Built EasyMesh WebUI JavaScript unit tests | No |
| `browser` | Isolated Playwright viewer and WebUI browser tests | No |
| `live` | Health, hwsim, optimizer, candidate, medium and separate private/IoT steering scorecards | Yes |
| `rooms` | Default readiness, every room, geometry backhaul and RF access | Yes |
| `rf` | RF contracts and bounded room checks | Yes |
| `rf-actions` | Native guarded load BTM, retry-pressure veto and weak-signal rescue | Yes |
| `soak` | Duration-bound P0 RF churn, health and recovery checks | Yes |

Select sections:

```sh
gen/tests/run-easymesh-suite.sh static webui browser
gen/tests/run-easymesh-suite.sh rf --yes-act
gen/tests/run-easymesh-suite.sh rf-actions --yes-act
gen/tests/run-easymesh-suite.sh live rooms --yes-act
gen/tests/run-easymesh-suite.sh soak --yes-act --soak-duration 900
gen/tests/run-easymesh-suite.sh live soak --yes-act --expected-clients 100
gen/tests/run-easymesh-suite.sh soak --yes-act --soak-preflight-only
```

Default soak: **43,200 seconds (12 hours)**. Shorter runs are shakedowns,
not long-duration acceptance.

### What a change needs

`gen/tests/affected-suites.py` reads a change and prints the least the lab VM needs
(nothing, `build.sh update`, `build.sh build`, or new BPI images first) and the
sections that can see it, with the paths that chose each one:

```sh
gen/tests/affected-suites.py origin/master          # this branch against master
gen/tests/affected-suites.py v1.4.0 HEAD --json      # for a script
```

It follows `gen/medium` and `gen/optimizer` into their own histories. Documents need
nothing; the optimizer, rooms, the medium (its daemon, console and radio module too) and
the guest's services an update and their sections; the VM's other stages a build;
recipes, `conf/`, `classes/` and `gen/build/` new images and every section; a path it
does not know every section. Requalify a change with what it prints. Run every
section and the 12-hour soak at release points: a tag, a lab handed over, or a change
to the images. The map is `RULES` in the script; `gen/tests/test_affected_suites.py`
keeps its decisions.

`--soak-preflight-only` retains source matching, full-roster preparation and
initial/final health/RF gates without churn. Its `p0-preflight` result records
`acceptance_eligible=false`; `total_runtime_seconds` includes final checks.
It is not a soak pass.

See RF action qualification (in [easymesh-medium](https://vcpe.dev/easymesh-medium/)).

Client count is auto-detected; override with `--expected-clients COUNT` or
`EASYMESH_EXPECTED_CLIENTS`. Checked-in policies remain unchanged.

For 100 clients, rooms run first. The runner guards/stops the room service,
reconstructs the roster (VM-restart-scale cost), then waits two minutes for
100 controller clients. This state spans all live/soak checks. Prior service
state is restored once at exit, including interruption. No room-selection
pre-step is needed; **do not operate the room during checks.**

Only successful baseline audits permit archiving superseded RF journals and
checksum receipts under `/home/easymesh/easymesh-evidence/recovery-archives/`.
Failed audits retain the journal. Room restart follows all native checks.

The exclusive guard prevents concurrent suites and room-owned RF changes.
Restoration failures count as failures.

World switching checks configured-policy convergence; absolute-best placement
is reported separately. Use `gen/optimizer/acceptance/room-world-switch-smoke.py --require-absolute-best`
for the stricter criterion, which may conflict with steering hysteresis.

For a **GET-only** RF check:

```sh
python3 gen/optimizer/acceptance/rf-access-smoke.py \
  --room-url "http://${EASYMESH_HOST_ADDRESS:-127.0.0.1}:$EASYMESH_ROOM_DEMO_PORT" \
  --output "test-results/rf-access-$(date -u +%Y%m%dT%H%M%SZ).json"
```

This checks access/freshness, not convergence. `--require-backhaul-load` requires
fresh native utilization on every wireless hop; unverified context fails.

## Prerequisites

Host tools: `python3`, `pytest`, Node 22+, `npm`, `lxc`, `ssh`, `curl`;
gateway tests: `python3-aiohttp`, `openssl`. Proxies derive from lab names and bind to
the LAN address, not loopback. Inspect
`lxc config device show "$EASYMESH_LXD_NAME"` and export its `listen` host IP
as `EASYMESH_HOST_ADDRESS` when `127.0.0.1` cannot reach them.

Install Python dependencies; activate this environment in every test terminal:

```sh
sudo apt-get install -y python3-venv
python3 -m venv "$HOME/.venvs/easymesh-tests"
source "$HOME/.venvs/easymesh-tests/bin/activate"
python3 -m pip install -r gen/tests/requirements.txt
```

Check Console NG first. `lab-config.sh` sets ports, not the host address:

```sh
source gen/build/lab-config.sh "$EASYMESH_LXD_NAME"
python3 gen/medium/observer/check-ready.py \
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
