#!/usr/bin/env bash
# The EMOSA option deploys emosa-lab at the pinned commit (gen/vm/lxd/emosa-lab.env) only.
set -euo pipefail
# hermetic: not the lab a caller configured (lab-config.sh, as the suite and vm.md do)
unset EASYMESH_LAB_NAME EASYMESH_LXD_NAME EASYMESH_LXD_STORAGE EASYMESH_PORT_BASE EASYMESH_ROOM_DEMO_PORT \
    EASYMESH_WEBUI_PORT LAB_GRAFANA_PORT LAB_LXD_UI_PORT LAB_OUTER_METRICS_PORT WMEDIUMD_CONSOLE_PORT EMOSA_LAB_UNPINNED

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
eval "$(sed -n '/^emosa_commit()/,/^}/p;/^emosa_pinned()/,/^}/p' "$root/gen/vm/lxd/build.sh")"
grep -Eq '^EMOSA_LAB_COMMIT=[0-9a-f]{40}$' "$root/gen/vm/lxd/emosa-lab.env"

tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
emosa_lab=$tmp/emosa-lab
git init -q "$emosa_lab"
echo one > "$emosa_lab/file"
git -C "$emosa_lab" add file
git -C "$emosa_lab" -c user.name=test -c user.email=test@example.invalid commit -qm one
emosa_pin=$(git -C "$emosa_lab" rev-parse HEAD)

emosa_pinned                                     # at the pin, clean
echo untracked > "$emosa_lab/new"
emosa_pinned                                     # untracked files do not count
echo two > "$emosa_lab/file"
if emosa_pinned 2>/dev/null; then echo 'a dirty checkout passed' >&2; exit 1; fi
test "$(emosa_commit)" = "$emosa_pin+dirty"
git -C "$emosa_lab" checkout -q file
emosa_pin=0123456789012345678901234567890123456789
if emosa_pinned 2>/dev/null; then echo 'another commit passed' >&2; exit 1; fi
EMOSA_LAB_UNPINNED=1 emosa_pinned 2>"$tmp/note"
grep -q '^note: emosa-lab .*, not the pinned 0123456789' "$tmp/note"
emosa_lab=$tmp/none
if emosa_pinned 2>/dev/null; then echo 'no checkout passed' >&2; exit 1; fi
echo 'PASS: the EMOSA option takes emosa-lab clean at its pin, another only with EMOSA_LAB_UNPINNED=1'
