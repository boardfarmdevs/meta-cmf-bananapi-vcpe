# Test tiers

Run the smallest tier that proves the change. Each higher tier includes the
preconditions of the tiers before it. These commands are intentionally separate
from build commands so a developer can choose the cost and scope explicitly.

## Tier 0 — static source and documentation

Use after documentation, script or frontend-only changes. No VM or image build
is required.

```sh
python3 gen/tests/test_documentation.py
python3 -m pytest -q gen/tests/test_clean_release.py
bash gen/vm/lxd/test-profiles.sh
bash gen/vm/lxd/test-build-storage.sh
bash gen/vm/lxd/test-import-storage.sh
bash gen/vm/lxd/test-instance-config.sh
```

Run adjacent unit tests for the subsystem changed. For example, a room/viewer
change should run its matching `gen/tests/viewer-*.js` or browser test; a native
patch should run its focused source/ABI test. Do not claim runtime behavior from
Tier 0.

## Tier 1 — BPI image build

Use after recipes, patches, machine configuration or em-cli artifact changes.

```sh
bash doc/easymesh/build/scripts/build-images.sh both
```

Require both `build-evidence/latest-*` records to have exit code zero, complete
image checksums and the expected controller/extender rootfs archives. This tier
proves image construction, not a running mesh.

## Tier 2 — VM baseline

Use after VM provisioning, packaging, hwsim, wmediumd, container deployment or
service changes. Build a uniquely named lab, then run:

```sh
gen/vm/lxd/build.sh status
gen/vm/lxd/build.sh check
```

This verifies the fixed client pool, native processes, baseline traffic and host
HTTP gates. Save the command output with the build evidence. It does not replace
room convergence testing.

## Tier 3 — focused room and UI behavior

Use after room data, optimizer, signal, topology or steering changes. Start the
named lab and run only the scenarios affected by the change, plus their source
or browser checks. Typical commands are:

```sh
node gen/tests/test-room-feature-acceptance.js --help
node gen/tests/test-room-backhaul-features.js --help
python3 gen/tests/room-final-readiness.py --help
```

Record the selected room names, URLs, source commit, measured convergence and
any failure. A successful request or green UI element is not convergence; require
fresh observations, correct associations and traffic where the scenario expects
them.

## Tier 4 — release candidate

Use before publishing a thin archive or VirtualBox bundle. Start from a clean
source checkout and completed Tier 1/2 evidence. Run the release-specific room
selection, archive checks, an exact-archive import on a separate named pool, and
the platform-specific boot check. Retain evidence outside the documentation tree.

Do not turn a failed room, incomplete catalog or untested import into a passing
release label. Record the exact scope as candidate/accepted in the artifact
metadata and release notes.
