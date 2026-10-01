#!/usr/bin/env bash
# build and check refuse while another lab VM (one with a wmediumd Console proxy) runs.
set -euo pipefail
# hermetic: not the lab a caller configured (lab-config.sh, as the suite and vm.md do)
unset EASYMESH_LAB_NAME EASYMESH_LXD_NAME EASYMESH_LXD_STORAGE EASYMESH_PORT_BASE EASYMESH_ROOM_DEMO_PORT \
    EASYMESH_WEBUI_PORT LAB_GRAFANA_PORT LAB_LXD_UI_PORT LAB_OUTER_METRICS_PORT WMEDIUMD_CONSOLE_PORT

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
eval "$(sed -n '/^other_running_labs()/,/^}/p;/^require_host_to_itself()/,/^}/p' "$root/gen/vm/lxd/build.sh")"

lxc() {
    test "$*" = 'list --format json'
    cat <<'JSON'
[{"name": "rdk-1001", "status": "Running", "expanded_devices": {"wmediumd-console": {}}},
 {"name": "prpl-1001", "status": "Running", "expanded_devices": {"wmediumd-console": {}}},
 {"name": "rdk-0930", "status": "Stopped", "expanded_devices": {"wmediumd-console": {}}},
 {"name": "easymesh-lab", "status": "Running", "expanded_devices": {"eth0": {}}}]
JSON
}

name=rdk-1001
test "$(other_running_labs)" = prpl-1001
if (EASYMESH_SHARED_HOST=0 require_host_to_itself) 2>/dev/null; then
    echo 'refusal expected while prpl-1001 runs' >&2
    exit 1
fi
(EASYMESH_SHARED_HOST=1 require_host_to_itself)
name=prpl-1001
test "$(other_running_labs)" = rdk-1001
name=rdk-2000
test "$(other_running_labs)" = 'rdk-1001 prpl-1001'
echo 'PASS: a lab VM refuses to build or check next to another running lab VM, unless shared on purpose'
